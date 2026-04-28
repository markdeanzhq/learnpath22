from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppError, NotFoundError
from app.models.sqlite_models import GoalResolutionSession
from app.repositories.project_overlay_repository import (
    create_source,
    get_extraction_session,
    get_source,
    list_session_edges,
    list_session_nodes,
    list_session_resources,
)
from app.repositories.project_repository import get_project
from app.services.goal_resolution_service import build_project_graph_hash
from app.services.project_overlay_extraction_service import create_extraction_session_from_sources


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


DRAFT_PROMPT_VERSION = "goal-extension-draft-v1"
DRAFT_ORIGIN = "rules_goal_extension"


def _normalize_missing_concepts(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        concept = item.strip()
        if concept and concept not in seen:
            seen.add(concept)
            result.append(concept)
    return result


def _goal_text_from_session(session: GoalResolutionSession, coverage_response: dict[str, Any]) -> str:
    goal_frame = _json_loads(session.goal_frame_json, None)
    if isinstance(goal_frame, dict) and isinstance(goal_frame.get("raw_text"), str):
        return goal_frame["raw_text"].strip()
    response_goal_frame = coverage_response.get("goal_frame")
    if isinstance(response_goal_frame, dict) and isinstance(response_goal_frame.get("raw_text"), str):
        return response_goal_frame["raw_text"].strip()
    return " ".join(_normalize_missing_concepts(coverage_response.get("missing_concepts")))


def _goal_trace(session: GoalResolutionSession) -> dict[str, Any]:
    return {
        "trace_type": "goal_resolution",
        "trace_id": session.session_id,
        "pack_hash": session.pack_hash,
        "project_graph_hash": session.project_graph_hash,
    }


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _goal_frame_from_coverage(coverage_response: dict[str, Any]) -> dict[str, Any]:
    goal_frame = coverage_response.get("goal_frame")
    return goal_frame if isinstance(goal_frame, dict) else {}


def _build_gap_analysis(
    *,
    goal_text: str,
    missing_concepts: list[str],
    coverage_response: dict[str, Any],
) -> dict[str, Any]:
    goal_frame = _goal_frame_from_coverage(coverage_response)
    covered_node_ids = _normalize_string_list(coverage_response.get("covered_target_node_ids"))
    covered_node_names = _normalize_string_list(coverage_response.get("covered_target_node_names"))
    target_concepts = _normalize_string_list(goal_frame.get("target_concepts")) or missing_concepts
    missing_text = "、".join(missing_concepts)
    return {
        "schema_version": "v1",
        "draft_origin": DRAFT_ORIGIN,
        "user_goal": goal_text,
        "coverage_status": coverage_response.get("coverage_status") or "in_domain_uncovered",
        "target_concepts": target_concepts,
        "covered_by_current_graph": {
            "target_node_ids": covered_node_ids,
            "target_node_names": covered_node_names,
        },
        "missing_concepts": missing_concepts,
        "why_current_graph_is_insufficient": f"当前机器学习基础图谱尚未覆盖“{missing_text}”，不能直接把该目标映射为正式路径节点。",
        "recommended_review_focus": [
            "确认新增概念是否确实属于本次学习目标，而不是相邻或过大的主题。",
            "确认概念名称是否需要拆分、改名或合并到已有知识点。",
            "补充并审核前置依赖关系后，再允许候选节点参与路径规划。",
        ],
    }


def _build_review_notes(missing_concepts: list[str]) -> list[str]:
    missing_text = "、".join(missing_concepts)
    return [
        f"请先审核“{missing_text}”这些扩展概念；未确认前它们只保留在项目级草稿区。",
        "审核节点名称、难度、重要性和前置关系后，再打开规划开关。",
        "正式路径仍由图算法基于已审核图谱生成，草稿不会绕过人工确认。",
    ]


def _build_draft_metadata(session: GoalResolutionSession) -> dict[str, Any]:
    return {
        "schema_version": "v1",
        "draft_origin": DRAFT_ORIGIN,
        "draft_engine": "rules",
        "prompt_version": DRAFT_PROMPT_VERSION,
        "model": None,
        "resolution_session_id": session.session_id,
        "requires_user_review": True,
        "can_directly_plan": False,
        "requires_planning_enabled": True,
        "safety_policy": {
            "writes_formal_graph": False,
            "writes_formal_path": False,
            "formal_path_source": "graph_algorithm_after_user_review",
        },
    }


def _draft_node_candidate(
    *,
    concept: str,
    source_id: str,
    goal_text: str,
    trace: dict[str, Any],
    draft_metadata: dict[str, Any],
) -> dict[str, Any]:
    summary = f"{concept} 是由学习目标“{goal_text}”触发的项目级扩展草稿，审核确认前不会参与路径规划。"
    return {
        "name": concept,
        "group": "concept",
        "category": "extension",
        "summary": summary,
        "difficulty_final": 3,
        "importance_final": 3,
        "estimated_hours": 3.0,
        "req_math": 2,
        "req_coding": 2,
        "req_ml": 2,
        "theory_weight": 0.5,
        "practice_weight": 0.5,
        "confidence": 0.35,
        "legality_rationale": "该节点来自领域内未覆盖目标，只能作为项目级 overlay draft 等待人工审核。",
        "evidence_spans": [{"source_id": source_id, "text": concept}],
        "provenance": {
            "origin": "goal_extension_draft",
            "draft_origin": DRAFT_ORIGIN,
            "summary": summary,
            "goal_trace": trace,
            "goal_text": goal_text,
            "missing_concept": concept,
            "draft_metadata": draft_metadata,
        },
    }


async def _validate_resolution_session(
    db: AsyncSession,
    *,
    project_id: str,
    resolution_session_id: str,
) -> tuple[GoalResolutionSession, dict[str, Any]]:
    session = await db.get(GoalResolutionSession, resolution_session_id)
    if session is None or session.expires_at < _naive_utc_now():
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    if session.status not in {"draft_previewed", "draft_created"}:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    if session.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    coverage_response = _json_loads(session.coverage_response_json, {})
    if not isinstance(coverage_response, dict):
        raise AppError(code=422, message="INVALID_COVERAGE_RESPONSE")
    if coverage_response.get("coverage_status") != "in_domain_uncovered":
        raise AppError(code=422, message="INVALID_COVERAGE_TRANSITION")
    if session.pack_hash is None:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    current_graph_hash = await build_project_graph_hash(db, project_id, session.pack_hash)
    if session.project_graph_hash != current_graph_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_RESOLUTION_SESSION,
            details={"reason_code": error_codes.PROJECT_GRAPH_DRIFT},
        )
    return session, coverage_response


