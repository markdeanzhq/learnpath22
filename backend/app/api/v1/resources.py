"""路径资源推荐与绑定 API"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError, NotFoundError
from app.repositories.project_overlay_repository import (
    create_resource_binding,
    get_candidate,
    get_persisted_search_result,
)
from app.repositories.project_repository import get_project
from app.services.domain_pack_service import get_domain_pack_service
from app.schemas.resource import ManualResourceBindRequest, PlanResourcesResponse, ResourceItem
from app.services.resource_recommendation_service import (
    bind_manual_resource,
    get_plan_resources,
    recommend_plan_resources,
)

router = APIRouter()


class ProjectResourceBindingRequest(BaseModel):
    resource_id: str = Field(min_length=1)
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    source_result_id: str | None = None
    binding_source: str = "overlay"


class ProjectResourceBindingResponse(BaseModel):
    id: str
    project_id: str
    resource_id: str
    target_type: str
    target_id: str
    source_result_id: str | None
    binding_source: str
    created_at: datetime


async def _validate_resource_binding_target(
    db: AsyncSession,
    *,
    project_id: str,
    domain: str,
    target_type: str,
    target_id: str,
) -> None:
    pack = get_domain_pack_service(domain)
    if target_type == "project_node":
        if target_id in pack.nodes_by_id:
            return
        candidate = await get_candidate(
            db,
            project_id=project_id,
            element_type="node",
            element_id=target_id,
        )
        if candidate is not None and candidate.promotion_status != "promoted":
            return
        raise AppError(code=422, message="RESOURCE_BINDING_TARGET_NOT_FOUND")
    if target_type == "path_stage":
        if target_id in pack.stages_by_id:
            return
        raise AppError(code=422, message="UNRESOLVABLE_PATH_STAGE_BINDING")
    raise AppError(code=422, message="INVALID_RESOURCE_BINDING_TARGET_TYPE")


@router.post(
    "/projects/{project_id}/resources/bindings",
    response_model=ProjectResourceBindingResponse,
)
async def bind_project_resource_endpoint(
    project_id: str,
    req: ProjectResourceBindingRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    if req.source_result_id:
        source_result = await get_persisted_search_result(
            db,
            project_id=project_id,
            result_id=req.source_result_id,
        )
        if source_result is None:
            raise AppError(code=422, message="SOURCE_RESULT_NOT_FOUND")

    await _validate_resource_binding_target(
        db,
        project_id=project_id,
        domain=project.domain,
        target_type=req.target_type,
        target_id=req.target_id,
    )

    try:
        binding = await create_resource_binding(
            db,
            project_id=project_id,
            resource_id=req.resource_id,
            target_type=req.target_type,
            target_id=req.target_id,
            source_result_id=req.source_result_id,
            binding_source=req.binding_source,
        )
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc

    return ProjectResourceBindingResponse(
        id=binding.id,
        project_id=binding.project_id,
        resource_id=binding.resource_id,
        target_type=binding.target_type,
        target_id=binding.target_id,
        source_result_id=binding.source_result_id,
        binding_source=binding.binding_source,
        created_at=binding.created_at,
    )


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
    node_id: str | None = Query(default=None),
    stage_name: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    return await recommend_plan_resources(
        db,
        project_id=project_id,
        path_id=path_id,
        node_id=node_id,
        stage_name=stage_name,
    )


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
