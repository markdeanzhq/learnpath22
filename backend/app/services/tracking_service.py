"""进度追踪服务"""
from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.tracking_repository import get_latest_event_per_node


async def get_tracking_summary(
    db: AsyncSession,
    project_id: str,
    total_plan_nodes: list[str],
) -> dict[str, Any]:
    """汇总学习进度。"""
    node_status = await get_latest_event_per_node(db, project_id)
    plan_set = set(total_plan_nodes)

    completed = sum(1 for nid in plan_set if node_status.get(nid) == "complete")
    in_progress = sum(1 for nid in plan_set if node_status.get(nid) == "start")
    skipped = sum(1 for nid in plan_set if node_status.get(nid) == "skip")
    pending = len(plan_set) - completed - in_progress - skipped

    total = len(plan_set)
    rate = round(completed / total, 3) if total > 0 else 0.0

    return {
        "total_nodes": total,
        "completed": completed,
        "in_progress": in_progress,
        "skipped": skipped,
        "pending": pending,
        "completion_rate": rate,
    }
