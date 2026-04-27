"""重规划服务：支持进度感知模式和画像更新模式"""
from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
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
from app.schemas.project import validate_path_mode
from app.services.formal_path_audit_service import enrich_formal_path_audit
from app.services.goal_service import UnsupportedGoalTypeError
from app.services.planner_service import build_filtered_graph, plan_with_profile
from app.services.project_graph_snapshot_service import build_project_graph_snapshot


def _profile_row_to_dict(profile_row: Any) -> dict[str, Any]:
    return {
        "math_level": profile_row.math_level,
        "coding_level": profile_row.coding_level,
        "ml_level": profile_row.ml_level,
        "theory_weight": profile_row.theory_weight,
        "weekly_hours": profile_row.weekly_hours,
        "deadline_weeks": profile_row.deadline_weeks,
        "path_mode_preference": profile_row.path_mode_preference,
        "persona_label": profile_row.persona_label,
        "persona_summary": profile_row.persona_summary,
        "persona_evidence": profile_row.persona_evidence,
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
        "path_mode_preference": snapshot.get("path_mode_preference"),
        "persona_label": snapshot.get("persona_label"),
        "persona_summary": snapshot.get("persona_summary"),
        "persona_evidence": snapshot.get("persona_evidence"),
    }


def _load_json_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str) and item]


def _load_json_dict(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _build_confirmed_goal_result(project: Any) -> dict[str, Any] | None:
    confirmed_target_node_ids = _load_json_list(getattr(project, "confirmed_target_node_ids_json", None))
    if not confirmed_target_node_ids:
        return None
    return {
        "goal_text": project.goal_text,
        "goal_type": project.goal_type,
        "target_node_ids": list(confirmed_target_node_ids),
        "confirmed_target_node_ids": list(confirmed_target_node_ids),
        "effective_target_node_ids": list(confirmed_target_node_ids),
        "mode": getattr(project, "confirmed_mode", None) or "steady",
        "description": getattr(project, "confirmed_description", None) or project.goal_text,
        "template_id": getattr(project, "confirmed_template_id", None),
        "resolve_source": getattr(project, "confirmed_resolve_source", None) or "confirmed",
        "candidate_id": getattr(project, "confirmed_candidate_id", None),
        "selected_candidate_id": getattr(project, "confirmed_candidate_id", None),
        "recommended_candidate_id": getattr(project, "confirmed_candidate_id", None),
        "requested_goal_type": getattr(project, "requested_goal_type", None),
        "auto_detected_goal_type": getattr(project, "auto_detected_goal_type", None),
        "effective_goal_type": project.goal_type,
        "goal_type_source": "confirmed_resolution",
        "source_breakdown": _load_json_dict(getattr(project, "confirmed_source_breakdown_json", None)),
        "score_breakdown": {},
        "warnings": [],
    }


def _apply_goal_target_effects(
    goal_result: dict[str, Any],
    removed_node_ids: set[str],
    visible_node_ids: set[str] | None = None,
) -> dict[str, Any]:
    updated_goal_result = deepcopy(goal_result)
    confirmed_target_node_ids = list(
        updated_goal_result.get("confirmed_target_node_ids") or updated_goal_result.get("target_node_ids") or []
    )
    if visible_node_ids is None:
        effective_target_node_ids = [nid for nid in confirmed_target_node_ids if nid not in removed_node_ids]
    else:
        effective_target_node_ids = [
            nid for nid in confirmed_target_node_ids
            if nid in visible_node_ids and nid not in removed_node_ids
        ]
    updated_goal_result["confirmed_target_node_ids"] = confirmed_target_node_ids
    updated_goal_result["effective_target_node_ids"] = effective_target_node_ids
    updated_goal_result["target_node_ids"] = effective_target_node_ids
    updated_goal_result.setdefault("selected_candidate_id", updated_goal_result.get("candidate_id"))
    updated_goal_result.setdefault("source_breakdown", {})
    updated_goal_result.setdefault("score_breakdown", {})
    updated_goal_result.setdefault("goal_type_source", "confirmed_resolution")
    return updated_goal_result


async def replan(
    db: AsyncSession,
    project_id: str,
    mode: str = "profile_update",
    path_mode: str | None = None,
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if not project:
        raise ValueError("项目不存在")
    path_mode = validate_path_mode(path_mode or getattr(project, "path_mode", None))
    project.path_mode = path_mode

    latest_profile_row = await get_latest_profile(db, project_id)
    latest_profile = _profile_row_to_dict(latest_profile_row) if latest_profile_row else None

    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)
    removed_nodes = snapshot.removed_node_ids
    removed_edges = snapshot.removed_edge_ids

    confirmed_goal_result = _build_confirmed_goal_result(project)

    if mode == "progress_aware":
        try:
            result = await _replan_progress_aware(
                db,
                project,
                latest_profile,
                snapshot,
                removed_nodes,
                removed_edges,
                confirmed_goal_result=confirmed_goal_result,
                path_mode=path_mode,
            )
        except UnsupportedGoalTypeError as exc:
            raise AppError(code=409, message="GOAL_DEFAULT_TARGETS_UNAVAILABLE", details={"reason": str(exc)}) from exc
    else:
        if not latest_profile:
            raise ValueError("请先提交画像")
        try:
            result = await _replan_profile_update(
                db,
                project,
                latest_profile,
                snapshot,
                removed_nodes,
                removed_edges,
                confirmed_goal_result=confirmed_goal_result,
                path_mode=path_mode,
            )
        except UnsupportedGoalTypeError as exc:
            raise AppError(code=409, message="GOAL_DEFAULT_TARGETS_UNAVAILABLE", details={"reason": str(exc)}) from exc

    if confirmed_goal_result and not result["plan_result"]["goal_result"]["target_node_ids"]:
        raise AppError(code=409, message="GOAL_TARGETS_REMOVED")
    await enrich_formal_path_audit(db, project=project, plan_result=result["plan_result"])

    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, result["plan_result"], version=version)

    return {
        "path_id": path.id,
        "version": path.version,
        "plan_result": result["plan_result"],
        "diff": result.get("diff"),
        "mode": mode,
        "snapshot": snapshot,
    }


