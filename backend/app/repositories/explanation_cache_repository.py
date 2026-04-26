"""规划解释缓存数据访问层"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import PlanExplanationCache


async def get_explanation_cache(
    db: AsyncSession,
    *,
    path_id: str,
    polish_requested: bool,
) -> PlanExplanationCache | None:
    result = await db.execute(
        select(PlanExplanationCache)
        .where(
            PlanExplanationCache.path_id == path_id,
            PlanExplanationCache.polish_requested == polish_requested,
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def upsert_explanation_cache(
    db: AsyncSession,
    *,
    project_id: str,
    path_id: str,
    plan_version: int,
    polish_requested: bool,
    explanation_json: str,
) -> PlanExplanationCache:
    cache = await get_explanation_cache(
        db,
        path_id=path_id,
        polish_requested=polish_requested,
    )
    if cache is None:
        cache = PlanExplanationCache(
            project_id=project_id,
            path_id=path_id,
            plan_version=plan_version,
            polish_requested=polish_requested,
            explanation_json=explanation_json,
        )
        db.add(cache)
    else:
        cache.project_id = project_id
        cache.plan_version = plan_version
        cache.explanation_json = explanation_json
    await db.flush()
    await db.commit()
    await db.refresh(cache)
    return cache
