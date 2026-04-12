"""重规划 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.api.v1.plans import _dict_stages_to_list
from app.core.exceptions import AppError, NotFoundError
from app.schemas.tracking import ReplanRequest
from app.services.replan_service import replan

router = APIRouter()


@router.post("/projects/{project_id}/replans")
async def trigger_replan(
    project_id: str,
    req: ReplanRequest,
    db: AsyncSession = Depends(get_db),
):
    """触发路径重规划。支持 progress_aware 和 profile_update 两种模式。"""
    try:
        result = await replan(db, project_id, mode=req.mode)
    except ValueError as e:
        raise AppError(code=400, message=str(e))

    plan_result = result["plan_result"]
    return {
        "id": result["path_id"],
        "version": result["version"],
        "mode": result["mode"],
        "stages": _dict_stages_to_list(plan_result["stage_plan"]),
        "budget_status": plan_result["budget_summary"]["status"],
        "total_hours": plan_result["total_hours"],
        "diff": result.get("diff"),
        "reason": req.reason,
    }
