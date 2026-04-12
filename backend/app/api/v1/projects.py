"""项目管理 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.repositories.project_repository import (
    create_project,
    delete_project,
    get_project,
    list_projects,
)
from app.schemas.project import (
    CreateProjectRequest,
    DeleteProjectResponse,
    ProjectResponse,
)

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse)
async def create_project_endpoint(
    req: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await create_project(
        db,
        title=req.title,
        goal_text=req.goal_text,
        goal_type=req.goal_type,
        domain=req.domain,
    )
    return project


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects_endpoint(
    db: AsyncSession = Depends(get_db),
):
    return await list_projects(db)


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    return project


@router.delete("/projects/{project_id}", response_model=DeleteProjectResponse)
async def delete_project_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    deleted = await delete_project(db, project_id)
    if not deleted:
        raise NotFoundError("项目不存在")
    return DeleteProjectResponse(id=project_id, message="项目已删除")
