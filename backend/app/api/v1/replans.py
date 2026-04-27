"""重规划 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.plans import _dict_stages_to_list
from app.core.exceptions import AppError, NotFoundError
from app.repositories.project_repository import get_project
from app.schemas.goal_resolution import (
    FeedbackPreviewSessionResponse,
    KnownNodeConfirmationDraftResponse,
)
from app.schemas.tracking import ReplanRequest
from app.services.domain_pack_service import get_domain_pack_service
from app.services.feedback_replan_service import (
    confirm_feedback_replan,
    confirm_known_node_draft,
    preview_feedback_replan,
)
from app.services.replan_service import replan

router = APIRouter()


class FeedbackPreviewRequest(BaseModel):
    feedback_text: str = Field(min_length=1)


def _build_node_name_map(stage_plan: dict[str, list[dict]]) -> dict[str, str]:
    return {
        task["node_id"]: task["name"]
        for tasks in stage_plan.values()
        for task in tasks
        if task.get("node_id") and task.get("name")
    }


def _build_diff_details(
    diff: dict | None,
    node_name_map: dict[str, str],
    pack_node_names: dict[str, str],
) -> dict | None:
    if not diff:
        return None

    details: dict[str, list[dict[str, str]]] = {}
    for key, node_ids in diff.items():
        if not node_ids:
            continue
        details[key] = [
            {
                "node_id": node_id,
                "node_name": node_name_map.get(node_id) or pack_node_names.get(node_id) or node_id,
            }
            for node_id in node_ids
        ]
    return details


@router.post("/projects/{project_id}/replans")
async def trigger_replan(
    project_id: str,
    req: ReplanRequest,
    db: AsyncSession = Depends(get_db),
):
    """触发路径重规划。支持 progress_aware 和 profile_update 两种模式。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        if req.path_mode is None:
            result = await replan(db, project_id, mode=req.mode)
        else:
            result = await replan(db, project_id, mode=req.mode, path_mode=req.path_mode)
    except ValueError as e:
        if str(e) == "INVALID_PATH_MODE":
            raise AppError(code=422, message="INVALID_PATH_MODE") from e
        raise AppError(code=400, message=str(e)) from e

    plan_result = result["plan_result"]
    stages = _dict_stages_to_list(plan_result["stage_plan"])
    node_name_map = _build_node_name_map(plan_result["stage_plan"])
    snapshot = result.get("snapshot")
    diff = result.get("diff")
    nodes_by_id = snapshot.nodes_by_id if snapshot is not None else get_domain_pack_service(project.domain).nodes_by_id
    snapshot_node_names = {nid: node["name"] for nid, node in nodes_by_id.items()}
    return {
        "id": result["path_id"],
        "version": result["version"],
        "mode": result["mode"],
        "stages": stages,
        "budget_status": plan_result["budget_summary"]["status"],
        "path_mode": plan_result.get("path_mode", req.path_mode or getattr(project, "path_mode", "standard")),
        "total_hours": plan_result["total_hours"],
        "diff": diff,
        "diff_details": _build_diff_details(diff, node_name_map, snapshot_node_names),
        "reason": req.reason,
    }


@router.post(
    "/projects/{project_id}/replans/feedback/preview",
    response_model=FeedbackPreviewSessionResponse,
)
async def preview_feedback_replan_endpoint(
    project_id: str,
    req: FeedbackPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    return await preview_feedback_replan(db, project_id=project_id, feedback_text=req.feedback_text)


@router.post(
    "/projects/{project_id}/replans/feedback/known-node-drafts/{draft_id}/confirm",
    response_model=KnownNodeConfirmationDraftResponse,
)
async def confirm_known_node_draft_endpoint(
    project_id: str,
    draft_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await confirm_known_node_draft(db, project_id=project_id, draft_id=draft_id)


@router.post("/projects/{project_id}/replans/feedback/{feedback_preview_id}/confirm")
async def confirm_feedback_replan_endpoint(
    project_id: str,
    feedback_preview_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await confirm_feedback_replan(db, project_id=project_id, feedback_preview_id=feedback_preview_id)
