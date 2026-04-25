from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.neo4j import Neo4jDriver
from app.repositories.project_overlay_repository import (
    get_projection_state,
    list_active_project_overlay_edges,
    list_active_project_overlay_nodes,
    list_active_project_overlay_resources,
    list_resource_bindings,
    upsert_projection_state,
)
from app.repositories.project_repository import get_project

PROJECT_NODE_LABEL = "ProjectKnowledgeNode"
PROJECT_RESOURCE_LABEL = "ProjectResource"
PROJECT_REQUIRES_RELATIONSHIP = "PROJECT_REQUIRES"
PROJECT_RELATED_RELATIONSHIP = "PROJECT_RELATED_TO"
PROJECT_RESOURCE_NODE_RELATIONSHIP = "PROJECT_COVERS"
PROJECT_OVERLAY_OWNER = "project_overlay"
PROJECTION_STATUS_MISSING = "missing"
PROJECTION_STATUS_EMPTY = "empty"
PROJECTION_STATUS_OK = "ok"
PROJECTION_STATUS_DRIFTED = "drifted"
PROJECTION_STATUS_ERROR = "error"
PROJECTION_STATUSES = {
    PROJECTION_STATUS_MISSING,
    PROJECTION_STATUS_EMPTY,
    PROJECTION_STATUS_OK,
    PROJECTION_STATUS_DRIFTED,
    PROJECTION_STATUS_ERROR,
}
ProjectionStatus = Literal["missing", "empty", "ok", "drifted", "error"]


