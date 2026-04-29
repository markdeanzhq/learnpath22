from __future__ import annotations

import json
import hashlib
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_neo4j
from app.core.exceptions import AppError, NotFoundError
from app.db.neo4j import Neo4jDriver
from app.repositories.graph_review_repository import (
    get_all_review_statuses,
    get_removed_edge_ids,
    get_removed_node_ids,
    upsert_review_status,
)
from app.repositories.plan_repository import extract_plan_node_ids, get_latest_plan
from app.repositories.project_overlay_repository import (
    create_source,
    get_extraction_session,
    get_source,
    list_active_project_overlay_edges,
    list_active_project_overlay_nodes,
    list_resource_bindings,
    list_session_edges,
    list_session_nodes,
    list_session_resources,
    update_planning_enabled,
    update_review_status,
    update_source,
)
from app.repositories.project_repository import get_project
from app.services.domain_pack_service import get_domain_pack_registry, get_domain_pack_service
from app.services.graph_service import (
    GRAPH_SCOPE_DOMAIN,
    GRAPH_SCOPE_PATH,
    GRAPH_SCOPE_PROJECT,
    build_edge_review_id,
    build_path_graph_elements_from_snapshot,
    build_project_graph_elements,
    get_graph_elements,
    get_graph_entity_metadata,
    get_path_subgraph,
)
from app.services.project_goal_extension_draft_service import (
    create_goal_extension_draft_from_resolution,
    preview_goal_extension_draft_proposal,
)
from app.services.project_graph_snapshot_service import build_project_graph_snapshot
from app.services.project_overlay_extraction_service import MAX_TEXT_CHARS, create_extraction_session_from_sources
from app.services.project_overlay_llm_extraction_service import preview_overlay_extraction_payload_from_sources
from app.services.project_overlay_projection_service import (
    get_project_overlay_projection_status,
    sync_project_overlay_projection,
)
from app.services.project_overlay_promotion_service import (
    commit_project_overlay_promotion,
    preview_project_overlay_promotion,
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


class OverlayReviewStatusRequest(BaseModel):
    review_status: str = Field(pattern="^(pending|confirmed|rejected|removed)$")


class OverlayPlanningRequest(BaseModel):
    planning_enabled: bool


class OverlaySourceRequest(BaseModel):
    source_type: Literal["pasted_text", "search_url"]
    raw_text: str | None = None
    raw_text_excerpt: str | None = None
    url: str | None = None
    title: str | None = None
    snippet: str | None = None
    provider: str | None = None
    query: str | None = None
    result_rank: int | None = Field(default=None, ge=1)
    retrieved_at: datetime | None = None
    summary: str | None = None
    quality_status: str | None = None
    metadata_json: str | None = None

    @model_validator(mode="after")
    def validate_source_payload(self) -> "OverlaySourceRequest":
        if self.source_type == "pasted_text" and not self.raw_text:
            raise ValueError("raw_text is required for pasted_text source")
        if self.source_type == "search_url" and not self.url:
            raise ValueError("url is required for search_url source")
        return self


class OverlaySourceUpdateRequest(BaseModel):
    raw_text_excerpt: str | None = None
    title: str | None = None
    snippet: str | None = None
    summary: str | None = None
    quality_status: str | None = None
    metadata_json: str | None = None


class OverlayExtractionPayloadPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(min_length=1)
    mode: Literal["default", "custom_extension"] = "default"


class OverlayExtractionSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_ids: list[str] = Field(min_length=1)
    mode: Literal["default", "custom_extension"] = "default"
    extraction_payload: Any | None = None
    session_provenance: dict[str, Any] | None = None


class GoalExtensionDraftRequest(BaseModel):
    resolution_session_id: str = Field(min_length=1)


class OverlayPromotionPreviewRequest(BaseModel):
    element_ids: list[str] | None = None


class OverlayPromotionCommitRequest(BaseModel):
    admin_secret: str | None = None
    requested_by: str | None = None
    element_ids: list[str] | None = None


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


def _empty_path_graph_response(
    *,
    path_id: str | None,
    empty_reason: str | None = None,
    node_ids: list[str] | None = None,
    missing_node_ids: list[str] | None = None,
) -> dict[str, Any]:
    graph_data: dict[str, Any] = {
        "scope": GRAPH_SCOPE_PATH,
        "path_id": path_id,
        "elements": [],
        "node_ids": sorted(set(node_ids or [])),
        "missing_node_ids": sorted(set(missing_node_ids or [])),
        "is_empty": True,
    }
    if empty_reason is not None:
        graph_data["empty_reason"] = empty_reason
    return graph_data


def _overlay_element_type_from_group(group: str) -> str:
    if group in {"nodes", "node"}:
        return "node"
    if group in {"edges", "edge"}:
        return "edge"
    if group in {"resources", "resource"}:
        return "resource"
    raise AppError(code=422, message="INVALID_OVERLAY_ELEMENT_TYPE")


def _source_response(source) -> dict:
    return {
        "source_id": source.source_id,
        "project_id": source.project_id,
        "source_type": source.source_type,
        "content_hash": source.content_hash,
        "raw_text_excerpt": source.raw_text_excerpt,
        "url": source.url,
        "title": source.title,
        "snippet": source.snippet,
        "provider": source.provider,
        "query": source.query,
        "result_rank": source.result_rank,
        "retrieved_at": source.retrieved_at,
        "summary": source.summary,
        "quality_status": source.quality_status,
        "metadata_json": source.metadata_json,
        "created_at": source.created_at,
    }


def _parse_json_field(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _overlay_candidate_response(candidate, *, element_id_key: str) -> dict:
    return {
        element_id_key: getattr(candidate, element_id_key),
        "project_id": candidate.project_id,
        "session_id": candidate.session_id,
        "validation_status": candidate.validation_status,
        "review_status": candidate.review_status,
        "planning_enabled": candidate.planning_enabled,
        "promotion_status": candidate.promotion_status,
        "source_ids": _parse_json_field(candidate.source_ids_json, []),
        "provenance": _parse_json_field(candidate.provenance_json, {}),
        "duplicate_candidates": _parse_json_field(candidate.duplicate_candidates_json, {"indexes": []}),
        "validation_errors": _parse_json_field(candidate.validation_errors_json, []),
        "legality_rationale": getattr(candidate, "legality_rationale", None),
        "confidence": candidate.confidence,
        "canonical_payload_hash": candidate.canonical_payload_hash,
        "created_at": candidate.created_at,
        "updated_at": candidate.updated_at,
    }


def _overlay_node_response(node) -> dict:
    response = _overlay_candidate_response(node, element_id_key="node_id")
    provenance = response.get("provenance") or {}
    response.update(
        {
            "name": node.name,
            "summary": provenance.get("summary"),
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
        }
    )
    return response


def _overlay_edge_response(edge) -> dict:
    response = _overlay_candidate_response(edge, element_id_key="edge_id")
    response.update(
        {
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "relation_type": edge.relation_type,
        }
    )
    return response


def _binding_response(binding) -> dict:
    return {
        "id": binding.id,
        "project_id": binding.project_id,
        "resource_id": binding.resource_id,
        "target_type": binding.target_type,
        "target_id": binding.target_id,
        "source_result_id": binding.source_result_id,
        "binding_source": binding.binding_source,
        "created_at": binding.created_at,
        "updated_at": binding.updated_at,
    }


def _overlay_resource_response(
    resource,
    *,
    sources_by_id: dict[str, Any] | None = None,
    bindings_by_resource_id: dict[str, list[Any]] | None = None,
) -> dict:
    response = _overlay_candidate_response(resource, element_id_key="resource_id")
    provenance = response.get("provenance") or {}
    evidence_source_id = provenance.get("evidence_source_id")
    evidence_source = None
    if evidence_source_id and sources_by_id is not None:
        source = sources_by_id.get(evidence_source_id)
        if source is not None:
            evidence_source = _source_response(source)
    bindings = []
    if bindings_by_resource_id is not None:
        bindings = [
            _binding_response(binding)
            for binding in bindings_by_resource_id.get(resource.resource_id, [])
        ]
    response.update(
        {
            "title": resource.title,
            "url": resource.url,
            "resource_type": resource.resource_type,
            "summary": resource.summary,
            "quality_score": resource.quality_score,
            "evidence_source_id": evidence_source_id,
            "source_evidence": evidence_source,
            "bindings": bindings,
            "binding_summary": {
                "count": len(bindings),
                "project_node_ids": sorted(
                    binding["target_id"] for binding in bindings if binding["target_type"] == "project_node"
                ),
                "path_stage_ids": sorted(
                    binding["target_id"] for binding in bindings if binding["target_type"] == "path_stage"
                ),
            },
        }
    )
    return response


def _overlay_session_response(
    *,
    session,
    sources: list[Any],
    nodes: list[Any],
    edges: list[Any],
    resources: list[Any],
    bindings: list[Any] | None = None,
    warnings: list[Any] | None = None,
) -> dict:
    warning_items = warnings if warnings is not None else _parse_json_field(session.warnings_json, [])
    sources_by_id = {source.source_id: source for source in sources}
    bindings_by_resource_id: dict[str, list[Any]] = {}
    for binding in bindings or []:
        bindings_by_resource_id.setdefault(binding.resource_id, []).append(binding)
    return {
        "session": {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "mode": session.mode,
            "session_status": session.session_status,
            "source_ids": _parse_json_field(session.source_ids_json, []),
            "warnings": warning_items,
            "provenance": _parse_json_field(getattr(session, "provenance_json", None), {}),
            "error_message": session.error_message,
            "created_at": session.created_at,
            "updated_at": session.updated_at,
        },
        "sources": [_source_response(source) for source in sources],
        "nodes": [_overlay_node_response(node) for node in nodes],
        "edges": [_overlay_edge_response(edge) for edge in edges],
        "resources": [
            _overlay_resource_response(
                resource,
                sources_by_id=sources_by_id,
                bindings_by_resource_id=bindings_by_resource_id,
            )
            for resource in resources
        ],
        "warnings": warning_items,
    }


async def _apply_review_statuses(
    db: AsyncSession,
    project_id: str,
    graph_data: dict,
) -> dict:
    review_statuses = await get_all_review_statuses(db, project_id)
    for elem in graph_data.get("elements", []):
        data = elem.get("data", {})
        if data.get("origin") == "overlay":
            continue
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

    baseline_result = await _force_sync_graph(neo4j, project.domain)
    overlay_result = await sync_project_overlay_projection(db, neo4j, project_id)
    return {**baseline_result, "overlay_projection": overlay_result}


@router.get("/projects/{project_id}/graph/overlay/projection/status")
async def get_overlay_projection_status_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    return await get_project_overlay_projection_status(db, project_id)


@router.get("/projects/{project_id}/graph")
async def get_graph(
    project_id: str,
    scope: str = Query(default=GRAPH_SCOPE_DOMAIN),
    path_id: str | None = Query(default=None),
    neo4j: Neo4jDriver = Depends(get_neo4j),
    db: AsyncSession = Depends(get_db),
):
    """获取项目关联的知识图谱，包含审核状态。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    if scope == GRAPH_SCOPE_PROJECT:
        pack = get_domain_pack_service(project.domain)
        graph_data = build_project_graph_elements(
            pack,
            overlay_nodes=await list_active_project_overlay_nodes(db, project_id),
            overlay_edges=await list_active_project_overlay_edges(db, project_id),
            removed_node_ids=await get_removed_node_ids(db, project_id),
            removed_edge_ids=await get_removed_edge_ids(db, project_id),
        )
    elif scope == GRAPH_SCOPE_PATH:
        if path_id not in {None, "latest"}:
            raise AppError(code=422, message="INVALID_GRAPH_PATH_ID")
        latest_path = await get_latest_plan(db, project_id)
        if latest_path is None:
            graph_data = _empty_path_graph_response(
                path_id=None,
                empty_reason="project_latest_plan_missing",
            )
        else:
            latest_node_ids = extract_plan_node_ids(latest_path.plan_json)
            if not latest_node_ids:
                graph_data = _empty_path_graph_response(
                    path_id=latest_path.id,
                    node_ids=latest_node_ids,
                )
            else:
                snapshot = await build_project_graph_snapshot(
                    db,
                    project_id,
                    domain=project.domain,
                )
                graph_data = build_path_graph_elements_from_snapshot(
                    snapshot,
                    node_ids=latest_node_ids,
                    path_id=latest_path.id,
                )
    elif scope == GRAPH_SCOPE_DOMAIN:
        graph_data = await _query_graph_elements(neo4j, scope=GRAPH_SCOPE_DOMAIN)
    else:
        raise AppError(code=422, message="INVALID_GRAPH_SCOPE")

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


@router.post("/projects/{project_id}/graph/overlay/sources")
async def create_overlay_source(
    project_id: str,
    req: OverlaySourceRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    content_hash = None
    excerpt = req.raw_text_excerpt
    if req.source_type == "pasted_text" and req.raw_text is not None:
        if len(req.raw_text) > MAX_TEXT_CHARS:
            raise AppError(code=422, message="TEXT_LIMIT_EXCEEDED")
        if excerpt is not None and len(excerpt) > MAX_TEXT_CHARS:
            raise AppError(code=422, message="TEXT_LIMIT_EXCEEDED")
        content_hash = hashlib.sha256(req.raw_text.encode("utf-8")).hexdigest()
        excerpt = excerpt or req.raw_text[:MAX_TEXT_CHARS]

    source = await create_source(
        db,
        project_id=project_id,
        source_type=req.source_type,
        content_hash=content_hash,
        raw_text_excerpt=excerpt,
        url=req.url,
        title=req.title,
        snippet=req.snippet,
        provider=req.provider,
        query=req.query,
        result_rank=req.result_rank,
        retrieved_at=req.retrieved_at,
        summary=req.summary,
        quality_status=req.quality_status,
        metadata_json=req.metadata_json,
    )
    return _source_response(source)


@router.patch("/projects/{project_id}/graph/overlay/sources/{source_id}")
async def update_overlay_source_endpoint(
    project_id: str,
    source_id: str,
    req: OverlaySourceUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    fields = req.model_dump(exclude_unset=True)
    raw_text_excerpt = fields.get("raw_text_excerpt")
    if raw_text_excerpt is not None and len(raw_text_excerpt) > MAX_TEXT_CHARS:
        raise AppError(code=422, message="TEXT_LIMIT_EXCEEDED")
    try:
        source = await update_source(
            db,
            project_id=project_id,
            source_id=source_id,
            **fields,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "OVERLAY_SOURCE_NOT_FOUND":
            raise NotFoundError("overlay source 不存在") from exc
        raise AppError(code=422, message=message) from exc
    return _source_response(source)


@router.post("/projects/{project_id}/graph/overlay/extraction-payload/preview")
async def preview_overlay_extraction_payload(
    project_id: str,
    req: OverlayExtractionPayloadPreviewRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        return await preview_overlay_extraction_payload_from_sources(
            db,
            project_id=project_id,
            source_ids=req.source_ids,
            mode=req.mode,
            domain=project.domain,
        )
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc


@router.post("/projects/{project_id}/graph/overlay/extraction-sessions")
async def create_overlay_extraction_session(
    project_id: str,
    req: OverlayExtractionSessionRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        created = await create_extraction_session_from_sources(
            db,
            project_id=project_id,
            source_ids=req.source_ids,
            mode=req.mode,
            extraction_payload=req.extraction_payload,
            domain=project.domain,
            session_provenance=req.session_provenance,
        )
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc

    return _overlay_session_response(
        session=created["session"],
        sources=created["sources"],
        nodes=created["nodes"],
        edges=created["edges"],
        resources=created["resources"],
        bindings=[],
        warnings=created["warnings"],
    )


@router.get("/projects/{project_id}/goal-resolution/extension-drafts/{resolution_session_id}/proposal")
async def get_goal_extension_draft_proposal(
    project_id: str,
    resolution_session_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    return await preview_goal_extension_draft_proposal(
        db,
        project_id=project_id,
        resolution_session_id=resolution_session_id,
    )


@router.post("/projects/{project_id}/goal-resolution/extension-drafts")
async def create_goal_extension_draft(
    project_id: str,
    req: GoalExtensionDraftRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        created = await create_goal_extension_draft_from_resolution(
            db,
            project_id=project_id,
            resolution_session_id=req.resolution_session_id,
        )
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc

    response = _overlay_session_response(
        session=created["session"],
        sources=created["sources"],
        nodes=created["nodes"],
        edges=created["edges"],
        resources=created["resources"],
        bindings=[],
        warnings=created["warnings"],
    )
    response["goal_trace"] = created["goal_trace"]
    response["missing_concepts"] = created["missing_concepts"]
    response["gap_analysis"] = created["gap_analysis"]
    response["review_notes"] = created["review_notes"]
    response["draft_metadata"] = created["draft_metadata"]
    response["draft_proposal"] = created.get("draft_proposal")
    return response


@router.get("/projects/{project_id}/graph/overlay/extraction-sessions/{session_id}")
async def get_overlay_extraction_session(
    project_id: str,
    session_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    session = await get_extraction_session(db, project_id, session_id)
    if session is None:
        raise NotFoundError("overlay extraction session 不存在")

    source_ids = _parse_json_field(session.source_ids_json, [])
    sources = []
    for source_id in source_ids:
        source = await get_source(db, project_id, source_id)
        if source is not None:
            sources.append(source)

    resources = await list_session_resources(db, project_id=project_id, session_id=session_id)
    resource_ids = {resource.resource_id for resource in resources}
    bindings = [
        binding
        for binding in await list_resource_bindings(db, project_id)
        if binding.resource_id in resource_ids
    ]

    return _overlay_session_response(
        session=session,
        sources=sources,
        nodes=await list_session_nodes(db, project_id=project_id, session_id=session_id),
        edges=await list_session_edges(db, project_id=project_id, session_id=session_id),
        resources=resources,
        bindings=bindings,
    )


@router.post("/projects/{project_id}/graph/overlay/promotion/preview")
async def preview_overlay_promotion(
    project_id: str,
    req: OverlayPromotionPreviewRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        return await preview_project_overlay_promotion(
            db,
            project_id=project_id,
            selected_element_ids=req.element_ids if req else None,
        )
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc


@router.post("/projects/{project_id}/graph/overlay/promotion/commit")
async def commit_overlay_promotion(
    project_id: str,
    req: OverlayPromotionCommitRequest,
    neo4j: Neo4jDriver = Depends(get_neo4j),
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        return await commit_project_overlay_promotion(
            db,
            neo4j,
            project_id=project_id,
            admin_secret=req.admin_secret,
            requested_by=req.requested_by,
            selected_element_ids=req.element_ids,
        )
    except AppError:
        raise
    except ValueError as exc:
        raise AppError(code=422, message=str(exc)) from exc
    except (RuntimeError, OSError) as exc:
        _raise_graph_operation_error("promotion commit 失败", exc)


@router.patch("/projects/{project_id}/graph/overlay/{element_group}/{element_id}/review")
async def review_overlay_element(
    project_id: str,
    element_group: str,
    element_id: str,
    req: OverlayReviewStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        element_type = _overlay_element_type_from_group(element_group)
        candidate = await update_review_status(
            db,
            project_id=project_id,
            element_type=element_type,
            element_id=element_id,
            review_status=req.review_status,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "OVERLAY_CANDIDATE_NOT_FOUND":
            raise NotFoundError("overlay 元素不存在") from exc
        raise AppError(code=422, message=message) from exc

    return {
        "element_type": element_type,
        "element_id": element_id,
        "validation_status": candidate.validation_status,
        "review_status": candidate.review_status,
        "planning_enabled": candidate.planning_enabled,
        "promotion_status": candidate.promotion_status,
    }


@router.patch("/projects/{project_id}/graph/overlay/{element_group}/{element_id}/planning")
async def set_overlay_planning(
    project_id: str,
    element_group: str,
    element_id: str,
    req: OverlayPlanningRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    try:
        element_type = _overlay_element_type_from_group(element_group)
        candidate = await update_planning_enabled(
            db,
            project_id=project_id,
            element_type=element_type,
            element_id=element_id,
            planning_enabled=req.planning_enabled,
        )
    except ValueError as exc:
        message = str(exc)
        if message == "OVERLAY_CANDIDATE_NOT_FOUND":
            raise NotFoundError("overlay 元素不存在") from exc
        raise AppError(code=422, message=message) from exc

    return {
        "element_type": element_type,
        "element_id": element_id,
        "validation_status": candidate.validation_status,
        "review_status": candidate.review_status,
        "planning_enabled": candidate.planning_enabled,
        "promotion_status": candidate.promotion_status,
    }


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
