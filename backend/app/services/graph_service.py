"""图谱查询服务：返回 Cytoscape.js 兼容格式"""
from __future__ import annotations

import logging
from collections import OrderedDict
from copy import deepcopy
from typing import TYPE_CHECKING, Any

from app.core.exceptions import AppError
from app.db.neo4j import Neo4jDriver
from app.services.domain_pack_service import DomainPackService

if TYPE_CHECKING:
    from app.services.project_graph_snapshot_service import ProjectGraphSnapshot

GRAPH_SCOPE_DOMAIN = "domain"
GRAPH_SCOPE_PROJECT = "project"
GRAPH_SCOPE_PATH = "path"
VALID_GRAPH_SCOPES = {GRAPH_SCOPE_DOMAIN, GRAPH_SCOPE_PROJECT, GRAPH_SCOPE_PATH}

logger = logging.getLogger(__name__)

_PACK_GRAPH_ELEMENTS_CACHE_MAX_SIZE = 16
_PackGraphElementsCacheKey = tuple[str, str, str]
_pack_graph_elements_cache: OrderedDict[_PackGraphElementsCacheKey, dict[str, Any]] = OrderedDict()
_pack_graph_elements_cache_stats = {
    "hits": 0,
    "misses": 0,
    "stores": 0,
    "clears": 0,
}


def get_pack_graph_elements_cache_stats() -> dict[str, int]:
    return dict(_pack_graph_elements_cache_stats)


def _record_pack_graph_cache_event(event: str) -> None:
    _pack_graph_elements_cache_stats[event] = _pack_graph_elements_cache_stats.get(event, 0) + 1


def clear_pack_graph_elements_cache(domain: str | None = None) -> None:
    _record_pack_graph_cache_event("clears")
    if domain is None:
        _pack_graph_elements_cache.clear()
        return
    for cache_key in list(_pack_graph_elements_cache):
        if cache_key[0] == domain:
            del _pack_graph_elements_cache[cache_key]


def _pack_graph_cache_key(pack: DomainPackService, scope: str) -> _PackGraphElementsCacheKey:
    return (pack.domain, pack.pack_hash, scope)


def _can_cache_pack_graph_elements(
    *,
    overlay_nodes: list[Any] | None,
    overlay_edges: list[Any] | None,
    removed_node_ids: set[str] | None,
    removed_edge_ids: set[str] | None,
) -> bool:
    return not overlay_nodes and not overlay_edges and not removed_node_ids and not removed_edge_ids


def _remember_pack_graph_elements(
    cache_key: _PackGraphElementsCacheKey,
    graph_data: dict[str, Any],
) -> None:
    _record_pack_graph_cache_event("stores")
    _pack_graph_elements_cache[cache_key] = deepcopy(graph_data)
    _pack_graph_elements_cache.move_to_end(cache_key)
    while len(_pack_graph_elements_cache) > _PACK_GRAPH_ELEMENTS_CACHE_MAX_SIZE:
        _pack_graph_elements_cache.popitem(last=False)


def build_edge_review_id(source: str, target: str, rel_type: str) -> str:
    return f"{source}->{target}::{rel_type}"


def _build_node_element(node: dict[str, Any], *, scope: str, origin: str = "baseline") -> dict[str, Any]:
    data = {
        "id": node.get("id"),
        "label": node.get("name"),
        "category": node.get("category"),
        "group_id": node.get("group_id") or node.get("group"),
        "difficulty": node.get("difficulty") or node.get("difficulty_final"),
        "importance": node.get("importance") or node.get("importance_final"),
        "estimated_hours": node.get("estimated_hours"),
        "is_main_path": node.get("is_main_path", False),
        "origin": origin,
        "scope": scope,
    }
    if origin == "overlay":
        data.update({key: node.get(key) for key in _OVERLAY_LIFECYCLE_FIELDS})
        data.update(
            {
                "promotion_status": node.get("promotion_status"),
                "source_ids": node.get("source_ids", []),
                "provenance": node.get("provenance", {}),
                "validation_errors": node.get("validation_errors", []),
                "confidence": node.get("confidence"),
            }
        )
    return {"group": "nodes", "data": data}


