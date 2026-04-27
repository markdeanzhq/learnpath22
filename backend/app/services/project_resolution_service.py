from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppError, NotFoundError
from app.models.sqlite_models import GoalResolutionSession, LearningProject
from app.repositories.project_repository import create_project, get_project
from app.schemas.project import validate_path_mode
from app.services.goal_resolution_service import (
    _build_goal_text_hash,
    answer_clarification_session,
    build_project_graph_hash,
    create_goal_resolution_preview,
    resolve_compatible_domain,
)
from app.services.domain_pack_service import get_domain_pack_service


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_session_candidates(session: GoalResolutionSession) -> list[dict[str, Any]]:
    if not session.candidates_json:
        return []
    try:
        raw = json.loads(session.candidates_json)
    except json.JSONDecodeError:
        return []
    return raw if isinstance(raw, list) else []


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _build_goal_resolution_summary(project: LearningProject) -> dict[str, Any] | None:
    if not project.confirmed_candidate_id or not project.confirmed_target_node_ids_json:
        return None
    return {
        "requested_goal_type": project.requested_goal_type,
        "auto_detected_goal_type": project.auto_detected_goal_type,
        "selected_candidate_id": project.confirmed_candidate_id,
        "confirmed_target_node_ids": json.loads(project.confirmed_target_node_ids_json),
        "partial_accepted": bool(getattr(project, "partial_accepted", False)),
        "missing_concepts": _json_loads(getattr(project, "missing_concepts_json", None), []),
    }


def _serialize_project(project: LearningProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "goal_text": project.goal_text,
        "goal_type": project.goal_type,
        "domain": project.domain,
        "status": project.status,
        "path_mode": getattr(project, "path_mode", None) or "standard",
        "created_at": project.created_at,
        "updated_at": project.updated_at,
        "goal_resolution": _build_goal_resolution_summary(project),
    }


async def _get_valid_session(
    db: AsyncSession,
    *,
    resolution_session_id: str,
    project_id: str | None = None,
) -> GoalResolutionSession:
    session = await db.get(GoalResolutionSession, resolution_session_id)
    if session is None or session.status == "expired" or session.expires_at < _naive_utc_now():
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    if project_id is not None and session.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    return session


async def _validate_session_integrity(
    db: AsyncSession,
    *,
    session: GoalResolutionSession,
    goal_text: str,
    domain: str,
    pack_hash: str,
    project_id: str | None = None,
    accept_partial: bool = False,
) -> dict[str, Any]:
    expected_status = "partial_previewed" if accept_partial else "previewed"
    if session.status != expected_status:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    coverage_response = _json_loads(session.coverage_response_json, {})
    if not isinstance(coverage_response, dict):
        raise AppError(code=422, message="INVALID_COVERAGE_RESPONSE")
    allowed_statuses = {"partial"} if accept_partial else {"covered", "adjacent_domain"}
    if coverage_response.get("coverage_status") not in allowed_statuses:
        raise AppError(code=422, message="INVALID_COVERAGE_TRANSITION")
    if session.goal_text_hash != _build_goal_text_hash(goal_text):
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    if session.domain != domain:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    if session.pack_hash != pack_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_RESOLUTION_SESSION,
            details={"reason_code": error_codes.PACK_HASH_DRIFT},
        )
    if project_id is None:
        if session.project_id is not None:
            raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
        return coverage_response
    if session.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_RESOLUTION_SESSION)
    current_graph_hash = await build_project_graph_hash(db, project_id, pack_hash)
    session_graph_hashes = [session.graph_hash, session.project_graph_hash]
    if not any(session_graph_hashes) or any(
        graph_hash is not None and graph_hash != current_graph_hash
        for graph_hash in session_graph_hashes
    ):
        raise AppError(
            code=409,
            message=error_codes.STALE_RESOLUTION_SESSION,
            details={"reason_code": error_codes.PROJECT_GRAPH_DRIFT},
        )
    return coverage_response


def _get_selected_candidate(
    session: GoalResolutionSession,
    selected_candidate_id: str,
) -> dict[str, Any]:
    candidates = _load_session_candidates(session)
    selected_candidate = next(
        (candidate for candidate in candidates if candidate.get("candidate_id") == selected_candidate_id),
        None,
    )
    if selected_candidate is None:
        raise AppError(code=422, message="INVALID_RESOLUTION_CANDIDATE")
    return selected_candidate


def _validate_path_mode_or_raise(path_mode: str | None) -> str:
    try:
        return validate_path_mode(path_mode)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_PATH_MODE") from exc


def _apply_confirmed_resolution(
    project: LearningProject,
    *,
    session: GoalResolutionSession,
    selected_candidate_id: str,
    selected_candidate: dict[str, Any],
    goal_text: str,
    partial_accepted: bool = False,
    missing_concepts: list[str] | None = None,
) -> None:
    project.goal_text = goal_text
    project.goal_type = selected_candidate["goal_type"]
    project.requested_goal_type = session.requested_goal_type
    project.auto_detected_goal_type = session.auto_detected_goal_type
    project.confirmed_target_node_ids_json = json.dumps(selected_candidate["target_node_ids"], ensure_ascii=False)
    project.confirmed_mode = selected_candidate["mode"]
    project.confirmed_description = selected_candidate["description"]
    project.confirmed_template_id = selected_candidate.get("template_id")
    project.confirmed_resolve_source = selected_candidate["resolve_source"]
    project.confirmed_source_breakdown_json = json.dumps(
        selected_candidate.get("source_breakdown", {}),
        ensure_ascii=False,
        sort_keys=True,
    )
    project.confirmed_candidate_id = selected_candidate_id
    project.resolution_pack_version = session.pack_version
    project.resolution_confirmed_at = _naive_utc_now()
    project.partial_accepted = partial_accepted
    project.missing_concepts_json = json.dumps(missing_concepts or [], ensure_ascii=False)


