"""项目数据访问层"""
from __future__ import annotations

from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import (
    GraphReviewStatus,
    KnowledgeSource,
    LearnerProfile,
    LearningPath,
    LearningProject,
    PathStage,
    PathTask,
    TrackingEvent,
)


async def create_project(
    db: AsyncSession,
    title: str,
    goal_text: str,
    goal_type: str,
    domain: str,
    *,
    commit: bool = True,
    **extra_fields: Any,
) -> LearningProject:
    project = LearningProject(
        title=title,
        goal_text=goal_text,
        goal_type=goal_type,
        domain=domain,
        **extra_fields,
    )
    db.add(project)
    await db.flush()
    if commit:
        await db.commit()
    await db.refresh(project)
    return project


async def get_project(db: AsyncSession, project_id: str) -> LearningProject | None:
    result = await db.execute(
        select(LearningProject).where(LearningProject.id == project_id)
    )
    return result.scalar_one_or_none()


async def list_projects(db: AsyncSession) -> list[LearningProject]:
    result = await db.execute(
        select(LearningProject).order_by(LearningProject.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_project(db: AsyncSession, project_id: str) -> bool:
    project = await get_project(db, project_id)
    if not project:
        return False

    path_ids = list(
        (
            await db.execute(
                select(LearningPath.id).where(LearningPath.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )

    stage_ids = []
    if path_ids:
        stage_ids = list(
            (
                await db.execute(
                    select(PathStage.id).where(PathStage.path_id.in_(path_ids))
                )
            )
            .scalars()
            .all()
        )

    if stage_ids:
        await db.execute(delete(PathTask).where(PathTask.stage_id.in_(stage_ids)))
    if path_ids:
        await db.execute(delete(PathStage).where(PathStage.path_id.in_(path_ids)))
        await db.execute(delete(LearningPath).where(LearningPath.id.in_(path_ids)))

    await db.execute(delete(LearnerProfile).where(LearnerProfile.project_id == project_id))
    await db.execute(delete(KnowledgeSource).where(KnowledgeSource.project_id == project_id))
    await db.execute(delete(TrackingEvent).where(TrackingEvent.project_id == project_id))
    await db.execute(delete(GraphReviewStatus).where(GraphReviewStatus.project_id == project_id))
    await db.execute(delete(LearningProject).where(LearningProject.id == project_id))
    await db.commit()
    return True
