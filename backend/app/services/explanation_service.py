"""结构化路径解释服务：从 audit 数据生成可读解释"""
from __future__ import annotations

from typing import Any

from app.schemas.explanation import (
    BudgetExplanation,
    DependencyChainExplanation,
    ExplanationResponse,
    NodeExplanation,
    OrderExplanation,
    ReinforcementExplanation,
    StageExplanation,
)


def build_explanation(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> ExplanationResponse:
    node_explanations = _build_node_explanations(audit, nodes_by_id)
    ordering_explanations = _build_ordering_explanations(audit, nodes_by_id)
    stage_explanations = _build_stage_explanations(audit, nodes_by_id)
    budget_explanation = _build_budget_explanation(audit)
    reinforcement_explanations = _build_reinforcement_explanations(audit, nodes_by_id)
    dependency_chain_explanations = _build_dependency_chain_explanations(audit, nodes_by_id)

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


def _build_node_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[NodeExplanation]:
    results: list[NodeExplanation] = []
    goal = audit.get("goal_result", {})
    target_ids = set(goal.get("target_node_ids", []))

    ordering_logs = audit.get("ordering_logs", {})
    reinforcement_logs = audit.get("reinforcement_logs", {})

    for nid, log in ordering_logs.items():
        if nid in target_ids:
            reason = "目标节点：直接匹配学习目标"
            decision = "target"
        elif nid in reinforcement_logs:
            gap = reinforcement_logs[nid].get("gap", {})
            reason = f"画像补强：差距总分 {gap.get('gap_total', 0):.3f}，补充基础知识"
            decision = "reinforced"
        else:
            reason = "前置依赖：目标节点的必要前置知识"
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
) -> list[OrderExplanation]:
    results: list[OrderExplanation] = []
    ordering_logs = audit.get("ordering_logs", {})

    for nid, log in ordering_logs.items():
        score = log.get("priority_score", 0)
        relevance = log.get("goal_relevance", 0)

        factors = []
        if relevance > 0.7:
            factors.append("高目标相关度")
        if log.get("gap", {}).get("gap_total", 0) > 0.3:
            factors.append("存在能力差距")
        factors.extend(log.get("reasons", []))

        results.append(OrderExplanation(
            node_id=nid,
            node_name=_get_node_name(nid, nodes_by_id),
            priority_score=score,
            goal_relevance=relevance,
            factors=factors,
        ))

    return results


def _build_stage_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[StageExplanation]:
    results: list[StageExplanation] = []
    stage_logs = audit.get("stage_logs", {})

    for nid, log in stage_logs.items():
        results.append(StageExplanation(
            node_id=nid,
            node_name=_get_node_name(nid, nodes_by_id),
            assigned_stage=log.get("assigned_stage", ""),
            reasons=log.get("reasons", []),
        ))

    return results


def _build_budget_explanation(
    audit: dict[str, Any],
) -> BudgetExplanation | None:
    bs = audit.get("budget_summary")
    if not bs:
        return None

    return BudgetExplanation(
        total_hours=bs.get("total_hours", bs.get("planned_hours", 0)),
        weekly_hours=bs.get("weekly_hours", 0),
        estimated_weeks=bs.get("estimated_weeks", 0),
        status=bs.get("status", ""),
        suggestion=bs.get("suggestion", ""),
    )


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


def _build_dependency_chain_explanations(
    audit: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[DependencyChainExplanation]:
    results: list[DependencyChainExplanation] = []
    target_ids = audit.get("goal_result", {}).get("target_node_ids", [])
    ordering_logs = audit.get("ordering_logs", {})

    ordered_ids = list(ordering_logs.keys())
    for target_id in target_ids:
        if target_id not in ordered_ids:
            continue
        target_index = ordered_ids.index(target_id)
        chain_ids = ordered_ids[: target_index + 1]
        results.append(DependencyChainExplanation(
            target_node_id=target_id,
            target_node_name=_get_node_name(target_id, nodes_by_id),
            chain_node_ids=chain_ids,
            chain_node_names=[_get_node_name(nid, nodes_by_id) for nid in chain_ids],
            reason="该目标节点需要按当前学习顺序先掌握其前置依赖，再学习目标本身",
        ))

    return results
