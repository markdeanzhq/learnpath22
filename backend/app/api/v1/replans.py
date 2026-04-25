"""重规划 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.plans import _dict_stages_to_list
from app.core.exceptions import AppError, NotFoundError
from app.repositories.project_repository import get_project
from app.schemas.tracking import ReplanRequest
from app.services.domain_pack_service import get_domain_pack_service
from app.services.replan_service import replan

router = APIRouter()


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