def _load_json(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _overlay_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _node_payload(node: Any) -> dict[str, Any]:
    return {
        "id": node.node_id,
        "overlay_id": node.node_id,
        "project_id": node.project_id,
        "session_id": node.session_id,
        "origin": "overlay",
        "owner": PROJECT_OVERLAY_OWNER,
        "name": node.name or node.node_id,
        "group_id": node.group,
        "category": node.category,
        "difficulty": node.difficulty_final,
        "importance": node.importance_final,
        "estimated_hours": node.estimated_hours,
        "req_math": node.req_math,
        "req_coding": node.req_coding,
        "req_ml": node.req_ml,
        "theory_weight": node.theory_weight,
        "practice_weight": node.practice_weight,
        "validation_status": node.validation_status,
        "review_status": node.review_status,
        "planning_enabled": node.planning_enabled,
        "promotion_status": node.promotion_status,
        "source_ids": _load_json(node.source_ids_json, []),
        "provenance_json": node.provenance_json,
        "validation_errors": _load_json(node.validation_errors_json, []),
        "confidence": node.confidence,
    }


def _resource_payload(resource: Any) -> dict[str, Any]:
    return {
        "id": resource.resource_id,
        "overlay_id": resource.resource_id,
        "project_id": resource.project_id,
        "session_id": resource.session_id,
        "origin": "overlay",
        "owner": PROJECT_OVERLAY_OWNER,
        "title": resource.title or resource.resource_id,
        "url": resource.url,
        "resource_type": resource.resource_type,
        "summary": resource.summary,
        "quality_score": resource.quality_score,
        "validation_status": resource.validation_status,
        "review_status": resource.review_status,
        "planning_enabled": resource.planning_enabled,
        "promotion_status": resource.promotion_status,
        "source_ids": _load_json(resource.source_ids_json, []),
        "provenance_json": resource.provenance_json,
        "validation_errors": _load_json(resource.validation_errors_json, []),
        "confidence": resource.confidence,
    }


def _edge_payload(edge: Any) -> dict[str, Any]:
    return {
        "id": edge.edge_id,
        "overlay_id": edge.edge_id,
        "project_id": edge.project_id,
        "session_id": edge.session_id,
        "source": edge.source_node_id,
        "target": edge.target_node_id,
        "relation_type": edge.relation_type,
        "origin": "overlay",
        "owner": PROJECT_OVERLAY_OWNER,
        "validation_status": edge.validation_status,
        "review_status": edge.review_status,
        "planning_enabled": edge.planning_enabled,
        "promotion_status": edge.promotion_status,
        "source_ids": _load_json(edge.source_ids_json, []),
        "provenance_json": edge.provenance_json,
        "validation_errors": _load_json(edge.validation_errors_json, []),
        "confidence": edge.confidence,
    }


def _binding_payload(binding: Any) -> dict[str, Any]:
    return {
        "id": binding.id,
        "project_id": binding.project_id,
        "resource_id": binding.resource_id,
        "target_type": binding.target_type,
        "target_id": binding.target_id,
        "source_result_id": binding.source_result_id,
        "binding_source": binding.binding_source,
        "owner": PROJECT_OVERLAY_OWNER,
        "origin": "overlay",
    }


def build_overlay_projection_payload(
    *,
    project_id: str,
    domain: str,
    nodes: list[Any],
    edges: list[Any],
    resources: list[Any],
    bindings: list[Any],
) -> dict[str, Any]:
    node_payloads = [_node_payload(node) for node in nodes]
    edge_payloads = [_edge_payload(edge) for edge in edges]
    resource_payloads = [_resource_payload(resource) for resource in resources]
    binding_payloads = [_binding_payload(binding) for binding in bindings]
    payload = {
        "project_id": project_id,
        "domain": domain,
        "nodes": sorted(node_payloads, key=lambda item: item["id"]),
        "edges": sorted(edge_payloads, key=lambda item: item["id"]),
        "resources": sorted(resource_payloads, key=lambda item: item["id"]),
        "bindings": sorted(binding_payloads, key=lambda item: item["id"]),
    }
    return {**payload, "overlay_hash": _overlay_hash(payload)}


def _split_project_edges(edges: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    requires = []
    related = []
    for edge in edges:
        if edge["relation_type"] == "REQUIRES":
            requires.append(edge)
        elif edge["relation_type"] == "RELATED_TO":
            related.append(edge)
    return requires, related


async def _run_projection(tx: Any, payload: dict[str, Any]) -> dict[str, int]:
    project_id = payload["project_id"]
    domain = payload["domain"]
    nodes = payload["nodes"]
    edges = payload["edges"]
    resources = payload["resources"]
    bindings = payload["bindings"]
    node_ids = [node["id"] for node in nodes]
    resource_ids = [resource["id"] for resource in resources]
    requires_edges, related_edges = _split_project_edges(edges)

    await tx.run(
        """
        MATCH ()-[r]->()
        WHERE r.project_id = $project_id AND r.owner = $owner
        DELETE r
        """,
        project_id=project_id,
        owner=PROJECT_OVERLAY_OWNER,
    )
    await tx.run(
        f"""
        MATCH (n:{PROJECT_NODE_LABEL})
        WHERE n.project_id = $project_id AND NOT n.overlay_id IN $node_ids
        DETACH DELETE n
        """,
        project_id=project_id,
        node_ids=node_ids,
    )
    await tx.run(
        f"""
        MATCH (r:{PROJECT_RESOURCE_LABEL})
        WHERE r.project_id = $project_id AND NOT r.overlay_id IN $resource_ids
        DETACH DELETE r
        """,
        project_id=project_id,
        resource_ids=resource_ids,
    )
    await tx.run(
        f"""
        UNWIND $nodes AS node
        MERGE (n:{PROJECT_NODE_LABEL} {{project_id: node.project_id, overlay_id: node.overlay_id}})
        SET n += node,
            n.projected_at = datetime()
        """,
        nodes=nodes,
    )
    await tx.run(
        f"""
        UNWIND $resources AS resource
        MERGE (r:{PROJECT_RESOURCE_LABEL} {{project_id: resource.project_id, overlay_id: resource.overlay_id}})
        SET r += resource,
            r.projected_at = datetime()
        """,
        resources=resources,
    )
    await _project_edges(tx, relationship_type=PROJECT_REQUIRES_RELATIONSHIP, edges=requires_edges, domain=domain)
    await _project_edges(tx, relationship_type=PROJECT_RELATED_RELATIONSHIP, edges=related_edges, domain=domain)
    await _project_node_resource_bindings(tx, bindings=bindings, domain=domain)
    return {
        "nodes": len(nodes) + len(resources),
        "edges": len(edges) + len([binding for binding in bindings if binding["target_type"] == "project_node"]),
    }


async def _project_edges(
    tx: Any,
    *,
    relationship_type: str,
    edges: list[dict[str, Any]],
    domain: str,
) -> None:
    await tx.run(
        f"""
        UNWIND $edges AS edge
        OPTIONAL MATCH (source_overlay:{PROJECT_NODE_LABEL} {{project_id: edge.project_id, overlay_id: edge.source}})
        OPTIONAL MATCH (source_base:KnowledgeNode {{id: edge.source, domain: $domain}})
        OPTIONAL MATCH (target_overlay:{PROJECT_NODE_LABEL} {{project_id: edge.project_id, overlay_id: edge.target}})
        OPTIONAL MATCH (target_base:KnowledgeNode {{id: edge.target, domain: $domain}})
        WITH edge, coalesce(source_overlay, source_base) AS source, coalesce(target_overlay, target_base) AS target
        WHERE source IS NOT NULL AND target IS NOT NULL
        MERGE (source)-[rel:{relationship_type} {{project_id: edge.project_id, overlay_id: edge.overlay_id}}]->(target)
        SET rel += edge,
            rel.domain = $domain,
            rel.projected_at = datetime()
        """,
        domain=domain,
        edges=edges,
    )


async def _project_node_resource_bindings(
    tx: Any,
    *,
    bindings: list[dict[str, Any]],
    domain: str,
) -> None:
    node_bindings = [binding for binding in bindings if binding["target_type"] == "project_node"]
    await tx.run(
        f"""
        UNWIND $bindings AS binding
        MATCH (resource:{PROJECT_RESOURCE_LABEL} {{project_id: binding.project_id, overlay_id: binding.resource_id}})
        OPTIONAL MATCH (target_overlay:{PROJECT_NODE_LABEL} {{
            project_id: binding.project_id,
            overlay_id: binding.target_id
        }})
        OPTIONAL MATCH (target_base:KnowledgeNode {{id: binding.target_id, domain: $domain}})
        WITH binding, resource, coalesce(target_overlay, target_base) AS target
        WHERE target IS NOT NULL
        MERGE (resource)-[rel:{PROJECT_RESOURCE_NODE_RELATIONSHIP} {{
            project_id: binding.project_id,
            overlay_id: binding.id
        }}]->(target)
        SET rel += binding,
            rel.domain = $domain,
            rel.projected_at = datetime()
        """,
        domain=domain,
        bindings=node_bindings,
    )


async def build_project_overlay_projection_payload(
    db: AsyncSession,
    project_id: str,
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError("PROJECT_NOT_FOUND")
    resources = await list_active_project_overlay_resources(db, project_id)
    resource_ids = {resource.resource_id for resource in resources}
    bindings = [
        binding
        for binding in await list_resource_bindings(db, project_id)
        if binding.resource_id in resource_ids
    ]
    return build_overlay_projection_payload(
        project_id=project_id,
        domain=project.domain,
        nodes=await list_active_project_overlay_nodes(db, project_id),
        edges=await list_active_project_overlay_edges(db, project_id),
        resources=resources,
        bindings=bindings,
    )


def _payload_has_overlay(payload: dict[str, Any]) -> bool:
    return bool(payload["nodes"] or payload["edges"] or payload["resources"] or payload["bindings"])


def _projection_status_response(
    *,
    project_id: str,
    status: ProjectionStatus,
    overlay_hash: str,
    projected_hash: str | None,
    reason: str,
    projected_at: Any = None,
) -> dict[str, Any]:
    response = {
        "project_id": project_id,
        "status": status,
        "ready": status in {PROJECTION_STATUS_EMPTY, PROJECTION_STATUS_OK},
        "in_sync": status in {PROJECTION_STATUS_EMPTY, PROJECTION_STATUS_OK},
        "overlay_hash": overlay_hash,
        "projected_hash": projected_hash,
        "reason": reason,
    }
    if projected_at is not None:
        response["projected_at"] = projected_at
    return response


def _canonical_projection_status(
    *,
    has_overlay: bool,
    state: Any,
    overlay_hash: str,
) -> tuple[ProjectionStatus, str]:
    if not has_overlay:
        return PROJECTION_STATUS_EMPTY, "no_overlay"
    if state is None:
        return PROJECTION_STATUS_MISSING, "projection_missing"
    if state.status == PROJECTION_STATUS_ERROR:
        return PROJECTION_STATUS_ERROR, state.error_message or "overlay_projection_error"
    if state.overlay_hash != overlay_hash:
        return PROJECTION_STATUS_DRIFTED, state.error_message or "overlay_projection_drifted"
    if state.status == PROJECTION_STATUS_OK:
        return PROJECTION_STATUS_OK, "synced"
    if state.status == PROJECTION_STATUS_EMPTY:
        return PROJECTION_STATUS_DRIFTED, "overlay_projection_drifted"
    return PROJECTION_STATUS_DRIFTED, state.error_message or "overlay_projection_drifted"


async def get_project_overlay_projection_status(
    db: AsyncSession,
    project_id: str,
) -> dict[str, Any]:
    try:
        payload = await build_project_overlay_projection_payload(db, project_id)
        state = await get_projection_state(db, project_id)
        status, reason = _canonical_projection_status(
            has_overlay=_payload_has_overlay(payload),
            state=state,
            overlay_hash=payload["overlay_hash"],
        )
        return _projection_status_response(
            project_id=project_id,
            status=status,
            overlay_hash=payload["overlay_hash"],
            projected_hash=state.overlay_hash if state is not None else None,
            reason=reason,
            projected_at=state.projected_at if state is not None else None,
        )
    except Exception as exc:
        return _projection_status_response(
            project_id=project_id,
            status=PROJECTION_STATUS_ERROR,
            overlay_hash="",
            projected_hash=None,
            reason=str(exc),
        )


async def sync_project_overlay_projection(
    db: AsyncSession,
    driver: Neo4jDriver,
    project_id: str,
    *,
    commit: bool = True,
) -> dict[str, Any]:
    payload = await build_project_overlay_projection_payload(db, project_id)
    state = await get_projection_state(db, project_id)
    has_overlay = _payload_has_overlay(payload)
    synced_status = PROJECTION_STATUS_OK if has_overlay else PROJECTION_STATUS_EMPTY
    node_count = len(payload["nodes"]) + len(payload["resources"])
    edge_count = len(payload["edges"]) + len(payload["bindings"])
    if state is not None and state.status == synced_status and state.overlay_hash == payload["overlay_hash"]:
        return {
            "project_id": project_id,
            "synced": False,
            "status": synced_status,
            "reason": "unchanged",
            "overlay_hash": payload["overlay_hash"],
            "projected_hash": state.overlay_hash,
            "nodes": node_count,
            "edges": edge_count,
        }

    try:
        result = await driver.execute_write(lambda tx: _run_projection(tx, payload))
    except Exception as exc:
        await upsert_projection_state(
            db,
            project_id=project_id,
            status=PROJECTION_STATUS_ERROR,
            overlay_hash=payload["overlay_hash"],
            error_message=str(exc),
            commit=commit,
        )
        return {
            "project_id": project_id,
            "synced": False,
            "status": PROJECTION_STATUS_ERROR,
            "reason": str(exc),
            "overlay_hash": payload["overlay_hash"],
            "projected_hash": None,
            "nodes": node_count,
            "edges": edge_count,
        }

    await upsert_projection_state(
        db,
        project_id=project_id,
        status=synced_status,
        overlay_hash=payload["overlay_hash"],
        error_message=None,
        commit=commit,
    )
    return {
        "project_id": project_id,
        "synced": True,
        "status": synced_status,
        "reason": "projected" if has_overlay else "no_overlay",
        "overlay_hash": payload["overlay_hash"],
        "projected_hash": payload["overlay_hash"],
        **result,
    }
