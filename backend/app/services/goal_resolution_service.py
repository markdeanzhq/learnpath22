from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.sqlite_models import GoalResolutionSession
from app.repositories.graph_review_repository import get_removed_edge_ids, get_removed_node_ids
from app.services.domain_pack_service import (
    DomainPackContract,
    get_domain_pack_registry,
    get_domain_pack_service,
)
from app.services.goal_service import UnsupportedGoalTypeError, resolve_goal_candidates


def _build_goal_text_hash(goal_text: str) -> str:
    return hashlib.sha256(goal_text.strip().encode("utf-8")).hexdigest()


def resolve_compatible_domain(
    domain: str | None,
    *,
    expected_domain: str | None = None,
) -> str:
    registry = get_domain_pack_registry()
    try:
        canonical_domain = registry.resolve_domain(expected_domain)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_DOMAIN") from exc

    if domain is None:
        return canonical_domain

    try:
        requested_domain = registry.resolve_domain(domain)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_DOMAIN") from exc

    if requested_domain != canonical_domain:
        raise AppError(code=422, message="INVALID_DOMAIN")
    return canonical_domain



def _resolve_pack(domain: str | None, *, expected_domain: str | None = None):
    return get_domain_pack_service(resolve_compatible_domain(domain, expected_domain=expected_domain))



def _validate_requested_goal_type(
    requested_goal_type: Optional[str],
    contract: DomainPackContract,
) -> None:
    if requested_goal_type is None:
        return
    if requested_goal_type not in set(contract.supported_goal_types):
        raise AppError(code=422, message="INVALID_GOAL_TYPE")


def _build_graph_hash(
    pack_hash: str,
    removed_node_ids: set[str] | list[str],
    removed_edge_ids: set[str] | list[str],
) -> str:
    payload = json.dumps(
        {
            "pack_hash": pack_hash,
            "removed_node_ids": sorted(removed_node_ids),
            "removed_edge_ids": sorted(removed_edge_ids),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def build_project_graph_hash(db: AsyncSession, project_id: str, pack_hash: str) -> str:
    removed_node_ids = await get_removed_node_ids(db, project_id)
    removed_edge_ids = await get_removed_edge_ids(db, project_id)
    return _build_graph_hash(pack_hash, removed_node_ids, removed_edge_ids)



def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def create_goal_resolution_preview(
    db: AsyncSession,
    *,
    goal_text: str,
    requested_goal_type: Optional[str],
    domain: str | None,
    expected_domain: str | None = None,
    project_id: str | None = None,
) -> dict[str, object]:
    pack = _resolve_pack(domain, expected_domain=expected_domain)
    assert pack.contract is not None
    _validate_requested_goal_type(requested_goal_type, pack.contract)

    try:
        result = resolve_goal_candidates(
            goal_text=goal_text,
            goal_type_override=requested_goal_type,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
        )
    except UnsupportedGoalTypeError as exc:
        raise AppError(code=422, message="INVALID_GOAL_TYPE") from exc

    candidates = list(result.get("candidates") or [])[:5]
    if not candidates:
        raise AppError(
            code=422,
            message="EMPTY_CANDIDATES",
            details={
                "reason_code": result.get("reason_code") or "no_supported_candidates",
                "reason_text": result.get("reason_text")
                or "当前目标未能匹配到可确认的学习目标候选，请尝试改写目标描述或切换目标类型。",
            },
        )

    recommended_candidate_id = str(result.get("recommended_candidate_id") or candidates[0]["candidate_id"])
    graph_hash = None
    if project_id is not None:
        graph_hash = await build_project_graph_hash(db, project_id, pack.contract.pack_hash)
    session = GoalResolutionSession(
        project_id=project_id,
        goal_text_hash=_build_goal_text_hash(goal_text),
        domain=pack.domain,
        requested_goal_type=requested_goal_type,
        auto_detected_goal_type=result["auto_detected_goal_type"],
        effective_goal_type=result["effective_goal_type"],
        pack_version=str(pack.manifest.get("version", "unknown")),
        pack_hash=pack.contract.pack_hash,
        graph_hash=graph_hash,
        candidates_json=json.dumps(candidates, ensure_ascii=False, sort_keys=True),
        recommended_candidate_id=recommended_candidate_id,
        status="previewed",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "session_id": session.session_id,
        "expires_at": _ensure_utc(session.expires_at),
        "auto_detected_goal_type": result["auto_detected_goal_type"],
        "effective_goal_type": result["effective_goal_type"],
        "recommended_candidate_id": recommended_candidate_id,
        "candidates": candidates,
    }
