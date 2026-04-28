from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.graph_review_repository import get_removed_edge_ids, get_removed_node_ids
from app.repositories.project_overlay_repository import (
    list_planner_visible_edges,
    list_planner_visible_nodes,
)
from app.repositories.project_repository import get_project
from app.services.domain_pack_service import DomainPackService, get_domain_pack_service


@dataclass(frozen=True)
class ProjectGraphSnapshot:
    domain: str
    manifest: dict[str, Any]
    nodes: list[dict[str, Any]]
    nodes_by_id: dict[str, dict[str, Any]]
    requires_edges: list[dict[str, Any]]
    related_edges: list[dict[str, Any]]
    requires_adj: dict[str, list[str]]
    requires_rev_adj: dict[str, list[str]]
    related_adj: dict[str, list[str]]
    goal_templates: list[dict[str, Any]]
    scoring_config: dict[str, Any]
    stage_rules: dict[str, Any]
    stages: list[dict[str, Any]]
    resources: list[dict[str, Any]]
    pack_hash: str
    contract: Any
    removed_node_ids: set[str]
    removed_edge_ids: set[str]
    overlay_lineage: dict[str, Any]
    project_graph_hash: str


def _load_json(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _typed_edge_id(source: str, target: str, relation_type: str) -> str:
    return f"{source}->{target}::{relation_type}"


def _copy_pack_node(node: dict[str, Any]) -> dict[str, Any]:
    copied = dict(node)
    copied.setdefault("aliases", [])
    copied.setdefault("keywords", [])
    return copied


def _overlay_node_to_pack_node(node: Any) -> dict[str, Any]:
    provenance = _load_json(node.provenance_json, {})
    return {
        "id": node.node_id,
        "name": node.name or node.node_id,
        "group": node.group,
        "category": node.category,
        "difficulty_final": node.difficulty_final,
        "importance_final": node.importance_final,
        "estimated_hours": node.estimated_hours,
        "req_math": node.req_math,
        "req_coding": node.req_coding,
        "req_ml": node.req_ml,
        "theory_weight": node.theory_weight,
        "practice_weight": node.practice_weight,
        "aliases": [],
        "keywords": [],
        "description": provenance.get("summary") or node.name or "",
        "is_foundation": False,
        "is_main_path": False,
        "bridge_value": 0,
        "origin": "overlay",
    }


def _overlay_node_hash_payload(node: Any) -> dict[str, Any]:
    provenance = _load_json(node.provenance_json, {})
    return {
        "id": node.node_id,
        "name": node.name,
        "group": node.group,
        "category": node.category,
        "description": provenance.get("summary") or node.name or "",
        "difficulty_final": node.difficulty_final,
        "importance_final": node.importance_final,
        "estimated_hours": node.estimated_hours,
        "req_math": node.req_math,
        "req_coding": node.req_coding,
        "req_ml": node.req_ml,
        "theory_weight": node.theory_weight,
        "practice_weight": node.practice_weight,
    }


def _overlay_edge_hash_payload(edge: Any) -> dict[str, Any]:
    return {
        "id": edge.edge_id,
        "source": edge.source_node_id,
        "target": edge.target_node_id,
        "relation_type": edge.relation_type,
    }


def _overlay_node_lineage(node: Any) -> dict[str, Any]:
    return {
        "node_id": node.node_id,
        "session_id": node.session_id,
        "validation_status": node.validation_status,
        "review_status": node.review_status,
        "planning_enabled": node.planning_enabled,
        "promotion_status": node.promotion_status,
        "source_ids": _load_json(node.source_ids_json, []),
        "provenance": _load_json(node.provenance_json, {}),
        "validation_errors": _load_json(node.validation_errors_json, []),
        "confidence": node.confidence,
        "legality_rationale": node.legality_rationale,
        "node_snapshot": _overlay_node_to_pack_node(node),
    }


def _overlay_edge_lineage(edge: Any) -> dict[str, Any]:
    return {
        "edge_id": edge.edge_id,
        "session_id": edge.session_id,
        "validation_status": edge.validation_status,
        "review_status": edge.review_status,
        "planning_enabled": edge.planning_enabled,
        "promotion_status": edge.promotion_status,
        "source_ids": _load_json(edge.source_ids_json, []),
        "provenance": _load_json(edge.provenance_json, {}),
        "validation_errors": _load_json(edge.validation_errors_json, []),
        "confidence": edge.confidence,
        "legality_rationale": edge.legality_rationale,
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relation_type": edge.relation_type,
        "edge_snapshot": {
            "id": edge.edge_id,
            "source": edge.source_node_id,
            "target": edge.target_node_id,
            "type": edge.relation_type,
            "origin": "overlay",
            "overlay_id": edge.edge_id,
        },
    }


def _build_adjacency(edges: list[dict[str, Any]]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    adj: dict[str, list[str]] = defaultdict(list)
    rev_adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        source = edge["source"]
        target = edge["target"]
        adj[source].append(target)
        rev_adj[target].append(source)
    return (
        {node_id: sorted(targets) for node_id, targets in sorted(adj.items())},
        {node_id: sorted(sources) for node_id, sources in sorted(rev_adj.items())},
    )


def _build_related_adjacency(edges: list[dict[str, Any]]) -> dict[str, list[str]]:
    adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adj[edge["source"]].append(edge["target"])
    return {node_id: sorted(targets) for node_id, targets in sorted(adj.items())}


def _canonical_data(value: Any) -> Any:
    return json.loads(_canonical_json(value))


def _project_graph_hash_payload(
    *,
    baseline_nodes: list[dict[str, Any]],
    baseline_requires_edges: list[dict[str, Any]],
    baseline_related_edges: list[dict[str, Any]],
    removed_node_ids: set[str],
    removed_edge_ids: set[str],
    overlay_nodes: list[Any],
    overlay_edges: list[Any],
) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "baseline_nodes": sorted(
            (_canonical_data(node) for node in baseline_nodes),
            key=lambda item: item["id"],
        ),
        "baseline_requires_edges": sorted(
            (_canonical_data(edge) for edge in baseline_requires_edges),
            key=lambda item: (item["source"], item["target"], item.get("type", "REQUIRES")),
        ),
        "baseline_related_edges": sorted(
            (_canonical_data(edge) for edge in baseline_related_edges),
            key=lambda item: (item["source"], item["target"], item.get("type", "RELATED_TO")),
        ),
        "removed_node_ids": sorted(removed_node_ids),
        "removed_edge_ids": sorted(removed_edge_ids),
        "overlay_nodes": sorted(
            (_overlay_node_hash_payload(node) for node in overlay_nodes),
            key=lambda item: item["id"],
        ),
        "overlay_edges": sorted(
            (_overlay_edge_hash_payload(edge) for edge in overlay_edges),
            key=lambda item: item["id"],
        ),
    }


def build_project_graph_hash_from_parts(
    *,
    baseline_nodes: list[dict[str, Any]],
    baseline_requires_edges: list[dict[str, Any]],
    baseline_related_edges: list[dict[str, Any]],
    removed_node_ids: set[str],
    removed_edge_ids: set[str],
    overlay_nodes: list[Any],
    overlay_edges: list[Any],
) -> str:
    payload = _project_graph_hash_payload(
        baseline_nodes=baseline_nodes,
        baseline_requires_edges=baseline_requires_edges,
        baseline_related_edges=baseline_related_edges,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
        overlay_nodes=overlay_nodes,
        overlay_edges=overlay_edges,
    )
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


async def build_project_graph_snapshot(
    db: AsyncSession,
    project_id: str,
    *,
    domain: str | None = None,
    baseline_pack: DomainPackService | None = None,
    include_overlay: bool = True,
) -> ProjectGraphSnapshot:
    if baseline_pack is None:
        if domain is None:
            project = await get_project(db, project_id)
            domain = project.domain if project is not None else None
        baseline_pack = get_domain_pack_service(domain)

    removed_node_ids = await get_removed_node_ids(db, project_id)
    removed_edge_ids = await get_removed_edge_ids(db, project_id)
    overlay_nodes = await list_planner_visible_nodes(db, project_id) if include_overlay else []
    overlay_edges = await list_planner_visible_edges(db, project_id) if include_overlay else []

    nodes_by_id = {
        node_id: _copy_pack_node(node)
        for node_id, node in baseline_pack.nodes_by_id.items()
        if node_id not in removed_node_ids
    }

    for node in overlay_nodes:
        if node.node_id in nodes_by_id:
            raise ValueError("OVERLAY_ID_COLLISION")
        nodes_by_id[node.node_id] = _overlay_node_to_pack_node(node)

    requires_edges: list[dict[str, Any]] = []
    related_edges: list[dict[str, Any]] = []
    requires_seen: set[str] = set()
    related_seen: set[str] = set()

    for edge in baseline_pack.requires_edges:
        source = edge["source"]
        target = edge["target"]
        edge_id = _typed_edge_id(source, target, "REQUIRES")
        if source not in nodes_by_id or target not in nodes_by_id or edge_id in removed_edge_ids:
            continue
        requires_seen.add(edge_id)
        requires_edges.append(dict(edge))

    for edge in baseline_pack.related_edges:
        source = edge["source"]
        target = edge["target"]
        edge_id = _typed_edge_id(source, target, "RELATED_TO")
        if source not in nodes_by_id or target not in nodes_by_id or edge_id in removed_edge_ids:
            continue
        related_seen.add(edge_id)
        related_edges.append(dict(edge))

    active_overlay_edges = []
    for edge in overlay_edges:
        if edge.source_node_id not in nodes_by_id or edge.target_node_id not in nodes_by_id:
            continue
        relation_type = edge.relation_type
        edge_payload = {
            "source": edge.source_node_id,
            "target": edge.target_node_id,
            "type": relation_type,
            "origin": "overlay",
            "overlay_id": edge.edge_id,
        }
        semantic_edge_id = _typed_edge_id(edge.source_node_id, edge.target_node_id, relation_type)
        if relation_type == "REQUIRES" and semantic_edge_id not in requires_seen:
            requires_seen.add(semantic_edge_id)
            active_overlay_edges.append(edge)
            requires_edges.append(edge_payload)
        elif relation_type == "RELATED_TO" and semantic_edge_id not in related_seen:
            related_seen.add(semantic_edge_id)
            active_overlay_edges.append(edge)
            related_edges.append(edge_payload)

    requires_edges = sorted(
        requires_edges,
        key=lambda item: (item["source"], item["target"], item.get("type", "REQUIRES")),
    )
    related_edges = sorted(
        related_edges,
        key=lambda item: (item["source"], item["target"], item.get("type", "RELATED_TO")),
    )
    requires_adj, requires_rev_adj = _build_adjacency(requires_edges)

    overlay_lineage = {
        "nodes": {
            node.node_id: _overlay_node_lineage(node)
            for node in sorted(overlay_nodes, key=lambda item: item.node_id)
        },
        "edges": {
            edge.edge_id: _overlay_edge_lineage(edge)
            for edge in sorted(active_overlay_edges, key=lambda item: item.edge_id)
        },
    }
    project_graph_hash = build_project_graph_hash_from_parts(
        baseline_nodes=list(baseline_pack.nodes_by_id.values()),
        baseline_requires_edges=baseline_pack.requires_edges,
        baseline_related_edges=baseline_pack.related_edges,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
        overlay_nodes=overlay_nodes,
        overlay_edges=active_overlay_edges,
    )

    return ProjectGraphSnapshot(
        domain=baseline_pack.domain,
        manifest=baseline_pack.manifest,
        nodes=sorted(nodes_by_id.values(), key=lambda item: item["id"]),
        nodes_by_id=nodes_by_id,
        requires_edges=requires_edges,
        related_edges=related_edges,
        requires_adj=requires_adj,
        requires_rev_adj=requires_rev_adj,
        related_adj=_build_related_adjacency(related_edges),
        goal_templates=baseline_pack.goal_templates,
        scoring_config=baseline_pack.scoring_config,
        stage_rules=baseline_pack.stage_rules,
        stages=baseline_pack.stages,
        resources=baseline_pack.resources,
        pack_hash=baseline_pack.pack_hash,
        contract=baseline_pack.contract,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
        overlay_lineage=overlay_lineage,
        project_graph_hash=project_graph_hash,
    )


async def build_project_graph_hash(
    db: AsyncSession,
    project_id: str,
    pack_hash: str | None = None,
    *,
    domain: str | None = None,
) -> str:
    snapshot = await build_project_graph_snapshot(db, project_id, domain=domain)
    return snapshot.project_graph_hash
