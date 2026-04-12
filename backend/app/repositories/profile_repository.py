"""画像数据访问层"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import LearnerProfile


async def create_profile(
    db: AsyncSession,
    project_id: str,
    **kwargs,
) -> LearnerProfile:
    profile = LearnerProfile(project_id=project_id, **kwargs)
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return profile


async def get_latest_profile(
    db: AsyncSession, project_id: str
) -> LearnerProfile | None:
    result = await db.execute(
        select(LearnerProfile)
        .where(LearnerProfile.project_id == project_id)
        .order_by(LearnerProfile.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
