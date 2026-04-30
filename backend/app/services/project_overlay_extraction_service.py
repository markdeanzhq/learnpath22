from __future__ import annotations

import json
from collections import Counter
from typing import Any

import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_search_api_key
from app.core.exceptions import AppError
from app.repositories.project_overlay_repository import (
    create_edge,
    create_extraction_session,
    create_node,
    create_resource,
    get_candidate,
    get_extraction_session,
    get_source,
    list_session_edges,
    list_session_nodes,
    list_session_resources,
    set_candidate_validation_result,
    update_candidate_fields,
    update_extraction_session_status,
    update_validation_status,
)
from app.services.domain_pack_service import get_domain_pack_service
from app.services.project_overlay_ids import build_overlay_id, overlay_payload_hash

MAX_TEXT_CHARS = 12_000
MAX_URL_SOURCES = 10
MAX_NODES = 30
MAX_EDGES = 45
MAX_RESOURCES = 30
ALLOWED_RELATION_TYPES = {"REQUIRES", "RELATED_TO"}
SUPPORTED_EXTRACTION_MODES = {"default", "custom_extension"}
PLANNER_NODE_FIELDS = {
    "name",
    "group",
    "category",
    "difficulty_final",
    "importance_final",
    "estimated_hours",
    "req_math",
    "req_coding",
    "req_ml",
    "theory_weight",
    "practice_weight",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_json_field(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _normalized_string(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    normalized = value.strip()
    return normalized or None


def _normalized_lookup_key(value: Any) -> str:
    normalized = _normalized_string(value)
    if not isinstance(normalized, str):
        return ""
    return normalized.lower()


def _normalize_node_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    evidence_spans = candidate.get("evidence_spans", [])
    if not isinstance(evidence_spans, list):
        evidence_spans = []
    provenance = candidate.get("provenance")
    if not isinstance(provenance, dict):
        provenance = {}
    return {
        "name": _normalized_string(candidate.get("name")),
        "group": _normalized_string(candidate.get("group")),
        "category": _normalized_string(candidate.get("category")),
        "difficulty_final": candidate.get("difficulty_final", candidate.get("difficulty")),
        "importance_final": candidate.get("importance_final", candidate.get("importance")),
        "estimated_hours": candidate.get("estimated_hours"),
        "req_math": candidate.get("req_math"),
        "req_coding": candidate.get("req_coding"),
        "req_ml": candidate.get("req_ml"),
        "theory_weight": candidate.get("theory_weight"),
        "practice_weight": candidate.get("practice_weight"),
        "confidence": candidate.get("confidence"),
        "legality_rationale": _normalized_string(candidate.get("legality_rationale")),
        "summary": _normalized_string(candidate.get("summary")),
        "evidence_spans": evidence_spans,
        "provenance": provenance,
    }


def _normalize_edge_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    relation_type = _normalized_string(candidate.get("relation_type"))
    if isinstance(relation_type, str):
        relation_type = relation_type.upper()
    return {
        "source_node_id": _normalized_string(candidate.get("source_node_id")),
        "target_node_id": _normalized_string(candidate.get("target_node_id")),
        "source_name_or_id": _normalized_string(candidate.get("source_name_or_id")),
        "target_name_or_id": _normalized_string(candidate.get("target_name_or_id")),
        "relation_type": relation_type,
        "confidence": candidate.get("confidence"),
        "legality_rationale": _normalized_string(candidate.get("legality_rationale")),
    }


def _normalize_resource_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _normalized_string(candidate.get("title")),
        "url": _normalized_string(candidate.get("url")),
        "resource_type": _normalized_string(candidate.get("resource_type")),
        "summary": _normalized_string(candidate.get("summary")),
        "quality_score": candidate.get("quality_score"),
        "confidence": candidate.get("confidence"),
        "evidence_source_id": _normalized_string(candidate.get("evidence_source_id")),
    }


def _bounded_list(payload: dict[str, Any], field_name: str, max_count: int) -> list[dict[str, Any]]:
    value = payload.get(field_name, [])
    if not isinstance(value, list):
        raise ValueError("INVALID_LLM_EXTRACTION_JSON")
    if len(value) > max_count:
        raise ValueError(f"{field_name.upper()}_LIMIT_EXCEEDED")
    if not all(isinstance(item, dict) for item in value):
        raise ValueError("INVALID_LLM_EXTRACTION_JSON")
    return value


def parse_extraction_payload(payload: Any) -> dict[str, list[Any]]:
    if not isinstance(payload, dict):
        raise ValueError("INVALID_LLM_EXTRACTION_JSON")
    allowed_keys = {"nodes", "edges", "resources", "warnings"}
    if set(payload) - allowed_keys:
        raise ValueError("INVALID_LLM_EXTRACTION_JSON")
    warnings = payload.get("warnings", [])
    if not isinstance(warnings, list):
        raise ValueError("INVALID_LLM_EXTRACTION_JSON")
    return {
        "nodes": _bounded_list(payload, "nodes", MAX_NODES),
        "edges": _bounded_list(payload, "edges", MAX_EDGES),
        "resources": _bounded_list(payload, "resources", MAX_RESOURCES),
        "warnings": warnings,
    }


def _node_validation_errors(candidate: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = sorted(field for field in PLANNER_NODE_FIELDS if candidate.get(field) is None)
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")
    if not candidate.get("summary"):
        errors.append("missing_summary")
    if not candidate.get("legality_rationale"):
        errors.append("missing_legality_rationale")
    for field_name in ("difficulty_final", "importance_final", "req_math", "req_coding", "req_ml"):
        value = candidate.get(field_name)
        if value is not None and (not isinstance(value, int) or value < 1 or value > 5):
            errors.append(f"invalid_{field_name}")
    estimated_hours = candidate.get("estimated_hours")
    if estimated_hours is not None and (not isinstance(estimated_hours, int | float) or estimated_hours <= 0):
        errors.append("invalid_estimated_hours")
    theory_weight = candidate.get("theory_weight")
    practice_weight = candidate.get("practice_weight")
    for field_name, value in [("theory_weight", theory_weight), ("practice_weight", practice_weight)]:
        if value is not None and (not isinstance(value, int | float) or value < 0 or value > 1):
            errors.append(f"invalid_{field_name}")
    if isinstance(theory_weight, int | float) and isinstance(practice_weight, int | float):
        if abs((theory_weight + practice_weight) - 1.0) > 0.001:
            errors.append("invalid_weight_sum")
    confidence = candidate.get("confidence")
    if confidence is not None and (not isinstance(confidence, int | float) or confidence < 0 or confidence > 1):
        errors.append("invalid_confidence")
    return errors


def _resource_validation_errors(candidate: dict[str, Any], source_ids: set[str]) -> list[str]:
    errors: list[str] = []
    for field_name in ("title", "url", "resource_type", "summary"):
        if not candidate.get(field_name):
            errors.append(f"missing_{field_name}")
    evidence_source_id = candidate.get("evidence_source_id")
    if not evidence_source_id:
        errors.append("missing_evidence_source_id")
    elif evidence_source_id not in source_ids:
        errors.append("invalid_evidence_source_id")
    quality_score = candidate.get("quality_score")
    if quality_score is not None and (not isinstance(quality_score, int | float) or quality_score < 0 or quality_score > 1):
        errors.append("invalid_quality_score")
    confidence = candidate.get("confidence")
    if confidence is not None and (not isinstance(confidence, int | float) or confidence < 0 or confidence > 1):
        errors.append("invalid_confidence")
    return errors


def _duplicate_payloads(
    items: list[dict[str, Any]],
    key_builder: str | Any,
) -> dict[str, list[int]]:
    if isinstance(key_builder, str):
        keys = [_normalized_lookup_key(item.get(key_builder)) for item in items]
    else:
        keys = [str(key_builder(item)).strip().lower() for item in items]
    counts = Counter(key for key in keys if key)
    duplicates: dict[str, list[int]] = {}
    for index, key in enumerate(keys):
        if key and counts[key] > 1:
            duplicates.setdefault(key, []).append(index)
    return duplicates


def _candidate_validation_status(
    *,
    errors: list[str],
    duplicate_indexes: list[int] | None = None,
) -> str:
    if errors:
        return "invalid"
    if duplicate_indexes:
        return "needs_review"
    return "valid"


def _resolve_node_reference(value: Any, lookup: dict[str, str]) -> Any:
    normalized = _normalized_string(value)
    if not isinstance(normalized, str):
        return normalized
    return lookup.get(normalized.lower(), normalized)


def _baseline_node_lookup(nodes_by_id: dict[str, dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for node_id, node in nodes_by_id.items():
        lookup[_normalized_lookup_key(node_id)] = node_id
        name_key = _normalized_lookup_key(node.get("name"))
        if name_key:
            lookup[name_key] = node_id
        for alias in node.get("aliases", []) or []:
            alias_key = _normalized_lookup_key(alias)
            if alias_key:
                lookup[alias_key] = node_id
    return lookup


def _normalize_extraction_mode(mode: str) -> str:
    normalized = mode.strip().lower()
    if normalized not in SUPPORTED_EXTRACTION_MODES:
        raise AppError(code=422, message="INVALID_OVERLAY_EXTRACTION_MODE")
    return normalized


def _node_candidate_to_fields(
    candidate: dict[str, Any],
    *,
    source_ids: list[str],
    duplicate_indexes: list[int] | None,
) -> tuple[dict[str, Any], list[str]]:
    errors = _node_validation_errors(candidate)
    provenance = {
        **(candidate.get("provenance") if isinstance(candidate.get("provenance"), dict) else {}),
        "source_ids": source_ids,
        "summary": candidate.get("summary"),
        "evidence_spans": candidate.get("evidence_spans", []),
    }
    fields = {
        "name": candidate.get("name"),
        "group": candidate.get("group"),
        "category": candidate.get("category"),
        "difficulty_final": candidate.get("difficulty_final"),
        "importance_final": candidate.get("importance_final"),
        "estimated_hours": candidate.get("estimated_hours"),
        "req_math": candidate.get("req_math"),
        "req_coding": candidate.get("req_coding"),
        "req_ml": candidate.get("req_ml"),
        "theory_weight": candidate.get("theory_weight"),
        "practice_weight": candidate.get("practice_weight"),
        "source_ids_json": _canonical_json(source_ids),
        "provenance_json": _canonical_json(provenance),
        "duplicate_candidates_json": _canonical_json({"indexes": duplicate_indexes or []}),
        "legality_rationale": candidate.get("legality_rationale"),
        "validation_errors_json": _canonical_json(errors) if errors else None,
        "confidence": candidate.get("confidence"),
    }
    return fields, errors


def _edge_validation_errors(
    candidate: dict[str, Any],
    *,
    valid_node_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    source = candidate.get("source_node_id") or candidate.get("source_name_or_id")
    target = candidate.get("target_node_id") or candidate.get("target_name_or_id")
    relation_type = candidate.get("relation_type")
    if not source or not target:
        errors.append("missing_endpoint")
    if relation_type not in ALLOWED_RELATION_TYPES:
        errors.append("invalid_relation_type")
    if source and target and source == target:
        errors.append("self_loop")
    if source and source not in valid_node_ids:
        errors.append("dangling_source")
    if target and target not in valid_node_ids:
        errors.append("dangling_target")
    confidence = candidate.get("confidence")
    if confidence is not None and (not isinstance(confidence, int | float) or confidence < 0 or confidence > 1):
        errors.append("invalid_confidence")
    if not candidate.get("legality_rationale"):
        errors.append("missing_legality_rationale")
    return errors


def _requires_cycle_errors(
    edges: list[dict[str, Any]],
    valid_node_ids: set[str],
    baseline_requires_edges: list[dict[str, Any]],
) -> set[int]:
    graph = nx.DiGraph()
    graph.add_nodes_from(valid_node_ids)
    for edge in baseline_requires_edges:
        source = edge.get("source")
        target = edge.get("target")
        if source in valid_node_ids and target in valid_node_ids and source != target:
            graph.add_edge(source, target)

    edge_indexes: dict[tuple[str, str], list[int]] = {}
    for index, edge in enumerate(edges):
        source = edge.get("source_node_id") or edge.get("source_name_or_id")
        target = edge.get("target_node_id") or edge.get("target_name_or_id")
        if edge.get("relation_type") == "REQUIRES" and source in valid_node_ids and target in valid_node_ids and source != target:
            graph.add_edge(source, target)
            edge_indexes.setdefault((source, target), []).append(index)
    if nx.is_directed_acyclic_graph(graph):
        return set()
    cycle_edges: set[int] = set()
    for cycle in nx.simple_cycles(graph):
        for source, target in zip(cycle, cycle[1:] + cycle[:1]):
            cycle_edges.update(edge_indexes.get((source, target), []))
    return cycle_edges


def _ensure_search_ready_for_mode(mode: str) -> None:
    if mode == "custom_extension" and not get_search_api_key():
        raise AppError(code=503, message="SEARCH_NOT_READY")


def _edge_candidate_to_fields(
    candidate: dict[str, Any],
    *,
    source_ids: list[str],
    duplicate_indexes: list[int] | None,
    valid_node_ids: set[str],
    has_requires_cycle: bool,
) -> tuple[dict[str, Any], list[str]]:
    errors = _edge_validation_errors(candidate, valid_node_ids=valid_node_ids)
    if has_requires_cycle:
        errors.append("requires_cycle")
    source = candidate.get("source_node_id")
    target = candidate.get("target_node_id")
    fields = {
        "source_node_id": source or "",
        "target_node_id": target or "",
        "relation_type": candidate.get("relation_type", ""),
        "source_ids_json": _canonical_json(source_ids),
        "provenance_json": _canonical_json({
            "source_ids": source_ids,
            "source_reference": source,
            "target_reference": target,
        }),
        "duplicate_candidates_json": _canonical_json({"indexes": duplicate_indexes or []}),
        "legality_rationale": candidate.get("legality_rationale"),
        "validation_errors_json": _canonical_json(errors) if errors else None,
        "confidence": candidate.get("confidence"),
    }
    return fields, errors


def _resource_candidate_to_fields(
    candidate: dict[str, Any],
    *,
    source_ids: list[str],
    source_id_set: set[str],
    duplicate_indexes: list[int] | None,
) -> tuple[dict[str, Any], list[str]]:
    errors = _resource_validation_errors(candidate, source_id_set)
    fields = {
        "title": candidate.get("title"),
        "url": candidate.get("url"),
        "resource_type": candidate.get("resource_type"),
        "summary": candidate.get("summary"),
        "quality_score": candidate.get("quality_score"),
        "source_ids_json": _canonical_json(source_ids),
        "provenance_json": _canonical_json({
            "source_ids": source_ids,
            "evidence_source_id": candidate.get("evidence_source_id"),
        }),
        "duplicate_candidates_json": _canonical_json({"indexes": duplicate_indexes or []}),
        "validation_errors_json": _canonical_json(errors) if errors else None,
        "confidence": candidate.get("confidence"),
    }
    return fields, errors


async def _load_sources_for_extraction(
    db: AsyncSession,
    *,
    project_id: str,
    source_ids: list[str],
    mode: str,
) -> list[Any]:
    mode = _normalize_extraction_mode(mode)
    _ensure_search_ready_for_mode(mode)
    if not source_ids:
        raise AppError(code=422, message="OVERLAY_SOURCE_REQUIRED")

    sources = []
    for source_id in source_ids:
        source = await get_source(db, project_id, source_id)
        if source is None:
            raise AppError(code=404, message="overlay source 不存在")
        if source.source_type == "pasted_text" and source.raw_text_excerpt and len(source.raw_text_excerpt) > MAX_TEXT_CHARS:
            raise AppError(code=422, message="TEXT_LIMIT_EXCEEDED")
        sources.append(source)
    if sum(1 for source in sources if source.source_type == "search_url") > MAX_URL_SOURCES:
        raise AppError(code=422, message="SOURCE_LIMIT_EXCEEDED")
    return sources


def _build_extraction_validation_plan(
    *,
    project_id: str,
    source_ids: list[str],
    extraction_payload: Any | None,
    domain: str | None = None,
    node_ids: list[str] | None = None,
    edge_ids: list[str] | None = None,
    resource_ids: list[str] | None = None,
) -> dict[str, Any]:
    payload = parse_extraction_payload(extraction_payload or {"nodes": [], "edges": [], "resources": [], "warnings": []})
    source_id_set = set(source_ids)
    pack = get_domain_pack_service(domain)
    baseline_node_ids = set(pack.nodes_by_id)
    node_lookup = _baseline_node_lookup(pack.nodes_by_id)

    normalized_nodes = [_normalize_node_candidate(candidate) for candidate in payload["nodes"]]
    normalized_resources = [_normalize_resource_candidate(candidate) for candidate in payload["resources"]]
    node_duplicates = _duplicate_payloads(normalized_nodes, "name")
    resource_duplicates = _duplicate_payloads(normalized_resources, "url")

    node_items = []
    valid_overlay_node_ids: set[str] = set()
    for index, candidate in enumerate(normalized_nodes):
        node_id = node_ids[index] if node_ids is not None else build_overlay_id(project_id, "n", {"candidate": candidate, "index": index})
        duplicate_indexes = node_duplicates.get(_normalized_lookup_key(candidate.get("name")))
        fields, errors = _node_candidate_to_fields(
            candidate,
            source_ids=source_ids,
            duplicate_indexes=duplicate_indexes,
        )
        validation_status = _candidate_validation_status(errors=errors, duplicate_indexes=duplicate_indexes)
        canonical_payload_hash = overlay_payload_hash(candidate)
        if validation_status == "valid":
            valid_overlay_node_ids.add(node_id)
            node_lookup[_normalized_lookup_key(node_id)] = node_id
            if candidate.get("name"):
                node_lookup[_normalized_lookup_key(candidate["name"])] = node_id
        node_items.append({
            "index": index,
            "node_id": node_id,
            "candidate": candidate,
            "fields": fields,
            "errors": errors,
            "duplicate_indexes": duplicate_indexes or [],
            "validation_status": validation_status,
            "canonical_payload_hash": canonical_payload_hash,
        })

    valid_node_ids = baseline_node_ids | valid_overlay_node_ids
    normalized_edges = []
    for candidate in payload["edges"]:
        normalized = _normalize_edge_candidate(candidate)
        normalized_edges.append({
            **normalized,
            "source_node_id": _resolve_node_reference(
                normalized.get("source_node_id") or normalized.get("source_name_or_id"),
                node_lookup,
            ),
            "target_node_id": _resolve_node_reference(
                normalized.get("target_node_id") or normalized.get("target_name_or_id"),
                node_lookup,
            ),
        })

    edge_duplicates = _duplicate_payloads(
        normalized_edges,
        lambda candidate: (
            f"{candidate.get('source_node_id') or ''}->"
            f"{candidate.get('target_node_id') or ''}::"
            f"{candidate.get('relation_type') or ''}"
        ),
    )
    edge_cycle_indexes = _requires_cycle_errors(normalized_edges, valid_node_ids, pack.requires_edges)
    edge_items = []
    for index, candidate in enumerate(normalized_edges):
        source = candidate.get("source_node_id")
        target = candidate.get("target_node_id")
        duplicate_key = f"{source or ''}->{target or ''}::{candidate.get('relation_type') or ''}".lower()
        duplicate_indexes = edge_duplicates.get(duplicate_key)
        fields, errors = _edge_candidate_to_fields(
            candidate,
            source_ids=source_ids,
            duplicate_indexes=duplicate_indexes,
            valid_node_ids=valid_node_ids,
            has_requires_cycle=index in edge_cycle_indexes,
        )
        edge_id = edge_ids[index] if edge_ids is not None else build_overlay_id(project_id, "e", {
            "candidate": {
                "source": source,
                "target": target,
                "relation_type": candidate.get("relation_type"),
            },
            "index": index,
        })
        edge_items.append({
            "index": index,
            "edge_id": edge_id,
            "candidate": candidate,
            "fields": fields,
            "errors": errors,
            "duplicate_indexes": duplicate_indexes or [],
            "validation_status": _candidate_validation_status(errors=errors, duplicate_indexes=duplicate_indexes),
            "canonical_payload_hash": overlay_payload_hash(candidate),
        })

    resource_items = []
    for index, candidate in enumerate(normalized_resources):
        duplicate_indexes = resource_duplicates.get(_normalized_lookup_key(candidate.get("url")))
        fields, errors = _resource_candidate_to_fields(
            candidate,
            source_ids=source_ids,
            source_id_set=source_id_set,
            duplicate_indexes=duplicate_indexes,
        )
        resource_items.append({
            "index": index,
            "resource_id": resource_ids[index] if resource_ids is not None else build_overlay_id(project_id, "r", {"candidate": candidate, "index": index}),
            "candidate": candidate,
            "fields": fields,
            "errors": errors,
            "duplicate_indexes": duplicate_indexes or [],
            "validation_status": _candidate_validation_status(errors=errors, duplicate_indexes=duplicate_indexes),
            "canonical_payload_hash": overlay_payload_hash(candidate),
        })

    return {
        "source_ids": source_ids,
        "warnings": payload["warnings"],
        "nodes": node_items,
        "edges": edge_items,
        "resources": resource_items,
    }


def _validation_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(items),
        "valid": sum(1 for item in items if item["validation_status"] == "valid"),
        "invalid": sum(1 for item in items if item["validation_status"] == "invalid"),
        "needs_review": sum(1 for item in items if item["validation_status"] == "needs_review"),
    }


def _validation_item_response(item: dict[str, Any], *, id_key: str) -> dict[str, Any]:
    candidate = item["candidate"]
    return {
        "index": item["index"],
        id_key: item[id_key],
        "validation_status": item["validation_status"],
        "validation_errors": item["errors"],
        "duplicate_candidates": {"indexes": item["duplicate_indexes"]},
        **candidate,
    }


def _validation_plan_response(plan: dict[str, Any]) -> dict[str, Any]:
    invalid_count = sum(
        _validation_counts(plan[key])["invalid"]
        for key in ("nodes", "edges", "resources")
    )
    needs_review_count = sum(
        _validation_counts(plan[key])["needs_review"]
        for key in ("nodes", "edges", "resources")
    )
    return {
        "source_ids": plan["source_ids"],
        "warnings": plan["warnings"],
        "counts": {
            "nodes": _validation_counts(plan["nodes"]),
            "edges": _validation_counts(plan["edges"]),
            "resources": _validation_counts(plan["resources"]),
        },
        "summary": {
            "has_blocking_errors": invalid_count > 0,
            "needs_review": needs_review_count > 0,
            "invalid_count": invalid_count,
            "needs_review_count": needs_review_count,
        },
        "nodes": [_validation_item_response(item, id_key="node_id") for item in plan["nodes"]],
        "edges": [_validation_item_response(item, id_key="edge_id") for item in plan["edges"]],
        "resources": [_validation_item_response(item, id_key="resource_id") for item in plan["resources"]],
    }


async def validate_extraction_payload_for_sources(
    db: AsyncSession,
    *,
    project_id: str,
    source_ids: list[str],
    mode: str = "default",
    extraction_payload: Any | None = None,
    domain: str | None = None,
) -> dict[str, Any]:
    mode = _normalize_extraction_mode(mode)
    await _load_sources_for_extraction(
        db,
        project_id=project_id,
        source_ids=source_ids,
        mode=mode,
    )
    return _validation_plan_response(_build_extraction_validation_plan(
        project_id=project_id,
        source_ids=source_ids,
        extraction_payload=extraction_payload,
        domain=domain,
    ))


async def create_extraction_session_from_sources(
    db: AsyncSession,
    *,
    project_id: str,
    source_ids: list[str],
    mode: str = "default",
    extraction_payload: Any | None = None,
    domain: str | None = None,
    session_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    mode = _normalize_extraction_mode(mode)
    sources = await _load_sources_for_extraction(
        db,
        project_id=project_id,
        source_ids=source_ids,
        mode=mode,
    )
    plan = _build_extraction_validation_plan(
        project_id=project_id,
        source_ids=source_ids,
        extraction_payload=extraction_payload,
        domain=domain,
    )
    session = await create_extraction_session(
        db,
        project_id=project_id,
        source_ids_json=_canonical_json(source_ids),
        mode=mode,
        warnings_json=_canonical_json(plan["warnings"]),
        provenance_json=_canonical_json(session_provenance or {}),
        commit=False,
    )

    created_nodes = []
    for item in plan["nodes"]:
        node = await create_node(
            db,
            project_id=project_id,
            node_id=item["node_id"],
            session_id=session.session_id,
            canonical_payload_hash=item["canonical_payload_hash"],
            commit=False,
            **item["fields"],
        )
        await update_validation_status(
            db,
            project_id=project_id,
            element_type="node",
            element_id=node.node_id,
            validation_status=item["validation_status"],
            validation_errors_json=_canonical_json(item["errors"]) if item["errors"] else None,
            commit=False,
        )
        created_nodes.append(node)

    created_edges = []
    for item in plan["edges"]:
        fields = item["fields"]
        edge = await create_edge(
            db,
            project_id=project_id,
            edge_id=item["edge_id"],
            session_id=session.session_id,
            source_node_id=fields["source_node_id"],
            target_node_id=fields["target_node_id"],
            relation_type=fields["relation_type"],
            canonical_payload_hash=item["canonical_payload_hash"],
            source_ids_json=fields["source_ids_json"],
            provenance_json=fields["provenance_json"],
            legality_rationale=fields["legality_rationale"],
            duplicate_candidates_json=fields["duplicate_candidates_json"],
            validation_errors_json=fields["validation_errors_json"],
            confidence=fields["confidence"],
            commit=False,
        )
        await update_validation_status(
            db,
            project_id=project_id,
            element_type="edge",
            element_id=edge.edge_id,
            validation_status=item["validation_status"],
            validation_errors_json=_canonical_json(item["errors"]) if item["errors"] else None,
            commit=False,
        )
        created_edges.append(edge)

    created_resources = []
    for item in plan["resources"]:
        resource = await create_resource(
            db,
            project_id=project_id,
            resource_id=item["resource_id"],
            session_id=session.session_id,
            canonical_payload_hash=item["canonical_payload_hash"],
            commit=False,
            **item["fields"],
        )
        await update_validation_status(
            db,
            project_id=project_id,
            element_type="resource",
            element_id=resource.resource_id,
            validation_status=item["validation_status"],
            validation_errors_json=_canonical_json(item["errors"]) if item["errors"] else None,
            commit=False,
        )
        created_resources.append(resource)

    await update_extraction_session_status(
        db,
        project_id=project_id,
        session_id=session.session_id,
        session_status="validated",
        commit=False,
    )
    await db.commit()
    await db.refresh(session)
    return {
        "session": session,
        "sources": sources,
        "nodes": created_nodes,
        "edges": created_edges,
        "resources": created_resources,
        "warnings": plan["warnings"],
    }


def _node_row_to_candidate(node: Any) -> dict[str, Any]:
    provenance = _parse_json_field(node.provenance_json, {})
    return {
        "name": node.name,
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
        "confidence": node.confidence,
        "legality_rationale": node.legality_rationale,
        "summary": provenance.get("summary"),
        "evidence_spans": provenance.get("evidence_spans", []),
        "provenance": provenance,
    }


def _edge_row_to_candidate(edge: Any) -> dict[str, Any]:
    return {
        "source_node_id": edge.source_node_id,
        "target_node_id": edge.target_node_id,
        "relation_type": edge.relation_type,
        "confidence": edge.confidence,
        "legality_rationale": edge.legality_rationale,
    }


def _resource_row_to_candidate(resource: Any) -> dict[str, Any]:
    provenance = _parse_json_field(resource.provenance_json, {})
    return {
        "title": resource.title,
        "url": resource.url,
        "resource_type": resource.resource_type,
        "summary": resource.summary,
        "quality_score": resource.quality_score,
        "confidence": resource.confidence,
        "evidence_source_id": provenance.get("evidence_source_id"),
    }


async def _revalidate_session_candidates(
    db: AsyncSession,
    *,
    project_id: str,
    session_id: str,
    domain: str | None = None,
) -> None:
    session = await get_extraction_session(db, project_id, session_id)
    if session is None:
        raise ValueError("OVERLAY_SESSION_NOT_FOUND")
    source_ids = _parse_json_field(session.source_ids_json, [])
    nodes = await list_session_nodes(db, project_id=project_id, session_id=session_id)
    edges = await list_session_edges(db, project_id=project_id, session_id=session_id)
    resources = await list_session_resources(db, project_id=project_id, session_id=session_id)
    plan = _build_extraction_validation_plan(
        project_id=project_id,
        source_ids=source_ids,
        extraction_payload={
            "nodes": [_node_row_to_candidate(node) for node in nodes],
            "edges": [_edge_row_to_candidate(edge) for edge in edges],
            "resources": [_resource_row_to_candidate(resource) for resource in resources],
            "warnings": _parse_json_field(session.warnings_json, []),
        },
        domain=domain,
        node_ids=[node.node_id for node in nodes],
        edge_ids=[edge.edge_id for edge in edges],
        resource_ids=[resource.resource_id for resource in resources],
    )

    for node, item in zip(nodes, plan["nodes"], strict=True):
        await set_candidate_validation_result(
            db,
            project_id=project_id,
            element_type="node",
            element_id=node.node_id,
            validation_status=item["validation_status"],
            validation_errors_json=_canonical_json(item["errors"]) if item["errors"] else None,
            duplicate_candidates_json=item["fields"]["duplicate_candidates_json"],
            canonical_payload_hash=item["canonical_payload_hash"],
            commit=False,
        )
    for edge, item in zip(edges, plan["edges"], strict=True):
        await update_candidate_fields(
            db,
            project_id=project_id,
            element_type="edge",
            element_id=edge.edge_id,
            reset_review_on_change=False,
            commit=False,
            canonical_payload_hash=item["canonical_payload_hash"],
            **item["fields"],
        )
        await set_candidate_validation_result(
            db,
            project_id=project_id,
            element_type="edge",
            element_id=edge.edge_id,
            validation_status=item["validation_status"],
            validation_errors_json=_canonical_json(item["errors"]) if item["errors"] else None,
            duplicate_candidates_json=item["fields"]["duplicate_candidates_json"],
            canonical_payload_hash=item["canonical_payload_hash"],
            commit=False,
        )
    for resource, item in zip(resources, plan["resources"], strict=True):
        await set_candidate_validation_result(
            db,
            project_id=project_id,
            element_type="resource",
            element_id=resource.resource_id,
            validation_status=item["validation_status"],
            validation_errors_json=_canonical_json(item["errors"]) if item["errors"] else None,
            duplicate_candidates_json=item["fields"]["duplicate_candidates_json"],
            canonical_payload_hash=item["canonical_payload_hash"],
            commit=False,
        )


def _require_session_id(candidate: Any) -> str:
    if not candidate.session_id:
        raise ValueError("OVERLAY_SESSION_NOT_FOUND")
    return candidate.session_id


async def update_overlay_node_candidate(
    db: AsyncSession,
    *,
    project_id: str,
    node_id: str,
    fields: dict[str, Any],
    domain: str | None = None,
) -> str:
    candidate = await get_candidate(db, project_id=project_id, element_type="node", element_id=node_id)
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    session_id = _require_session_id(candidate)
    next_candidate = _node_row_to_candidate(candidate)
    next_candidate.update(fields)
    normalized = _normalize_node_candidate(next_candidate)
    update_fields, _ = _node_candidate_to_fields(
        normalized,
        source_ids=_parse_json_field(candidate.source_ids_json, []),
        duplicate_indexes=None,
    )
    update_fields["canonical_payload_hash"] = overlay_payload_hash(normalized)
    await update_candidate_fields(
        db,
        project_id=project_id,
        element_type="node",
        element_id=node_id,
        reset_review_on_change=True,
        commit=False,
        **update_fields,
    )
    await _revalidate_session_candidates(db, project_id=project_id, session_id=session_id, domain=domain)
    await db.commit()
    return session_id


async def update_overlay_edge_candidate(
    db: AsyncSession,
    *,
    project_id: str,
    edge_id: str,
    fields: dict[str, Any],
    domain: str | None = None,
) -> str:
    candidate = await get_candidate(db, project_id=project_id, element_type="edge", element_id=edge_id)
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    session_id = _require_session_id(candidate)
    next_candidate = _edge_row_to_candidate(candidate)
    if "source_name_or_id" in fields and "source_node_id" not in fields:
        next_candidate["source_node_id"] = None
    if "target_name_or_id" in fields and "target_node_id" not in fields:
        next_candidate["target_node_id"] = None
    next_candidate.update(fields)
    normalized = _normalize_edge_candidate(next_candidate)
    source_ids = _parse_json_field(candidate.source_ids_json, [])
    pack = get_domain_pack_service(domain)
    node_lookup = _baseline_node_lookup(pack.nodes_by_id)
    for node in await list_session_nodes(db, project_id=project_id, session_id=session_id):
        if node.validation_status == "valid":
            node_lookup[_normalized_lookup_key(node.node_id)] = node.node_id
            if node.name:
                node_lookup[_normalized_lookup_key(node.name)] = node.node_id
    resolved = {
        **normalized,
        "source_node_id": _resolve_node_reference(
            normalized.get("source_node_id") or normalized.get("source_name_or_id"),
            node_lookup,
        ),
        "target_node_id": _resolve_node_reference(
            normalized.get("target_node_id") or normalized.get("target_name_or_id"),
            node_lookup,
        ),
    }
    update_fields, _ = _edge_candidate_to_fields(
        resolved,
        source_ids=source_ids,
        duplicate_indexes=None,
        valid_node_ids=set(pack.nodes_by_id),
        has_requires_cycle=False,
    )
    update_fields["canonical_payload_hash"] = overlay_payload_hash(resolved)
    await update_candidate_fields(
        db,
        project_id=project_id,
        element_type="edge",
        element_id=edge_id,
        reset_review_on_change=True,
        commit=False,
        **update_fields,
    )
    await _revalidate_session_candidates(db, project_id=project_id, session_id=session_id, domain=domain)
    await db.commit()
    return session_id


async def update_overlay_resource_candidate(
    db: AsyncSession,
    *,
    project_id: str,
    resource_id: str,
    fields: dict[str, Any],
    domain: str | None = None,
) -> str:
    candidate = await get_candidate(db, project_id=project_id, element_type="resource", element_id=resource_id)
    if candidate is None:
        raise ValueError("OVERLAY_CANDIDATE_NOT_FOUND")
    session_id = _require_session_id(candidate)
    next_candidate = _resource_row_to_candidate(candidate)
    next_candidate.update(fields)
    normalized = _normalize_resource_candidate(next_candidate)
    source_ids = _parse_json_field(candidate.source_ids_json, [])
    update_fields, _ = _resource_candidate_to_fields(
        normalized,
        source_ids=source_ids,
        source_id_set=set(source_ids),
        duplicate_indexes=None,
    )
    update_fields["canonical_payload_hash"] = overlay_payload_hash(normalized)
    await update_candidate_fields(
        db,
        project_id=project_id,
        element_type="resource",
        element_id=resource_id,
        reset_review_on_change=True,
        commit=False,
        **update_fields,
    )
    await _revalidate_session_candidates(db, project_id=project_id, session_id=session_id, domain=domain)
    await db.commit()
    return session_id
