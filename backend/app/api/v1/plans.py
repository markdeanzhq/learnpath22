"""路径规划 API"""
import json
from copy import deepcopy
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError, NotFoundError
from app.repositories.explanation_cache_repository import (
    get_explanation_cache,
    upsert_explanation_cache,
)
from app.repositories.plan_repository import (
    get_latest_plan,
    get_plan_version_count,
    save_plan,
)
from app.repositories.profile_repository import get_latest_profile
from app.repositories.project_repository import get_project
from app.schemas.explanation import (
    ExplanationAskRequest,
    ExplanationAskResponse,
    ExplanationResponse,
)
from app.schemas.project import validate_path_mode
from app.services.domain_pack_service import get_domain_pack_service
from app.services.explanation_service import (
    answer_explanation_question,
    build_explanation,
    polish_explanation,
)
from app.services.goal_service import UnsupportedGoalTypeError
from app.services.planner_service import plan_with_profile
from app.services.project_graph_snapshot_service import build_project_graph_snapshot

router = APIRouter()


class GeneratePlanRequest(BaseModel):
    path_mode: str | None = None


def _validate_path_mode_or_raise(path_mode: str | None) -> str:
    try:
        return validate_path_mode(path_mode)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_PATH_MODE") from exc


def _dict_stages_to_list(stage_dict: dict) -> list[dict]:
    """将 {阶段名: [tasks]} 转换为 [{stage_index, stage_name, tasks, estimated_hours}]"""
    result = []
    for idx, (name, tasks) in enumerate(stage_dict.items()):
        result.append({
            "stage_index": idx,
            "stage_name": name,
            "tasks": tasks,
            "estimated_hours": sum(t.get("estimated_hours", 0) for t in tasks),
        })
    return result


def _load_plan_stages(plan_json: str | None) -> list[dict[str, Any]]:
    raw_stages = json.loads(plan_json) if plan_json else {}
    if isinstance(raw_stages, dict):
        return _dict_stages_to_list(raw_stages)
    return raw_stages if isinstance(raw_stages, list) else []


def _build_explanation_nodes_by_id(
    pack,
    audit: dict[str, Any],
    stages: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    nodes_by_id = dict(pack.nodes_by_id)
    fallback_reasons: list[str] = []
    live_pack_fields: list[str] = []
    planned_node_ids: set[str] = set()

    for stage in stages:
        for task in stage.get("tasks", []):
            if not isinstance(task, dict) or not task.get("node_id"):
                continue
            node_id = task["node_id"]
            planned_node_ids.add(node_id)
            snapshot_node = dict(nodes_by_id.get(node_id, {"id": node_id}))
            if task.get("name"):
                snapshot_node["name"] = task["name"]
            if task.get("difficulty") is not None:
                snapshot_node["difficulty_final"] = task["difficulty"]
            if task.get("importance") is not None:
                snapshot_node["importance_final"] = task["importance"]
            if task.get("estimated_hours") is not None:
                snapshot_node["estimated_hours"] = task["estimated_hours"]
            nodes_by_id[node_id] = snapshot_node

    for node_id in audit.get("ordering_logs", {}):
        if node_id not in planned_node_ids:
            fallback_reasons.append(f"node_snapshot_missing:{node_id}")
            live_pack_fields.append("nodes_by_id")

    overlay_lineage = audit.get("overlay_lineage")
    overlay_nodes = (
        overlay_lineage.get("nodes")
        if isinstance(overlay_lineage, dict) and isinstance(overlay_lineage.get("nodes"), dict)
        else {}
    )
    for node_id, lineage in overlay_nodes.items():
        node_snapshot = lineage.get("node_snapshot") if isinstance(lineage, dict) else None
        if isinstance(node_snapshot, dict):
            nodes_by_id[node_id] = dict(node_snapshot)

    if not isinstance(overlay_lineage, dict):
        fallback_reasons.append("overlay_lineage_missing")

    return nodes_by_id, {
        "fallback_reasons": fallback_reasons,
        "live_pack_fields": live_pack_fields,
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


def _build_confirmed_goal_result(project) -> dict[str, Any] | None:
    confirmed_target_node_ids = _load_json_list(project.confirmed_target_node_ids_json)
    if not confirmed_target_node_ids:
        return None
    return {
        "goal_text": project.goal_text,
        "goal_type": project.goal_type,
        "target_node_ids": list(confirmed_target_node_ids),
        "confirmed_target_node_ids": list(confirmed_target_node_ids),
        "effective_target_node_ids": list(confirmed_target_node_ids),
        "mode": project.confirmed_mode or "steady",
        "description": project.confirmed_description or project.goal_text,
        "template_id": project.confirmed_template_id,
        "resolve_source": project.confirmed_resolve_source or "confirmed",
        "candidate_id": project.confirmed_candidate_id,
        "selected_candidate_id": project.confirmed_candidate_id,
        "recommended_candidate_id": project.confirmed_candidate_id,
        "requested_goal_type": project.requested_goal_type,
        "auto_detected_goal_type": project.auto_detected_goal_type,
        "effective_goal_type": project.goal_type,
        "goal_type_source": "confirmed_resolution",
        "source_breakdown": _load_json_dict(project.confirmed_source_breakdown_json),
        "score_breakdown": {},
        "warnings": [],
    }


@router.post("/projects/{project_id}/plans")
async def generate_plan(
    project_id: str,
    req: GeneratePlanRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    profile_row = await get_latest_profile(db, project_id)
    if not profile_row:
        raise AppError(code=400, message="请先完成画像测评再生成路径")

    profile = {
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
    requested_path_mode = req.path_mode if req and req.path_mode is not None else None
    path_mode = _validate_path_mode_or_raise(
        requested_path_mode or getattr(project, "path_mode", None)
    )
    project.path_mode = path_mode

    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)

    confirmed_goal_result = _build_confirmed_goal_result(project)
    try:
        plan_result = plan_with_profile(
            goal_text=project.goal_text,
            goal_type=project.goal_type,
            profile=profile,
            pack=snapshot,
            removed_node_ids=snapshot.removed_node_ids,
            removed_edge_ids=snapshot.removed_edge_ids,
            confirmed_goal_result=deepcopy(confirmed_goal_result) if confirmed_goal_result else None,
            path_mode=path_mode,
        )
    except ValueError as exc:
        if str(exc) == "INVALID_PATH_MODE":
            raise AppError(code=422, message="INVALID_PATH_MODE") from exc
        raise
    except UnsupportedGoalTypeError as exc:
        raise AppError(code=409, message="GOAL_DEFAULT_TARGETS_UNAVAILABLE", details={"reason": str(exc)}) from exc

    if confirmed_goal_result and not plan_result["goal_result"]["target_node_ids"]:
        raise AppError(code=409, message="GOAL_TARGETS_REMOVED")

    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, plan_result, version=version)

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": _dict_stages_to_list(plan_result["stage_plan"]),
        "budget_status": plan_result["budget_summary"]["status"],
        "path_mode": plan_result.get("path_mode", path_mode),
        "total_hours": plan_result["total_hours"],
        "node_count": plan_result["node_count"],
        "reinforced_ids": plan_result["reinforced_ids"],
        "text_output": plan_result["text_output"],
    }


@router.get("/projects/{project_id}/plans/latest")
async def get_latest_plan_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径")

    stages = _load_plan_stages(path.plan_json)
    audit = json.loads(path.audit_json) if path.audit_json else None

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": stages,
        "budget_status": path.budget_status,
        "path_mode": (audit or {}).get("path_mode", "standard"),
        "total_hours": path.total_hours,
        "audit": audit,
    }


