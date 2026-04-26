from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.models.sqlite_models import GoalResolutionSession
from app.services.domain_pack_service import (
    DomainPackContract,
    get_domain_pack_registry,
    get_domain_pack_service,
)
from app.services.goal_service import UnsupportedGoalTypeError, resolve_goal_candidates
from app.services.project_graph_snapshot_service import build_project_graph_snapshot


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


async def build_project_graph_hash(db: AsyncSession, project_id: str, pack_hash: str) -> str:
    snapshot = await build_project_graph_snapshot(db, project_id)
    if snapshot.pack_hash != pack_hash:
        raise AppError(code=409, message="STALE_RESOLUTION_SESSION")
    return snapshot.project_graph_hash


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _node_name(node_id: str, nodes_by_id: dict[str, dict[str, object]]) -> str:
    node = nodes_by_id.get(node_id)
    name = node.get("name") if isinstance(node, dict) else None
    return str(name) if isinstance(name, str) and name.strip() else node_id


def _enrich_candidate_nodes(
    candidates: list[dict[str, object]],
    nodes_by_id: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for candidate in candidates:
        target_node_ids = [str(node_id) for node_id in candidate.get("target_node_ids", [])]
        target_nodes = [
            {"node_id": node_id, "node_name": _node_name(node_id, nodes_by_id)}
            for node_id in target_node_ids
        ]
        enriched.append({
            **candidate,
            "target_node_names": [node["node_name"] for node in target_nodes],
            "target_nodes": target_nodes,
        })
    return enriched


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
    if project_id is not None:
        pack = await build_project_graph_snapshot(db, project_id, domain=pack.domain, baseline_pack=pack)
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

    candidates = _enrich_candidate_nodes(list(result.get("candidates") or [])[:5], pack.nodes_by_id)
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
    graph_hash = pack.project_graph_hash if project_id is not None else None
    session_pack_hash = pack.pack_hash if project_id is not None else pack.contract.pack_hash
    session = GoalResolutionSession(
        project_id=project_id,
        goal_text_hash=_build_goal_text_hash(goal_text),
        domain=pack.domain,
        requested_goal_type=requested_goal_type,
        auto_detected_goal_type=result["auto_detected_goal_type"],
        effective_goal_type=result["effective_goal_type"],
        pack_version=str(pack.manifest.get("version", "unknown")),
        pack_hash=session_pack_hash,
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
