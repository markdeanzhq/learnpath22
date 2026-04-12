"""图谱审核数据访问层"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import GraphReviewStatus


async def get_review_status(
    db: AsyncSession,
    project_id: str,
    element_type: str,
    element_id: str,
) -> Optional[GraphReviewStatus]:
    result = await db.execute(
        select(GraphReviewStatus).where(
            and_(
                GraphReviewStatus.project_id == project_id,
                GraphReviewStatus.element_type == element_type,
                GraphReviewStatus.element_id == element_id,
            )
        )
    )
    return result.scalar_one_or_none()


async def upsert_review_status(
    db: AsyncSession,
    project_id: str,
    element_type: str,
    element_id: str,
    status: str,
) -> GraphReviewStatus:
    existing = await get_review_status(db, project_id, element_type, element_id)
    if existing:
        existing.status = status
    else:
        existing = GraphReviewStatus(
            project_id=project_id,
            element_type=element_type,
            element_id=element_id,
            status=status,
        )
        db.add(existing)
    await db.commit()
    await db.refresh(existing)
    return existing


async def get_all_review_statuses(
    db: AsyncSession,
    project_id: str,
) -> dict[str, dict[str, str]]:
    """返回 {element_type: {element_id: status}}。"""
    result = await db.execute(
        select(GraphReviewStatus).where(
            GraphReviewStatus.project_id == project_id
        )
    )
    rows = result.scalars().all()
    statuses: dict[str, dict[str, str]] = {"node": {}, "edge": {}}
    for row in rows:
        statuses.setdefault(row.element_type, {})[row.element_id] = row.status
    return statuses


async def get_removed_node_ids(
    db: AsyncSession,
    project_id: str,
) -> set[str]:
    """获取被移除的节点 ID 集合。"""
    result = await db.execute(
        select(GraphReviewStatus.element_id).where(
            and_(
                GraphReviewStatus.project_id == project_id,
                GraphReviewStatus.element_type == "node",
                GraphReviewStatus.status == "removed",
            )
        )
    )
    return set(result.scalars().all())


async def get_removed_edge_ids(
    db: AsyncSession,
    project_id: str,
) -> set[str]:
    """获取被移除的边 ID 集合。格式为 source->target。"""
    result = await db.execute(
        select(GraphReviewStatus.element_id).where(
            and_(
                GraphReviewStatus.project_id == project_id,
                GraphReviewStatus.element_type == "edge",
                GraphReviewStatus.status == "removed",
            )
        )
    )
    return set(result.scalars().all())
