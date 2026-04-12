"""搜索 API"""
from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError, NotFoundError
from app.repositories.project_repository import get_project
from app.services.search_service import search

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    max_results: int = Field(default=5, ge=1, le=20)


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

    return {"query": req.query, "results": results, "count": len(results)}
