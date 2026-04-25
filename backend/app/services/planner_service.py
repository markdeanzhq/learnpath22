"""规划服务：串联完整规划流程"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.planner.audit import build_plan_audit
from app.planner.budget import calc_budget_summary
from app.planner.closure import extract_subgraph, get_prerequisite_closure
from app.planner.renderer import render_path_text
from app.planner.scoring import compute_goal_relevance, select_profile_reinforcements
from app.planner.staging import build_stage_plan
from app.planner.topology import topo_sort_with_profile_priority
from app.schemas.project import validate_path_mode
from app.services.domain_pack_service import DomainPackService
from app.services.goal_service import UnsupportedGoalTypeError, resolve_goal


def build_filtered_graph(
    pack: DomainPackService,
    removed_node_ids: set[str] | None = None,
    removed_edge_ids: set[str] | None = None,
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    removed_nodes = removed_node_ids or set()
    removed_edges = removed_edge_ids or set()

    filtered_adj: dict[str, list[str]] = {}
    filtered_rev_adj: dict[str, list[str]] = {}

    for src, tgts in pack.requires_adj.items():
        if src in removed_nodes:
            continue
        filtered_adj[src] = [
            tgt for tgt in tgts
            if tgt not in removed_nodes and f"{src}->{tgt}::REQUIRES" not in removed_edges
        ]

    for tgt, srcs in pack.requires_rev_adj.items():
        if tgt in removed_nodes:
            continue
        filtered_rev_adj[tgt] = [
            src for src in srcs
            if src not in removed_nodes and f"{src}->{tgt}::REQUIRES" not in removed_edges
        ]

    return filtered_adj, filtered_rev_adj


def _node_hours(pack: DomainPackService, node_ids: list[str]) -> float:
    return round(sum(pack.nodes_by_id[nid]["estimated_hours"] for nid in node_ids), 1)


def _mode_adjusted_goal_mode(goal_mode: str, path_mode: str) -> str:
    if path_mode == "theory_first":
        return "steady"
    if path_mode == "practice_first":
        return "practice"
    return goal_mode


def _build_included_nodes(node_ids: list[str], required_ids: set[str]) -> list[dict[str, Any]]:
    return [
        {
            "node_id": node_id,
            "reason": "required_closure" if node_id in required_ids else "optional_reinforcement",
        }
        for node_id in node_ids
    ]


def _build_excluded_nodes(
    optional_ids: set[str],
    included_ids: set[str],
    path_mode: str,
) -> list[dict[str, Any]]:
    if path_mode != "compressed":
        return []
    return [
        {"node_id": node_id, "exclusion_reason": "compressed_optional_reinforcement"}
        for node_id in sorted(optional_ids - included_ids)
    ]


def plan_with_profile(
    goal_text: str,
    goal_type: str | None,
    profile: dict[str, Any],
    pack: DomainPackService,
    removed_node_ids: set[str] | None = None,
    removed_edge_ids: set[str] | None = None,
    confirmed_goal_result: dict[str, Any] | None = None,
    path_mode: str = "standard",
) -> dict[str, Any]:
    path_mode = validate_path_mode(path_mode)
    scoring_config = pack.scoring_config
    stage_rules = pack.stage_rules
    
    removed_nodes = removed_node_ids or set()
    removed_edges = removed_edge_ids or set()

    # 1. 目标解析
    if confirmed_goal_result is None:
        goal_result = resolve_goal(
            goal_text=goal_text,
            goal_type_override=goal_type,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types if pack.contract is not None else (),
            default_goal_policy=pack.contract.default_goal_policy if pack.contract is not None else None,
        )
    else:
        goal_result = deepcopy(confirmed_goal_result)
        goal_result.setdefault("goal_text", goal_text)
        goal_result.setdefault("goal_type", goal_type or "domain")
        goal_result.setdefault("mode", "steady")
        goal_result.setdefault("description", goal_text)
        goal_result.setdefault("template_id", None)
        goal_result.setdefault("resolve_source", "confirmed")
        goal_result.setdefault("source_breakdown", {})
        goal_result.setdefault("score_breakdown", {})
        goal_result.setdefault("warnings", [])
        goal_result["target_node_ids"] = list(goal_result.get("target_node_ids") or [])

    confirmed_target_node_ids = list(
        goal_result.get("confirmed_target_node_ids") or goal_result.get("target_node_ids") or []
    )
    visible_node_ids = set(pack.nodes_by_id)
    target_node_ids = [
        nid for nid in confirmed_target_node_ids
        if nid in visible_node_ids and nid not in removed_nodes
    ]
    # legacy 场景的默认目标只能来自 pack-owned policy；confirmed 场景必须显式暴露空 effective targets
    if not target_node_ids and confirmed_goal_result is None:
        goal_type_label = goal_result.get("goal_type")
        raise UnsupportedGoalTypeError(
            "No effective target nodes available for "
            f"goal_type={goal_type_label} after applying pack default policy"
        )

    goal_result["confirmed_target_node_ids"] = confirmed_target_node_ids
    goal_result["effective_target_node_ids"] = list(target_node_ids)
    goal_result["target_node_ids"] = target_node_ids
    goal_result["path_mode"] = path_mode
    mode = _mode_adjusted_goal_mode(goal_result["mode"], path_mode)
    goal_type_resolved = goal_result["goal_type"]

    filtered_adj, filtered_rev_adj = build_filtered_graph(
        pack,
        removed_node_ids=removed_nodes,
        removed_edge_ids=removed_edges,
    )

    # 2. 前置闭包
    closure_ids = get_prerequisite_closure(target_node_ids, filtered_rev_adj)

    # 3. 画像补强
    # 过滤掉被移除的候选节点
    candidates_by_id = {
        nid: n for nid, n in pack.nodes_by_id.items() 
        if nid not in removed_nodes
    }

    reinforced_ids, reinforcement_logs = select_profile_reinforcements(
        nodes_by_id=candidates_by_id,
        target_node_ids=target_node_ids,
        closure_ids=closure_ids,
        profile=profile,
        config=scoring_config,
    )
    reinforced_closure_ids = get_prerequisite_closure(reinforced_ids, filtered_rev_adj)

    required_ids = set(closure_ids) | set(target_node_ids)
    optional_ids = set(reinforced_ids) | set(reinforced_closure_ids)
    if path_mode == "compressed":
        final_ids = sorted(required_ids)
        reinforced_ids = [node_id for node_id in reinforced_ids if node_id in required_ids]
        reinforcement_logs = {
            node_id: log
            for node_id, log in reinforcement_logs.items()
            if node_id in required_ids
        }
    else:
        final_ids = sorted(required_ids | optional_ids)

    # 4. 子图提取
    sub_adj, indegree = extract_subgraph(final_ids, filtered_adj)

    # 5. 目标相关度
    goal_relevance_map = compute_goal_relevance(
        final_ids, target_node_ids, filtered_adj
    )

    # 6. 拓扑排序
    ordered_ids, ordering_logs = topo_sort_with_profile_priority(
        sub_adj=sub_adj,
        indegree=indegree,
        nodes_by_id=candidates_by_id,
        profile=profile,
        goal_relevance_map=goal_relevance_map,
        mode=mode,
        config=scoring_config,
    )

    # 7. 阶段划分
    stage_plan, stage_logs = build_stage_plan(
        ordered_ids=ordered_ids,
        nodes_by_id=candidates_by_id,
        profile=profile,
        goal_type=goal_type_resolved,
        stage_rules=stage_rules,
        scoring_config=scoring_config,
    )

    # 8. 时间预算
    planned_hours = _node_hours(pack, ordered_ids)
    required_hours = _node_hours(pack, sorted(required_ids))
    budget_summary = calc_budget_summary(profile, planned_hours)
    if (
        path_mode == "compressed"
        and budget_summary["status"] != "feasible"
        and required_hours > budget_summary["available_hours"]
    ):
        budget_summary["status"] = "over_budget_required_closure"
        budget_summary["suggestion"] = "目标及硬前置依赖已超出预算，不能裁剪硬依赖链"
    budget_summary["path_mode"] = path_mode
    budget_summary["required_hours"] = required_hours

    included_nodes = _build_included_nodes(ordered_ids, required_ids)
    excluded_nodes = _build_excluded_nodes(optional_ids, set(ordered_ids), path_mode)

    # 9. 审计日志
    audit = build_plan_audit(
        goal_result=goal_result,
        profile=profile,
        budget_summary=budget_summary,
        reinforcement_logs=reinforcement_logs,
        ordering_logs=ordering_logs,
        stage_logs=stage_logs,
        removed_node_ids=sorted(removed_nodes),
        removed_edge_ids=sorted(removed_edges),
        filtered_requires_adj=filtered_adj,
        filtered_requires_rev_adj=filtered_rev_adj,
        pack_version=pack.manifest.get("version"),
        project_graph_hash=getattr(pack, "project_graph_hash", None),
        overlay_lineage=getattr(pack, "overlay_lineage", None),
        closure_ids=sorted(closure_ids),
        reinforced_ids=sorted(reinforced_ids),
        final_ids=sorted(final_ids),
        path_mode=path_mode,
        ordering_mode=mode,
        budget_status=budget_summary["status"],
        included_nodes=included_nodes,
        excluded_nodes=excluded_nodes,
    )

    # 10. 文本渲染
    text_output = render_path_text(stage_plan, budget_summary, reinforced_ids)

    return {
        "goal_result": goal_result,
        "ordered_ids": ordered_ids,
        "stage_plan": stage_plan,
        "reinforced_ids": reinforced_ids,
        "budget_summary": budget_summary,
        "audit": audit,
        "text_output": text_output,
        "total_hours": planned_hours,
        "node_count": len(ordered_ids),
        "path_mode": path_mode,
    }