def _should_cache_explanation(response: ExplanationResponse, *, polish: bool) -> bool:
    if not polish:
        return True
    return response.meta is not None and response.meta.polish.applied


async def _build_latest_explanation_response(
    project_id: str,
    db: AsyncSession,
    *,
    polish: bool = False,
    use_cache: bool = True,
) -> tuple[ExplanationResponse, set[str]]:
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径")

    audit = json.loads(path.audit_json) if path.audit_json else None
    if not audit:
        raise NotFoundError("暂无审计数据")

    stages = _load_plan_stages(path.plan_json)
    latest_plan_node_ids = {
        task.get("node_id")
        for stage in stages
        for task in stage.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("node_id"), str)
    }
    if use_cache:
        cached = await get_explanation_cache(db, path_id=path.id, polish_requested=polish)
        if cached is not None:
            return ExplanationResponse.model_validate_json(cached.explanation_json), latest_plan_node_ids

    pack = get_domain_pack_service(project.domain)
    nodes_by_id, context = _build_explanation_nodes_by_id(pack, audit, stages)
    pack_version = audit.get("pack_version") or pack.manifest.get("version")
    context.update(
        {
            "plan_version": path.version,
            "stages": stages,
            "total_hours": path.total_hours,
            "budget_status": path.budget_status,
            "path_mode": audit.get("path_mode") or getattr(project, "path_mode", None) or "standard",
            "pack_version": str(pack_version) if pack_version is not None else None,
            "pack_version_source": "audit" if audit.get("pack_version") else "live_pack",
            "project_graph_hash": audit.get("project_graph_hash"),
            "project_graph_hash_source": "audit" if audit.get("project_graph_hash") else "missing",
        }
    )
    scoring_config = audit.get("scoring_config") if isinstance(audit.get("scoring_config"), dict) else pack.scoring_config
    if "scoring_config" not in audit:
        context.setdefault("fallback_reasons", []).append("scoring_config_missing")
        context.setdefault("live_pack_fields", []).append("scoring_config")
    response = build_explanation(
        audit,
        nodes_by_id,
        pack.requires_rev_adj,
        scoring_config,
        context=context,
    )
    response = polish_explanation(response, requested=polish)
    if _should_cache_explanation(response, polish=polish):
        await upsert_explanation_cache(
            db,
            project_id=project_id,
            path_id=path.id,
            plan_version=path.version,
            polish_requested=polish,
            explanation_json=response.model_dump_json(),
        )
    return response, latest_plan_node_ids


@router.get("/projects/{project_id}/explanation", response_model=ExplanationResponse)
async def get_explanation(
    project_id: str,
    polish: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """获取最新路径的结构化解释。`polish=true` 时只启用可选 LLM 自然语言润色。"""
    response, _latest_plan_node_ids = await _build_latest_explanation_response(project_id, db, polish=polish)
    return response


@router.post(
    "/projects/{project_id}/explanation/ask",
    response_model=ExplanationAskResponse,
)
async def ask_explanation(
    project_id: str,
    req: ExplanationAskRequest,
    db: AsyncSession = Depends(get_db),
):
    response, latest_plan_node_ids = await _build_latest_explanation_response(project_id, db, polish=False)
    return answer_explanation_question(
        response,
        req,
        latest_plan_node_ids=latest_plan_node_ids,
    )
