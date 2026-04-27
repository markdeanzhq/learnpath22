from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.common import ErrorResponse
from app.schemas.goal_resolution import (
    ClarificationAnswerRequest,
    ClarificationSessionResponse,
    CoveragePreviewResponse,
    GoalResolutionPreviewRequest,
)
from app.services.goal_resolution_service import (
    answer_clarification_session,
    create_goal_resolution_preview,
)

router = APIRouter()


@router.post(
    "/goal-resolution/preview",
    response_model=CoveragePreviewResponse,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def preview_goal_resolution_endpoint(
    req: GoalResolutionPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    return await create_goal_resolution_preview(
        db,
        goal_text=req.goal_text,
        requested_goal_type=req.requested_goal_type,
        domain=req.domain,
    )


@router.post(
    "/goal-resolution/clarifications/{clarification_session_id}/answers",
    response_model=ClarificationSessionResponse,
    responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
async def answer_clarification_endpoint(
    clarification_session_id: str,
    req: ClarificationAnswerRequest,
    db: AsyncSession = Depends(get_db),
):
    return await answer_clarification_session(
        db,
        clarification_session_id=clarification_session_id,
        answers=[answer.model_dump() for answer in req.answers],
    )
