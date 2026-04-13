"""规划服务：串联完整规划流程"""
from __future__ import annotations

from typing import Any

from app.planner.audit import build_plan_audit
from app.planner.budget import calc_budget_summary
from app.planner.closure import extract_subgraph, get_prerequisite_closure
from app.planner.renderer import render_path_text
from app.planner.scoring import compute_goal_relevance, select_profile_reinforcements
from app.planner.staging import build_stage_plan
from app.planner.topology import topo_sort_with_profile_priority
from app.services.domain_pack_service import DomainPackService
from app.services.goal_service import resolve_goal


def plan_with_profile(
    goal_text: str,
    goal_type: str | None,
    profile: dict[str, Any],
    pack: DomainPackService,
    removed_node_ids: set[str] | None = None,
    removed_edge_ids: set[str] | None = None,
) -> dict[str, Any]:
    scoring_config = pack.scoring_config
    stage_rules = pack.stage_rules
    
    removed_nodes = removed_node_ids or set()
    removed_edges = removed_edge_ids or set()

    # 1. 目标解析
    goal_result = resolve_goal(
        goal_text=goal_text,
        goal_type_override=goal_type,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
    )

    # 过滤掉被移除的目标节点
    target_node_ids = [
        nid for nid in goal_result["target_node_ids"] 
        if nid not in removed_nodes
    ]
    # 如果目标节点全被删了，回退到默认
    if not target_node_ids:
        target_node_ids = ["ml_c09", "ml_d08", "ml_e03"]
        target_node_ids = [nid for nid in target_node_ids if nid not in removed_nodes]

    goal_result["target_node_ids"] = target_node_ids
    mode = goal_result["mode"]
    goal_type_resolved = goal_result["goal_type"]

    # 过滤邻接表
    filtered_rev_adj = {}
    for tgt, srcs in pack.requires_rev_adj.items():
        if tgt in removed_nodes:
            continue
        filtered_rev_adj[tgt] = [
            s for s in srcs
            if s not in removed_nodes and f"{s}->{tgt}::REQUIRES" not in removed_edges
        ]

    filtered_adj = {}
    for src, tgts in pack.requires_adj.items():
        if src in removed_nodes:
            continue
        filtered_adj[src] = [
            t for t in tgts
            if t not in removed_nodes and f"{src}->{t}::REQUIRES" not in removed_edges
        ]

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

    final_ids = list(set(closure_ids + target_node_ids + reinforced_ids))

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
    planned_hours = round(
        sum(pack.nodes_by_id[nid]["estimated_hours"] for nid in ordered_ids), 1
    )
    budget_summary = calc_budget_summary(profile, planned_hours)

    # 9. 审计日志
    audit = build_plan_audit(
        goal_result=goal_result,
        profile=profile,
        budget_summary=budget_summary,
        reinforcement_logs=reinforcement_logs,
        ordering_logs=ordering_logs,
        stage_logs=stage_logs,
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
    }
