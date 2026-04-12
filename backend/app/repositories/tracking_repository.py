"""进度事件数据访问层"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import TrackingEvent


async def add_event(
    db: AsyncSession,
    project_id: str,
    node_id: str,
    event_type: str,
    note: str | None = None,
) -> TrackingEvent:
    event = TrackingEvent(
        project_id=project_id,
        node_id=node_id,
        event_type=event_type,
        note=note,
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def get_events(
    db: AsyncSession, project_id: str
) -> list[TrackingEvent]:
    result = await db.execute(
        select(TrackingEvent)
        .where(TrackingEvent.project_id == project_id)
        .order_by(TrackingEvent.created_at.desc())
    )
    return list(result.scalars().all())


async def get_latest_event_per_node(
    db: AsyncSession, project_id: str
) -> dict[str, str]:
    """返回每个节点的最新事件类型 {node_id: event_type}。"""
    events = await get_events(db, project_id)
    latest: dict[str, str] = {}
    for event in reversed(events):  # 从旧到新，后面覆盖
        latest[event.node_id] = event.event_type
    return latest
