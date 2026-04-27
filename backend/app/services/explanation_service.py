"""结构化路径解释服务：从 audit 数据生成可读解释"""
from __future__ import annotations

import json
import logging
from collections import deque
from types import SimpleNamespace
from typing import Any

import httpx

from app.core.config import get_llm_config, get_llm_polish_enabled
from app.planner.scoring import (
    DEFAULT_MODE_ADJUSTMENTS,
    DEFAULT_PRIORITY_WEIGHTS,
    decompose_priority_score,
)
from app.schemas.explanation import (
    AuditHighlight,
    BudgetExplanation,
    DependencyChainExplanation,
    EvidenceRef,
    ExplanationAskRequest,
    ExplanationAskResponse,
    ExplanationReadability,
    ExplanationMeta,
    ExplanationProvenance,
    ExplanationResponse,
    GenerationStep,
    GoalResolutionSummary,
    NodeExplanation,
    NodeGroupSummary,
    OrderingSummary,
    OverviewSummary,
    OrderExplanation,
    PolishMeta,
    ReadableBudgetSummary,
    ReinforcementExplanation,
    StageExplanation,
    StageSummary,
    TraceSummary,
)

logger = logging.getLogger(__name__)

POLISH_MAX_LENGTH = 200
POLISH_TIMEOUT_SECONDS = 30.0
ASK_MAX_LENGTH = 800
ASK_TIMEOUT_SECONDS = 8.0

_WEAKEST_DIM_PRIORITY: tuple[str, ...] = ("gap_ml", "gap_math", "gap_code")
_DIM_LABEL: dict[str, str] = {
    "gap_math": "数学基础",
    "gap_code": "编程实现",
    "gap_ml": "机器学习概念",
}

_PRIORITY_COMPONENT_LABELS: dict[str, str] = {
    "importance": "教学重要度",
    "goal_relevance": "目标相关度",
    "preference_fit": "画像偏好匹配",
    "main_path_bonus": "主路径加成",
    "bridge_value": "桥接价值",
    "difficulty_penalty": "难度惩罚",
    "gap_penalty": "能力差距惩罚",
    "time_cost_penalty": "时间成本惩罚",
    "mode.steady.difficulty_reduction": "稳妥模式难度缓冲",
    "mode.steady.foundation_bonus": "稳妥模式基础优先",
    "mode.efficient.goal_relevance_bonus": "高效模式目标聚焦",
    "mode.efficient.time_saving_bonus": "高效模式节时加成",
    "mode.practice.practice_weight_bonus": "实践模式权重加成",
    "mode.practice.practice_flag_bonus": "实践模式实操加成",
}

_PATH_MODE_LABELS: dict[str, str] = {
    "standard": "标准",
    "compressed": "压缩",
    "theory_first": "理论优先",
    "practice_first": "实践优先",
}

_ORDERING_MODE_LABELS: dict[str, str] = {
    "steady": "稳妥",
    "efficient": "高效",
    "practice": "实践",
}

_BUDGET_STATUS_LABELS: dict[str, str] = {
    "feasible": "预算可行",
    "tight": "时间较紧",
    "insufficient": "预算不足",
    "over_budget_required_closure": "硬前置超预算",
}

_GOAL_TYPE_LABELS: dict[str, str] = {
    "domain": "领域型",
    "concept": "概念型",
    "problem": "问题型",
}

_RESOLVE_SOURCE_LABELS: dict[str, str] = {
    "template": "模板规则",
    "jieba": "词面召回",
    "llm": "LLM",
    "confirmed": "人工确认",
    "domain_default": "领域默认策略",
}

_GENERATION_STEP_TITLES: dict[str, str] = {
    "goal_resolution": "目标解析",
    "prerequisite_closure": "硬前置闭包",
    "profile_reinforcement": "画像补强",
    "topological_ordering": "拓扑排序",
    "stage_assignment": "阶段划分",
    "time_budget": "时间预算",
}

_STAGE_REASON_TRANSLATIONS: dict[str, str] = {
    "category=foundation": "该节点属于通用基础类。",
    "category=math_foundation": "该节点属于数学基础类。",
    "category=ml_core": "该节点属于机器学习核心概念类。",
    "category=algorithm": "该节点属于算法核心类。",
    "category=evaluation": "该节点属于评估与度量类。",
    "category=practice": "该节点属于实践应用类。",
    "goal_type=domain": "当前目标是领域型目标，阶段划分优先覆盖完整主线。",
    "goal_type=concept": "当前目标是概念型目标，阶段划分围绕核心概念展开。",
    "goal_type=problem": "当前目标是问题型目标，阶段划分围绕问题求解链路展开。",
    "default_stage_rule": "该节点按默认阶段规则分配到当前阶段。",
    "beginner_override": "因学习者处于初学阶段且能力差距较大，该节点被强制提前到基础准备阶段。",
}


def _build_ancestors_by_target(
    target_ids: list[str],
    requires_rev_adj: dict[str, list[str]],
) -> dict[str, set[str]]:
    """对每个目标做无界反向 BFS，返回该目标的祖先集合（不含目标自身）。"""
    ancestors: dict[str, set[str]] = {}
    for target in target_ids:
        visited: set[str] = set()
        queue: deque[str] = deque([target])
        while queue:
            cur = queue.popleft()
            for prev in requires_rev_adj.get(cur, ()):
                if prev not in visited and prev != target:
                    visited.add(prev)
                    queue.append(prev)
        ancestors[target] = visited
    return ancestors


def _pick_weakest_dimension(gap: dict[str, float]) -> str:
    """返回差距最大维度的中文 label；平局按 ml > math > code 决定性 tie-break。"""
    values = {dim: gap.get(dim, 0) for dim in _WEAKEST_DIM_PRIORITY}
    max_val = max(values.values(), default=0)
    for dim in _WEAKEST_DIM_PRIORITY:
        if values[dim] == max_val:
            return _DIM_LABEL[dim]
    return _DIM_LABEL[_WEAKEST_DIM_PRIORITY[0]]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _format_scalar(value: Any) -> str:
    if value is None:
        return "未提供"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return f"{value:g}"
    return str(value)


def _label_value(value: str | None, labels: dict[str, str]) -> str:
    if not value:
        return "未提供"
    return labels.get(value, value)


def _ordered_unique_node_ids(
    node_ids: Any,
    ordered_ids: list[str] | None = None,
) -> list[str]:
    if isinstance(node_ids, str):
        raw_items: list[Any] = [node_ids]
    elif isinstance(node_ids, (list, set, tuple)):
        raw_items = list(node_ids)
    else:
        raw_items = []
    items = [node_id for node_id in raw_items if isinstance(node_id, str) and node_id]
    if not ordered_ids:
        return _dedupe_strings(items)

    wanted = set(items)
    ordered = [node_id for node_id in ordered_ids if node_id in wanted]
    if len(ordered) == len(wanted):
        return ordered

    existing = set(ordered)
    for node_id in items:
        if node_id not in existing:
            ordered.append(node_id)
            existing.add(node_id)
    return ordered


def _resolve_node_names(
    node_ids: Any,
    nodes_by_id: dict[str, dict[str, Any]],
    ordered_ids: list[str] | None = None,
) -> list[str]:
    return [
        _get_node_name(node_id, nodes_by_id)
        for node_id in _ordered_unique_node_ids(node_ids, ordered_ids)
    ]


def _format_goal_focus(goal_names: list[str]) -> str:
    names = _dedupe_strings(goal_names)
    if not names:
        return "当前学习目标"
    if len(names) == 1:
        return f"「{names[0]}」"
    if len(names) == 2:
        return f"「{names[0]}」和「{names[1]}」"
    return f"「{names[0]}」和「{names[1]}」等目标"


def _format_source_breakdown(source_breakdown: dict[str, Any]) -> str:
    parts = [
        f"{key}={_format_scalar(value)}"
        for key, value in source_breakdown.items()
        if isinstance(key, str) and key
    ]
    return "，".join(parts)


def _extract_factor_label(factor: str) -> str:
    if " (" in factor:
        return factor.split(" (", 1)[0]
    return factor


