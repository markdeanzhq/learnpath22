from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.models.sqlite_models import GoalResolutionSession, LearningProject
from app.repositories.project_repository import create_project, get_project
from app.services.goal_resolution_service import (
    _build_goal_text_hash,
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


def _build_goal_resolution_summary(project: LearningProject) -> dict[str, Any] | None:
    if not project.confirmed_candidate_id or not project.confirmed_target_node_ids_json:
        return None
    return {
        "requested_goal_type": project.requested_goal_type,
        "auto_detected_goal_type": project.auto_detected_goal_type,
        "selected_candidate_id": project.confirmed_candidate_id,
        "confirmed_target_node_ids": json.loads(project.confirmed_target_node_ids_json),
    }


def _serialize_project(project: LearningProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "title": project.title,
        "goal_text": project.goal_text,
        "goal_type": project.goal_type,
        "domain": project.domain,
        "status": project.status,
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
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    if project_id is not None and session.project_id != project_id:
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    return session


async def _validate_session_integrity(
    db: AsyncSession,
    *,
    session: GoalResolutionSession,
    goal_text: str,
    domain: str,
    pack_hash: str,
    project_id: str | None = None,
) -> None:
    if session.status != "previewed":
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    if session.goal_text_hash != _build_goal_text_hash(goal_text):
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    if session.domain != domain:
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    if session.pack_hash != pack_hash:
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    if project_id is None:
        if session.project_id is not None:
            raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
        return
    if session.project_id != project_id:
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    current_graph_hash = await build_project_graph_hash(db, project_id, pack_hash)
    if session.graph_hash != current_graph_hash:
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")


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


def _apply_confirmed_resolution(
    project: LearningProject,
    *,
    session: GoalResolutionSession,
    selected_candidate_id: str,
    selected_candidate: dict[str, Any],
    goal_text: str,
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


async def create_project_from_resolution_session(
    db: AsyncSession,
    *,
    title: str,
    goal_text: str,
    domain: str | None,
    resolution_session_id: str,
    selected_candidate_id: str,
) -> dict[str, Any]:
    session = await _get_valid_session(db, resolution_session_id=resolution_session_id)
    selected_candidate = _get_selected_candidate(session, selected_candidate_id)
    resolved_domain = resolve_compatible_domain(domain)
    pack = get_domain_pack_service(resolved_domain)
    await _validate_session_integrity(
        db,
        session=session,
        goal_text=goal_text,
        domain=resolved_domain,
        pack_hash=pack.contract.pack_hash,
    )

    project = await create_project(
        db,
        title=title,
        goal_text=goal_text,
        goal_type=selected_candidate["goal_type"],
        domain=resolved_domain,
        commit=False,
        requested_goal_type=session.requested_goal_type,
        auto_detected_goal_type=session.auto_detected_goal_type,
        confirmed_target_node_ids_json=json.dumps(selected_candidate["target_node_ids"], ensure_ascii=False),
        confirmed_mode=selected_candidate["mode"],
        confirmed_description=selected_candidate["description"],
        confirmed_template_id=selected_candidate.get("template_id"),
        confirmed_resolve_source=selected_candidate["resolve_source"],
        confirmed_source_breakdown_json=json.dumps(selected_candidate.get("source_breakdown", {}), ensure_ascii=False, sort_keys=True),
        confirmed_candidate_id=selected_candidate_id,
        resolution_pack_version=session.pack_version,
        resolution_confirmed_at=_naive_utc_now(),
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


async def update_project_goal_resolution(
    db: AsyncSession,
    *,
    project_id: str,
    goal_text: str,
    domain: str | None,
    resolution_session_id: str,
    selected_candidate_id: str,
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
    await _validate_session_integrity(
        db,
        session=session,
        goal_text=goal_text,
        domain=resolved_domain,
        pack_hash=pack.contract.pack_hash,
        project_id=project_id,
    )
    _apply_confirmed_resolution(
        project,
        session=session,
        selected_candidate_id=selected_candidate_id,
        selected_candidate=selected_candidate,
        goal_text=goal_text,
    )
    session.status = "confirmed"
    await db.commit()
    await db.refresh(project)
    await db.refresh(session)
    return _serialize_project(project)
