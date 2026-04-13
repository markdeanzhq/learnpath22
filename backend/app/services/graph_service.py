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
