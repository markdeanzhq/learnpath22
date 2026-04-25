"""搜索 API"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError, NotFoundError
from app.repositories.project_overlay_repository import (
    create_persisted_search_result,
    list_persisted_search_results,
    list_resource_bindings,
)
from app.repositories.project_repository import get_project
from app.services.saved_search_overlay_bridge_service import ensure_overlay_sources_for_persisted_results
from app.services.search_service import search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=20)


class PersistSearchResultRequest(BaseModel):
    query: str = Field(min_length=1)
    provider: str = Field(default="tavily", min_length=1)
    url: str = Field(min_length=1)
    title: str = Field(min_length=1)
    snippet: str | None = None
    result_rank: int | None = Field(default=None, ge=1)
    retrieved_at: datetime | None = None
    summary: str | None = None
    quality_status: str | None = None
    is_selected: bool = True
    metadata_json: str | None = None


class PersistedSearchResultResponse(BaseModel):
    result_id: str
    source_id: str | None
    query: str
    provider: str
    url: str
    title: str
    snippet: str | None
    result_rank: int | None
    retrieved_at: datetime | None
    summary: str | None
    quality_status: str | None
    is_selected: bool
    binding_count: int
    created_at: datetime


class BridgeSearchResultsRequest(BaseModel):
    result_ids: list[str] = Field(min_length=1)


class BridgedSearchResultResponse(BaseModel):
    result_id: str
    source_id: str
    source_type: str
    reused: bool
    repaired: bool


class BridgeSearchResultsResponse(BaseModel):
    source_ids: list[str]
    results: list[BridgedSearchResultResponse]


@router.post("/projects/{project_id}/search")
async def search_resources(
    project_id: str,
    req: SearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """搜索学习资料。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        results = await search(req.query, max_results=req.max_results)
    except AppError:
        raise

    return {
        "query": req.query,
        "results": results,
        "count": len(results),
        "source": "tavily",
    }


def _persisted_search_response(result, binding_counts: dict[str, int]) -> PersistedSearchResultResponse:
    return PersistedSearchResultResponse(
        result_id=result.result_id,
        source_id=result.source_id,
        query=result.query,
        provider=result.provider,
        url=result.url,
        title=result.title,
        snippet=result.snippet,
        result_rank=result.result_rank,
        retrieved_at=result.retrieved_at,
        summary=result.summary,
        quality_status=result.quality_status,
        is_selected=result.is_selected,
        binding_count=binding_counts.get(result.result_id, 0),
        created_at=result.created_at,
    )


@router.post(
    "/projects/{project_id}/search-results",
    response_model=PersistedSearchResultResponse,
)
async def persist_search_result(
    project_id: str,
    req: PersistSearchResultRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    result = await create_persisted_search_result(
        db,
        project_id=project_id,
        query=req.query,
        provider=req.provider,
        url=req.url,
        title=req.title,
        snippet=req.snippet,
        result_rank=req.result_rank,
        retrieved_at=req.retrieved_at,
        summary=req.summary,
        quality_status=req.quality_status,
        is_selected=req.is_selected,
        metadata_json=req.metadata_json,
    )
    return _persisted_search_response(result, {})


@router.get(
    "/projects/{project_id}/search-results",
    response_model=list[PersistedSearchResultResponse],
)
async def list_search_results(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    results = await list_persisted_search_results(db, project_id)
    bindings = await list_resource_bindings(db, project_id)
    binding_counts: dict[str, int] = {}
    for binding in bindings:
        if binding.source_result_id:
            binding_counts[binding.source_result_id] = binding_counts.get(binding.source_result_id, 0) + 1
    return [_persisted_search_response(result, binding_counts) for result in results]


@router.post(
    "/projects/{project_id}/search-results/bridge-overlay-sources",
    response_model=BridgeSearchResultsResponse,
)
async def bridge_search_results_to_overlay_sources(
    project_id: str,
    req: BridgeSearchResultsRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        bridged = await ensure_overlay_sources_for_persisted_results(
            db,
            project_id=project_id,
            result_ids=req.result_ids,
        )
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc

    results = [
        BridgedSearchResultResponse(
            result_id=item["result"].result_id,
            source_id=item["source_id"],
            source_type=item["source"].source_type,
            reused=item["reused"],
            repaired=item["repaired"],
        )
        for item in bridged
    ]
    return BridgeSearchResultsResponse(
        source_ids=[item.source_id for item in results],
        results=results,
    )
