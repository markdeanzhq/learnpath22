"""重规划服务：支持进度感知模式和画像更新模式"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.planner.audit import build_plan_audit
from app.planner.budget import calc_budget_summary
from app.planner.closure import extract_subgraph
from app.planner.renderer import render_path_text
from app.planner.scoring import compute_goal_relevance
from app.planner.staging import build_stage_plan
from app.planner.topology import topo_sort_with_profile_priority
from app.repositories.plan_repository import get_latest_plan, get_plan_version_count, save_plan
from app.repositories.profile_repository import get_latest_profile
from app.repositories.project_repository import get_project
from app.repositories.tracking_repository import get_latest_event_per_node
from app.repositories.graph_review_repository import get_removed_node_ids, get_removed_edge_ids
from app.services.domain_pack_service import get_domain_pack_service
from app.services.planner_service import plan_with_profile


def _profile_row_to_dict(profile_row: Any) -> dict[str, Any]:
    return {
        "math_level": profile_row.math_level,
        "coding_level": profile_row.coding_level,
        "ml_level": profile_row.ml_level,
        "theory_weight": profile_row.theory_weight,
        "weekly_hours": profile_row.weekly_hours,
        "deadline_weeks": profile_row.deadline_weeks,
    }


def _profile_snapshot_to_dict(snapshot: dict[str, Any] | None) -> dict[str, Any] | None:
    if not snapshot:
        return None
    theory_weight = snapshot.get("theory_weight")
    practice_weight = snapshot.get("practice_weight")
    if theory_weight is None and practice_weight is not None:
        theory_weight = 1.0 - practice_weight
    return {
        "math_level": snapshot.get("math_level"),
        "coding_level": snapshot.get("coding_level"),
        "ml_level": snapshot.get("ml_level"),
        "theory_weight": theory_weight,
        "weekly_hours": snapshot.get("weekly_hours"),
        "deadline_weeks": snapshot.get("deadline_weeks"),
    }


async def replan(
    db: AsyncSession,
    project_id: str,
    mode: str = "profile_update",
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if not project:
        raise ValueError("项目不存在")

    latest_profile_row = await get_latest_profile(db, project_id)
    latest_profile = _profile_row_to_dict(latest_profile_row) if latest_profile_row else None

    pack = get_domain_pack_service(project.domain)
    removed_nodes = await get_removed_node_ids(db, project_id)
    removed_edges = await get_removed_edge_ids(db, project_id)

    if mode == "progress_aware":
        result = await _replan_progress_aware(db, project, latest_profile, pack, removed_nodes, removed_edges)
    else:
        if not latest_profile:
            raise ValueError("请先提交画像")
        result = await _replan_profile_update(db, project, latest_profile, pack, removed_nodes, removed_edges)

    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, result["plan_result"], version=version)

    return {
        "path_id": path.id,
        "version": path.version,
        "plan_result": result["plan_result"],
        "diff": result.get("diff"),
        "mode": mode,
    }


async def _replan_profile_update(
    db: AsyncSession,
    project: Any,
    profile: dict[str, Any],
    pack: Any,
    removed_node_ids: set[str],
    removed_edge_ids: set[str],
) -> dict[str, Any]:
    """画像更新模式：全量重生成 + 与上一版 diff。"""
    old_plan = await get_latest_plan(db, project.id)
    old_node_ids: set[str] = set()
    if old_plan and old_plan.plan_json:
        old_stages = json.loads(old_plan.plan_json)
        if isinstance(old_stages, dict):
            for tasks in old_stages.values():
                old_node_ids.update(t["node_id"] for t in tasks)
        elif isinstance(old_stages, list):
            for stage in old_stages:
                old_node_ids.update(t["node_id"] for t in stage.get("tasks", []))

    plan_result = plan_with_profile(
        goal_text=project.goal_text,
        goal_type=project.goal_type,
        profile=profile,
        pack=pack,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
    )

    new_node_ids = set(plan_result["ordered_ids"])

    diff = {
        "added": sorted(new_node_ids - old_node_ids),
        "removed": sorted(old_node_ids - new_node_ids),
        "unchanged": sorted(new_node_ids & old_node_ids),
    }

    return {"plan_result": plan_result, "diff": diff}


def _build_filtered_graph(
    pack: Any,
    removed_node_ids: set[str],
    removed_edge_ids: set[str],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    filtered_adj: dict[str, list[str]] = {}
    filtered_rev_adj: dict[str, list[str]] = {}

    for src, tgts in pack.requires_adj.items():
        if src in removed_node_ids:
            continue
        valid_targets = [
            tgt for tgt in tgts
            if tgt not in removed_node_ids and f"{src}->{tgt}" not in removed_edge_ids
        ]
        filtered_adj[src] = valid_targets

    for tgt, srcs in pack.requires_rev_adj.items():
        if tgt in removed_node_ids:
            continue
        valid_sources = [
            src for src in srcs
            if src not in removed_node_ids and f"{src}->{tgt}" not in removed_edge_ids
        ]
        filtered_rev_adj[tgt] = valid_sources

    return filtered_adj, filtered_rev_adj


def _resolve_pending_node_ids(
    candidate_ids: set[str],
    satisfied_ids: set[str],
    excluded_ids: set[str],
    requires_rev_adj: dict[str, list[str]],
) -> set[str]:
    pending_ids = set(candidate_ids)

    changed = True
    while changed:
        changed = False
        for nid in list(pending_ids):
            prereqs = requires_rev_adj.get(nid, [])
            if any(prereq in excluded_ids for prereq in prereqs):
                pending_ids.remove(nid)
                changed = True
                continue
            if any(prereq not in pending_ids and prereq not in satisfied_ids for prereq in prereqs):
                pending_ids.remove(nid)
                changed = True

    return pending_ids


async def _replan_progress_aware(
    db: AsyncSession,
    project: Any,
    latest_profile: dict[str, Any] | None,
    pack: Any,
    removed_node_ids: set[str],
    removed_edge_ids: set[str],
) -> dict[str, Any]:
    """进度感知模式：锁定已完成节点，跳过 skipped，仅重规划 pending。"""
    node_status = await get_latest_event_per_node(db, project.id)
    old_plan = await get_latest_plan(db, project.id)
    if not old_plan or not old_plan.audit_json:
        if not latest_profile:
            raise ValueError("请先提交画像")
        profile = latest_profile
    else:
        old_audit = json.loads(old_plan.audit_json)
        profile = _profile_snapshot_to_dict(old_audit.get("profile_snapshot"))
        if not profile:
            if not latest_profile:
                raise ValueError("请先提交画像")
            profile = latest_profile

    full_plan = plan_with_profile(
        goal_text=project.goal_text,
        goal_type=project.goal_type,
        profile=profile,
        pack=pack,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
    )

    plan_node_ids = set(full_plan["ordered_ids"])
    completed_ids = {
        nid for nid, st in node_status.items()
        if st == "complete" and nid in plan_node_ids and nid not in removed_node_ids
    }
    skipped_ids = {
        nid for nid, st in node_status.items()
        if st == "skip" and nid in plan_node_ids and nid not in removed_node_ids
    }

    filtered_adj, filtered_rev_adj = _build_filtered_graph(
        pack,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
    )

    candidate_ids = plan_node_ids - completed_ids - skipped_ids
    pending_ids = _resolve_pending_node_ids(
        candidate_ids=candidate_ids,
        satisfied_ids=completed_ids,
        excluded_ids=skipped_ids | removed_node_ids,
        requires_rev_adj=filtered_rev_adj,
    )

    pending_target_ids = [
        nid for nid in full_plan["goal_result"]["target_node_ids"]
        if nid in pending_ids
    ]

    sub_adj, indegree = extract_subgraph(list(pending_ids), filtered_adj)
    goal_relevance_map = compute_goal_relevance(
        list(pending_ids), pending_target_ids, filtered_adj
    )
    pending_ordered_ids, ordering_logs = topo_sort_with_profile_priority(
        sub_adj=sub_adj,
        indegree=indegree,
        nodes_by_id=pack.nodes_by_id,
        profile=profile,
        goal_relevance_map=goal_relevance_map,
        mode=full_plan["goal_result"]["mode"],
        config=pack.scoring_config,
    )
    pending_stage_plan, stage_logs = build_stage_plan(
        ordered_ids=pending_ordered_ids,
        nodes_by_id=pack.nodes_by_id,
        profile=profile,
        goal_type=full_plan["goal_result"]["goal_type"],
        stage_rules=pack.stage_rules,
        scoring_config=pack.scoring_config,
    )

    pending_reinforced_ids = [
        nid for nid in full_plan["reinforced_ids"] if nid in pending_ids
    ]
    total_hours = round(
        sum(pack.nodes_by_id[nid]["estimated_hours"] for nid in pending_ordered_ids), 1
    )
    budget_summary = calc_budget_summary(profile, total_hours)
    reinforcement_logs = {
        nid: log
        for nid, log in full_plan["audit"].get("reinforcement_logs", {}).items()
        if nid in pending_ids
    }
    audit = build_plan_audit(
        goal_result={
            **full_plan["goal_result"],
            "target_node_ids": pending_target_ids,
        },
        profile=profile,
        budget_summary=budget_summary,
        reinforcement_logs=reinforcement_logs,
        ordering_logs=ordering_logs,
        stage_logs=stage_logs,
    )

    plan_result = {
        **full_plan,
        "goal_result": audit["goal_result"],
        "ordered_ids": pending_ordered_ids,
        "stage_plan": pending_stage_plan,
        "reinforced_ids": pending_reinforced_ids,
        "budget_summary": budget_summary,
        "audit": audit,
        "text_output": render_path_text(
            pending_stage_plan, budget_summary, pending_reinforced_ids
        ),
        "total_hours": total_hours,
        "node_count": len(pending_ordered_ids),
    }

    diff = {
        "completed": sorted(completed_ids),
        "skipped": sorted(skipped_ids),
        "pending": sorted(pending_ordered_ids),
    }

    return {"plan_result": plan_result, "diff": diff}