def _build_edge_element(edge: dict[str, Any], *, scope: str, origin: str = "baseline") -> dict[str, Any]:
    rel_type = edge.get("rel_type") or edge.get("type")
    edge_id = edge.get("id") or build_edge_review_id(edge["source"], edge["target"], rel_type)
    data = {
        "id": edge_id,
        "source": edge["source"],
        "target": edge["target"],
        "type": rel_type,
        "reason": edge.get("reason", ""),
        "origin": origin,
        "scope": scope,
    }
    if origin == "overlay":
        data.update({key: edge.get(key) for key in _OVERLAY_LIFECYCLE_FIELDS})
        data.update(
            {
                "promotion_status": edge.get("promotion_status"),
                "source_ids": edge.get("source_ids", []),
                "provenance": edge.get("provenance", {}),
                "validation_errors": edge.get("validation_errors", []),
                "confidence": edge.get("confidence"),
            }
        )
    return {"group": "edges", "data": data}


_OVERLAY_LIFECYCLE_FIELDS = ("validation_status", "review_status", "planning_enabled")


def _load_json(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        import json

        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _overlay_node_to_element(node: Any, *, scope: str) -> dict[str, Any]:
    provenance = _load_json(node.provenance_json, {})
    return _build_node_element(
        {
            "id": node.node_id,
            "name": node.name or node.node_id,
            "group": node.group,
            "category": node.category,
            "difficulty_final": node.difficulty_final,
            "importance_final": node.importance_final,
            "estimated_hours": node.estimated_hours,
            "validation_status": node.validation_status,
            "review_status": node.review_status,
            "planning_enabled": node.planning_enabled,
            "promotion_status": node.promotion_status,
            "source_ids": _load_json(node.source_ids_json, []),
            "provenance": provenance,
            "validation_errors": _load_json(node.validation_errors_json, []),
            "confidence": node.confidence,
        },
        scope=scope,
        origin="overlay",
    )


def _overlay_edge_to_element(edge: Any, *, scope: str) -> dict[str, Any]:
    return _build_edge_element(
        {
            "id": edge.edge_id,
            "source": edge.source_node_id,
            "target": edge.target_node_id,
            "type": edge.relation_type,
            "validation_status": edge.validation_status,
            "review_status": edge.review_status,
            "planning_enabled": edge.planning_enabled,
            "promotion_status": edge.promotion_status,
            "source_ids": _load_json(edge.source_ids_json, []),
            "provenance": _load_json(edge.provenance_json, {}),
            "validation_errors": _load_json(edge.validation_errors_json, []),
            "confidence": edge.confidence,
        },
        scope=scope,
        origin="overlay",
    )


def _snapshot_overlay_node_to_element(
    node: dict[str, Any],
    *,
    scope: str,
    lineage: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage_data = lineage if isinstance(lineage, dict) else {}
    payload = dict(node)
    payload.update(
        {
            "validation_status": lineage_data.get("validation_status"),
            "review_status": lineage_data.get("review_status"),
            "planning_enabled": lineage_data.get("planning_enabled"),
            "promotion_status": lineage_data.get("promotion_status"),
            "source_ids": lineage_data.get("source_ids", []),
            "provenance": lineage_data.get("provenance", {}),
            "validation_errors": lineage_data.get("validation_errors", []),
            "confidence": lineage_data.get("confidence"),
        }
    )
    return _build_node_element(payload, scope=scope, origin="overlay")


def _snapshot_overlay_edge_to_element(
    edge: dict[str, Any],
    *,
    relation_type: str,
    scope: str,
    lineage: dict[str, Any] | None,
) -> dict[str, Any]:
    lineage_data = lineage if isinstance(lineage, dict) else {}
    payload = dict(edge)
    payload.update(
        {
            "id": payload.get("overlay_id")
            or payload.get("id")
            or lineage_data.get("edge_id")
            or build_edge_review_id(
                payload["source"],
                payload["target"],
                payload.get("type") or relation_type,
            ),
            "type": payload.get("type") or relation_type,
            "validation_status": lineage_data.get("validation_status"),
            "review_status": lineage_data.get("review_status"),
            "planning_enabled": lineage_data.get("planning_enabled"),
            "promotion_status": lineage_data.get("promotion_status"),
            "source_ids": lineage_data.get("source_ids", []),
            "provenance": lineage_data.get("provenance", {}),
            "validation_errors": lineage_data.get("validation_errors", []),
            "confidence": lineage_data.get("confidence"),
            "reason": payload.get("reason") or lineage_data.get("legality_rationale", ""),
            "legality_rationale": lineage_data.get("legality_rationale"),
        }
    )
    return _build_edge_element(payload, scope=scope, origin="overlay")


async def get_graph_elements(
    driver: Neo4jDriver,
    scope: str = GRAPH_SCOPE_DOMAIN,
    node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按 scope 返回 baseline 图谱数据（Cytoscape.js elements 格式）。"""
    if scope not in {GRAPH_SCOPE_DOMAIN, GRAPH_SCOPE_PATH}:
        raise AppError(code=422, message="INVALID_GRAPH_SCOPE")

    if scope == GRAPH_SCOPE_PATH:
        return await _get_subgraph_elements(driver, node_ids or [], scope=scope)

    return await _get_full_graph_elements(driver, scope=scope)


def build_project_graph_elements(
    pack: DomainPackService,
    *,
    overlay_nodes: list[Any] | None = None,
    overlay_edges: list[Any] | None = None,
    removed_node_ids: set[str] | None = None,
    removed_edge_ids: set[str] | None = None,
    scope: str = GRAPH_SCOPE_PROJECT,
) -> dict[str, Any]:
    cache_key = None
    if _can_cache_pack_graph_elements(
        overlay_nodes=overlay_nodes,
        overlay_edges=overlay_edges,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
    ):
        cache_key = _pack_graph_cache_key(pack, scope)
        cached_graph = _pack_graph_elements_cache.get(cache_key)
        if cached_graph is not None:
            _record_pack_graph_cache_event("hits")
            logger.debug(
                "pack_graph_elements_cache_hit domain=%s scope=%s",
                pack.domain,
                scope,
            )
            _pack_graph_elements_cache.move_to_end(cache_key)
            return deepcopy(cached_graph)
        _record_pack_graph_cache_event("misses")
        logger.debug(
            "pack_graph_elements_cache_miss domain=%s scope=%s",
            pack.domain,
            scope,
        )

    removed_nodes = removed_node_ids or set()
    removed_edges = removed_edge_ids or set()
    nodes_by_id = {
        node_id: node
        for node_id, node in pack.nodes_by_id.items()
        if node_id not in removed_nodes
    }
    overlay_node_ids = {node.node_id for node in overlay_nodes or []}
    visible_node_ids = set(nodes_by_id) | overlay_node_ids

    elements = [
        _build_node_element(node, scope=scope)
        for _, node in sorted(nodes_by_id.items())
    ]
    elements.extend(_overlay_node_to_element(node, scope=scope) for node in overlay_nodes or [])

    baseline_edges = []
    for relation_type, edges in (("REQUIRES", pack.requires_edges), ("RELATED_TO", pack.related_edges)):
        for edge in edges:
            edge_id = build_edge_review_id(edge["source"], edge["target"], relation_type)
            if edge_id in removed_edges:
                continue
            if edge["source"] not in visible_node_ids or edge["target"] not in visible_node_ids:
                continue
            baseline_edges.append({**edge, "rel_type": relation_type})

    elements.extend(
        _build_edge_element(edge, scope=scope)
        for edge in sorted(baseline_edges, key=lambda item: (item["source"], item["target"], item["rel_type"]))
    )
    elements.extend(_overlay_edge_to_element(edge, scope=scope) for edge in overlay_edges or [])

    graph_data = {"scope": scope, "elements": elements, "is_empty": len(elements) == 0}
    if cache_key is not None:
        _remember_pack_graph_elements(cache_key, graph_data)
    return graph_data


def _empty_induced_graph_response(
    *,
    path_id: str | None,
    requested_node_ids: list[str],
    missing_node_ids: list[str],
) -> dict[str, Any]:
    graph_data: dict[str, Any] = {
        "scope": GRAPH_SCOPE_PATH,
        "path_id": path_id,
        "elements": [],
        "node_ids": requested_node_ids,
        "missing_node_ids": missing_node_ids,
        "is_empty": True,
    }
    if missing_node_ids and requested_node_ids:
        graph_data["empty_reason"] = "path_nodes_missing"
    return graph_data


def build_path_graph_elements_from_snapshot(
    snapshot: "ProjectGraphSnapshot",
    *,
    node_ids: list[str],
    path_id: str | None,
) -> dict[str, Any]:
    requested_node_ids = sorted(set(node_ids))
    visible_node_ids = [
        node_id for node_id in requested_node_ids if node_id in snapshot.nodes_by_id
    ]
    visible_node_id_set = set(visible_node_ids)
    missing_node_ids = sorted(set(requested_node_ids) - visible_node_id_set)
    overlay_nodes = (snapshot.overlay_lineage or {}).get("nodes") or {}
    overlay_edges = (snapshot.overlay_lineage or {}).get("edges") or {}

    elements: list[dict[str, Any]] = []
    for node_id in visible_node_ids:
        node = snapshot.nodes_by_id[node_id]
        if node.get("origin") == "overlay":
            elements.append(
                _snapshot_overlay_node_to_element(
                    node,
                    scope=GRAPH_SCOPE_PATH,
                    lineage=overlay_nodes.get(node_id),
                )
            )
            continue
        elements.append(_build_node_element(node, scope=GRAPH_SCOPE_PATH))

    for relation_type, edges in (
        ("REQUIRES", snapshot.requires_edges),
        ("RELATED_TO", snapshot.related_edges),
    ):
        for edge in edges:
            if (
                edge["source"] not in visible_node_id_set
                or edge["target"] not in visible_node_id_set
            ):
                continue
            if edge.get("origin") == "overlay":
                elements.append(
                    _snapshot_overlay_edge_to_element(
                        edge,
                        relation_type=relation_type,
                        scope=GRAPH_SCOPE_PATH,
                        lineage=overlay_edges.get(edge.get("overlay_id", "")),
                    )
                )
                continue
            elements.append(
                _build_edge_element(
                    {
                        **edge,
                        "rel_type": edge.get("rel_type")
                        or edge.get("type")
                        or relation_type,
                    },
                    scope=GRAPH_SCOPE_PATH,
                )
            )

    if not elements:
        return _empty_induced_graph_response(
            path_id=path_id,
            requested_node_ids=requested_node_ids,
            missing_node_ids=missing_node_ids,
        )
    return {
        "scope": GRAPH_SCOPE_PATH,
        "path_id": path_id,
        "elements": elements,
        "node_ids": requested_node_ids,
        "missing_node_ids": missing_node_ids,
        "is_empty": False,
    }


def build_pack_subgraph_elements(
    pack: DomainPackService,
    *,
    node_ids: list[str],
) -> dict[str, Any]:
    requested_node_ids = sorted(set(node_ids))
    visible_node_ids = [
        node_id for node_id in requested_node_ids if node_id in pack.nodes_by_id
    ]
    visible_node_id_set = set(visible_node_ids)
    missing_node_ids = sorted(set(requested_node_ids) - visible_node_id_set)

    elements: list[dict[str, Any]] = [
        _build_node_element(pack.nodes_by_id[node_id], scope=GRAPH_SCOPE_PATH)
        for node_id in visible_node_ids
    ]

    baseline_edges: list[dict[str, Any]] = []
    for relation_type, edges in (
        ("REQUIRES", pack.requires_edges),
        ("RELATED_TO", pack.related_edges),
    ):
        for edge in edges:
            if edge["source"] in visible_node_id_set and edge["target"] in visible_node_id_set:
                baseline_edges.append({**edge, "rel_type": relation_type})

    elements.extend(
        _build_edge_element(edge, scope=GRAPH_SCOPE_PATH)
        for edge in sorted(
            baseline_edges,
            key=lambda item: (item["source"], item["target"], item["rel_type"]),
        )
    )

    if not elements:
        return _empty_induced_graph_response(
            path_id=None,
            requested_node_ids=requested_node_ids,
            missing_node_ids=missing_node_ids,
        )
    return {
        "scope": GRAPH_SCOPE_PATH,
        "path_id": None,
        "elements": elements,
        "node_ids": requested_node_ids,
        "missing_node_ids": missing_node_ids,
        "is_empty": False,
    }


async def _get_full_graph_elements(
    driver: Neo4jDriver,
    scope: str,
) -> dict[str, Any]:
    try:
        nodes_data = await driver.execute_query(
            "MATCH (n:KnowledgeNode) RETURN n ORDER BY n.id"
        )
        edges_data = await driver.execute_query(
            "MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode) "
            "RETURN a.id AS source, b.id AS target, "
            "type(r) AS rel_type, r.reason AS reason "
            "ORDER BY source, target"
        )
    except Exception as exc:
        raise AppError(code=500, message=f"图谱查询失败: {exc}") from exc

    elements = [
        *[_build_node_element(record.get("n", {}), scope=scope) for record in nodes_data],
        *[_build_edge_element(record, scope=scope) for record in edges_data],
    ]
    return {"scope": scope, "elements": elements, "is_empty": len(elements) == 0}


async def _get_subgraph_elements(
    driver: Neo4jDriver,
    node_ids: list[str],
    scope: str,
) -> dict[str, Any]:
    try:
        nodes_data = await driver.execute_query(
            "MATCH (n:KnowledgeNode) WHERE n.id IN $ids RETURN n ORDER BY n.id",
            {"ids": node_ids},
        )
        edges_data = await driver.execute_query(
            "MATCH (a:KnowledgeNode)-[r]->(b:KnowledgeNode) "
            "WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN a.id AS source, b.id AS target, "
            "type(r) AS rel_type, r.reason AS reason "
            "ORDER BY source, target",
            {"ids": node_ids},
        )
    except Exception as exc:
        raise AppError(code=500, message=f"项目子图查询失败: {exc}") from exc

    elements = [
        *[_build_node_element(record.get("n", {}), scope=scope) for record in nodes_data],
        *[_build_edge_element(record, scope=scope) for record in edges_data],
    ]
    return {
        "scope": scope,
        "elements": elements,
        "node_ids": sorted(set(node_ids)),
        "is_empty": len(elements) == 0,
    }


async def get_full_graph(driver: Neo4jDriver) -> dict[str, Any]:
    return await get_graph_elements(driver, scope=GRAPH_SCOPE_DOMAIN)


async def get_path_subgraph(
    driver: Neo4jDriver, node_ids: list[str]
) -> dict[str, Any]:
    return await get_graph_elements(driver, scope=GRAPH_SCOPE_PATH, node_ids=node_ids)


def build_graph_entity_metadata_from_pack(
    pack: DomainPackService,
    *,
    include_empty: bool = True,
) -> dict[str, Any]:
    ordered_stages = sorted(
        pack.stages,
        key=lambda stage: (stage["order"], stage["id"]),
    )
    stages = [
        {
            "id": stage["id"],
            "name": stage["name"],
            "order": stage["order"],
            "description": stage.get("description", ""),
            "category_keys": list(stage.get("category_keys", [])),
            "node_ids": sorted(set(stage.get("node_ids", []))),
            "resource_ids": [],
        }
        for stage in ordered_stages
    ]
    stages_by_id = {stage["id"]: stage for stage in stages}

    resources = [
        {
            "id": resource["id"],
            "title": resource["title"],
            "resource_type": resource["resource_type"],
            "description": resource.get("description", ""),
            "stage_ids": sorted(set(resource.get("stage_ids", []))),
            "node_ids": sorted(set(resource.get("node_ids", []))),
        }
        for resource in sorted(pack.resources, key=lambda resource: resource["id"])
    ]

    stage_sequences = sorted(
        [
            {
                "source": previous["id"],
                "target": current["id"],
                "type": "PRECEDES",
            }
            for previous, current in zip(ordered_stages, ordered_stages[1:])
        ],
        key=lambda edge: (edge["source"], edge["target"]),
    )
    stage_nodes = sorted(
        [
            {
                "stage_id": stage["id"],
                "node_id": node_id,
                "type": "CONTAINS",
            }
            for stage in ordered_stages
            for node_id in sorted(set(stage.get("node_ids", [])))
        ],
        key=lambda edge: (edge["stage_id"], edge["node_id"]),
    )
    stage_resources = sorted(
        [
            {
                "stage_id": stage_id,
                "resource_id": resource["id"],
                "type": "HAS_RESOURCE",
            }
            for resource in resources
            for stage_id in resource["stage_ids"]
        ],
        key=lambda edge: (edge["stage_id"], edge["resource_id"]),
    )
    resource_nodes = sorted(
        [
            {
                "resource_id": resource["id"],
                "node_id": node_id,
                "type": "COVERS",
            }
            for resource in resources
            for node_id in resource["node_ids"]
        ],
        key=lambda edge: (edge["resource_id"], edge["node_id"]),
    )

    for edge in stage_resources:
        stage = stages_by_id.get(edge["stage_id"])
        if stage is not None:
            stage["resource_ids"].append(edge["resource_id"])

    for stage in stages:
        stage["resource_ids"].sort()

    metadata = {
        "domain": pack.domain,
        "stages": stages,
        "resources": resources,
        "relationships": {
            "stage_sequences": stage_sequences,
            "stage_nodes": stage_nodes,
            "stage_resources": stage_resources,
            "resource_nodes": resource_nodes,
        },
    }
    if include_empty:
        metadata["is_empty"] = len(stages) == 0 and len(resources) == 0
    return metadata


async def get_graph_entity_metadata(
    driver: Neo4jDriver,
    domain: str,
) -> dict[str, Any]:
    stages_data = await driver.execute_query(
        "MATCH (s:Stage) WHERE s.domain = $domain RETURN s ORDER BY s.order, s.id",
        {"domain": domain},
    )
    resources_data = await driver.execute_query(
        "MATCH (r:Resource) WHERE r.domain = $domain RETURN r ORDER BY r.id",
        {"domain": domain},
    )
    stage_sequence_data = await driver.execute_query(
        "MATCH (a:Stage)-[:PRECEDES]->(b:Stage) "
        "WHERE a.domain = $domain AND b.domain = $domain "
        "RETURN a.id AS source, b.id AS target ORDER BY source, target",
        {"domain": domain},
    )
    stage_node_data = await driver.execute_query(
        "MATCH (s:Stage)-[:CONTAINS]->(n:KnowledgeNode) "
        "WHERE s.domain = $domain AND n.domain = $domain "
        "RETURN s.id AS stage_id, n.id AS node_id ORDER BY stage_id, node_id",
        {"domain": domain},
    )
    stage_resource_data = await driver.execute_query(
        "MATCH (s:Stage)-[:HAS_RESOURCE]->(r:Resource) "
        "WHERE s.domain = $domain AND r.domain = $domain "
        "RETURN s.id AS stage_id, r.id AS resource_id ORDER BY stage_id, resource_id",
        {"domain": domain},
    )
    resource_node_data = await driver.execute_query(
        "MATCH (r:Resource)-[:COVERS]->(n:KnowledgeNode) "
        "WHERE r.domain = $domain AND n.domain = $domain "
        "RETURN r.id AS resource_id, n.id AS node_id ORDER BY resource_id, node_id",
        {"domain": domain},
    )

    stages = [
        {
            "id": record["s"].get("id"),
            "name": record["s"].get("name"),
            "order": record["s"].get("order"),
            "description": record["s"].get("description", ""),
            "category_keys": record["s"].get("category_keys", []),
            "node_ids": [],
            "resource_ids": [],
        }
        for record in stages_data
    ]
    resources = [
        {
            "id": record["r"].get("id"),
            "title": record["r"].get("title"),
            "resource_type": record["r"].get("resource_type"),
            "description": record["r"].get("description", ""),
            "stage_ids": [],
            "node_ids": [],
        }
        for record in resources_data
    ]

    stages_by_id = {stage["id"]: stage for stage in stages}
    resources_by_id = {resource["id"]: resource for resource in resources}

    stage_sequences = [
        {"source": record["source"], "target": record["target"], "type": "PRECEDES"}
        for record in stage_sequence_data
    ]
    stage_nodes = [
        {"stage_id": record["stage_id"], "node_id": record["node_id"], "type": "CONTAINS"}
        for record in stage_node_data
    ]
    stage_resources = [
        {
            "stage_id": record["stage_id"],
            "resource_id": record["resource_id"],
            "type": "HAS_RESOURCE",
        }
        for record in stage_resource_data
    ]
    resource_nodes = [
        {
            "resource_id": record["resource_id"],
            "node_id": record["node_id"],
            "type": "COVERS",
        }
        for record in resource_node_data
    ]

    for relation in stage_nodes:
        stage = stages_by_id.get(relation["stage_id"])
        if stage is not None:
            stage["node_ids"].append(relation["node_id"])

    for relation in stage_resources:
        stage = stages_by_id.get(relation["stage_id"])
        resource = resources_by_id.get(relation["resource_id"])
        if stage is not None:
            stage["resource_ids"].append(relation["resource_id"])
        if resource is not None:
            resource["stage_ids"].append(relation["stage_id"])

    for relation in resource_nodes:
        resource = resources_by_id.get(relation["resource_id"])
        if resource is not None:
            resource["node_ids"].append(relation["node_id"])

    for stage in stages:
        stage["node_ids"].sort()
        stage["resource_ids"].sort()

    for resource in resources:
        resource["stage_ids"].sort()
        resource["node_ids"].sort()

    return {
        "domain": domain,
        "stages": stages,
        "resources": resources,
        "relationships": {
            "stage_sequences": stage_sequences,
            "stage_nodes": stage_nodes,
            "stage_resources": stage_resources,
            "resource_nodes": resource_nodes,
        },
        "is_empty": len(stages) == 0 and len(resources) == 0,
    }
