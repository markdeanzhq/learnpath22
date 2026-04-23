"""资源绑定数据访问层"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import ResourceBinding


async def list_resource_bindings(
    db: AsyncSession,
    project_id: str,
    path_id: str,
) -> list[ResourceBinding]:
    result = await db.execute(
        select(ResourceBinding)
        .where(
            ResourceBinding.project_id == project_id,
            ResourceBinding.path_id == path_id,
        )
        .order_by(ResourceBinding.created_at.asc())
    )
    return result.scalars().all()


async def create_resource_binding(
    db: AsyncSession,
    *,
    project_id: str,
    path_id: str,
    title: str,
    url: str,
    source_type: str,
    snippet: str | None = None,
    score: float | None = None,
    stage_name: str | None = None,
    node_id: str | None = None,
) -> ResourceBinding:
    binding = ResourceBinding(
        project_id=project_id,
        path_id=path_id,
        stage_name=stage_name,
        node_id=node_id,
        title=title,
        url=url,
        snippet=snippet,
        score=score,
        source_type=source_type,
    )
    db.add(binding)
    await db.flush()
    await db.commit()
    await db.refresh(binding)
    return binding


async def delete_auto_resource_bindings(
    db: AsyncSession,
    *,
    project_id: str,
    path_id: str,
) -> None:
    await db.execute(
        delete(ResourceBinding).where(
            ResourceBinding.project_id == project_id,
            ResourceBinding.path_id == path_id,
            ResourceBinding.source_type == "tavily_auto",
        )
    )
    await db.commit()
