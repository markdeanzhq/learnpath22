"""结构化路径解释服务：从 audit 数据生成可读解释"""
from __future__ import annotations

import json
import logging
from collections import deque
from typing import Any

from app.core.config import get_llm_config, get_llm_polish_enabled
from app.planner.scoring import (
    DEFAULT_MODE_ADJUSTMENTS,
    DEFAULT_PRIORITY_WEIGHTS,
    decompose_priority_score,
)
from app.schemas.explanation import (
    BudgetExplanation,
    DependencyChainExplanation,
    ExplanationResponse,
    NodeExplanation,
    OrderExplanation,
    ReinforcementExplanation,
    StageExplanation,
)

logger = logging.getLogger(__name__)

POLISH_MAX_LENGTH = 200
POLISH_TIMEOUT_SECONDS = 5.0

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


def _resolve_requires_rev_adj(
    audit: dict[str, Any],
    legacy_requires_rev_adj: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    snapshot_requires_rev_adj = audit.get("filtered_requires_rev_adj")
    if isinstance(snapshot_requires_rev_adj, dict) and snapshot_requires_rev_adj:
        return snapshot_requires_rev_adj
    logger.info("Explanation 使用 legacy requires_rev_adj fallback")
    return legacy_requires_rev_adj or {}


def build_explanation(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    legacy_requires_rev_adj: dict[str, list[str]],
    scoring_config: dict[str, Any],
) -> ExplanationResponse:
    goal = audit.get("goal_result", {}) or {}
    target_ids: list[str] = list(goal.get("target_node_ids", []))
    mode: str = audit.get("ordering_mode") or goal.get("mode", "")
    profile_snapshot: dict[str, Any] = audit.get("profile_snapshot") or {}
    requires_rev_adj = _resolve_requires_rev_adj(audit, legacy_requires_rev_adj)
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

    return ExplanationResponse(
        node_explanations=node_explanations,
        ordering_explanations=ordering_explanations,
        stage_explanations=stage_explanations,
        budget_explanation=budget_explanation,
        reinforcement_explanations=reinforcement_explanations,
        dependency_chain_explanations=dependency_chain_explanations,
    )


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


def polish_explanation(
    response: ExplanationResponse,
    llm_client_factory=None,
) -> ExplanationResponse:
    """对解释 DTO 进行 LLM 自然语言润色。失败安全降级为原文。"""
    if not get_llm_polish_enabled():
        return response

    llm_cfg = get_llm_config()
    if not llm_cfg.get("llm_api_key"):
        return response

    items = _collect_polish_items(response)
    if not items:
        return response

    polished_map = _call_llm_polish(items, llm_cfg, llm_client_factory)
    if not polished_map:
        return response

    return _apply_polished_texts(response, polished_map)


def _collect_polish_items(response: ExplanationResponse) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for ne in response.node_explanations:
        items.append({"key": f"node:{ne.node_id}", "text": ne.reason})
    for se in response.stage_explanations:
        base = se.rationale or "、".join(se.reasons)
        if base:
            items.append({"key": f"stage:{se.node_id}", "text": base})
    return items


def _call_llm_polish(
    items: list[dict[str, str]],
    llm_cfg: dict[str, str],
    llm_client_factory,
) -> dict[str, str]:
    try:
        if llm_client_factory is None:
            from openai import OpenAI
            client = OpenAI(
                api_key=llm_cfg["llm_api_key"],
                base_url=llm_cfg.get("llm_base_url", "https://api.openai.com/v1"),
                timeout=POLISH_TIMEOUT_SECONDS,
            )
        else:
            client = llm_client_factory(llm_cfg)

        payload = json.dumps(items, ensure_ascii=False)
        response = client.chat.completions.create(
            model=llm_cfg.get("llm_model", "gpt-3.5-turbo"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是教育路径解释润色器。对输入 JSON 数组中的每一项 `text` "
                        "改写为通顺自然的中文解释，保留原意与数值/因子名，不引入未提供的事实。"
                        "每条 ≤ 80 字。只返回 JSON 数组，格式 [{\"key\":\"...\",\"text\":\"...\"}]。"
                    ),
                },
                {"role": "user", "content": payload},
            ],
            temperature=0.2,
            max_tokens=800,
        )

        content = response.choices[0].message.content.strip()
        parsed = json.loads(content)
        if not isinstance(parsed, list):
            return {}

        polished: dict[str, str] = {}
        for entry in parsed:
            key = entry.get("key")
            text = entry.get("text", "")
            if not key or not isinstance(text, str):
                continue
            if not text or len(text) > POLISH_MAX_LENGTH:
                continue
            polished[key] = text
        return polished
    except Exception as exc:
        logger.warning("LLM 解释润色失败，回落原文: %s", exc)
        return {}


def _apply_polished_texts(
    response: ExplanationResponse,
    polished: dict[str, str],
) -> ExplanationResponse:
    node_out: list[NodeExplanation] = []
    for ne in response.node_explanations:
        key = f"node:{ne.node_id}"
        if key in polished:
            node_out.append(ne.model_copy(update={
                "raw_reason": ne.reason,
                "reason": polished[key],
            }))
        else:
            node_out.append(ne)

    stage_out: list[StageExplanation] = []
    for se in response.stage_explanations:
        key = f"stage:{se.node_id}"
        if key in polished:
            original = se.rationale or "、".join(se.reasons)
            stage_out.append(se.model_copy(update={
                "raw_rationale": original,
                "rationale": polished[key],
            }))
        else:
            stage_out.append(se)

    return response.model_copy(update={
        "node_explanations": node_out,
        "stage_explanations": stage_out,
    })
