from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.sqlite_models import GoalResolutionSession
from app.services.domain_pack_service import get_domain_pack_service
from app.services.goal_service import resolve_goal_candidates

_VALID_GOAL_TYPES = {"domain", "concept", "problem"}


def _build_goal_text_hash(goal_text: str) -> str:
    return hashlib.sha256(goal_text.strip().encode("utf-8")).hexdigest()


def _validate_requested_goal_type(requested_goal_type: Optional[str]) -> None:
    if requested_goal_type is None:
        return
    if requested_goal_type not in _VALID_GOAL_TYPES:
        raise AppError(code=422, message="INVALID_GOAL_TYPE")


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def create_goal_resolution_preview(
    db: AsyncSession,
    *,
    goal_text: str,
    requested_goal_type: Optional[str],
    domain: str,
) -> dict[str, object]:
    _validate_requested_goal_type(requested_goal_type)

    pack = get_domain_pack_service(domain)
    result = resolve_goal_candidates(
        goal_text=goal_text,
        goal_type_override=requested_goal_type,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
    )

    candidates = list(result.get("candidates") or [])[:5]
    if not candidates:
        raise AppError(code=422, message="EMPTY_CANDIDATES")

    recommended_candidate_id = str(result.get("recommended_candidate_id") or candidates[0]["candidate_id"])
    session = GoalResolutionSession(
        goal_text_hash=_build_goal_text_hash(goal_text),
        requested_goal_type=requested_goal_type,
        auto_detected_goal_type=result["auto_detected_goal_type"],
        effective_goal_type=result["effective_goal_type"],
        pack_version=str(pack.manifest.get("version", "unknown")),
        graph_hash=None,
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
