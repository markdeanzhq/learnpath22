from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import ProjectOverlayEdge, ProjectOverlayNode, ProjectOverlayResource

OverlayKind = Literal["n", "e", "r"]

_MODEL_BY_KIND = {
    "n": (ProjectOverlayNode, ProjectOverlayNode.node_id),
    "e": (ProjectOverlayEdge, ProjectOverlayEdge.edge_id),
    "r": (ProjectOverlayResource, ProjectOverlayResource.resource_id),
}


def canonicalize_overlay_payload(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def overlay_payload_hash(payload: Any) -> str:
    return hashlib.sha256(canonicalize_overlay_payload(payload).encode("utf-8")).hexdigest()


def build_overlay_id(project_id: str, kind: OverlayKind, canonical_source: Any) -> str:
    digest = overlay_payload_hash(canonical_source)[:24]
    overlay_id = f"po:{project_id}:{kind}:{digest}"
    if len(overlay_id) > 160:
        raise ValueError("Overlay ID exceeds 160 characters")
    return overlay_id


async def assert_overlay_id_available(
    db: AsyncSession,
    *,
    kind: OverlayKind,
    overlay_id: str,
    canonical_payload_hash: str,
) -> None:
    model, id_column = _MODEL_BY_KIND[kind]
    result = await db.execute(select(model).where(id_column == overlay_id))
    existing = result.scalar_one_or_none()
    if existing is None:
        return
    if existing.canonical_payload_hash == canonical_payload_hash:
        return
    raise ValueError("OVERLAY_ID_COLLISION")
