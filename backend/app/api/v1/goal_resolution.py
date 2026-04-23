from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.schemas.goal_resolution import (
    GoalResolutionPreviewRequest,
    GoalResolutionPreviewResponse,
)
from app.services.goal_resolution_service import create_goal_resolution_preview

router = APIRouter()


@router.post("/goal-resolution/preview", response_model=GoalResolutionPreviewResponse)
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