async def _replan_profile_update(
    db: AsyncSession,
    project: Any,
    profile: dict[str, Any],
    pack: Any,
    removed_node_ids: set[str],
    removed_edge_ids: set[str],
    confirmed_goal_result: dict[str, Any] | None = None,
    path_mode: str = "standard",
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
        confirmed_goal_result=deepcopy(confirmed_goal_result) if confirmed_goal_result else None,
        path_mode=path_mode,
    )

    new_node_ids = set(plan_result["ordered_ids"])

    diff = {
        "added": sorted(new_node_ids - old_node_ids),
        "removed": sorted(old_node_ids - new_node_ids),
        "unchanged": sorted(new_node_ids & old_node_ids),
    }

    return {"plan_result": plan_result, "diff": diff}


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
    confirmed_goal_result: dict[str, Any] | None = None,
    path_mode: str = "standard",
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
        confirmed_goal_result=deepcopy(confirmed_goal_result) if confirmed_goal_result else None,
        path_mode=path_mode,
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

    filtered_adj, filtered_rev_adj = build_filtered_graph(
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
    budget_summary["path_mode"] = path_mode
    reinforcement_logs = {
        nid: log
        for nid, log in full_plan["audit"].get("reinforcement_logs", {}).items()
        if nid in pending_ids
    }
    audit_goal_result = _apply_goal_target_effects(
        full_plan["goal_result"],
        removed_node_ids,
        set(pack.nodes_by_id),
    )
    audit_goal_result["effective_target_node_ids"] = pending_target_ids
    audit_goal_result["target_node_ids"] = pending_target_ids

    audit = build_plan_audit(
        goal_result=audit_goal_result,
        profile=profile,
        budget_summary=budget_summary,
        reinforcement_logs=reinforcement_logs,
        ordering_logs=ordering_logs,
        stage_logs=stage_logs,
        removed_node_ids=sorted(removed_node_ids),
        removed_edge_ids=sorted(removed_edge_ids),
        filtered_requires_adj=filtered_adj,
        filtered_requires_rev_adj=filtered_rev_adj,
        pack_version=pack.manifest.get("version"),
        project_graph_hash=getattr(pack, "project_graph_hash", None),
        overlay_lineage=getattr(pack, "overlay_lineage", None),
        closure_ids=sorted(full_plan["audit"].get("closure_ids", [])),
        reinforced_ids=sorted(pending_reinforced_ids),
        final_ids=sorted(pending_ordered_ids),
        path_mode=path_mode,
        ordering_mode=(
            full_plan["audit"].get("ordering_mode")
            or full_plan["goal_result"].get("mode")
        ),
        budget_status=budget_summary["status"],
        included_nodes=[
            {"node_id": node_id, "reason": "remaining_after_progress_filter"}
            for node_id in pending_ordered_ids
        ],
        excluded_nodes=[
            {"node_id": node_id, "exclusion_reason": "progress_completed"}
            for node_id in sorted(completed_ids)
        ] + [
            {"node_id": node_id, "exclusion_reason": "progress_skipped"}
            for node_id in sorted(skipped_ids)
        ],
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
        "path_mode": path_mode,
    }

    diff = {
        "completed": sorted(completed_ids),
        "skipped": sorted(skipped_ids),
        "pending": sorted(pending_ordered_ids),
    }

    return {"plan_result": plan_result, "diff": diff}