async def create_project_from_resolution_session(
    db: AsyncSession,
    *,
    title: str,
    goal_text: str,
    domain: str | None,
    resolution_session_id: str,
    selected_candidate_id: str,
    path_mode: str = "standard",
    accept_partial: bool = False,
) -> dict[str, Any]:
    path_mode = _validate_path_mode_or_raise(path_mode)
    session = await _get_valid_session(db, resolution_session_id=resolution_session_id)
    selected_candidate = _get_selected_candidate(session, selected_candidate_id)
    resolved_domain = resolve_compatible_domain(domain)
    pack = get_domain_pack_service(resolved_domain)
    coverage_response = await _validate_session_integrity(
        db,
        session=session,
        goal_text=goal_text,
        domain=resolved_domain,
        pack_hash=pack.contract.pack_hash,
        accept_partial=accept_partial,
    )
    missing_concepts = coverage_response.get("missing_concepts", []) if accept_partial else []
    if not isinstance(missing_concepts, list):
        missing_concepts = []

    project = await create_project(
        db,
        title=title,
        goal_text=goal_text,
        goal_type=selected_candidate["goal_type"],
        domain=resolved_domain,
        commit=False,
        path_mode=path_mode,
        requested_goal_type=session.requested_goal_type,
        auto_detected_goal_type=session.auto_detected_goal_type,
        confirmed_target_node_ids_json=json.dumps(selected_candidate["target_node_ids"], ensure_ascii=False),
        confirmed_mode=selected_candidate["mode"],
        confirmed_description=selected_candidate["description"],
        confirmed_template_id=selected_candidate.get("template_id"),
        confirmed_resolve_source=selected_candidate["resolve_source"],
        confirmed_source_breakdown_json=json.dumps(
            selected_candidate.get("source_breakdown", {}),
            ensure_ascii=False,
            sort_keys=True,
        ),
        confirmed_candidate_id=selected_candidate_id,
        resolution_pack_version=session.pack_version,
        resolution_confirmed_at=_naive_utc_now(),
        partial_accepted=accept_partial,
        missing_concepts_json=json.dumps(missing_concepts, ensure_ascii=False),
    )
    session.project_id = project.id
    session.status = "confirmed"
    await db.commit()
    await db.refresh(project)
    await db.refresh(session)

    return _serialize_project(project)


async def preview_project_goal_resolution(
    db: AsyncSession,
    *,
    project_id: str,
    goal_text: str,
    requested_goal_type: str | None,
    domain: str | None,
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise NotFoundError("项目不存在")

    preview = await create_goal_resolution_preview(
        db,
        goal_text=goal_text,
        requested_goal_type=requested_goal_type,
        domain=domain,
        expected_domain=project.domain,
        project_id=project_id,
    )
    return preview


async def answer_project_goal_clarification(
    db: AsyncSession,
    *,
    project_id: str,
    clarification_session_id: str,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    return await answer_clarification_session(
        db,
        clarification_session_id=clarification_session_id,
        answers=answers,
        project_id=project_id,
    )


async def update_project_goal_resolution(
    db: AsyncSession,
    *,
    project_id: str,
    goal_text: str,
    domain: str | None,
    resolution_session_id: str,
    selected_candidate_id: str,
    path_mode: str | None = None,
    accept_partial: bool = False,
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise NotFoundError("项目不存在")

    resolved_domain = resolve_compatible_domain(domain, expected_domain=project.domain)
    session = await _get_valid_session(
        db,
        resolution_session_id=resolution_session_id,
        project_id=project_id,
    )
    selected_candidate = _get_selected_candidate(session, selected_candidate_id)
    pack = get_domain_pack_service(resolved_domain)
    coverage_response = await _validate_session_integrity(
        db,
        session=session,
        goal_text=goal_text,
        domain=resolved_domain,
        pack_hash=pack.contract.pack_hash,
        project_id=project_id,
        accept_partial=accept_partial,
    )
    missing_concepts = coverage_response.get("missing_concepts", []) if accept_partial else []
    if not isinstance(missing_concepts, list):
        missing_concepts = []
    _apply_confirmed_resolution(
        project,
        session=session,
        selected_candidate_id=selected_candidate_id,
        selected_candidate=selected_candidate,
        goal_text=goal_text,
        partial_accepted=accept_partial,
        missing_concepts=missing_concepts,
    )
    if path_mode is not None:
        project.path_mode = _validate_path_mode_or_raise(path_mode)
    session.status = "confirmed"
    await db.commit()
    await db.refresh(project)
    await db.refresh(session)
    return _serialize_project(project)
