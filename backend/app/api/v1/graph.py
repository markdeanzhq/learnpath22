from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_neo4j
from app.core.exceptions import AppError, NotFoundError
from app.db.neo4j import Neo4jDriver
from app.repositories.graph_review_repository import (
    get_all_review_statuses,
    upsert_review_status,
)
from app.repositories.plan_repository import get_latest_plan_node_ids
from app.repositories.project_repository import get_project
from app.services.domain_pack_service import get_domain_pack_registry, get_domain_pack_service
from app.services.graph_service import (
    GRAPH_SCOPE_DOMAIN,
    GRAPH_SCOPE_PROJECT,
    build_edge_review_id,
    get_graph_elements,
    get_graph_entity_metadata,
    get_path_subgraph,
)
from app.services.graph_sync_service import get_graph_sync_service

router = APIRouter()


def _get_default_domain() -> str:
    try:
        return get_domain_pack_registry().resolve_domain()
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_DOMAIN") from exc


def _validate_node_exists(node_id: str, domain: str | None = None) -> None:
    pack = get_domain_pack_service(domain)
    if node_id not in pack.nodes_by_id:
        raise AppError(code=404, message="节点不存在")


def _validate_edge_exists(edge_id: str, domain: str | None = None) -> None:
    pack = get_domain_pack_service(domain)
    valid_edges = {
        build_edge_review_id(edge["source"], edge["target"], "REQUIRES")
        for edge in pack.requires_edges
    } | {
        build_edge_review_id(edge["source"], edge["target"], "RELATED_TO")
        for edge in pack.related_edges
    }
    if edge_id not in valid_edges:
        raise AppError(code=404, message="边不存在")


class ReviewStatusRequest(BaseModel):
    status: str = Field(pattern="^(confirmed|removed|pending)$")


def _raise_graph_operation_error(message: str, exc: RuntimeError | ValueError) -> None:
    raise AppError(code=500, message=f"{message}: {exc}") from exc


async def _force_sync_graph(neo4j: Neo4jDriver, domain: str) -> dict:
    try:
        return await get_graph_sync_service(neo4j).force_sync_domain_pack(domain)
    except (RuntimeError, ValueError) as exc:
        _raise_graph_operation_error("图谱同步失败", exc)


async def _query_graph_elements(
    neo4j: Neo4jDriver,
    *,
    scope: Literal["domain", "project"],
    node_ids: list[str] | None = None,
) -> dict:
    try:
        if node_ids is None:
            return await get_graph_elements(neo4j, scope=scope)
        return await get_graph_elements(neo4j, scope=scope, node_ids=node_ids)
    except (RuntimeError, ValueError) as exc:
        _raise_graph_operation_error("图谱查询失败", exc)


async def _query_path_subgraph(neo4j: Neo4jDriver, node_ids: list[str]) -> dict:
    try:
        return await get_path_subgraph(neo4j, node_ids)
    except (RuntimeError, ValueError) as exc:
        _raise_graph_operation_error("图谱查询失败", exc)


async def _query_graph_entity_metadata(neo4j: Neo4jDriver, domain: str) -> dict:
    try:
        return await get_graph_entity_metadata(neo4j, domain)
    except (RuntimeError, ValueError) as exc:
        _raise_graph_operation_error("扩展实体查询失败", exc)


async def _apply_review_statuses(
    db: AsyncSession,
    project_id: str,
    graph_data: dict,
) -> dict:
    review_statuses = await get_all_review_statuses(db, project_id)
    for elem in graph_data.get("elements", []):
        data = elem.get("data", {})
        if elem["group"] == "nodes":
            data["review_status"] = review_statuses.get("node", {}).get(data["id"], "pending")
            continue
        if elem["group"] == "edges":
            edge_id = data.get("id") or build_edge_review_id(
                data["source"],
                data["target"],
                data["type"],
            )
            data["id"] = edge_id
            data["review_status"] = review_statuses.get("edge", {}).get(edge_id, "pending")
    return graph_data


@router.post("/graph/seed")
async def seed_graph_endpoint(
    neo4j: Neo4jDriver = Depends(get_neo4j),
):
    """将 Domain Pack 数据同步到 Neo4j（幂等操作）。"""
    result = await _force_sync_graph(neo4j, _get_default_domain())
    return {
        "nodes": result["nodes"],
        "edges": result["edges"],
        "message": "Graph synced successfully",
        "domain": result["domain"],
        "version": result["version"],
        "reason": result["reason"],
    }


@router.post("/projects/{project_id}/graph/sync")
async def sync_project_graph(
    project_id: str,
    neo4j: Neo4jDriver = Depends(get_neo4j),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    return await _force_sync_graph(neo4j, project.domain)


@router.get("/projects/{project_id}/graph")
async def get_graph(
    project_id: str,
    scope: Literal["domain", "project"] = Query(default=GRAPH_SCOPE_DOMAIN),
    neo4j: Neo4jDriver = Depends(get_neo4j),
    db: AsyncSession = Depends(get_db),
):
    """获取项目关联的知识图谱，包含审核状态。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    if scope == GRAPH_SCOPE_PROJECT:
        latest_node_ids = await get_latest_plan_node_ids(db, project_id)
        graph_data = await _query_graph_elements(
            neo4j,
            scope=GRAPH_SCOPE_PROJECT,
            node_ids=latest_node_ids,
        )
    else:
        graph_data = await _query_graph_elements(neo4j, scope=GRAPH_SCOPE_DOMAIN)

    return await _apply_review_statuses(db, project_id, graph_data)


@router.get("/projects/{project_id}/graph/subgraph")
async def get_subgraph(
    project_id: str,
    node_ids: str,
    neo4j: Neo4jDriver = Depends(get_neo4j),
    db: AsyncSession = Depends(get_db),
):
    """获取指定节点的子图。node_ids 用逗号分隔。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    ids = [nid.strip() for nid in node_ids.split(",") if nid.strip()]
    graph_data = await _query_path_subgraph(neo4j, ids)
    return await _apply_review_statuses(db, project_id, graph_data)


@router.get("/projects/{project_id}/graph/entities")
async def get_graph_entities(
    project_id: str,
    neo4j: Neo4jDriver = Depends(get_neo4j),
    db: AsyncSession = Depends(get_db),
):
    """获取 Stage / Resource 扩展实体的只读视图。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    return await _query_graph_entity_metadata(neo4j, project.domain)


@router.patch("/projects/{project_id}/graph/nodes/{node_id}")
async def review_node(
    project_id: str,
    node_id: str,
    req: ReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """审核节点：确认/移除/恢复。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    _validate_node_exists(node_id, project.domain)
    row = await upsert_review_status(db, project_id, "node", node_id, req.status)
    return {"element_type": "node", "element_id": node_id, "status": row.status}


@router.patch("/projects/{project_id}/graph/edges/{edge_id}")
async def review_edge(
    project_id: str,
    edge_id: str,
    req: ReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    """审核边：确认/移除/恢复。edge_id 格式为 source->target::type。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    _validate_edge_exists(edge_id, project.domain)
    row = await upsert_review_status(db, project_id, "edge", edge_id, req.status)
    return {"element_type": "edge", "element_id": edge_id, "status": row.status}
