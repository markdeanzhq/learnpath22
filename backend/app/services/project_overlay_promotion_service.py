from __future__ import annotations

import json
import os
import secrets
import shutil
import tempfile
from pathlib import Path
from typing import Any

import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_domain_pack_promotion_config
from app.core.exceptions import AppError
from app.db.neo4j import Neo4jDriver
from app.repositories.project_overlay_repository import (
    create_promotion_batch,
    create_promotion_item,
    list_project_overlay_edges,
    list_project_overlay_nodes,
    list_project_overlay_resources,
    list_resource_bindings,
    update_promotion_batch,
    update_promotion_status,
)
from app.repositories.project_repository import get_project
from app.services import domain_pack_service as domain_pack_module
from app.services.graph_sync_service import get_graph_sync_service
from app.services.project_overlay_projection_service import sync_project_overlay_projection

PACK_FILENAMES = (
    "manifest.json",
    "nodes.json",
    "requires_edges.json",
    "related_edges.json",
    "resources.json",
)
ALLOWED_PROMOTION_STATUSES = {"not_promoted", "promotion_ready"}
ALLOWED_RELATION_TYPES = {"REQUIRES", "RELATED_TO"}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _pretty_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _clone(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False))


def _load_json(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _norm(value: Any) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _edge_key(source: str, target: str, relation_type: str) -> str:
    return f"{source}->{target}::{relation_type}"


def _candidate_id(candidate: Any) -> str:
    return (
        getattr(candidate, "node_id", None)
        or getattr(candidate, "edge_id", None)
        or getattr(candidate, "resource_id")
    )


def _candidate_type(candidate: Any) -> str:
    if hasattr(candidate, "node_id"):
        return "node"
    if hasattr(candidate, "edge_id"):
        return "edge"
    return "resource"


def _candidate_is_promotable(candidate: Any) -> bool:
    if hasattr(candidate, "resource_id") and not candidate.planning_enabled:
        return False
    return (
        candidate.validation_status == "valid"
        and candidate.review_status == "confirmed"
        and candidate.promotion_status in ALLOWED_PROMOTION_STATUSES
    )


def _node_to_pack_payload(node: Any) -> dict[str, Any]:
    provenance = _load_json(node.provenance_json, {})
    return {
        "id": node.node_id,
        "name": node.name or node.node_id,
        "group": node.group,
        "category": node.category,
        "description": provenance.get("summary") or node.legality_rationale or node.name or node.node_id,
        "difficulty_final": node.difficulty_final,
        "importance_final": node.importance_final,
        "estimated_hours": node.estimated_hours,
        "is_main_path": False,
        "is_foundation": False,
        "is_practice": node.category == "practice",
        "req_math": node.req_math,
        "req_coding": node.req_coding,
        "req_ml": node.req_ml,
        "theory_weight": node.theory_weight,
        "practice_weight": node.practice_weight,
        "bridge_value": 0.0,
        "optional_level": 0.3,
        "aliases": [],
        "keywords": [],
    }


def _edge_to_pack_payload(edge: Any) -> dict[str, Any]:
    return {
        "id": edge.edge_id,
        "source": edge.source_node_id,
        "target": edge.target_node_id,
        "reason": edge.legality_rationale or "project overlay promotion",
    }


def _pack_edge_payload(edge: dict[str, Any]) -> dict[str, Any]:
    return {key: edge[key] for key in ("source", "target", "reason")}


def _pack_resource_payload(resource: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: resource[key]
        for key in ("id", "title", "resource_type", "description", "node_ids", "stage_ids")
    }
    if resource.get("url"):
        payload["url"] = resource["url"]
    return payload


def _binding_payload(binding: Any) -> dict[str, Any]:
    return {
        "id": binding.id,
        "resource_id": binding.resource_id,
        "target_type": binding.target_type,
        "target_id": binding.target_id,
        "source_result_id": binding.source_result_id,
        "binding_source": binding.binding_source,
    }


def _resource_binding_parts(resource: Any, bindings: list[Any]) -> tuple[list[Any], list[str], list[str]]:
    resource_bindings = [binding for binding in bindings if binding.resource_id == resource.resource_id]
    node_ids = sorted(
        {
            binding.target_id
            for binding in resource_bindings
            if binding.target_type == "project_node"
        }
    )
    stage_ids = sorted(
        {
            binding.target_id
            for binding in resource_bindings
            if binding.target_type == "path_stage"
        }
    )
    return resource_bindings, node_ids, stage_ids


def _resource_to_pack_payload(resource: Any, bindings: list[Any]) -> dict[str, Any]:
    _, node_ids, stage_ids = _resource_binding_parts(resource, bindings)
    payload = {
        "id": resource.resource_id,
        "title": resource.title or resource.resource_id,
        "resource_type": resource.resource_type or "article",
        "description": resource.summary or resource.title or resource.resource_id,
        "node_ids": node_ids,
        "stage_ids": stage_ids,
    }
    if resource.url:
        payload["url"] = resource.url
    return payload


def _resource_preview_payload(resource: Any, bindings: list[Any]) -> dict[str, Any]:
    resource_bindings, _, _ = _resource_binding_parts(resource, bindings)
    return {
        **_resource_to_pack_payload(resource, bindings),
        "binding_decisions": [_binding_payload(binding) for binding in resource_bindings],
        "lineage": {
            "session_id": resource.session_id,
            "source_ids": _load_json(resource.source_ids_json, []),
            "provenance": _load_json(resource.provenance_json, {}),
            "validation_status": resource.validation_status,
            "review_status": resource.review_status,
            "planning_enabled": resource.planning_enabled,
            "promotion_status": resource.promotion_status,
            "validation_errors": _load_json(resource.validation_errors_json, []),
            "confidence": resource.confidence,
        },
    }


def _pack_file_payloads(pack: Any) -> dict[str, Any]:
    return {
        "manifest.json": _clone(pack.manifest),
        "nodes.json": _clone(pack.nodes),
        "requires_edges.json": _clone(pack.requires_edges),
        "related_edges.json": _clone(pack.related_edges),
        "resources.json": _clone(pack.resources),
    }


def _build_merged_payloads(
    pack: Any,
    *,
    nodes: list[dict[str, Any]],
    edges: list[tuple[str, dict[str, Any]]],
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    payloads = _pack_file_payloads(pack)
    payloads["nodes.json"] = sorted(payloads["nodes.json"] + nodes, key=lambda item: item["id"])
    requires = [_pack_edge_payload(edge) for relation_type, edge in edges if relation_type == "REQUIRES"]
    related = [_pack_edge_payload(edge) for relation_type, edge in edges if relation_type == "RELATED_TO"]
    payloads["requires_edges.json"] = sorted(
        payloads["requires_edges.json"] + requires,
        key=lambda item: (item["source"], item["target"], item.get("reason", "")),
    )
    payloads["related_edges.json"] = sorted(
        payloads["related_edges.json"] + related,
        key=lambda item: (item["source"], item["target"], item.get("reason", "")),
    )
    pack_resources = [_pack_resource_payload(resource) for resource in resources]
    payloads["resources.json"] = sorted(payloads["resources.json"] + pack_resources, key=lambda item: item["id"])
    payloads["manifest.json"]["node_count"] = len(payloads["nodes.json"])
    return payloads


def _validate_node_payloads(pack: Any, nodes: list[dict[str, Any]], errors: list[str]) -> None:
    baseline_ids = set(pack.nodes_by_id)
    baseline_names = {_norm(node.get("name")) for node in pack.nodes if _norm(node.get("name"))}
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    required = {
        "id",
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
    for node in nodes:
        node_id = node.get("id")
        missing = sorted(field for field in required if node.get(field) is None)
        if missing:
            errors.append(f"node_missing_fields:{node_id}:{','.join(missing)}")
        if node_id in baseline_ids or node_id in seen_ids:
            errors.append(f"duplicate_node_id:{node_id}")
        seen_ids.add(node_id)
        name_key = _norm(node.get("name"))
        if name_key and (name_key in baseline_names or name_key in seen_names):
            errors.append(f"duplicate_node_name:{node.get('name')}")
        if name_key:
            seen_names.add(name_key)


def _validate_resource_payloads(pack: Any, resources: list[dict[str, Any]], errors: list[str]) -> None:
    baseline_ids = set(pack.resources_by_id)
    baseline_titles = {_norm(resource.get("title")) for resource in pack.resources if _norm(resource.get("title"))}
    seen_ids: set[str] = set()
    seen_titles: set[str] = set()
    for resource in resources:
        resource_id = resource.get("id")
        if resource_id in baseline_ids or resource_id in seen_ids:
            errors.append(f"duplicate_resource_id:{resource_id}")
        seen_ids.add(resource_id)
        title_key = _norm(resource.get("title"))
        if title_key and (title_key in baseline_titles or title_key in seen_titles):
            errors.append(f"duplicate_resource_title:{resource.get('title')}")
        if title_key:
            seen_titles.add(title_key)


def _validate_edge_payloads(
    pack: Any,
    *,
    node_ids: set[str],
    edges: list[tuple[str, dict[str, Any]]],
    errors: list[str],
) -> None:
    baseline_edges = {
        _edge_key(edge["source"], edge["target"], "REQUIRES") for edge in pack.requires_edges
    } | {_edge_key(edge["source"], edge["target"], "RELATED_TO") for edge in pack.related_edges}
    seen_edges: set[str] = set()
    requires_graph = nx.DiGraph()
    requires_graph.add_nodes_from(node_ids)
    requires_graph.add_edges_from((edge["source"], edge["target"]) for edge in pack.requires_edges)
    for relation_type, edge in edges:
        source = edge.get("source")
        target = edge.get("target")
        edge_id = _edge_key(str(source), str(target), relation_type)
        if relation_type not in ALLOWED_RELATION_TYPES:
            errors.append(f"invalid_relation_type:{edge_id}")
        if not source or source not in node_ids:
            errors.append(f"dangling_source:{edge_id}")
        if not target or target not in node_ids:
            errors.append(f"dangling_target:{edge_id}")
        if source and target and source == target:
            errors.append(f"self_loop:{edge_id}")
        if edge_id in baseline_edges or edge_id in seen_edges:
            errors.append(f"duplicate_edge:{edge_id}")
        seen_edges.add(edge_id)
        if relation_type == "REQUIRES" and source in node_ids and target in node_ids:
            requires_graph.add_edge(source, target)
    if not nx.is_directed_acyclic_graph(requires_graph):
        errors.append("requires_cycle")


def _validate_candidate_selection(
    *,
    selected_element_ids: set[str] | None,
    all_candidates: list[Any],
    errors: list[str],
) -> list[Any]:
    candidates_by_id = {}
    for candidate in all_candidates:
        candidates_by_id[_candidate_id(candidate)] = candidate
    if selected_element_ids is not None:
        unknown = sorted(selected_element_ids - set(candidates_by_id))
        errors.extend(f"unknown_element:{element_id}" for element_id in unknown)
    selected = []
    for element_id, candidate in candidates_by_id.items():
        if selected_element_ids is not None and element_id not in selected_element_ids:
            continue
        if candidate.promotion_status == "promoted":
            continue
        if _candidate_is_promotable(candidate):
            selected.append(candidate)
        elif selected_element_ids is not None:
            errors.append(f"candidate_not_promotable:{element_id}")
    return selected


def _validate_pack_reload(domain: str, payloads: dict[str, Any]) -> tuple[str | None, str | None]:
    source_pack_dir = domain_pack_module.PACK_DIR.resolve()
    old_pack_dir = domain_pack_module.PACK_DIR
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_pack_dir = Path(temp_dir) / "domain_packs"
        shutil.copytree(source_pack_dir, temp_pack_dir)
        domain_dir = temp_pack_dir / domain
        for filename, payload in payloads.items():
            (domain_dir / filename).write_text(_pretty_json(payload), encoding="utf-8")
        domain_pack_module.PACK_DIR = temp_pack_dir
        try:
            reloaded = domain_pack_module.get_domain_pack_service(domain, force_reload=True)
            return reloaded.pack_hash, None
        except Exception as exc:
            return None, f"pack_reload_validation_failed:{exc}"
        finally:
            domain_pack_module.PACK_DIR = old_pack_dir
            try:
                domain_pack_module.get_domain_pack_service(domain, force_reload=True)
            except Exception:
                pass


def _build_preview_report(
    *,
    project_id: str,
    domain: str,
    baseline_pack_hash: str,
    resulting_pack_hash: str | None,
    node_payloads: list[dict[str, Any]],
    edge_payloads: list[tuple[str, dict[str, Any]]],
    resource_payloads: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> dict[str, Any]:
    status = "invalid" if errors else "ready"
    if not errors and not node_payloads and not edge_payloads and not resource_payloads:
        status = "empty"
    return {
        "project_id": project_id,
        "domain": domain,
        "valid": not errors,
        "status": status,
        "candidate_count": len(node_payloads) + len(edge_payloads) + len(resource_payloads),
        "baseline_pack_hash": baseline_pack_hash,
        "resulting_pack_hash": resulting_pack_hash,
        "errors": errors,
        "warnings": warnings,
        "nodes": node_payloads,
        "edges": [dict(edge, relation_type=relation_type) for relation_type, edge in edge_payloads],
        "resources": resource_payloads,
        "would_write": PACK_FILENAMES,
    }


async def preview_project_overlay_promotion(
    db: AsyncSession,
    *,
    project_id: str,
    selected_element_ids: list[str] | None = None,
) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise ValueError("PROJECT_NOT_FOUND")
    project_domain = project.domain
    pack = domain_pack_module.get_domain_pack_service(project_domain, force_reload=True)
    errors: list[str] = []
    warnings: list[str] = []
    selected_ids = set(selected_element_ids) if selected_element_ids is not None else None
    nodes = await list_project_overlay_nodes(db, project_id)
    edges = await list_project_overlay_edges(db, project_id)
    resources = await list_project_overlay_resources(db, project_id)
    selected_candidates = _validate_candidate_selection(
        selected_element_ids=selected_ids,
        all_candidates=[*nodes, *edges, *resources],
        errors=errors,
    )
    selected_nodes = [candidate for candidate in selected_candidates if hasattr(candidate, "node_id")]
    selected_edges = [candidate for candidate in selected_candidates if hasattr(candidate, "edge_id")]
    selected_resources = [candidate for candidate in selected_candidates if hasattr(candidate, "resource_id")]
    bindings = await list_resource_bindings(db, project_id)

    node_payloads = [_node_to_pack_payload(node) for node in selected_nodes]
    edge_payloads = [(edge.relation_type, _edge_to_pack_payload(edge)) for edge in selected_edges]
    resource_payloads = [_resource_preview_payload(resource, bindings) for resource in selected_resources]
    node_ids = set(pack.nodes_by_id) | {node["id"] for node in node_payloads}

    _validate_node_payloads(pack, node_payloads, errors)
    _validate_edge_payloads(pack, node_ids=node_ids, edges=edge_payloads, errors=errors)
    _validate_resource_payloads(pack, resource_payloads, errors)

    payloads = _build_merged_payloads(
        pack,
        nodes=node_payloads,
        edges=edge_payloads,
        resources=resource_payloads,
    )
    resulting_hash = None
    if not errors:
        resulting_hash, reload_error = _validate_pack_reload(project_domain, payloads)
        if reload_error:
            errors.append(reload_error)

    return _build_preview_report(
        project_id=project_id,
        domain=project_domain,
        baseline_pack_hash=pack.pack_hash,
        resulting_pack_hash=resulting_hash,
        node_payloads=node_payloads,
        edge_payloads=edge_payloads,
        resource_payloads=resource_payloads,
        errors=errors,
        warnings=warnings,
    )


def _apply_pack_files(domain: str, payloads: dict[str, Any]) -> list[tuple[Path, Path]]:
    domain_dir = (domain_pack_module.PACK_DIR / domain).resolve()
    temp_paths: dict[str, Path] = {}
    backups: list[tuple[Path, Path]] = []
    try:
        for filename, payload in payloads.items():
            temp_path = domain_dir / f".{filename}.promotion.tmp"
            temp_path.write_text(_pretty_json(payload), encoding="utf-8")
            temp_paths[filename] = temp_path
        for filename in payloads:
            path = domain_dir / filename
            backup = domain_dir / f".{filename}.promotion.bak"
            if backup.exists():
                backup.unlink()
            os.replace(path, backup)
            backups.append((path, backup))
            os.replace(temp_paths[filename], path)
        return backups
    except Exception:
        for temp_path in temp_paths.values():
            if temp_path.exists():
                temp_path.unlink()
        _restore_pack_files(backups)
        raise


def _restore_pack_files(backups: list[tuple[Path, Path]]) -> None:
    for path, backup in reversed(backups):
        if backup.exists():
            if path.exists():
                path.unlink()
            os.replace(backup, path)


def _cleanup_pack_backups(backups: list[tuple[Path, Path]]) -> None:
    for _, backup in backups:
        if backup.exists():
            backup.unlink()


async def _write_and_sync_pack(
    *,
    domain: str,
    payloads: dict[str, Any],
    driver: Neo4jDriver,
) -> tuple[str, dict[str, Any], list[tuple[Path, Path]]]:
    backups = _apply_pack_files(domain, payloads)
    try:
        reloaded = domain_pack_module.get_domain_pack_service(domain, force_reload=True)
        sync_result = await get_graph_sync_service(driver).force_sync_domain_pack(domain)
    except Exception:
        _restore_pack_files(backups)
        try:
            domain_pack_module.get_domain_pack_service(domain, force_reload=True)
        except Exception:
            pass
        raise
    return reloaded.pack_hash, sync_result, backups


def _restore_domain_pack_cache(domain: str) -> dict[str, Any]:
    try:
        restored = domain_pack_module.get_domain_pack_service(domain, force_reload=True)
        return {"ok": True, "pack_hash": restored.pack_hash, "error": None}
    except Exception as exc:
        return {"ok": False, "pack_hash": None, "error": str(exc)}


async def commit_project_overlay_promotion(
    db: AsyncSession,
    driver: Neo4jDriver,
    *,
    project_id: str,
    admin_secret: str | None,
    requested_by: str | None = None,
    selected_element_ids: list[str] | None = None,
) -> dict[str, Any]:
    config = get_domain_pack_promotion_config()
    if not config["enabled"]:
        raise AppError(code=403, message="PROMOTION_DISABLED")
    configured_secret = str(config.get("admin_secret") or "")
    if not admin_secret or not configured_secret or not secrets.compare_digest(admin_secret, configured_secret):
        raise AppError(code=403, message="PROMOTION_FORBIDDEN")

    preview = await preview_project_overlay_promotion(
        db,
        project_id=project_id,
        selected_element_ids=selected_element_ids,
    )
    if not preview["valid"]:
        raise AppError(code=422, message="PROMOTION_PREVIEW_INVALID", details={"preview": preview})
    if preview["status"] == "empty":
        return {**preview, "synced": False, "reason": "no_candidates", "batch": None, "sync": None}

    project = await get_project(db, project_id)
    if project is None:
        raise ValueError("PROJECT_NOT_FOUND")
    project_domain = project.domain
    pack = domain_pack_module.get_domain_pack_service(project_domain, force_reload=True)
    payloads = _build_merged_payloads(
        pack,
        nodes=preview["nodes"],
        edges=[(edge["relation_type"], edge) for edge in preview["edges"]],
        resources=preview["resources"],
    )
    resulting_hash = None
    sync_result = None
    overlay_projection_result = None
    backups: list[tuple[Path, Path]] = []
    batch = None
    preview = {**preview}
    try:
        resulting_hash, sync_result, backups = await _write_and_sync_pack(
            domain=project_domain,
            payloads=payloads,
            driver=driver,
        )
        preview = {**preview, "resulting_pack_hash": resulting_hash}

        batch = await create_promotion_batch(
            db,
            project_id=project_id,
            requested_by=requested_by,
            baseline_pack_hash=preview["baseline_pack_hash"],
            resulting_pack_hash=resulting_hash,
            preview_report_json=_canonical_json(preview),
            commit=False,
        )
        element_ids = [item["id"] for item in preview["nodes"] + preview["resources"]]
        element_ids.extend(item["id"] for item in preview["edges"])
        candidates = [
            *await list_project_overlay_nodes(db, project_id),
            *await list_project_overlay_edges(db, project_id),
            *await list_project_overlay_resources(db, project_id),
        ]
        candidates_by_id = {_candidate_id(candidate): candidate for candidate in candidates}
        for element_id in element_ids:
            candidate = candidates_by_id[element_id]
            element_type = _candidate_type(candidate)
            item = await create_promotion_item(
                db,
                project_id=project_id,
                batch_id=batch.batch_id,
                element_type=element_type,
                element_id=element_id,
                source_session_id=candidate.session_id,
                source_ids_json=candidate.source_ids_json,
                provenance_json=_canonical_json(
                    {
                        "source_project_id": project_id,
                        "candidate_provenance": _load_json(candidate.provenance_json, {}),
                        "baseline_pack_hash": preview["baseline_pack_hash"],
                        "resulting_pack_hash": resulting_hash,
                    }
                ),
                commit=False,
            )
            item.status = "promoted"
            await update_promotion_status(
                db,
                project_id=project_id,
                element_type=element_type,
                element_id=element_id,
                promotion_status="promoted",
                commit=False,
            )
        await update_promotion_batch(
            db,
            project_id=project_id,
            batch_id=batch.batch_id,
            status="promoted",
            resulting_pack_hash=resulting_hash,
            commit=False,
        )
        overlay_projection_result = await sync_project_overlay_projection(
            db,
            driver,
            project_id,
            commit=False,
        )
        if overlay_projection_result["status"] == "error":
            raise RuntimeError(overlay_projection_result["reason"])
        await db.commit()
    except Exception as exc:
        await db.rollback()
        rollback: dict[str, Any] = {
            "pack_restored": False,
            "cache_reload": None,
            "baseline_sync": None,
        }
        if backups:
            _restore_pack_files(backups)
            rollback["pack_restored"] = True
        rollback["cache_reload"] = _restore_domain_pack_cache(project_domain)
        try:
            rollback_sync = await get_graph_sync_service(driver).force_sync_domain_pack(project_domain)
            rollback["baseline_sync"] = {"ok": True, "result": rollback_sync, "error": None}
        except Exception as rollback_exc:
            rollback["baseline_sync"] = {"ok": False, "result": None, "error": str(rollback_exc)}
        failed_preview = {
            **preview,
            "resulting_pack_hash": resulting_hash,
            "failure_reason": str(exc),
            "rollback": rollback,
        }
        failed_batch = await create_promotion_batch(
            db,
            project_id=project_id,
            requested_by=requested_by,
            baseline_pack_hash=preview["baseline_pack_hash"],
            resulting_pack_hash=resulting_hash,
            preview_report_json=_canonical_json(failed_preview),
            error_message=str(exc),
            commit=False,
        )
        failed_batch.status = "failed"
        await db.commit()
        raise AppError(
            code=500,
            message="PROMOTION_COMMIT_FAILED",
            details={"batch_id": failed_batch.batch_id, "reason": str(exc), "rollback": rollback},
        ) from exc

    _cleanup_pack_backups(backups)
    cache_reload = _restore_domain_pack_cache(project_domain)
    if not cache_reload["ok"]:
        raise AppError(
            code=500,
            message="PROMOTION_CACHE_RELOAD_FAILED",
            details={"reason": cache_reload["error"]},
        )
    await db.refresh(batch)
    return {
        **preview,
        "synced": True,
        "reason": "promoted",
        "batch": {
            "batch_id": batch.batch_id,
            "status": batch.status,
            "requested_by": batch.requested_by,
            "baseline_pack_hash": batch.baseline_pack_hash,
            "resulting_pack_hash": batch.resulting_pack_hash,
        },
        "sync": sync_result,
        "overlay_projection": overlay_projection_result,
    }
