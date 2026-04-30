from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.repositories.project_overlay_repository import create_persisted_search_result
from app.services.project_overlay_extraction_service import (
    create_extraction_session_from_sources,
    validate_extraction_payload_for_sources,
)
from app.services.project_overlay_llm_extraction_service import preview_overlay_extraction_payload_from_sources
from app.services.saved_search_overlay_bridge_service import ensure_overlay_sources_for_persisted_results
from app.services.search_service import search

DEFAULT_SEARCH_PROVIDER = "tavily"
RECOVERABLE_EXTRACTION_ERRORS = {
    "LLM_EXTRACTION_FAILED",
    "LLM_NOT_READY",
    "INVALID_LLM_EXTRACTION_JSON",
    "AUTO_DRAFT_EMPTY_EXTRACTION",
}


def _normalize_query(query: str | None, fallback_goal_text: str | None) -> str:
    normalized = (query or "").strip() or (fallback_goal_text or "").strip()
    if not normalized:
        raise AppError(code=422, message="AUTO_DRAFT_QUERY_REQUIRED")
    return normalized


def _normalize_search_result(result: dict[str, Any], *, index: int, query: str) -> dict[str, Any] | None:
    url = str(result.get("url") or "").strip()
    if not url:
        return None

    title = str(result.get("title") or "").strip() or url
    snippet = result.get("snippet") or result.get("content")
    provider = str(result.get("provider") or DEFAULT_SEARCH_PROVIDER).strip() or DEFAULT_SEARCH_PROVIDER
    score = result.get("score")
    metadata = {
        "auto_overlay_draft": True,
        "query": query,
        "score": score,
    }
    return {
        "query": query,
        "provider": provider,
        "url": url,
        "title": title,
        "snippet": str(snippet).strip() if snippet is not None else None,
        "result_rank": index + 1,
        "is_selected": True,
        "metadata_json": json.dumps(metadata, ensure_ascii=False, sort_keys=True),
    }


def _empty_extraction_preview(*, source_ids: list[str], mode: str, warning: str) -> dict[str, Any]:
    payload = {"nodes": [], "edges": [], "resources": [], "warnings": [warning]}
    return {
        "source_ids": source_ids,
        "mode": mode,
        "extraction_payload": payload,
        "warnings": payload["warnings"],
        "counts": {"nodes": 0, "edges": 0, "resources": 0},
        "provenance": {
            "schema_version": "v1",
            "draft_origin": "auto_overlay_draft",
            "draft_engine": "search_sources_only",
            "extraction_error": warning,
            "writes_formal_graph": False,
            "writes_formal_path": False,
        },
    }


async def create_project_overlay_auto_draft(
    db: AsyncSession,
    *,
    project_id: str,
    query: str | None,
    fallback_goal_text: str | None,
    domain: str | None,
    max_results: int = 5,
    mode: str = "default",
) -> dict[str, Any]:
    effective_query = _normalize_query(query, fallback_goal_text)
    search_results = await search(effective_query, max_results=max_results)
    if not search_results:
        raise AppError(code=422, message="AUTO_DRAFT_NO_SEARCH_RESULTS")

    persisted_results = []
    for index, result in enumerate(search_results):
        normalized = _normalize_search_result(result, index=index, query=effective_query)
        if normalized is None:
            continue
        persisted_results.append(
            await create_persisted_search_result(
                db,
                project_id=project_id,
                commit=True,
                **normalized,
            )
        )

    if not persisted_results:
        raise AppError(code=422, message="AUTO_DRAFT_NO_USABLE_SEARCH_RESULTS")

    bridged = await ensure_overlay_sources_for_persisted_results(
        db,
        project_id=project_id,
        result_ids=[result.result_id for result in persisted_results],
    )
    source_ids = [item["source_id"] for item in bridged]
    extraction_status = "extracted"
    extraction_error: str | None = None
    try:
        preview = await preview_overlay_extraction_payload_from_sources(
            db,
            project_id=project_id,
            source_ids=source_ids,
            mode=mode,
            domain=domain,
        )
        preview_counts = preview.get("counts") or {}
        extracted_count = sum(int(preview_counts.get(key) or 0) for key in ("nodes", "edges", "resources"))
        if extracted_count <= 0:
            extraction_status = "empty_extraction"
            extraction_error = "AUTO_DRAFT_EMPTY_EXTRACTION"
            preview = _empty_extraction_preview(source_ids=source_ids, mode=mode, warning=extraction_error)
    except AppError as exc:
        if exc.message not in RECOVERABLE_EXTRACTION_ERRORS:
            raise
        extraction_status = "extraction_failed"
        extraction_error = exc.message
        preview = _empty_extraction_preview(source_ids=source_ids, mode=mode, warning=exc.message)
    except ValueError as exc:
        extraction_status = "extraction_failed"
        extraction_error = str(exc) or "INVALID_LLM_EXTRACTION_JSON"
        preview = _empty_extraction_preview(source_ids=source_ids, mode=mode, warning=extraction_error)

    preview_counts = preview.get("counts") or {}
    validation = await validate_extraction_payload_for_sources(
        db,
        project_id=project_id,
        source_ids=source_ids,
        mode=mode,
        extraction_payload=preview["extraction_payload"],
        domain=domain,
    )
    created = await create_extraction_session_from_sources(
        db,
        project_id=project_id,
        source_ids=source_ids,
        mode=mode,
        extraction_payload=preview["extraction_payload"],
        domain=domain,
        session_provenance={
            **preview.get("provenance", {}),
            "draft_origin": "auto_overlay_draft",
            "draft_engine": "search_llm" if extraction_status == "extracted" else "search_sources_only",
            "query": effective_query,
            "selected_result_ids": [result.result_id for result in persisted_results],
            "source_ids": source_ids,
            "preview_counts": preview_counts,
            "pre_validation_summary": validation.get("summary"),
            "extraction_status": extraction_status,
            "extraction_error": extraction_error,
            "writes_formal_graph": False,
            "writes_formal_path": False,
        },
    )
    return {
        "created": created,
        "preview": preview,
        "validation": validation,
        "query": effective_query,
        "search_results": search_results,
        "persisted_results": persisted_results,
        "bridged_results": bridged,
        "source_ids": source_ids,
        "extraction_status": extraction_status,
        "extraction_error": extraction_error,
    }
