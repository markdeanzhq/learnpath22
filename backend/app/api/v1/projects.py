"""项目管理 API"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.repositories.project_repository import (
    delete_project,
    get_project,
    list_projects,
)
from app.schemas.common import ErrorResponse
from app.schemas.goal_resolution import (
    ClarificationAnswerRequest,
    ClarificationSessionResponse,
    CoveragePreviewResponse,
    GoalResolutionPreviewRequest,
)
from app.schemas.project import (
    CreateProjectRequest,
    DeleteProjectResponse,
    ProjectResponse,
    UpdateProjectGoalResolutionRequest,
)
from app.services.project_resolution_service import (
    answer_project_goal_clarification,
    create_project_from_resolution_session,
    preview_project_goal_resolution,
    update_project_goal_resolution,
)

router = APIRouter()


@router.post("/projects", response_model=ProjectResponse)
async def create_project_endpoint(
    req: CreateProjectRequest,
    db: AsyncSession = Depends(get_db),
):
    return await create_project_from_resolution_session(
        db,
        title=req.title,
        goal_text=req.goal_text,
        domain=req.domain,
        resolution_session_id=req.resolution_session_id,
        selected_candidate_id=req.selected_candidate_id,
        path_mode=req.path_mode,
        accept_partial=req.accept_partial,
    )


@router.post(
    "/projects/{project_id}/goal-resolution/preview",
    response_model=CoveragePreviewResponse,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def preview_project_goal_resolution_endpoint(
    project_id: str,
    req: GoalResolutionPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    return await preview_project_goal_resolution(
        db,
        project_id=project_id,
        goal_text=req.goal_text,
        requested_goal_type=req.requested_goal_type,
        domain=req.domain,
    )


@router.post(
    "/projects/{project_id}/goal-resolution/clarifications/{clarification_session_id}/answers",
    response_model=ClarificationSessionResponse,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def answer_project_goal_clarification_endpoint(
    project_id: str,
    clarification_session_id: str,
    req: ClarificationAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    return await answer_project_goal_clarification(
        db,
        project_id=project_id,
        clarification_session_id=clarification_session_id,
        answers=[answer.model_dump() for answer in req.answers],
    )


@router.put("/projects/{project_id}/goal-resolution", response_model=ProjectResponse)
async def update_project_goal_resolution_endpoint(
    project_id: str,
    req: UpdateProjectGoalResolutionRequest,
    db: AsyncSession = Depends(get_db),
):
    return await update_project_goal_resolution(
        db,
        project_id=project_id,
        goal_text=req.goal_text,
        domain=req.domain,
        resolution_session_id=req.resolution_session_id,
        selected_candidate_id=req.selected_candidate_id,
        path_mode=req.path_mode,
        accept_partial=req.accept_partial,
    )


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
