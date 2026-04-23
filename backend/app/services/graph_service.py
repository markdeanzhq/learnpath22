"""图谱查询服务：返回 Cytoscape.js 兼容格式"""
from __future__ import annotations

from typing import Any

from app.core.exceptions import AppError
from app.db.neo4j import Neo4jDriver

GRAPH_SCOPE_DOMAIN = "domain"
GRAPH_SCOPE_PROJECT = "project"


def build_edge_review_id(source: str, target: str, rel_type: str) -> str:
    return f"{source}->{target}::{rel_type}"


def _build_node_element(node: dict[str, Any]) -> dict[str, Any]:
    return {
        "group": "nodes",
        "data": {
            "id": node.get("id"),
            "label": node.get("name"),
            "category": node.get("category"),
            "group_id": node.get("group_id") or node.get("group"),
            "difficulty": node.get("difficulty") or node.get("difficulty_final"),
            "importance": node.get("importance") or node.get("importance_final"),
            "estimated_hours": node.get("estimated_hours"),
            "is_main_path": node.get("is_main_path", False),
        },
    }


def _build_edge_element(edge: dict[str, Any]) -> dict[str, Any]:
    edge_id = build_edge_review_id(edge["source"], edge["target"], edge["rel_type"])
    return {
        "group": "edges",
        "data": {
            "id": edge_id,
            "source": edge["source"],
            "target": edge["target"],
            "type": edge["rel_type"],
            "reason": edge.get("reason", ""),
        },
    }


async def get_graph_elements(
    driver: Neo4jDriver,
    scope: str = GRAPH_SCOPE_DOMAIN,
    node_ids: list[str] | None = None,
) -> dict[str, Any]:
    """按 scope 返回图谱数据（Cytoscape.js elements 格式）。"""
    if scope not in {GRAPH_SCOPE_DOMAIN, GRAPH_SCOPE_PROJECT}:
        raise AppError(code=422, message="scope 仅支持 domain 或 project")

    if scope == GRAPH_SCOPE_PROJECT:
        if not node_ids:
            return {
                "scope": scope,
                "elements": [],
                "is_empty": True,
                "empty_reason": "project_latest_plan_missing",
                "message": "项目尚未生成学习路径，暂时无法返回项目相关子图",
            }
        return await _get_subgraph_elements(driver, node_ids, scope=scope)

    return await _get_full_graph_elements(driver, scope=scope)


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
        *[_build_node_element(record.get("n", {})) for record in nodes_data],
        *[_build_edge_element(record) for record in edges_data],
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
        *[_build_node_element(record.get("n", {})) for record in nodes_data],
        *[_build_edge_element(record) for record in edges_data],
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
    return await get_graph_elements(driver, scope=GRAPH_SCOPE_PROJECT, node_ids=node_ids)


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
