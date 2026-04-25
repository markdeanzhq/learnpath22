from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import PersistedSearchResult, ProjectOverlaySource
from app.repositories.project_overlay_repository import get_persisted_search_result, get_source


def _metadata_with_result_id(result: PersistedSearchResult) -> str:
    import json

    try:
        metadata = json.loads(result.metadata_json) if result.metadata_json else {}
    except json.JSONDecodeError:
        metadata = {"raw_metadata": result.metadata_json}
    if not isinstance(metadata, dict):
        metadata = {"raw_metadata": metadata}
    metadata.setdefault("persisted_result_id", result.result_id)
    return json.dumps(metadata, ensure_ascii=False, sort_keys=True)


def _bridge_source_id(project_id: str, result_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"learnpath-overlay-source:{project_id}:{result_id}"))


async def _find_equivalent_search_source(
    db: AsyncSession,
    *,
    project_id: str,
    result: PersistedSearchResult,
) -> ProjectOverlaySource | None:
    query = select(ProjectOverlaySource).where(
        ProjectOverlaySource.project_id == project_id,
        ProjectOverlaySource.source_type == "search_url",
        ProjectOverlaySource.url == result.url,
        ProjectOverlaySource.provider == result.provider,
        ProjectOverlaySource.query == result.query,
    )
    if result.result_rank is None:
        query = query.where(ProjectOverlaySource.result_rank.is_(None))
    else:
        query = query.where(ProjectOverlaySource.result_rank == result.result_rank)

    found = await db.execute(query.order_by(ProjectOverlaySource.created_at.asc()))
    return found.scalars().first()


async def _resolve_overlay_source_for_persisted_result(
    db: AsyncSession,
    *,
    project_id: str,
    result_id: str,
) -> dict[str, Any]:
    result = await get_persisted_search_result(db, project_id=project_id, result_id=result_id)
    if result is None:
        raise ValueError("PERSISTED_SEARCH_RESULT_NOT_FOUND")

    reused = False
    repaired = False
    source = None
    if result.source_id:
        source = await get_source(db, project_id, result.source_id)
        if source is not None:
            reused = True
        else:
            repaired = True
            result.source_id = None
            await db.flush()

    if source is None:
        source = await _find_equivalent_search_source(db, project_id=project_id, result=result)
        if source is None:
            source = ProjectOverlaySource(
                source_id=_bridge_source_id(project_id, result.result_id),
                project_id=project_id,
                source_type="search_url",
                url=result.url,
                title=result.title,
                snippet=result.snippet,
                provider=result.provider,
                query=result.query,
                result_rank=result.result_rank,
                retrieved_at=result.retrieved_at,
                summary=result.summary,
                quality_status=result.quality_status,
                metadata_json=_metadata_with_result_id(result),
            )
            db.add(source)
            await db.flush()
        else:
            reused = True
        result.source_id = source.source_id
        await db.flush()

    return {
        "result": result,
        "source": source,
        "source_id": source.source_id,
        "reused": reused,
        "repaired": repaired,
    }


async def ensure_overlay_source_for_persisted_result(
    db: AsyncSession,
    *,
    project_id: str,
    result_id: str,
    commit: bool = True,
) -> dict[str, Any]:
    try:
        async with db.begin_nested():
            item = await _resolve_overlay_source_for_persisted_result(
                db,
                project_id=project_id,
                result_id=result_id,
            )
    except IntegrityError:
        item = await _resolve_overlay_source_for_persisted_result(
            db,
            project_id=project_id,
            result_id=result_id,
        )
        item["reused"] = True

    if commit:
        await db.commit()
        await db.refresh(item["result"])
        await db.refresh(item["source"])

    return item


async def ensure_overlay_sources_for_persisted_results(
    db: AsyncSession,
    *,
    project_id: str,
    result_ids: list[str],
) -> list[dict[str, Any]]:
    if not result_ids:
        raise ValueError("PERSISTED_SEARCH_RESULTS_REQUIRED")
    if len(set(result_ids)) != len(result_ids):
        raise ValueError("DUPLICATE_PERSISTED_SEARCH_RESULT_ID")

    resolved = []
    async with db.begin_nested():
        for result_id in result_ids:
            resolved.append(
                await ensure_overlay_source_for_persisted_result(
                    db,
                    project_id=project_id,
                    result_id=result_id,
                    commit=False,
                )
            )
    await db.commit()
    for item in resolved:
        await db.refresh(item["result"])
        await db.refresh(item["source"])
    return resolved
