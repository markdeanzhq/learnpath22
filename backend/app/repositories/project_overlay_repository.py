"""Project overlay repository."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, TypeAlias

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import (
    PersistedSearchResult,
    ProjectOverlayEdge,
    ProjectOverlayExtractionSession,
    ProjectOverlayNode,
    ProjectOverlayProjectionState,
    ProjectOverlayPromotionBatch,
    ProjectOverlayPromotionItem,
    ProjectOverlayResource,
    ProjectOverlayResourceBinding,
    ProjectOverlaySource,
)

OverlayElementType: TypeAlias = Literal["node", "edge", "resource"]

VALIDATION_STATUSES = {"unchecked", "valid", "invalid", "needs_review"}
REVIEW_STATUSES = {"pending", "confirmed", "rejected", "removed"}
PROMOTION_STATUSES = {"not_promoted", "promotion_ready", "promoted", "promotion_failed"}
ACTIVE_PROMOTION_STATUSES = {"not_promoted", "promotion_ready", "promotion_failed"}
RESOURCE_BINDING_TARGET_TYPES = {"project_node", "path_stage"}
SESSION_STATUS_TRANSITIONS = {
    "drafted": {"validated", "archived", "failed"},
    "validated": {"reviewed", "archived", "failed"},
    "reviewed": {"promoted", "archived", "failed"},
    "promoted": set(),
    "archived": set(),
    "failed": {"archived"},
}
EDITABLE_SESSION_STATUSES = {"drafted", "validated", "reviewed"}
PLANNER_VISIBLE_SESSION_STATUSES = {"drafted", "validated", "reviewed"}

_CANDIDATE_MODELS = {
    "node": (ProjectOverlayNode, ProjectOverlayNode.node_id),
    "edge": (ProjectOverlayEdge, ProjectOverlayEdge.edge_id),
    "resource": (ProjectOverlayResource, ProjectOverlayResource.resource_id),
}


def _validate_status(value: str, allowed: set[str], field_name: str) -> None:
    if value not in allowed:
        raise ValueError(f"INVALID_{field_name.upper()}")


def _reject_lifecycle_overrides(fields: dict[str, Any], forbidden: set[str]) -> None:
    blocked = forbidden & fields.keys()
    if blocked:
        raise ValueError(f"LIFECYCLE_FIELDS_NOT_ALLOWED:{','.join(sorted(blocked))}")


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def create_source(
    db: AsyncSession,
    *,
    project_id: str,
    source_type: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlaySource:
    source = ProjectOverlaySource(project_id=project_id, source_type=source_type, **fields)
    db.add(source)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(source)
    return source


async def get_source(
    db: AsyncSession,
    project_id: str,
    source_id: str,
) -> ProjectOverlaySource | None:
    result = await db.execute(
        select(ProjectOverlaySource).where(
            ProjectOverlaySource.project_id == project_id,
            ProjectOverlaySource.source_id == source_id,
        )
    )
    return result.scalar_one_or_none()


async def list_sources(db: AsyncSession, project_id: str) -> list[ProjectOverlaySource]:
    result = await db.execute(
        select(ProjectOverlaySource)
        .where(ProjectOverlaySource.project_id == project_id)
        .order_by(ProjectOverlaySource.created_at.desc())
    )
    return list(result.scalars().all())


async def source_is_referenced(
    db: AsyncSession,
    *,
    project_id: str,
    source_id: str,
) -> bool:
    result = await db.execute(
        select(ProjectOverlayExtractionSession).where(
            ProjectOverlayExtractionSession.project_id == project_id,
            ProjectOverlayExtractionSession.source_ids_json.like(f'%"{source_id}"%'),
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


async def update_source(
    db: AsyncSession,
    *,
    project_id: str,
    source_id: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlaySource:
    source = await get_source(db, project_id, source_id)
    if source is None:
        raise ValueError("OVERLAY_SOURCE_NOT_FOUND")
    if await source_is_referenced(db, project_id=project_id, source_id=source_id):
        raise ValueError("OVERLAY_SOURCE_IMMUTABLE")
    for field_name, value in fields.items():
        setattr(source, field_name, value)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(source)
    return source


async def create_extraction_session(
    db: AsyncSession,
    *,
    project_id: str,
    source_ids_json: str | None = None,
    mode: str = "default",
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayExtractionSession:
    _reject_lifecycle_overrides(fields, {"session_status"})
    session = ProjectOverlayExtractionSession(
        project_id=project_id,
        source_ids_json=source_ids_json,
        mode=mode,
        **fields,
    )
    db.add(session)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(session)
    return session


async def get_extraction_session(
    db: AsyncSession,
    project_id: str,
    session_id: str,
) -> ProjectOverlayExtractionSession | None:
    result = await db.execute(
        select(ProjectOverlayExtractionSession).where(
            ProjectOverlayExtractionSession.project_id == project_id,
            ProjectOverlayExtractionSession.session_id == session_id,
        )
    )
    return result.scalar_one_or_none()


async def list_session_nodes(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    include_promoted: bool = False,
) -> list[ProjectOverlayNode]:
    filters = [
        ProjectOverlayNode.project_id == project_id,
        ProjectOverlayNode.session_id == session_id,
    ]
    if not include_promoted:
        filters.append(ProjectOverlayNode.promotion_status.in_(ACTIVE_PROMOTION_STATUSES))
    result = await db.execute(
        select(ProjectOverlayNode)
        .where(*filters)
        .order_by(ProjectOverlayNode.created_at.asc(), ProjectOverlayNode.node_id.asc())
    )
    return list(result.scalars().all())


async def list_session_edges(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    include_promoted: bool = False,
) -> list[ProjectOverlayEdge]:
    filters = [
        ProjectOverlayEdge.project_id == project_id,
        ProjectOverlayEdge.session_id == session_id,
    ]
    if not include_promoted:
        filters.append(ProjectOverlayEdge.promotion_status.in_(ACTIVE_PROMOTION_STATUSES))
    result = await db.execute(
        select(ProjectOverlayEdge)
        .where(*filters)
        .order_by(ProjectOverlayEdge.created_at.asc(), ProjectOverlayEdge.edge_id.asc())
    )
    return list(result.scalars().all())


async def list_project_overlay_nodes(db: AsyncSession, project_id: str) -> list[ProjectOverlayNode]:
    result = await db.execute(
        select(ProjectOverlayNode)
        .where(ProjectOverlayNode.project_id == project_id)
        .order_by(ProjectOverlayNode.created_at.asc(), ProjectOverlayNode.node_id.asc())
    )
    return list(result.scalars().all())


async def list_active_project_overlay_nodes(db: AsyncSession, project_id: str) -> list[ProjectOverlayNode]:
    result = await db.execute(
        select(ProjectOverlayNode)
        .where(
            ProjectOverlayNode.project_id == project_id,
            ProjectOverlayNode.promotion_status.in_(ACTIVE_PROMOTION_STATUSES),
        )
        .order_by(ProjectOverlayNode.created_at.asc(), ProjectOverlayNode.node_id.asc())
    )
    return list(result.scalars().all())


async def list_project_overlay_edges(db: AsyncSession, project_id: str) -> list[ProjectOverlayEdge]:
    result = await db.execute(
        select(ProjectOverlayEdge)
        .where(ProjectOverlayEdge.project_id == project_id)
        .order_by(ProjectOverlayEdge.created_at.asc(), ProjectOverlayEdge.edge_id.asc())
    )
    return list(result.scalars().all())


async def list_active_project_overlay_edges(db: AsyncSession, project_id: str) -> list[ProjectOverlayEdge]:
    result = await db.execute(
        select(ProjectOverlayEdge)
        .where(
            ProjectOverlayEdge.project_id == project_id,
            ProjectOverlayEdge.promotion_status.in_(ACTIVE_PROMOTION_STATUSES),
        )
        .order_by(ProjectOverlayEdge.created_at.asc(), ProjectOverlayEdge.edge_id.asc())
    )
    return list(result.scalars().all())


async def list_project_overlay_resources(db: AsyncSession, project_id: str) -> list[ProjectOverlayResource]:
    result = await db.execute(
        select(ProjectOverlayResource)
        .where(ProjectOverlayResource.project_id == project_id)
        .order_by(ProjectOverlayResource.created_at.asc(), ProjectOverlayResource.resource_id.asc())
    )
    return list(result.scalars().all())


async def list_active_project_overlay_resources(db: AsyncSession, project_id: str) -> list[ProjectOverlayResource]:
    result = await db.execute(
        select(ProjectOverlayResource)
        .where(
            ProjectOverlayResource.project_id == project_id,
            ProjectOverlayResource.promotion_status.in_(ACTIVE_PROMOTION_STATUSES),
        )
        .order_by(ProjectOverlayResource.created_at.asc(), ProjectOverlayResource.resource_id.asc())
    )
    return list(result.scalars().all())


async def list_session_resources(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    include_promoted: bool = False,
) -> list[ProjectOverlayResource]:
    filters = [
        ProjectOverlayResource.project_id == project_id,
        ProjectOverlayResource.session_id == session_id,
    ]
    if not include_promoted:
        filters.append(ProjectOverlayResource.promotion_status.in_(ACTIVE_PROMOTION_STATUSES))
    result = await db.execute(
        select(ProjectOverlayResource)
        .where(*filters)
        .order_by(ProjectOverlayResource.created_at.asc(), ProjectOverlayResource.resource_id.asc())
    )
    return list(result.scalars().all())


async def _session_has_reviewed_candidates(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
) -> bool:
    for model in (ProjectOverlayNode, ProjectOverlayEdge, ProjectOverlayResource):
        result = await db.execute(
            select(model).where(
                model.project_id == project_id,
                model.session_id == session_id,
                model.review_status != "pending",
            ).limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return True
    return False


async def update_extraction_session_status(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    session_status: str,
    error_message: str | None = None,
    commit: bool = True,
) -> ProjectOverlayExtractionSession:
    session = await get_extraction_session(db, project_id, session_id)
    if session is None:
        raise ValueError("OVERLAY_SESSION_NOT_FOUND")
    allowed_next = SESSION_STATUS_TRANSITIONS.get(session.session_status)
    if allowed_next is None or session_status not in allowed_next:
        raise ValueError("INVALID_OVERLAY_SESSION_TRANSITION")
    if session_status == "reviewed" and not await _session_has_reviewed_candidates(
        db,
        project_id=project_id,
        session_id=session_id,
    ):
        raise ValueError("OVERLAY_SESSION_REVIEW_REQUIRED")
    session.session_status = session_status
    if error_message is not None:
        session.error_message = error_message
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(session)
    return session


async def _ensure_session_editable(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
) -> None:
    session = await get_extraction_session(db, project_id, session_id)
    if session is None:
        raise ValueError("OVERLAY_SESSION_NOT_FOUND")
    if session.session_status not in EDITABLE_SESSION_STATUSES:
        raise ValueError("OVERLAY_SESSION_NOT_EDITABLE")


async def _get_replayable_candidate(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    element_type: OverlayElementType,
    element_id: str,
    canonical_payload_hash: str,
) -> ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource | None:
    model, id_column = _CANDIDATE_MODELS[element_type]
    result = await db.execute(select(model).where(id_column == element_id))
    candidate = result.scalar_one_or_none()
    if candidate is None:
        return None
    if candidate.project_id != project_id or candidate.canonical_payload_hash != canonical_payload_hash:
        raise ValueError("OVERLAY_ID_COLLISION")
    if candidate.session_id != session_id:
        raise ValueError("OVERLAY_ID_REPLAY_SESSION_MISMATCH")
    return candidate


async def create_node(
    db: AsyncSession,
    *,
    project_id: str,
    node_id: str,
    session_id: str,
    canonical_payload_hash: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayNode:
    _reject_lifecycle_overrides(
        fields,
        {"validation_status", "review_status", "planning_enabled", "promotion_status"},
    )
    await _ensure_session_editable(db, project_id=project_id, session_id=session_id)
    existing = await _get_replayable_candidate(
        db,
        project_id=project_id,
        session_id=session_id,
        element_type="node",
        element_id=node_id,
        canonical_payload_hash=canonical_payload_hash,
    )
    if existing is not None:
        return existing
    node = ProjectOverlayNode(
        project_id=project_id,
        node_id=node_id,
        session_id=session_id,
        canonical_payload_hash=canonical_payload_hash,
        **fields,
    )
    db.add(node)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(node)
    return node


async def create_edge(
    db: AsyncSession,
    *,
    project_id: str,
    edge_id: str,
    session_id: str,
    source_node_id: str,
    target_node_id: str,
    relation_type: str,
    canonical_payload_hash: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayEdge:
    _reject_lifecycle_overrides(
        fields,
        {"validation_status", "review_status", "planning_enabled", "promotion_status"},
    )
    await _ensure_session_editable(db, project_id=project_id, session_id=session_id)
    existing = await _get_replayable_candidate(
        db,
        project_id=project_id,
        session_id=session_id,
        element_type="edge",
        element_id=edge_id,
        canonical_payload_hash=canonical_payload_hash,
    )
    if existing is not None:
        return existing
    edge = ProjectOverlayEdge(
        project_id=project_id,
        edge_id=edge_id,
        session_id=session_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        relation_type=relation_type,
        canonical_payload_hash=canonical_payload_hash,
        **fields,
    )
    db.add(edge)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(edge)
    return edge


async def create_resource(
    db: AsyncSession,
    *,
    project_id: str,
    resource_id: str,
    session_id: str,
    canonical_payload_hash: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayResource:
    _reject_lifecycle_overrides(
        fields,
        {"validation_status", "review_status", "planning_enabled", "promotion_status"},
    )
    await _ensure_session_editable(db, project_id=project_id, session_id=session_id)
    existing = await _get_replayable_candidate(
        db,
        project_id=project_id,
        session_id=session_id,
        element_type="resource",
        element_id=resource_id,
        canonical_payload_hash=canonical_payload_hash,
    )
    if existing is not None:
        return existing
    resource = ProjectOverlayResource(
        project_id=project_id,
        resource_id=resource_id,
        session_id=session_id,
        canonical_payload_hash=canonical_payload_hash,
        **fields,
    )
    db.add(resource)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(resource)
    return resource


async def get_candidate(
    db: AsyncSession,
    *,
    project_id: str,
    element_type: OverlayElementType,
    element_id: str,
) -> ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource | None:
    model, id_column = _CANDIDATE_MODELS[element_type]
    result = await db.execute(
        select(model).where(
            model.project_id == project_id,
            id_column == element_id,
        )
    )
    return result.scalar_one_or_none()


async def _ensure_candidate_session_editable(
    db: AsyncSession,
    *,
    candidate: ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource,
) -> None:
    if candidate.promotion_status == "promoted":
        raise ValueError("OVERLAY_CANDIDATE_PROMOTED_READ_ONLY")
    await _ensure_session_editable(
        db,
        project_id=candidate.project_id,
        session_id=candidate.session_id,
    )


async def update_validation_status(
    db: AsyncSession,
    *,
    project_id: str,
    element_type: OverlayElementType,
    element_id: str,
    validation_status: str,
    validation_errors_json: str | None = None,
    commit: bool = True,
) -> ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource:
    _validate_status(validation_status, VALIDATION_STATUSES, "validation_status")
    candidate = await get_candidate(
        db,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
    )
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    await _ensure_candidate_session_editable(db, candidate=candidate)
    candidate.validation_status = validation_status
    if validation_status == "valid":
        candidate.validation_errors_json = None
    elif validation_errors_json is not None:
        candidate.validation_errors_json = validation_errors_json
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(candidate)
    return candidate


async def update_review_status(
    db: AsyncSession,
    *,
    project_id: str,
    element_type: OverlayElementType,
    element_id: str,
    review_status: str,
    commit: bool = True,
) -> ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource:
    _validate_status(review_status, REVIEW_STATUSES, "review_status")
    candidate = await get_candidate(
        db,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
    )
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    await _ensure_candidate_session_editable(db, candidate=candidate)
    candidate.review_status = review_status
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(candidate)
    return candidate


async def update_planning_enabled(
    db: AsyncSession,
    *,
    project_id: str,
    element_type: OverlayElementType,
    element_id: str,
    planning_enabled: bool,
    commit: bool = True,
) -> ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource:
    candidate = await get_candidate(
        db,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
    )
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    await _ensure_candidate_session_editable(db, candidate=candidate)
    candidate.planning_enabled = planning_enabled
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(candidate)
    return candidate


async def update_promotion_status(
    db: AsyncSession,
    *,
    project_id: str,
    element_type: OverlayElementType,
    element_id: str,
    promotion_status: str,
    commit: bool = True,
) -> ProjectOverlayNode | ProjectOverlayEdge | ProjectOverlayResource:
    _validate_status(promotion_status, PROMOTION_STATUSES, "promotion_status")
    candidate = await get_candidate(
        db,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
    )
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    await _ensure_candidate_session_editable(db, candidate=candidate)
    candidate.promotion_status = promotion_status
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(candidate)
    return candidate


async def list_planner_visible_nodes(db: AsyncSession, project_id: str) -> list[ProjectOverlayNode]:
    result = await db.execute(
        select(ProjectOverlayNode)
        .join(
            ProjectOverlayExtractionSession,
            and_(
                ProjectOverlayExtractionSession.project_id == ProjectOverlayNode.project_id,
                ProjectOverlayExtractionSession.session_id == ProjectOverlayNode.session_id,
            ),
        )
        .where(
            ProjectOverlayNode.project_id == project_id,
            ProjectOverlayNode.validation_status == "valid",
            ProjectOverlayNode.review_status == "confirmed",
            ProjectOverlayNode.planning_enabled.is_(True),
            ProjectOverlayNode.promotion_status.in_(ACTIVE_PROMOTION_STATUSES),
            ProjectOverlayExtractionSession.session_status.in_(PLANNER_VISIBLE_SESSION_STATUSES),
        )
        .order_by(ProjectOverlayNode.node_id)
    )
    return list(result.scalars().all())


async def list_planner_visible_edges(db: AsyncSession, project_id: str) -> list[ProjectOverlayEdge]:
    result = await db.execute(
        select(ProjectOverlayEdge)
        .join(
            ProjectOverlayExtractionSession,
            and_(
                ProjectOverlayExtractionSession.project_id == ProjectOverlayEdge.project_id,
                ProjectOverlayExtractionSession.session_id == ProjectOverlayEdge.session_id,
            ),
        )
        .where(
            ProjectOverlayEdge.project_id == project_id,
            ProjectOverlayEdge.validation_status == "valid",
            ProjectOverlayEdge.review_status == "confirmed",
            ProjectOverlayEdge.planning_enabled.is_(True),
            ProjectOverlayEdge.promotion_status.in_(ACTIVE_PROMOTION_STATUSES),
            ProjectOverlayExtractionSession.session_status.in_(PLANNER_VISIBLE_SESSION_STATUSES),
        )
        .order_by(ProjectOverlayEdge.edge_id)
    )
    edges = list(result.scalars().all())
    if not edges:
        return []
    visible_overlay_node_ids = {
        node.node_id for node in await list_planner_visible_nodes(db, project_id)
    }
    return [
        edge
        for edge in edges
        if not edge.source_node_id.startswith("po:") or edge.source_node_id in visible_overlay_node_ids
        if not edge.target_node_id.startswith("po:") or edge.target_node_id in visible_overlay_node_ids
    ]


async def list_resource_bindings(
    db: AsyncSession,
    project_id: str,
) -> list[ProjectOverlayResourceBinding]:
    result = await db.execute(
        select(ProjectOverlayResourceBinding)
        .where(ProjectOverlayResourceBinding.project_id == project_id)
        .order_by(ProjectOverlayResourceBinding.created_at.asc())
    )
    return list(result.scalars().all())


async def get_projection_state(
    db: AsyncSession,
    project_id: str,
) -> ProjectOverlayProjectionState | None:
    return await db.get(ProjectOverlayProjectionState, project_id)


async def list_projection_states(db: AsyncSession) -> list[ProjectOverlayProjectionState]:
    result = await db.execute(
        select(ProjectOverlayProjectionState).order_by(ProjectOverlayProjectionState.updated_at.desc())
    )
    return list(result.scalars().all())


async def upsert_projection_state(
    db: AsyncSession,
    *,
    project_id: str,
    status: str,
    overlay_hash: str | None,
    error_message: str | None = None,
    commit: bool = True,
) -> ProjectOverlayProjectionState:
    state = await get_projection_state(db, project_id)
    now = _utc_now_naive()
    if state is None:
        state = ProjectOverlayProjectionState(project_id=project_id)
        db.add(state)
    state.status = status
    state.overlay_hash = overlay_hash
    state.error_message = error_message
    state.projected_at = now if status == "ok" else state.projected_at
    state.updated_at = now
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(state)
    return state


async def create_resource_binding(
    db: AsyncSession,
    *,
    project_id: str,
    resource_id: str,
    target_type: str,
    target_id: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayResourceBinding:
    if target_type not in RESOURCE_BINDING_TARGET_TYPES:
        raise ValueError("INVALID_RESOURCE_BINDING_TARGET_TYPE")
    resource = await get_candidate(
        db,
        project_id=project_id,
        element_type="resource",
        element_id=resource_id,
    )
    if resource is None:
        raise ValueError("OVERLAY_RESOURCE_NOT_FOUND")
    if resource.promotion_status == "promoted":
        raise ValueError("OVERLAY_CANDIDATE_PROMOTED_READ_ONLY")
    binding = ProjectOverlayResourceBinding(
        project_id=project_id,
        resource_id=resource_id,
        target_type=target_type,
        target_id=target_id,
        **fields,
    )
    db.add(binding)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(binding)
    return binding


async def create_promotion_batch(
    db: AsyncSession,
    *,
    project_id: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayPromotionBatch:
    _reject_lifecycle_overrides(fields, {"status"})
    batch = ProjectOverlayPromotionBatch(project_id=project_id, **fields)
    db.add(batch)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(batch)
    return batch


async def update_promotion_batch(
    db: AsyncSession,
    *,
    project_id: str,
    batch_id: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayPromotionBatch:
    batch = await db.get(ProjectOverlayPromotionBatch, batch_id)
    if batch is None or batch.project_id != project_id:
        raise ValueError("OVERLAY_PROMOTION_BATCH_NOT_FOUND")
    for field_name, value in fields.items():
        setattr(batch, field_name, value)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(batch)
    return batch


async def create_promotion_item(
    db: AsyncSession,
    *,
    project_id: str,
    batch_id: str,
    element_type: str,
    element_id: str,
    commit: bool = True,
    **fields: Any,
) -> ProjectOverlayPromotionItem:
    _reject_lifecycle_overrides(fields, {"status"})
    item = ProjectOverlayPromotionItem(
        project_id=project_id,
        batch_id=batch_id,
        element_type=element_type,
        element_id=element_id,
        **fields,
    )
    db.add(item)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(item)
    return item


async def create_persisted_search_result(
    db: AsyncSession,
    *,
    project_id: str,
    query: str,
    provider: str,
    url: str,
    title: str,
    commit: bool = True,
    **fields: Any,
) -> PersistedSearchResult:
    result = PersistedSearchResult(
        project_id=project_id,
        query=query,
        provider=provider,
        url=url,
        title=title,
        **fields,
    )
    db.add(result)
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(result)
    return result


async def get_persisted_search_result(
    db: AsyncSession,
    *,
    project_id: str,
    result_id: str,
) -> PersistedSearchResult | None:
    result = await db.execute(
        select(PersistedSearchResult).where(
            PersistedSearchResult.project_id == project_id,
            PersistedSearchResult.result_id == result_id,
        )
    )
    return result.scalar_one_or_none()


async def list_persisted_search_results(
    db: AsyncSession,
    project_id: str,
) -> list[PersistedSearchResult]:
    result = await db.execute(
        select(PersistedSearchResult)
        .where(PersistedSearchResult.project_id == project_id)
        .order_by(PersistedSearchResult.created_at.desc())
    )
    return list(result.scalars().all())
