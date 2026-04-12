"""进度追踪 API"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError, NotFoundError
from app.repositories.plan_repository import get_all_planned_node_ids, get_latest_plan
from app.repositories.project_repository import get_project
from app.repositories.tracking_repository import add_event, get_events
from app.services.domain_pack_service import get_domain_pack_service
from app.schemas.tracking import (
    AddTrackingEventRequest,
    TrackingEventResponse,
    TrackingSummary,
)
from app.services.tracking_service import get_tracking_summary

router = APIRouter()


def _is_valid_tracking_node(project_domain: str, node_id: str) -> bool:
    pack = get_domain_pack_service(project_domain)
    return node_id in pack.nodes_by_id


@router.post(
    "/projects/{project_id}/tracking/events",
    response_model=TrackingEventResponse,
)
async def add_tracking_event(
    project_id: str,
    req: AddTrackingEventRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    if not _is_valid_tracking_node(project.domain, req.node_id):
        raise AppError(code=400, message="无效的知识点节点")
    event = await add_event(
        db,
        project_id=project_id,
        node_id=req.node_id,
        event_type=req.event_type,
        note=req.note,
    )
    return event


@router.get(
    "/projects/{project_id}/tracking/events",
    response_model=list[TrackingEventResponse],
)
async def list_tracking_events(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    return await get_events(db, project_id)


@router.get(
    "/projects/{project_id}/tracking/summary",
    response_model=TrackingSummary,
)
async def get_summary(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径，无法统计进度")

    all_node_ids = await get_all_planned_node_ids(db, project_id)
    summary = await get_tracking_summary(db, project_id, all_node_ids)
    return summary