async def create_goal_extension_draft_from_resolution(
    db: AsyncSession,
    *,
    project_id: str,
    resolution_session_id: str,
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    session, coverage_response = await _validate_resolution_session(
        db,
        project_id=project_id,
        resolution_session_id=resolution_session_id,
    )
    missing_concepts = _normalize_missing_concepts(coverage_response.get("missing_concepts"))
    if not missing_concepts:
        raise AppError(code=422, message="MISSING_CONCEPTS_REQUIRED")
    goal_text = _goal_text_from_session(session, coverage_response)
    trace = _goal_trace(session)
    gap_analysis = _build_gap_analysis(
        goal_text=goal_text,
        missing_concepts=missing_concepts,
        coverage_response=coverage_response,
    )
    review_notes = _build_review_notes(missing_concepts)
    draft_metadata = _build_draft_metadata(session)
    existing_session_id = coverage_response.get("overlay_extraction_session_id")
    if session.status == "draft_created" and isinstance(existing_session_id, str):
        existing_session = await get_extraction_session(db, project_id, existing_session_id)
        if existing_session is None:
            raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
        source_ids = _json_loads(existing_session.source_ids_json, [])
        sources = []
        if isinstance(source_ids, list):
            for source_id in source_ids:
                if not isinstance(source_id, str):
                    continue
                source = await get_source(db, project_id, source_id)
                if source is not None:
                    sources.append(source)
        return {
            "session": existing_session,
            "sources": sources,
            "nodes": await list_session_nodes(db, project_id=project_id, session_id=existing_session_id),
            "edges": await list_session_edges(db, project_id=project_id, session_id=existing_session_id),
            "resources": await list_session_resources(db, project_id=project_id, session_id=existing_session_id),
            "warnings": _json_loads(existing_session.warnings_json, []),
            "goal_trace": trace,
            "missing_concepts": missing_concepts,
            "gap_analysis": gap_analysis,
            "review_notes": review_notes,
            "draft_metadata": draft_metadata,
        }

    source_text = f"学习目标：{goal_text}\n待扩展概念：{'、'.join(missing_concepts)}"
    source = await create_source(
        db,
        project_id=project_id,
        source_type="pasted_text",
        content_hash=hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        raw_text_excerpt=source_text[:500],
        summary=f"目标扩展草稿：{'、'.join(missing_concepts)}",
        quality_status="goal_extension_draft",
        metadata_json=_json_dumps({
            "origin": "goal_extension_draft",
            "draft_origin": DRAFT_ORIGIN,
            "goal_trace": trace,
            "coverage_status": "in_domain_uncovered",
            "missing_concepts": missing_concepts,
            "gap_analysis": gap_analysis,
            "review_notes": review_notes,
            "draft_metadata": draft_metadata,
        }),
        commit=False,
    )
    extraction_payload = {
        "nodes": [
            _draft_node_candidate(
                concept=concept,
                source_id=source.source_id,
                goal_text=goal_text,
                trace=trace,
                draft_metadata=draft_metadata,
            )
            for concept in missing_concepts
        ],
        "edges": [],
        "resources": [],
        "warnings": ["goal_extension_draft_requires_review"],
    }
    created = await create_extraction_session_from_sources(
        db,
        project_id=project_id,
        source_ids=[source.source_id],
        mode="default",
        extraction_payload=extraction_payload,
        domain=project.domain,
        session_provenance={
            "origin": "goal_extension_draft",
            "draft_origin": DRAFT_ORIGIN,
            "goal_trace": trace,
            "coverage_status": "in_domain_uncovered",
            "missing_concepts": missing_concepts,
            "gap_analysis": gap_analysis,
            "review_notes": review_notes,
            "draft_metadata": draft_metadata,
        },
    )
    coverage_response["overlay_extraction_session_id"] = created["session"].session_id
    coverage_response["gap_analysis"] = gap_analysis
    coverage_response["review_notes"] = review_notes
    coverage_response["draft_metadata"] = draft_metadata
    session.coverage_response_json = _json_dumps(coverage_response)
    session.status = "draft_created"
    await db.commit()
    await db.refresh(created["session"])
    return {
        **created,
        "goal_trace": trace,
        "missing_concepts": missing_concepts,
        "gap_analysis": gap_analysis,
        "review_notes": review_notes,
        "draft_metadata": draft_metadata,
    }