def _build_compressed_dependency_note(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> str | None:
    path_mode = (
        audit.get("path_mode")
        or (audit.get("budget_summary") or {}).get("path_mode")
        or "standard"
    )
    if path_mode != "compressed":
        return None

    budget_status = audit.get("budget_status") or (audit.get("budget_summary") or {}).get("status")
    excluded_nodes = audit.get("excluded_nodes") or []
    if budget_status == "over_budget_required_closure":
        return (
            "压缩模式不会裁剪硬前置依赖；当前目标的硬前置闭包已超过预算，"
            "系统仍保留完整依赖链。"
        )

    excluded_names = [
        _get_node_name(item.get("node_id", ""), nodes_by_id)
        for item in excluded_nodes
        if isinstance(item, dict) and item.get("node_id")
    ]
    if excluded_names:
        shown = "、".join(excluded_names[:3])
        suffix = " 等" if len(excluded_names) > 3 else ""
        return (
            f"压缩模式不会裁剪硬前置依赖；仅裁剪 {shown}{suffix} 可选补强节点。"
        )
    return "压缩模式不会裁剪硬前置依赖；如需压缩，只会优先裁剪可选补强节点。"



def _resolve_requires_rev_adj_with_provenance(
    audit: dict[str, Any],
    legacy_requires_rev_adj: dict[str, list[str]] | None,
) -> tuple[dict[str, list[str]], dict[str, Any]]:
    provenance: dict[str, Any] = {
        "fallback_reasons": [],
        "live_pack_fields": [],
        "filtered_requires_rev_adj_state": "missing",
        "filtered_requires_rev_adj_source": "legacy_live_pack",
    }

    if "filtered_requires_rev_adj" not in audit:
        provenance["fallback_reasons"].append("filtered_requires_rev_adj_missing")
    else:
        snapshot_requires_rev_adj = audit.get("filtered_requires_rev_adj")
        if snapshot_requires_rev_adj is None:
            provenance["filtered_requires_rev_adj_state"] = "null"
            provenance["fallback_reasons"].append("filtered_requires_rev_adj_null")
        elif isinstance(snapshot_requires_rev_adj, dict):
            provenance["filtered_requires_rev_adj_state"] = (
                "non_empty_dict" if snapshot_requires_rev_adj else "empty_dict"
            )
            provenance["filtered_requires_rev_adj_source"] = "audit_snapshot"
            provenance["fallback_used"] = False
            return snapshot_requires_rev_adj, provenance
        else:
            provenance["filtered_requires_rev_adj_state"] = "invalid_type"
            provenance["fallback_reasons"].append("filtered_requires_rev_adj_invalid_type")

    if legacy_requires_rev_adj is not None:
        provenance["live_pack_fields"].append("requires_rev_adj")
    provenance["fallback_used"] = True
    logger.info(
        "Explanation 使用 legacy requires_rev_adj fallback: %s",
        provenance["filtered_requires_rev_adj_state"],
    )
    return legacy_requires_rev_adj or {}, provenance


def _resolve_requires_rev_adj(
    audit: dict[str, Any],
    legacy_requires_rev_adj: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    requires_rev_adj, _ = _resolve_requires_rev_adj_with_provenance(
        audit, legacy_requires_rev_adj
    )
    return requires_rev_adj


def build_explanation(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    legacy_requires_rev_adj: dict[str, list[str]],
    scoring_config: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> ExplanationResponse:
    context = context or {}
    goal = audit.get("goal_result", {}) or {}
    target_ids: list[str] = list(goal.get("target_node_ids", []))
    mode: str = audit.get("ordering_mode") or goal.get("mode", "")
    profile_snapshot: dict[str, Any] = audit.get("profile_snapshot") or {}
    requires_rev_adj, requires_provenance = _resolve_requires_rev_adj_with_provenance(
        audit, legacy_requires_rev_adj
    )
    scoring_config = scoring_config or {}

    ancestors_by_target = _build_ancestors_by_target(target_ids, requires_rev_adj)
    priority_weights = scoring_config.get("priority_weights", DEFAULT_PRIORITY_WEIGHTS)
    mode_adjustments = scoring_config.get("mode_adjustments", DEFAULT_MODE_ADJUSTMENTS)

    node_explanations = _build_node_explanations(
        audit, nodes_by_id, target_ids, ancestors_by_target
    )
    ordering_explanations = _build_ordering_explanations(
        audit, nodes_by_id, profile_snapshot, mode, priority_weights, mode_adjustments
    )
    stage_explanations = _build_stage_explanations(audit, nodes_by_id)

    ordered_ids = list(audit.get("ordering_logs", {}).keys())
    dep_chains: dict[str, list[str]] = {
        tid: _real_prereq_chain(tid, ordered_ids, requires_rev_adj)
        for tid in target_ids
        if tid in ordered_ids
    }

    budget_explanation = _build_budget_explanation(
        audit, nodes_by_id, dep_chains, target_ids
    )
    reinforcement_explanations = _build_reinforcement_explanations(audit, nodes_by_id)
    dependency_chain_explanations = _build_dependency_chain_explanations(
        audit, nodes_by_id, dep_chains
    )
    meta = _build_explanation_meta(audit, context, requires_provenance)
    readability: ExplanationReadability | None = None
    try:
        readability = _build_explanation_readability(
            audit=audit,
            context=context,
            nodes_by_id=nodes_by_id,
            node_explanations=node_explanations,
            ordering_explanations=ordering_explanations,
            stage_explanations=stage_explanations,
            budget_explanation=budget_explanation,
            reinforcement_explanations=reinforcement_explanations,
            dependency_chain_explanations=dependency_chain_explanations,
            meta=meta,
        )
    except Exception:
        logger.exception("Explanation readability 构建失败，回退 legacy explanation blocks")
        meta = _mark_readability_failure(meta)

    return ExplanationResponse(
        node_explanations=node_explanations,
        ordering_explanations=ordering_explanations,
        stage_explanations=stage_explanations,
        budget_explanation=budget_explanation,
        reinforcement_explanations=reinforcement_explanations,
        dependency_chain_explanations=dependency_chain_explanations,
        readability=readability,
        meta=meta,
    )


def _mark_readability_failure(meta: ExplanationMeta) -> ExplanationMeta:
    fallback_reasons = _dedupe_strings(
        [*meta.provenance.fallback_reasons, "readability_build_failed"]
    )
    return meta.model_copy(
        update={
            "provenance": meta.provenance.model_copy(
                update={
                    "fallback_used": True,
                    "fallback_reasons": fallback_reasons,
                }
            )
        }
    )


def _build_explanation_readability(
    *,
    audit: dict[str, Any],
    context: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    node_explanations: list[NodeExplanation],
    ordering_explanations: list[OrderExplanation],
    stage_explanations: list[StageExplanation],
    budget_explanation: BudgetExplanation | None,
    reinforcement_explanations: list[ReinforcementExplanation],
    dependency_chain_explanations: list[DependencyChainExplanation],
    meta: ExplanationMeta,
) -> ExplanationReadability:
    overview_summary = _build_overview_summary(audit, context, nodes_by_id)
    goal_resolution_summary = _build_goal_resolution_summary(audit, nodes_by_id)
    ordering_summary = _build_readable_ordering_summary(audit, ordering_explanations)
    stage_summary = _build_readable_stage_summary(
        audit,
        context,
        nodes_by_id,
        stage_explanations,
    )
    budget_summary = _build_readable_budget_summary(
        audit,
        context,
        nodes_by_id,
        budget_explanation,
    )
    trace_summary = _build_trace_summary(audit, meta)
    generation_steps = _build_generation_steps(
        audit=audit,
        goal_resolution_summary=goal_resolution_summary,
        ordering_summary=ordering_summary,
        stage_summary=stage_summary,
        budget_summary=budget_summary,
        reinforcement_explanations=reinforcement_explanations,
        dependency_chain_explanations=dependency_chain_explanations,
    )
    node_groups = _build_node_group_summaries(node_explanations)
    audit_highlights = _build_audit_highlights(
        audit=audit,
        goal_resolution_summary=goal_resolution_summary,
        ordering_summary=ordering_summary,
        stage_summary=stage_summary,
        budget_summary=budget_summary,
        trace_summary=trace_summary,
        meta=meta,
        dependency_chain_explanations=dependency_chain_explanations,
    )

    return ExplanationReadability(
        overview_summary=overview_summary,
        goal_resolution_summary=goal_resolution_summary,
        generation_steps=generation_steps,
        node_groups=node_groups,
        ordering_summary=ordering_summary,
        stage_summary=stage_summary,
        budget_summary=budget_summary,
        trace_summary=trace_summary,
        audit_highlights=audit_highlights,
    )


def _build_overview_summary(
    audit: dict[str, Any],
    context: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> OverviewSummary:
    goal = audit.get("goal_result", {}) or {}
    ordered_ids = list(audit.get("ordering_logs", {}).keys())
    target_ids = _ordered_unique_node_ids(goal.get("target_node_ids", []), ordered_ids)
    goal_names = _resolve_node_names(target_ids, nodes_by_id, ordered_ids)
    budget_summary = audit.get("budget_summary") or {}
    total_hours = budget_summary.get("total_hours", context.get("total_hours"))
    budget_status = audit.get("budget_status") or context.get("budget_status") or budget_summary.get("status")
    path_mode = audit.get("path_mode") or context.get("path_mode") or budget_summary.get("path_mode")
    node_count = len(ordered_ids or audit.get("final_ids", []))
    hours_text = (
        f"{_format_scalar(total_hours)} 小时"
        if total_hours is not None
        else "时长信息待补充"
    )
    headline = (
        f"这条{_label_value(path_mode, _PATH_MODE_LABELS)}路径围绕"
        f"{_format_goal_focus(goal_names)}生成，共 {node_count} 个节点 / {hours_text}，"
        f"预算状态为{_label_value(budget_status, _BUDGET_STATUS_LABELS)}。"
    )
    notes: list[str] = []
    compressed_note = _build_compressed_dependency_note(audit, nodes_by_id)
    if compressed_note:
        notes.append(compressed_note)
    return OverviewSummary(
        headline=headline,
        goal_names=goal_names,
        node_count=node_count,
        total_hours=total_hours,
        budget_status=budget_status,
        path_mode=path_mode,
        notes=notes,
    )


def _build_goal_resolution_summary(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> GoalResolutionSummary:
    goal = audit.get("goal_result", {}) or {}
    target_ids = _ordered_unique_node_ids(goal.get("target_node_ids", []))
    target_names = _resolve_node_names(target_ids, nodes_by_id, target_ids)
    final_goal_text = goal.get("description") or goal.get("goal_text")
    if not final_goal_text and target_names:
        final_goal_text = "、".join(target_names)
    source_breakdown = goal.get("source_breakdown") or {}
    warnings = [
        item for item in (goal.get("warnings") or [])
        if isinstance(item, str) and item
    ]
    return GoalResolutionSummary(
        final_goal_text=final_goal_text,
        goal_type=goal.get("goal_type") or goal.get("effective_goal_type"),
        mode=goal.get("mode"),
        resolve_source=goal.get("resolve_source"),
        target_node_ids=target_ids,
        target_node_names=target_names,
        source_breakdown=source_breakdown if isinstance(source_breakdown, dict) else {},
        warnings=warnings,
    )


def _build_generation_steps(
    *,
    audit: dict[str, Any],
    goal_resolution_summary: GoalResolutionSummary,
    ordering_summary: OrderingSummary,
    stage_summary: StageSummary,
    budget_summary: ReadableBudgetSummary | None,
    reinforcement_explanations: list[ReinforcementExplanation],
    dependency_chain_explanations: list[DependencyChainExplanation],
) -> list[GenerationStep]:
    ordered_ids = list(audit.get("ordering_logs", {}).keys())
    target_ids = _ordered_unique_node_ids(
        goal_resolution_summary.target_node_ids,
        ordered_ids,
    )
    closure_ids = _ordered_unique_node_ids(audit.get("closure_ids", []), ordered_ids)
    if not closure_ids:
        chain_node_ids = [
            node_id
            for chain in dependency_chain_explanations
            for node_id in chain.chain_node_ids
            if node_id not in target_ids
        ]
        closure_ids = _ordered_unique_node_ids(chain_node_ids, ordered_ids)
    reinforced_ids = _ordered_unique_node_ids(
        audit.get("reinforced_ids", []) or [item.node_id for item in reinforcement_explanations],
        ordered_ids,
    )

    source_text = _label_value(goal_resolution_summary.resolve_source, _RESOLVE_SOURCE_LABELS)
    goal_type_text = _label_value(goal_resolution_summary.goal_type, _GOAL_TYPE_LABELS)
    goal_evidence = [
        f"目标类型：{goal_type_text}",
        f"解析来源：{source_text}",
    ]
    if goal_resolution_summary.final_goal_text:
        goal_evidence.append(f"最终目标：{goal_resolution_summary.final_goal_text}")
    if goal_resolution_summary.source_breakdown:
        goal_evidence.append(
            f"来源占比：{_format_source_breakdown(goal_resolution_summary.source_breakdown)}"
        )
    if goal_resolution_summary.warnings:
        goal_evidence.append(f"警告：{'、'.join(goal_resolution_summary.warnings)}")
    goal_focus = _format_goal_focus(goal_resolution_summary.target_node_names)
    if goal_focus == "当前学习目标" and goal_resolution_summary.final_goal_text:
        goal_focus = f"「{goal_resolution_summary.final_goal_text}」"
    goal_summary = (
        f"最终采用{goal_type_text}目标"
        f"{goal_focus}，"
        f"解析来源为{source_text}。"
    )

    prerequisite_evidence = [
        f"硬前置节点：{len(closure_ids)} 个",
        f"依赖链条：{len(dependency_chain_explanations)} 条",
    ]
    prerequisite_summary = (
        f"系统根据依赖快照纳入 {len(closure_ids)} 个硬前置节点，"
        "保证目标节点进入学习顺序前具备必要基础。"
    )

    reinforcement_focuses = _dedupe_strings(
        [
            _pick_weakest_dimension(item.gap or {})
            for item in reinforcement_explanations
            if item.gap
        ]
    )
    reinforcement_evidence = [f"补强节点：{len(reinforced_ids)} 个"]
    if reinforcement_focuses:
        reinforcement_evidence.append(f"优先补齐：{'、'.join(reinforcement_focuses[:3])}")
    if reinforced_ids:
        reinforcement_summary = (
            f"系统结合画像差距额外补入 {len(reinforced_ids)} 个节点，"
            f"优先修补{'、'.join(reinforcement_focuses[:3]) or '关键能力差距'}。"
        )
    else:
        reinforcement_summary = "当前画像下未触发额外画像补强节点。"

    ordering_mode_text = _label_value(ordering_summary.mode, _ORDERING_MODE_LABELS)
    ordering_factor_labels = _dedupe_strings(
        [_extract_factor_label(item) for item in ordering_summary.key_factors]
    )
    ordering_evidence = ordering_summary.key_factors[:3]
    ordering_summary_text = (
        f"系统先满足依赖关系，再以{ordering_mode_text}模式排列 {len(ordered_ids)} 个节点。"
    )
    if ordering_factor_labels:
        ordering_summary_text = (
            f"{ordering_summary_text[:-1]}，重点参考"
            f"{'、'.join(ordering_factor_labels[:3])}。"
        )

    stage_names = [stage.get("stage_name", "") for stage in stage_summary.stages if stage.get("stage_name")]
    stage_evidence = [f"阶段数：{stage_summary.stage_count}"]
    if stage_names:
        stage_evidence.append(f"阶段名称：{'、'.join(stage_names[:3])}")
    stage_node_ids = _ordered_unique_node_ids(
        [
            node_id
            for stage in stage_summary.stages
            for node_id in stage.get("node_ids", [])
            if isinstance(node_id, str) and node_id
        ],
        ordered_ids,
    )
    stage_summary_text = (
        f"路径被分成 {stage_summary.stage_count} 个阶段，"
        "按照节点类别和目标类型规则逐步推进。"
    )

    budget_status_text = (
        _label_value(budget_summary.status, _BUDGET_STATUS_LABELS)
        if budget_summary is not None
        else "未提供"
    )
    budget_evidence: list[str] = []
    if budget_summary is not None:
        if budget_summary.total_hours is not None:
            budget_evidence.append(f"总时长：{_format_scalar(budget_summary.total_hours)} 小时")
        if budget_summary.weekly_hours is not None:
            budget_evidence.append(f"每周投入：{_format_scalar(budget_summary.weekly_hours)} 小时")
        if budget_summary.estimated_weeks is not None:
            budget_evidence.append(f"预计周期：{_format_scalar(budget_summary.estimated_weeks)} 周")
        budget_evidence.append(f"预算状态：{budget_status_text}")
        if budget_summary.compressed_dependency_note:
            budget_evidence.append(budget_summary.compressed_dependency_note)
    budget_summary_text = (
        f"路径总时长按规则估算后为"
        f"{_format_scalar(budget_summary.total_hours) if budget_summary and budget_summary.total_hours is not None else '未提供'} 小时，"
        f"预算状态为{budget_status_text}。"
    )

    return [
        GenerationStep(
            step_id="goal_resolution",
            title=_GENERATION_STEP_TITLES["goal_resolution"],
            summary=goal_summary,
            evidence_items=goal_evidence,
            node_ids=target_ids,
        ),
        GenerationStep(
            step_id="prerequisite_closure",
            title=_GENERATION_STEP_TITLES["prerequisite_closure"],
            summary=prerequisite_summary,
            evidence_items=prerequisite_evidence,
            node_ids=closure_ids,
        ),
        GenerationStep(
            step_id="profile_reinforcement",
            title=_GENERATION_STEP_TITLES["profile_reinforcement"],
            summary=reinforcement_summary,
            evidence_items=reinforcement_evidence,
            node_ids=reinforced_ids,
        ),
        GenerationStep(
            step_id="topological_ordering",
            title=_GENERATION_STEP_TITLES["topological_ordering"],
            summary=ordering_summary_text,
            evidence_items=ordering_evidence,
            node_ids=ordered_ids,
        ),
        GenerationStep(
            step_id="stage_assignment",
            title=_GENERATION_STEP_TITLES["stage_assignment"],
            summary=stage_summary_text,
            evidence_items=stage_evidence,
            node_ids=stage_node_ids,
        ),
        GenerationStep(
            step_id="time_budget",
            title=_GENERATION_STEP_TITLES["time_budget"],
            summary=budget_summary_text,
            evidence_items=budget_evidence,
            node_ids=ordered_ids,
        ),
    ]


def _build_node_group_summaries(
    node_explanations: list[NodeExplanation],
) -> list[NodeGroupSummary]:
    group_defs = (
        ("target", "目标节点", "这些节点直接对应最终学习目标。"),
        ("reinforced", "画像补强节点", "这些节点用于补齐画像差距，不是最终目标本身。"),
        ("prerequisite", "硬前置节点", "这些节点是进入目标学习前必须先掌握的硬前置依赖。"),
    )
    groups: list[NodeGroupSummary] = []
    for group_id, title, default_summary in group_defs:
        items = [
            item for item in node_explanations
            if item.decision_type == group_id
        ]
        if not items:
            continue
        groups.append(
            NodeGroupSummary(
                group_id=group_id,
                title=title,
                summary=f"{default_summary[:-1]} 共 {len(items)} 个。",
                node_ids=[item.node_id for item in items],
                nodes=[
                    {
                        "node_id": item.node_id,
                        "node_name": item.node_name,
                        "reason": item.reason,
                        "decision_type": item.decision_type,
                    }
                    for item in items
                ],
            )
        )
    return groups


def _build_readable_ordering_summary(
    audit: dict[str, Any],
    ordering_explanations: list[OrderExplanation],
) -> OrderingSummary:
    ordered_ids = list(audit.get("ordering_logs", {}).keys())
    mode = audit.get("ordering_mode") or (audit.get("goal_result", {}) or {}).get("mode")
    key_factors: list[str] = []
    for explanation in ordering_explanations:
        for factor in explanation.factors:
            if factor not in key_factors:
                key_factors.append(factor)
            if len(key_factors) >= 5:
                break
        if len(key_factors) >= 5:
            break
    factor_labels = _dedupe_strings([_extract_factor_label(item) for item in key_factors])
    summary = (
        f"排序先满足依赖关系，再以{_label_value(mode, _ORDERING_MODE_LABELS)}模式安排"
        f" {len(ordered_ids)} 个节点的先后顺序。"
    )
    if factor_labels:
        summary = (
            f"{summary[:-1]}，主要参考{'、'.join(factor_labels[:3])}等规则因子。"
        )
    return OrderingSummary(
        summary=summary,
        mode=mode,
        ordered_node_ids=ordered_ids,
        key_factors=key_factors,
    )


def _build_readable_stage_summary(
    audit: dict[str, Any],
    context: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    stage_explanations: list[StageExplanation],
) -> StageSummary:
    stages: list[dict[str, Any]] = []
    context_stages = context.get("stages")
    if isinstance(context_stages, list) and context_stages:
        for idx, stage in enumerate(context_stages):
            if not isinstance(stage, dict):
                continue
            tasks = stage.get("tasks") or []
            node_ids = [
                task.get("node_id")
                for task in tasks
                if isinstance(task, dict) and task.get("node_id")
            ]
            stages.append(
                {
                    "stage_index": stage.get("stage_index", idx),
                    "stage_name": stage.get("stage_name") or f"阶段 {idx + 1}",
                    "node_ids": node_ids,
                    "node_names": _resolve_node_names(node_ids, nodes_by_id, node_ids),
                    "estimated_hours": stage.get("estimated_hours"),
                }
            )
    else:
        ordered_ids = list(audit.get("ordering_logs", {}).keys())
        grouped: dict[str, list[str]] = {}
        for explanation in stage_explanations:
            grouped.setdefault(explanation.assigned_stage, []).append(explanation.node_id)
        for idx, (stage_name, node_ids) in enumerate(grouped.items()):
            ordered_node_ids = _ordered_unique_node_ids(node_ids, ordered_ids)
            stages.append(
                {
                    "stage_index": idx,
                    "stage_name": stage_name or f"阶段 {idx + 1}",
                    "node_ids": ordered_node_ids,
                    "node_names": _resolve_node_names(ordered_node_ids, nodes_by_id, ordered_node_ids),
                    "estimated_hours": round(
                        sum(
                            float((nodes_by_id.get(node_id) or {}).get("estimated_hours", 0) or 0)
                            for node_id in ordered_node_ids
                        ),
                        1,
                    ),
                }
            )
    stage_labels = [
        f"{stage['stage_name']}（{len(stage.get('node_ids', []))} 节点）"
        for stage in stages
    ]
    summary = f"路径被划分为 {len(stages)} 个阶段。"
    if stage_labels:
        summary = (
            f"{summary[:-1]}：{'、'.join(stage_labels[:3])}，"
            "阶段分配依据节点类别与目标类型规则。"
        )
    return StageSummary(
        summary=summary,
        stage_count=len(stages),
        stages=stages,
    )


def _build_readable_budget_summary(
    audit: dict[str, Any],
    context: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    budget_explanation: BudgetExplanation | None,
) -> ReadableBudgetSummary | None:
    budget = audit.get("budget_summary") or {}
    if not budget and budget_explanation is None:
        return None

    total_hours = budget.get("total_hours", context.get("total_hours"))
    weekly_hours = budget.get("weekly_hours")
    estimated_weeks = budget.get("estimated_weeks")
    status = audit.get("budget_status") or context.get("budget_status") or budget.get("status")
    path_mode = audit.get("path_mode") or context.get("path_mode") or budget.get("path_mode")
    compressed_note = _build_compressed_dependency_note(audit, nodes_by_id)

    if budget_explanation is not None and budget_explanation.suggestion:
        summary_parts = [budget_explanation.suggestion.strip()]
    else:
        summary_parts = [
            (
                f"总时长 {_format_scalar(total_hours)} 小时，"
                f"按每周 {_format_scalar(weekly_hours)} 小时预计 "
                f"{_format_scalar(estimated_weeks)} 周，"
                f"预算状态为{_label_value(status, _BUDGET_STATUS_LABELS)}。"
            )
        ]
    if compressed_note and all(compressed_note not in part for part in summary_parts):
        summary_parts.append(compressed_note)

    return ReadableBudgetSummary(
        summary="\n".join(part for part in summary_parts if part),
        total_hours=total_hours,
        weekly_hours=weekly_hours,
        estimated_weeks=estimated_weeks,
        status=status,
        path_mode=path_mode,
        compressed_dependency_note=compressed_note,
    )


def _build_trace_summary(
    audit: dict[str, Any],
    meta: ExplanationMeta,
) -> TraceSummary:
    overlay_lineage = audit.get("overlay_lineage")
    overlay_nodes = (
        overlay_lineage.get("nodes")
        if isinstance(overlay_lineage, dict) and isinstance(overlay_lineage.get("nodes"), dict)
        else {}
    )
    overlay_edges = (
        overlay_lineage.get("edges")
        if isinstance(overlay_lineage, dict) and isinstance(overlay_lineage.get("edges"), dict)
        else {}
    )
    return TraceSummary(
        pack_version=meta.pack_version,
        project_graph_hash=meta.project_graph_hash,
        overlay_node_count=len(overlay_nodes),
        overlay_edge_count=len(overlay_edges),
        overlay_lineage_items=_summarize_overlay_lineage(overlay_nodes, overlay_edges),
        fallback_used=meta.provenance.fallback_used,
        fallback_reasons=list(meta.provenance.fallback_reasons),
        live_pack_fields=list(meta.provenance.live_pack_fields),
        decision_chain=audit.get("decision_chain") or [],
        authority_labels=audit.get("authority_labels") or [],
        llm_fallback_status=audit.get("llm_fallback_status") or {},
    )


def _summarize_overlay_lineage(
    overlay_nodes: dict[str, Any],
    overlay_edges: dict[str, Any],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for node_id, lineage in overlay_nodes.items():
        if not isinstance(lineage, dict):
            continue
        snapshot = lineage.get("node_snapshot") if isinstance(lineage.get("node_snapshot"), dict) else {}
        items.append(
            {
                "kind": "node",
                "id": node_id,
                "name": snapshot.get("name") or node_id,
                "source_ids": lineage.get("source_ids") or [],
                "validation_status": lineage.get("validation_status"),
                "review_status": lineage.get("review_status"),
                "promotion_status": lineage.get("promotion_status"),
                "confidence": lineage.get("confidence"),
            }
        )
    for edge_id, lineage in overlay_edges.items():
        if not isinstance(lineage, dict):
            continue
        items.append(
            {
                "kind": "edge",
                "id": edge_id,
                "source_node_id": lineage.get("source_node_id"),
                "target_node_id": lineage.get("target_node_id"),
                "relation_type": lineage.get("relation_type"),
                "source_ids": lineage.get("source_ids") or [],
                "validation_status": lineage.get("validation_status"),
                "review_status": lineage.get("review_status"),
                "promotion_status": lineage.get("promotion_status"),
                "confidence": lineage.get("confidence"),
            }
        )
    return items[:10]


def _build_audit_highlights(
    *,
    audit: dict[str, Any],
    goal_resolution_summary: GoalResolutionSummary,
    ordering_summary: OrderingSummary,
    stage_summary: StageSummary,
    budget_summary: ReadableBudgetSummary | None,
    trace_summary: TraceSummary,
    meta: ExplanationMeta,
    dependency_chain_explanations: list[DependencyChainExplanation],
) -> list[AuditHighlight]:
    goal = audit.get("goal_result", {}) or {}
    ordered_ids = list(audit.get("ordering_logs", {}).keys())
    closure_ids = _ordered_unique_node_ids(audit.get("closure_ids", []), ordered_ids)
    closure_source = "audit.closure_ids"
    if not closure_ids:
        chain_node_ids = [
            node_id
            for chain in dependency_chain_explanations
            for node_id in chain.chain_node_ids
            if node_id not in goal_resolution_summary.target_node_ids
        ]
        closure_ids = _ordered_unique_node_ids(chain_node_ids, ordered_ids)
        closure_source = "dependency_chain_explanations"
    reinforced_ids = _ordered_unique_node_ids(
        audit.get("reinforced_ids", []) or list((audit.get("reinforcement_logs") or {}).keys())
    )
    fallback_summary = "未使用 live pack 回退。"
    if meta.provenance.fallback_used:
        reasons = "、".join(meta.provenance.fallback_reasons) or "未提供原因"
        fallback_summary = f"已记录 fallback/error provenance：{reasons}。"

    highlights = [
        AuditHighlight(
            key="goal_resolution",
            title="目标解析依据",
            summary=(
                f"最终采用 {_label_value(goal_resolution_summary.resolve_source, _RESOLVE_SOURCE_LABELS)} "
                f"来源的{_label_value(goal_resolution_summary.goal_type, _GOAL_TYPE_LABELS)}目标，"
                f"命中 {len(goal_resolution_summary.target_node_ids)} 个目标节点。"
            ),
            value={
                "final_goal_text": goal_resolution_summary.final_goal_text,
                "target_node_ids": goal_resolution_summary.target_node_ids,
                "source_breakdown": goal_resolution_summary.source_breakdown,
                "warnings": goal_resolution_summary.warnings,
            },
            source="audit.goal_result",
        ),
        AuditHighlight(
            key="dependency_closure",
            title="硬前置闭包",
            summary=(
                f"依赖快照要求纳入 {len(closure_ids)} 个硬前置节点，"
                f"最终路径节点数为 {len(audit.get('final_ids', []) or audit.get('ordering_logs', {}))}。"
            ),
            value={
                "closure_ids": closure_ids,
                "target_node_ids": goal.get("target_node_ids", []),
            },
            source=closure_source,
        ),
        AuditHighlight(
            key="profile_reinforcement",
            title="画像补强依据",
            summary=(
                f"画像补强阶段纳入 {len(reinforced_ids)} 个节点。"
                if reinforced_ids
                else "当前画像未触发额外补强节点。"
            ),
            value={
                "reinforced_ids": reinforced_ids,
                "reinforcement_log_count": len(audit.get("reinforcement_logs", {})),
            },
            source="audit.reinforcement_logs",
        ),
        AuditHighlight(
            key="ordering",
            title="排序依据",
            summary=(
                f"排序模式为 {_label_value(ordering_summary.mode, _ORDERING_MODE_LABELS)}，"
                f"共排序 {len(ordering_summary.ordered_node_ids)} 个节点。"
            ),
            value={
                "ordered_node_ids": ordering_summary.ordered_node_ids,
                "key_factors": ordering_summary.key_factors,
            },
            source="audit.ordering_logs",
        ),
        AuditHighlight(
            key="stage_assignment",
            title="阶段划分依据",
            summary=f"阶段划分共 {stage_summary.stage_count} 个阶段。",
            value={"stages": stage_summary.stages},
            source="audit.stage_logs",
        ),
        AuditHighlight(
            key="budget",
            title="预算依据",
            summary=(
                f"预算状态为 {_label_value(budget_summary.status, _BUDGET_STATUS_LABELS)}。"
                if budget_summary is not None
                else "未提供预算摘要。"
            ),
            value=(
                {
                    "total_hours": budget_summary.total_hours,
                    "weekly_hours": budget_summary.weekly_hours,
                    "estimated_weeks": budget_summary.estimated_weeks,
                    "compressed_dependency_note": budget_summary.compressed_dependency_note,
                }
                if budget_summary is not None
                else None
            ),
            source="audit.budget_summary",
        ),
        AuditHighlight(
            key="overlay_lineage",
            title="项目扩展快照",
            summary=(
                f"项目扩展快照包含 {trace_summary.overlay_node_count} 个节点和 "
                f"{trace_summary.overlay_edge_count} 条边。"
            ),
            value={
                "overlay_node_count": trace_summary.overlay_node_count,
                "overlay_edge_count": trace_summary.overlay_edge_count,
                "pack_version": trace_summary.pack_version,
                "project_graph_hash": trace_summary.project_graph_hash,
                "lineage_items": trace_summary.overlay_lineage_items,
            },
            source="audit.overlay_lineage",
        ),
        AuditHighlight(
            key="fallback_status",
            title="回退与错误标记",
            summary=fallback_summary,
            value={
                "fallback_used": meta.provenance.fallback_used,
                "fallback_reasons": meta.provenance.fallback_reasons,
                "live_pack_fields": meta.provenance.live_pack_fields,
            },
            source="meta.provenance",
        ),
        AuditHighlight(
            key="authority_labels",
            title="规则权威与 AI 辅助边界",
            summary="正式路径以规则和用户确认事实为权威，AI 只作为辅助理解或解释润色标签展示。",
            value={
                "labels": trace_summary.authority_labels,
                "llm_fallback_status": trace_summary.llm_fallback_status,
            },
            source="audit.authority_labels",
        ),
        AuditHighlight(
            key="decision_chain",
            title="完整决策链",
            summary=f"审计链记录 {len(trace_summary.decision_chain)} 个正式路径生成步骤，可不重跑 LLM 复原决策。",
            value={"steps": trace_summary.decision_chain},
            source="audit.decision_chain",
        ),
    ]
    return highlights


def _get_node_name(nid: str, nodes_by_id: dict[str, dict[str, Any]]) -> str:
    node = nodes_by_id.get(nid)
    return node["name"] if node else nid


def _prereq_reason(
    nid: str,
    target_ids: list[str],
    ancestors_by_target: dict[str, set[str]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> str:
    """按 related targets 数量产出 1/2/≥3 三种差异化模板。"""
    related_names = [
        nodes_by_id[t]["name"]
        for t in target_ids
        if nid in ancestors_by_target.get(t, set()) and t in nodes_by_id
    ]
    if not related_names:
        return "前置依赖：作为目标节点的必要前置知识"
    if len(related_names) == 1:
        return f"作为目标「{related_names[0]}」的前置基础"
    if len(related_names) == 2:
        return f"作为目标「{related_names[0]}」和「{related_names[1]}」的共同基础"
    return f"作为目标「{related_names[0]}」和「{related_names[1]}」等目标的共同基础"


def _build_node_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    target_ids: list[str],
    ancestors_by_target: dict[str, set[str]],
) -> list[NodeExplanation]:
    results: list[NodeExplanation] = []
    target_set = set(target_ids)
    ordering_logs = audit.get("ordering_logs", {})
    reinforcement_logs = audit.get("reinforcement_logs", {})

    for nid, log in ordering_logs.items():
        if nid in target_set:
            reason = "目标节点：直接匹配学习目标"
            decision = "target"
        elif nid in reinforcement_logs:
            gap = reinforcement_logs[nid].get("gap", {}) or {}
            weakest = _pick_weakest_dimension(gap)
            reason = (
                f"画像补强：{weakest}差距最明显（总分 {gap.get('gap_total', 0):.3f}），"
                f"优先补齐该方向基础"
            )
            decision = "reinforced"
        else:
            reason = _prereq_reason(nid, target_ids, ancestors_by_target, nodes_by_id)
            decision = "prerequisite"

        results.append(NodeExplanation(
            node_id=nid,
            node_name=_get_node_name(nid, nodes_by_id),
            reason=reason,
            gap=log.get("gap"),
            decision_type=decision,
        ))

    return results


def _build_ordering_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    profile_snapshot: dict[str, Any],
    mode: str,
    priority_weights: dict[str, float],
    mode_adjustments: dict[str, dict[str, float]],
) -> list[OrderExplanation]:
    results: list[OrderExplanation] = []
    ordering_logs = audit.get("ordering_logs", {})

    for nid, log in ordering_logs.items():
        score = log.get("priority_score", 0)
        relevance = log.get("goal_relevance", 0)
        gap = log.get("gap", {}) or {}

        factors = _compute_top3_factors(
            nodes_by_id.get(nid), profile_snapshot, gap, relevance,
            mode, priority_weights, mode_adjustments,
        )
        factors.extend(log.get("reasons", []))

        results.append(OrderExplanation(
            node_id=nid,
            node_name=_get_node_name(nid, nodes_by_id),
            priority_score=score,
            goal_relevance=relevance,
            factors=factors,
        ))

    return results


def _compute_top3_factors(
    node: dict[str, Any] | None,
    profile: dict[str, Any],
    gap: dict[str, float],
    goal_relevance: float,
    mode: str,
    priority_weights: dict[str, float],
    mode_adjustments: dict[str, dict[str, float]],
) -> list[str]:
    """重算 signed contributions 并取 |contribution| top-3，格式 '<中文 label> (<±0.XXX>)'。"""
    if not node or not profile or "gap_total" not in gap:
        return []
    try:
        contribs = decompose_priority_score(
            node=node,
            profile=profile,
            gap=gap,
            goal_relevance=goal_relevance,
            mode=mode,
            weights=priority_weights,
            mode_adjustments=mode_adjustments,
        )
    except (KeyError, TypeError):
        return []

    top3 = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:3]
    return [
        f"{_PRIORITY_COMPONENT_LABELS.get(key, key)} ({value:+.3f})"
        for key, value in top3
    ]


def _translate_stage_reasons(tokens: list[str]) -> str:
    """把 audit 里的英文 token（如 `category=foundation`）翻译成中文说明；未命中丢弃。"""
    parts = [
        _STAGE_REASON_TRANSLATIONS[t]
        for t in tokens
        if t in _STAGE_REASON_TRANSLATIONS
    ]
    return " ".join(parts) if parts else "该节点按当前阶段规则分配。"


def _real_prereq_chain(
    target_id: str,
    ordered_ids: list[str],
    requires_rev_adj: dict[str, list[str]],
) -> list[str]:
    """返回 target 的真实 REQUIRES 反向闭包，并按 ordered_ids 的学习顺序排序。"""
    visited: set[str] = set()
    queue: deque[str] = deque([target_id])
    while queue:
        cur = queue.popleft()
        for prev in requires_rev_adj.get(cur, ()):
            if prev not in visited:
                visited.add(prev)
                queue.append(prev)
    closure = visited | {target_id}
    return [nid for nid in ordered_ids if nid in closure]


def _build_stage_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[StageExplanation]:
    results: list[StageExplanation] = []
    stage_logs = audit.get("stage_logs", {})

    for nid, log in stage_logs.items():
        reasons = log.get("reasons", [])
        results.append(StageExplanation(
            node_id=nid,
            node_name=_get_node_name(nid, nodes_by_id),
            assigned_stage=log.get("assigned_stage", ""),
            reasons=reasons,
            rationale=_translate_stage_reasons(reasons),
        ))

    return results


def _build_budget_explanation(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    dep_chains: dict[str, list[str]],
    target_ids: list[str],
) -> BudgetExplanation | None:
    bs = audit.get("budget_summary")
    if not bs:
        return None

    original_suggestion = bs.get("suggestion", "")
    prefix = _build_summary_prefix(audit, nodes_by_id, dep_chains, target_ids)
    persona_note = _build_persona_note(audit)
    path_mode_note = _build_path_mode_note(audit, nodes_by_id)
    parts = [
        part
        for part in (prefix, persona_note, path_mode_note, original_suggestion)
        if part
    ]
    suggestion = "\n".join(parts)

    return BudgetExplanation(
        total_hours=bs.get("total_hours", bs.get("planned_hours", 0)),
        weekly_hours=bs.get("weekly_hours", 0),
        estimated_weeks=bs.get("estimated_weeks", 0),
        status=bs.get("status", ""),
        suggestion=suggestion,
    )


def _build_persona_note(audit: dict[str, Any]) -> str:
    profile_snapshot = audit.get("profile_snapshot") or {}
    summary = profile_snapshot.get("persona_summary")
    if not isinstance(summary, str) or not summary.strip():
        return ""
    return f"学习者画像：{summary.strip()}"


def _build_path_mode_note(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> str:
    path_mode = audit.get("path_mode", "standard")
    budget_status = audit.get("budget_status") or (audit.get("budget_summary") or {}).get("status")
    excluded_nodes = audit.get("excluded_nodes") or []
    if budget_status == "over_budget_required_closure":
        return "当前目标的硬前置闭包已超过预算，系统保留完整依赖链，未裁剪必要知识点。"
    if path_mode != "compressed" or not excluded_nodes:
        return ""
    names = [
        _get_node_name(item.get("node_id", ""), nodes_by_id)
        for item in excluded_nodes
        if isinstance(item, dict) and item.get("node_id")
    ]
    if not names:
        return "压缩模式已裁剪可选补强节点，仅保留目标与必要前置依赖。"
    shown = "、".join(names[:3])
    suffix = "等" if len(names) > 3 else ""
    return f"压缩模式已裁剪 {shown}{suffix} 等可选补强节点，仅保留目标与必要前置依赖。"


def _build_summary_prefix(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    dep_chains: dict[str, list[str]],
    target_ids: list[str],
) -> str:
    """按 design §3.5 拼接 '路径从「...」出发，经「...」，聚焦于「...」；共 N 节点 / H 小时。'"""
    ordered = list(audit.get("ordering_logs", {}).keys())
    if not ordered:
        return ""
    first_name = _get_node_name(ordered[0], nodes_by_id)
    target_names = [
        _get_node_name(tid, nodes_by_id) for tid in target_ids if tid in nodes_by_id
    ]

    bridge_names: list[str] = []
    if target_ids:
        chain = dep_chains.get(target_ids[0], [])
        if len(chain) > 2:
            mid = chain[1:-1]
            bridge_names = [_get_node_name(n, nodes_by_id) for n in mid[:2]]

    if len(target_names) == 1:
        focus = f"聚焦于「{target_names[0]}」"
    elif len(target_names) == 2:
        focus = f"聚焦于「{target_names[0]}」和「{target_names[1]}」"
    elif len(target_names) >= 3:
        focus = f"聚焦于「{target_names[0]}」和「{target_names[1]}」等目标"
    else:
        focus = "围绕当前学习目标展开"

    segments = [f"路径从「{first_name}」出发"]
    if bridge_names:
        segments.append(f"经「{'」与「'.join(bridge_names)}」")
    segments.append(focus)

    node_count = len(ordered)
    total_hours = (audit.get("budget_summary") or {}).get("total_hours", 0)
    return (
        "，".join(segments)
        + f"；共 {node_count} 节点 / {total_hours} 小时。"
    )


def _build_dependency_chain_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    dep_chains: dict[str, list[str]],
) -> list[DependencyChainExplanation]:
    results: list[DependencyChainExplanation] = []
    target_ids = audit.get("goal_result", {}).get("target_node_ids", [])

    for target_id in target_ids:
        chain_ids = dep_chains.get(target_id)
        if not chain_ids:
            continue
        results.append(DependencyChainExplanation(
            target_node_id=target_id,
            target_node_name=_get_node_name(target_id, nodes_by_id),
            chain_node_ids=chain_ids,
            chain_node_names=[_get_node_name(nid, nodes_by_id) for nid in chain_ids],
            reason="该目标节点需要按当前学习顺序先掌握其前置依赖，再学习目标本身",
        ))

    return results


def _build_reinforcement_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[ReinforcementExplanation]:
    results: list[ReinforcementExplanation] = []
    reinforcement_logs = audit.get("reinforcement_logs", {})

    for nid, log in reinforcement_logs.items():
        results.append(ReinforcementExplanation(
            node_id=nid,
            node_name=_get_node_name(nid, nodes_by_id),
            gap=log.get("gap", {}),
            reinforce_score=log.get("reinforce_score", 0),
            reasons=log.get("reasons", []),
        ))

    return results


def _build_explanation_meta(
    audit: dict[str, Any],
    context: dict[str, Any],
    requires_provenance: dict[str, Any],
) -> ExplanationMeta:
    fallback_reasons = list(requires_provenance.get("fallback_reasons", []))
    fallback_reasons.extend(context.get("fallback_reasons", []))
    live_pack_fields = list(requires_provenance.get("live_pack_fields", []))
    live_pack_fields.extend(context.get("live_pack_fields", []))

    pack_version = audit.get("pack_version")
    if pack_version is None:
        pack_version = context.get("pack_version")
        if context.get("pack_version_source") == "live_pack":
            fallback_reasons.append("pack_version_missing")
            live_pack_fields.append("pack_version")

    project_graph_hash = audit.get("project_graph_hash")
    if project_graph_hash is None:
        project_graph_hash = context.get("project_graph_hash")
        if context.get("project_graph_hash_source") == "live_pack":
            fallback_reasons.append("project_graph_hash_missing")
            live_pack_fields.append("project_graph_hash")

    provenance = ExplanationProvenance(
        fallback_used=bool(fallback_reasons or live_pack_fields),
        fallback_reasons=_dedupe_strings(fallback_reasons),
        live_pack_fields=_dedupe_strings(live_pack_fields),
    )
    return ExplanationMeta(
        plan_version=context.get("plan_version"),
        pack_version=str(pack_version) if pack_version is not None else None,
        project_graph_hash=str(project_graph_hash) if project_graph_hash is not None else None,
        provenance=provenance,
        polish=PolishMeta(),
    )


def _node_ids_in_explanation(response: ExplanationResponse) -> set[str]:
    ids: set[str] = set()
    for item in response.node_explanations:
        ids.add(item.node_id)
    for item in response.ordering_explanations:
        ids.add(item.node_id)
    for item in response.stage_explanations:
        ids.add(item.node_id)
    return ids


def answer_explanation_question(
    response: ExplanationResponse,
    request: ExplanationAskRequest,
    llm_client_factory=None,
    *,
    latest_plan_node_ids: set[str] | None = None,
) -> ExplanationAskResponse:
    node_ids = latest_plan_node_ids if latest_plan_node_ids is not None else _node_ids_in_explanation(response)
    if request.node_id and request.node_id not in node_ids:
        return ExplanationAskResponse(
            question_id=request.question_id,
            answer="该问题指向的知识点不在当前最新学习路径中，无法基于本路径解释。",
            limitations=["node_not_in_latest_plan"],
            fallback_reason="invalid_node_id",
        )

    fallback = _rule_based_ask_response(response, request)
    llm_cfg = get_llm_config()
    if not llm_cfg.get("llm_api_key"):
        return fallback.model_copy(update={"fallback_reason": "missing_api_key"})

    payload = _build_ask_payload(response, request, fallback)
    answer, limitations, fallback_reason = _call_llm_ask(payload, llm_cfg, llm_client_factory)
    if not answer:
        return fallback.model_copy(update={"fallback_reason": fallback_reason or "invalid_response"})
    return fallback.model_copy(
        update={
            "answer": answer,
            "limitations": _dedupe_strings([*fallback.limitations, *limitations]),
            "ai_used": True,
            "fallback_reason": None,
        }
    )


def _rule_based_ask_response(
    response: ExplanationResponse,
    request: ExplanationAskRequest,
) -> ExplanationAskResponse:
    handlers = {
        "why_path_order": _answer_why_path_order,
        "why_include_node": _answer_why_include_node,
        "why_stage_assignment": _answer_why_stage_assignment,
        "budget_feasibility": _answer_budget_feasibility,
        "what_if_time_limited": _answer_what_if_time_limited,
    }
    answer, refs, limitations = handlers[request.question_id](response, request.node_id)
    return ExplanationAskResponse(
        question_id=request.question_id,
        answer=answer,
        evidence_refs=refs,
        limitations=limitations,
        ai_used=False,
        fallback_reason=None,
    )


def _find_node_explanation(
    response: ExplanationResponse,
    node_id: str | None,
) -> NodeExplanation | None:
    if not node_id:
        return None
    for item in response.node_explanations:
        if item.node_id == node_id:
            return item
    return None


def _find_stage_explanation(
    response: ExplanationResponse,
    node_id: str | None,
) -> StageExplanation | None:
    if not node_id:
        return None
    for item in response.stage_explanations:
        if item.node_id == node_id:
            return item
    return None


def _find_node_group_summary(
    response: ExplanationResponse,
    node_id: str | None,
) -> dict[str, Any] | None:
    if not node_id or not response.readability:
        return None
    for group in response.readability.node_groups:
        if node_id in group.node_ids:
            return {
                "group_id": group.group_id,
                "title": group.title,
                "summary": group.summary,
            }
    return None


def _serialize_audit_highlight_summaries(
    response: ExplanationResponse,
    keys: set[str],
) -> list[dict[str, Any]]:
    if not response.readability:
        return []
    return [
        {
            "key": item.key,
            "title": item.title,
            "summary": item.summary,
            "source": item.source,
        }
        for item in response.readability.audit_highlights
        if item.key in keys
    ]


def _answer_why_path_order(
    response: ExplanationResponse,
    _node_id: str | None,
) -> tuple[str, list[EvidenceRef], list[str]]:
    summary = response.readability.ordering_summary.summary if response.readability else "排序先满足依赖关系，再参考目标相关度、画像差距和模式权重。"
    return summary, [EvidenceRef(source="readability.ordering_summary")], []


def _answer_why_include_node(
    response: ExplanationResponse,
    node_id: str | None,
) -> tuple[str, list[EvidenceRef], list[str]]:
    for item in response.node_explanations:
        if item.node_id == node_id:
            return item.reason, [EvidenceRef(source="node_explanations", node_id=item.node_id)], []
    return "该知识点未出现在当前路径解释中。", [], ["node_explanation_missing"]


def _answer_why_stage_assignment(
    response: ExplanationResponse,
    node_id: str | None,
) -> tuple[str, list[EvidenceRef], list[str]]:
    for item in response.stage_explanations:
        if item.node_id == node_id:
            answer = item.rationale or "、".join(item.reasons) or "该节点按阶段规则分配。"
            return answer, [EvidenceRef(source="stage_explanations", node_id=item.node_id)], []
    return "该知识点没有可用的阶段解释。", [], ["stage_explanation_missing"]


def _answer_budget_feasibility(
    response: ExplanationResponse,
    _node_id: str | None,
) -> tuple[str, list[EvidenceRef], list[str]]:
    if response.readability and response.readability.budget_summary:
        return response.readability.budget_summary.summary, [EvidenceRef(source="readability.budget_summary")], []
    if response.budget_explanation:
        return response.budget_explanation.suggestion, [EvidenceRef(source="budget_explanation")], []
    return "当前路径没有可用的预算解释。", [], ["budget_explanation_missing"]


def _answer_what_if_time_limited(
    response: ExplanationResponse,
    _node_id: str | None,
) -> tuple[str, list[EvidenceRef], list[str]]:
    if response.readability and response.readability.budget_summary:
        note = response.readability.budget_summary.compressed_dependency_note
        if note:
            return note, [EvidenceRef(source="readability.budget_summary.compressed_dependency_note")], []
    return (
        "如果时间有限，可以优先查看压缩模式或减少可选补强；硬前置依赖不应被裁剪。",
        [EvidenceRef(source="readability.budget_summary")],
        [],
    )


def _build_ask_payload(
    response: ExplanationResponse,
    request: ExplanationAskRequest,
    fallback: ExplanationAskResponse,
) -> dict[str, Any]:
    related_node = request.node_id
    node_explanation = _find_node_explanation(response, related_node)
    stage_explanation = _find_stage_explanation(response, related_node)
    overview = response.readability.overview_summary if response.readability else None
    ordering_summary = response.readability.ordering_summary if response.readability else None
    stage_summary = response.readability.stage_summary if response.readability else None
    budget_summary = (
        response.readability.budget_summary
        if response.readability and response.readability.budget_summary
        else None
    )
    payload: dict[str, Any] = {
        "question": {
            "question_id": request.question_id,
            "node_id": related_node,
            "node_name": node_explanation.node_name if node_explanation else None,
        },
        "rule_answer": fallback.answer,
        "evidence_refs": [ref.model_dump(exclude_none=True) for ref in fallback.evidence_refs],
        "limitations": list(fallback.limitations),
    }

    if request.question_id == "why_path_order":
        payload.update(
            {
                "readability": {
                    "overview": (
                        {
                            "headline": overview.headline,
                            "node_count": overview.node_count,
                            "path_mode": overview.path_mode,
                        }
                        if overview
                        else None
                    ),
                    "ordering_summary": (
                        ordering_summary.model_dump()
                        if ordering_summary
                        else None
                    ),
                },
                "rule_explanation": {
                    "ordering_explanations": [
                        {
                            "node_id": item.node_id,
                            "node_name": item.node_name,
                            "priority_score": item.priority_score,
                            "goal_relevance": item.goal_relevance,
                            "factors": item.factors[:3],
                        }
                        for item in response.ordering_explanations[:5]
                    ],
                },
                "audit_summary": _serialize_audit_highlight_summaries(
                    response,
                    {"dependency_closure", "ordering"},
                ),
            }
        )
        return payload

    if request.question_id == "why_include_node":
        payload.update(
            {
                "readability": {
                    "node_group": _find_node_group_summary(response, related_node),
                },
                "rule_explanation": {
                    "node_explanation": (
                        {
                            "node_id": node_explanation.node_id,
                            "node_name": node_explanation.node_name,
                            "decision_type": node_explanation.decision_type,
                            "reason": node_explanation.reason,
                        }
                        if node_explanation
                        else None
                    ),
                    "stage_explanation": (
                        {
                            "assigned_stage": stage_explanation.assigned_stage,
                            "rationale": stage_explanation.rationale,
                        }
                        if stage_explanation
                        else None
                    ),
                },
                "audit_summary": _serialize_audit_highlight_summaries(
                    response,
                    {"goal_resolution", "dependency_closure", "profile_reinforcement"},
                ),
            }
        )
        return payload

    if request.question_id == "why_stage_assignment":
        payload.update(
            {
                "readability": {
                    "stage_summary": (
                        stage_summary.model_dump()
                        if stage_summary
                        else None
                    ),
                },
                "rule_explanation": {
                    "stage_explanation": (
                        {
                            "node_id": stage_explanation.node_id,
                            "node_name": stage_explanation.node_name,
                            "assigned_stage": stage_explanation.assigned_stage,
                            "reasons": list(stage_explanation.reasons),
                            "rationale": stage_explanation.rationale,
                        }
                        if stage_explanation
                        else None
                    ),
                },
                "audit_summary": _serialize_audit_highlight_summaries(
                    response,
                    {"stage_assignment"},
                ),
            }
        )
        return payload

    if request.question_id == "budget_feasibility":
        payload.update(
            {
                "readability": {
                    "overview": (
                        {
                            "headline": overview.headline,
                            "total_hours": overview.total_hours,
                            "budget_status": overview.budget_status,
                        }
                        if overview
                        else None
                    ),
                    "budget_summary": (
                        budget_summary.model_dump()
                        if budget_summary
                        else None
                    ),
                },
                "rule_explanation": {
                    "budget_explanation": (
                        response.budget_explanation.model_dump()
                        if response.budget_explanation
                        else None
                    ),
                },
                "audit_summary": _serialize_audit_highlight_summaries(
                    response,
                    {"budget"},
                ),
            }
        )
        return payload

    payload.update(
        {
            "readability": {
                "overview": (
                    {
                        "headline": overview.headline,
                        "notes": list(overview.notes),
                    }
                    if overview
                    else None
                ),
                "budget_summary": (
                    budget_summary.model_dump()
                    if budget_summary
                    else None
                ),
            },
            "rule_explanation": {
                "budget_explanation": (
                    response.budget_explanation.model_dump()
                    if response.budget_explanation
                    else None
                ),
            },
            "audit_summary": _serialize_audit_highlight_summaries(
                response,
                {"budget"},
            ),
        }
    )
    return payload


def _strip_code_fence(content: str) -> str:
    stripped = content.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _is_timeout_error(exc: Exception) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    return exc.__class__.__name__ in {"APITimeoutError", "TimeoutException", "ReadTimeout", "ConnectTimeout"}


def _is_blocked_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "blocked" in message or "content_filter" in message or "safety" in message


def _is_unsupported_chat_param_error(exc: Exception, param: str) -> bool:
    message = str(exc).lower()
    if param not in message:
        return False
    markers = (
        "unsupported",
        "not support",
        "does not support",
        "unrecognized",
        "unknown parameter",
        "invalid parameter",
        "only default",
    )
    return any(marker in message for marker in markers)


def _should_retry_chat_completion(exc: Exception, optional_args: dict[str, Any]) -> bool:
    return (
        "temperature" in optional_args
        and _is_unsupported_chat_param_error(exc, "temperature")
    ) or (
        "max_tokens" in optional_args
        and _is_unsupported_chat_param_error(exc, "max_tokens")
    )


def _create_chat_completion(
    client,
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float,
):
    attempts: list[dict[str, Any]] = [
        {"temperature": temperature, "max_tokens": max_tokens},
        {"max_tokens": max_tokens},
        {"temperature": temperature, "max_completion_tokens": max_tokens},
        {"max_completion_tokens": max_tokens},
    ]
    last_exc: Exception | None = None

    for optional_args in attempts:
        try:
            if isinstance(client, _HttpChatClient):
                return client.create_chat_completion(
                    model=model,
                    messages=messages,
                    **optional_args,
                )
            return client.chat.completions.create(
                model=model,
                messages=messages,
                **optional_args,
            )
        except Exception as exc:
            last_exc = exc
            if not _should_retry_chat_completion(exc, optional_args):
                raise
            logger.info("LLM chat 参数不兼容，重试简化参数: %s", exc)

    if last_exc is not None:
        raise last_exc
    raise RuntimeError("LLM chat completion failed without an exception")


def _call_llm_ask(
    payload: dict[str, Any],
    llm_cfg: dict[str, str],
    llm_client_factory,
) -> tuple[str | None, list[str], str | None]:
    try:
        client = _build_llm_client(llm_cfg, llm_client_factory, timeout=ASK_TIMEOUT_SECONDS)
        response = _create_chat_completion(
            client,
            model=llm_cfg.get("llm_model", "gpt-3.5-turbo"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是学习路径解释助手。只能基于用户提供的结构化 explanation payload 回答，"
                        "不得引入外部资料、不得建议修改或重排路径、不得声称看过完整 raw audit。"
                        "如果信息不足要明确说明局限。"
                        "只返回 JSON 对象："
                        "{\"answer\":\"...\",\"limitations\":[\"...\"]}。"
                        "answer 必须是中文且不超过 120 字。"
                    ),
                },
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.2,
            max_tokens=300,
        )
        content = _strip_code_fence(response.choices[0].message.content)
        if not content:
            return None, [], "invalid_response"
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            return None, [], "invalid_response"
        answer = parsed.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            return None, [], "invalid_response"
        answer = answer.strip()
        if len(answer) > ASK_MAX_LENGTH:
            return None, [], "length_exceeded"
        limitations = _dedupe_strings(
            [
                item
                for item in parsed.get("limitations", [])
                if isinstance(item, str)
            ]
        )
        return answer, limitations, None
    except Exception as exc:
        if _is_timeout_error(exc):
            logger.warning("LLM 解释问答超时，回落规则回答: %s", exc)
            return None, [], "timeout"
        if _is_blocked_error(exc):
            logger.info("LLM 解释问答被服务商拦截，回落规则回答: %s", exc)
            return None, [], "blocked"
        logger.warning("LLM 解释问答失败，回落规则回答: %s", exc)
        return None, [], "invalid_response"


def polish_explanation(
    response: ExplanationResponse,
    llm_client_factory=None,
    *,
    requested: bool = True,
) -> ExplanationResponse:
    """对解释 DTO 进行 LLM 自然语言润色。失败安全降级为原文。"""
    if not requested:
        return _with_polish_meta(response, PolishMeta(requested=False))
    if not get_llm_polish_enabled():
        return _with_polish_meta(
            response,
            PolishMeta(requested=True, fallback_reason="disabled"),
        )

    llm_cfg = get_llm_config()
    if not llm_cfg.get("llm_api_key"):
        return _with_polish_meta(
            response,
            PolishMeta(requested=True, fallback_reason="missing_api_key"),
        )

    items = _collect_polish_items(response)
    if not items:
        return _with_polish_meta(
            response,
            PolishMeta(requested=True, fallback_reason="empty_scope"),
        )

    polished_map, fallback_reason = _call_llm_polish(items, llm_cfg, llm_client_factory)
    if not polished_map:
        return _with_polish_meta(
            response,
            PolishMeta(requested=True, fallback_reason=fallback_reason or "invalid_response"),
        )

    polished_response, scope = _apply_polished_texts(response, polished_map)
    if not scope:
        return _with_polish_meta(
            response,
            PolishMeta(requested=True, fallback_reason="invalid_response"),
        )
    return _with_polish_meta(
        polished_response,
        PolishMeta(requested=True, applied=True, scope=scope),
    )


def _with_polish_meta(response: ExplanationResponse, polish: PolishMeta) -> ExplanationResponse:
    meta = response.meta or ExplanationMeta()
    return response.model_copy(update={"meta": meta.model_copy(update={"polish": polish})})


def _collect_polish_items(response: ExplanationResponse) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for ne in response.node_explanations:
        items.append({"key": f"node:{ne.node_id}", "text": ne.reason})
    for se in response.stage_explanations:
        base = se.rationale or "、".join(se.reasons)
        if base:
            items.append({"key": f"stage:{se.node_id}", "text": base})
    return items


def _build_polish_messages(payload: str, *, user_only: bool = False) -> list[dict[str, str]]:
    if user_only:
        return [
            {
                "role": "user",
                "content": (
                    "请把下面 JSON 数组中每个 text 改写成自然、简洁的中文短句，含义不变。"
                    "输出同样格式的 JSON 数组，只包含 key 和 text。\n"
                    f"{payload}"
                ),
            }
        ]
    return [
        {
            "role": "system",
            "content": (
                "你是教育路径解释润色器。对输入 JSON 数组中的每一项 `text` "
                "改写为通顺自然的中文解释，保留原意与数值/因子名，不引入未提供的事实。"
                "每条 ≤ 80 字。只返回 JSON 数组，格式 [{\"key\":\"...\",\"text\":\"...\"}]。"
            ),
        },
        {"role": "user", "content": payload},
    ]


def _request_llm_polish(client, llm_cfg: dict[str, str], messages: list[dict[str, str]]):
    return _create_chat_completion(
        client,
        model=llm_cfg.get("llm_model", "gpt-3.5-turbo"),
        messages=messages,
        temperature=0.2,
        max_tokens=800,
    )


def _call_llm_polish(
    items: list[dict[str, str]],
    llm_cfg: dict[str, str],
    llm_client_factory,
) -> tuple[dict[str, str], str | None]:
    try:
        client = _build_llm_client(llm_cfg, llm_client_factory, timeout=POLISH_TIMEOUT_SECONDS)
        payload = json.dumps(items, ensure_ascii=False)
        try:
            response = _request_llm_polish(
                client,
                llm_cfg,
                _build_polish_messages(payload),
            )
        except Exception as exc:
            if not _is_blocked_error(exc):
                raise
            logger.info("LLM 解释润色首次请求被拦截，改用简化提示重试: %s", exc)
            try:
                response = _request_llm_polish(
                    client,
                    llm_cfg,
                    _build_polish_messages(payload, user_only=True),
                )
            except Exception as retry_exc:
                if _is_timeout_error(retry_exc):
                    logger.warning("LLM 解释润色重试超时，回落原文: %s", retry_exc)
                    return {}, "timeout"
                if _is_blocked_error(retry_exc):
                    logger.info("LLM 解释润色重试仍被服务商拦截，回落原文: %s", retry_exc)
                    return {}, "blocked"
                logger.warning("LLM 解释润色重试失败，回落原文: %s", retry_exc)
                return {}, "invalid_response"

        content = _strip_code_fence(response.choices[0].message.content)
        if not content:
            return {}, "invalid_response"
        parsed = json.loads(content)
        if not isinstance(parsed, list):
            return {}, "invalid_response"

        polished: dict[str, str] = {}
        rejected_for_length = False
        for entry in parsed:
            if not isinstance(entry, dict):
                continue
            key = entry.get("key")
            text = entry.get("text", "")
            if not key or not isinstance(text, str):
                continue
            if not text:
                continue
            if len(text) > POLISH_MAX_LENGTH:
                rejected_for_length = True
                continue
            polished[key] = text
        if polished:
            return polished, None
        return {}, "length_exceeded" if rejected_for_length else "invalid_response"
    except Exception as exc:
        if _is_timeout_error(exc):
            logger.warning("LLM 解释润色超时，回落原文: %s", exc)
            return {}, "timeout"
        if _is_blocked_error(exc):
            logger.info("LLM 解释润色被服务商拦截，回落原文: %s", exc)
            return {}, "blocked"
        logger.warning("LLM 解释润色失败，回落原文: %s", exc)
        return {}, "invalid_response"


class _HttpChatClient:
    def __init__(self, llm_cfg: dict[str, str], *, timeout: float):
        self.base_url = llm_cfg.get("llm_base_url", "https://api.openai.com/v1").rstrip("/")
        self.model = llm_cfg.get("llm_model", "gpt-3.5-turbo")
        self.api_key = llm_cfg["llm_api_key"]
        self.timeout = timeout

    def create_chat_completion(self, *, model: str, messages: list[dict[str, str]], **optional_args):
        payload = {
            "model": model or self.model,
            "messages": messages,
            **optional_args,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                return _chat_completion_from_dict(response.json())
        except httpx.TimeoutException as exc:
            raise TimeoutError("LLM request timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(_extract_httpx_error_message(exc.response)) from exc


def _extract_httpx_error_message(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text or f"HTTP {response.status_code}"
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or error.get("code") or error.get("type")
            if message:
                return str(message)
        if isinstance(error, str):
            return error
        message = data.get("message") or data.get("detail")
        if message:
            return str(message)
    return f"HTTP {response.status_code}"


def _chat_completion_from_dict(data: dict[str, Any]):
    choices = []
    for choice in data.get("choices", []):
        message = choice.get("message", {}) if isinstance(choice, dict) else {}
        choices.append(SimpleNamespace(
            message=SimpleNamespace(content=message.get("content")),
            finish_reason=choice.get("finish_reason") if isinstance(choice, dict) else None,
        ))
    return SimpleNamespace(choices=choices, usage=data.get("usage"))


def _build_llm_client(llm_cfg: dict[str, str], llm_client_factory, *, timeout: float):
    if llm_client_factory is not None:
        return llm_client_factory(llm_cfg)
    return _HttpChatClient(llm_cfg, timeout=timeout)


def _apply_polished_texts(
    response: ExplanationResponse,
    polished: dict[str, str],
) -> tuple[ExplanationResponse, list[str]]:
    scope: list[str] = []
    node_changed = False
    node_out: list[NodeExplanation] = []
    for ne in response.node_explanations:
        key = f"node:{ne.node_id}"
        if key in polished and polished[key] != ne.reason:
            node_changed = True
            node_out.append(ne.model_copy(update={
                "raw_reason": ne.reason,
                "reason": polished[key],
            }))
        else:
            node_out.append(ne)

    stage_changed = False
    stage_out: list[StageExplanation] = []
    for se in response.stage_explanations:
        key = f"stage:{se.node_id}"
        original = se.rationale or "、".join(se.reasons)
        if key in polished and polished[key] != original:
            stage_changed = True
            stage_out.append(se.model_copy(update={
                "raw_rationale": original,
                "rationale": polished[key],
            }))
        else:
            stage_out.append(se)

    if node_changed:
        scope.append("node_reason")
    if stage_changed:
        scope.append("stage_rationale")
    return response.model_copy(update={
        "node_explanations": node_out,
        "stage_explanations": stage_out,
    }), scope
