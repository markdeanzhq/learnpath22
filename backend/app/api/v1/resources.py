"""路径资源推荐与绑定 API"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.resource import ManualResourceBindRequest, PlanResourcesResponse, ResourceItem
from app.services.resource_recommendation_service import (
    bind_manual_resource,
    get_plan_resources,
    recommend_plan_resources,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/plans/{path_id}/resources",
    response_model=PlanResourcesResponse,
)
async def get_plan_resources_endpoint(
    project_id: str,
    path_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await get_plan_resources(db, project_id=project_id, path_id=path_id)


@router.post(
    "/projects/{project_id}/plans/{path_id}/resources/recommend",
    response_model=PlanResourcesResponse,
)
async def recommend_plan_resources_endpoint(
    project_id: str,
    path_id: str,
    db: AsyncSession = Depends(get_db),
):
    return await recommend_plan_resources(db, project_id=project_id, path_id=path_id)


@router.post(
    "/projects/{project_id}/plans/{path_id}/resources/bind",
    response_model=ResourceItem,
)
async def bind_manual_resource_endpoint(
    project_id: str,
    path_id: str,
    req: ManualResourceBindRequest,
    db: AsyncSession = Depends(get_db),
):
    return await bind_manual_resource(
        db,
        project_id=project_id,
        path_id=path_id,
        stage_name=req.stage_name,
        node_id=req.node_id,
        title=req.title,
        url=req.url,
        snippet=req.snippet,
    )
