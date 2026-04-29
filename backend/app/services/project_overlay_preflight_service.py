"""Project overlay preflight service."""
from __future__ import annotations

from typing import Any

import networkx as nx
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.plan_repository import extract_plan_node_ids, get_latest_plan
from app.repositories.project_overlay_repository import (
    list_active_project_overlay_edges,
    list_active_project_overlay_nodes,
    list_planner_visible_edges,
    list_planner_visible_nodes,
)
from app.services.project_graph_snapshot_service import build_project_graph_snapshot


def _edge_key(source: str, target: str, relation_type: str) -> str:
    return f"{source}->{target}::{relation_type}"


def _snapshot_overlay_lineage(snapshot) -> dict[str, Any]:
    overlay_lineage = getattr(snapshot, "overlay_lineage", {}) or {}
    return overlay_lineage if isinstance(overlay_lineage, dict) else {}


def _snapshot_overlay_nodes(snapshot) -> dict[str, Any]:
    nodes = _snapshot_overlay_lineage(snapshot).get("nodes")
    return nodes if isinstance(nodes, dict) else {}


def _snapshot_overlay_edges(snapshot) -> dict[str, Any]:
    edges = _snapshot_overlay_lineage(snapshot).get("edges")
    return edges if isinstance(edges, dict) else {}


def _baseline_edge_keys(snapshot) -> set[str]:
    keys: set[str] = set()
    for edge in [*snapshot.requires_edges, *snapshot.related_edges]:
        if edge.get("origin") == "overlay":
            continue
        source = edge.get("source")
        target = edge.get("target")
        relation_type = edge.get("type") or "REQUIRES"
        if isinstance(source, str) and isinstance(target, str) and isinstance(relation_type, str):
            keys.add(_edge_key(source, target, relation_type))
    return keys


def _cycle_overlay_edge_ids(snapshot) -> list[str]:
    graph = nx.DiGraph()
    overlay_requires: dict[tuple[str, str], list[str]] = {}
    for edge in snapshot.requires_edges:
        source = edge.get("source")
        target = edge.get("target")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        graph.add_edge(source, target)
        if edge.get("origin") == "overlay" and isinstance(edge.get("overlay_id"), str):
            overlay_requires.setdefault((source, target), []).append(edge["overlay_id"])
    if nx.is_directed_acyclic_graph(graph):
        return []

    cycle_edge_ids: set[str] = set()
    for cycle in nx.simple_cycles(graph):
        for source, target in zip(cycle, cycle[1:] + cycle[:1]):
            cycle_edge_ids.update(overlay_requires.get((source, target), []))
    return sorted(cycle_edge_ids)


def _candidate_counts(items: list[Any]) -> dict[str, int]:
    return {
        "total": len(items),
        "valid": sum(1 for item in items if item.validation_status == "valid"),
        "confirmed": sum(1 for item in items if item.review_status == "confirmed"),
        "pending_review": sum(1 for item in items if item.validation_status == "valid" and item.review_status == "pending"),
        "planning_disabled": sum(
            1
            for item in items
            if item.validation_status == "valid" and item.review_status == "confirmed" and not item.planning_enabled
        ),
        "invalid": sum(1 for item in items if item.validation_status in {"invalid", "needs_review"}),
    }


def _path_overlay_edge_ids(overlay_edges: dict[str, Any], path_node_ids: set[str]) -> list[str]:
    result: list[str] = []
    for edge_id, edge in overlay_edges.items():
        if not isinstance(edge_id, str) or not isinstance(edge, dict):
            continue
        edge_snapshot = edge.get("edge_snapshot") if isinstance(edge.get("edge_snapshot"), dict) else {}
        source = edge.get("source_node_id") or edge_snapshot.get("source")
        target = edge.get("target_node_id") or edge_snapshot.get("target")
        if source in path_node_ids and target in path_node_ids:
            result.append(edge_id)
    return sorted(result)


def _preflight_summary(status: str, counts: dict[str, Any]) -> str:
    if status == "blocked":
        return "增强图谱存在阻塞问题，请处理后再生成路径对比。"
    visible_nodes = counts["visible_overlay_nodes"]
    visible_edges = counts["visible_overlay_edges"]
    if status == "warning":
        return f"{visible_nodes} 个节点 / {visible_edges} 条关系可进入增强图谱，但存在需要注意的草稿状态或关系问题。"
    return f"{visible_nodes} 个节点 / {visible_edges} 条关系可进入增强图谱，当前未发现阻塞问题。"


async def build_project_overlay_preflight(
    db: AsyncSession,
    *,
    project_id: str,
    domain: str | None = None,
) -> dict[str, Any]:
    active_nodes = await list_active_project_overlay_nodes(db, project_id)
    active_edges = await list_active_project_overlay_edges(db, project_id)
    planner_nodes = await list_planner_visible_nodes(db, project_id)
    planner_edges = await list_planner_visible_edges(db, project_id)

    blocking_items: list[dict[str, Any]] = []
    warning_items: list[dict[str, Any]] = []
    try:
        baseline_snapshot = await build_project_graph_snapshot(db, project_id, domain=domain, include_overlay=False)
        enhanced_snapshot = await build_project_graph_snapshot(db, project_id, domain=domain, include_overlay=True)
    except ValueError as exc:
        counts = {
            "active_nodes": len(active_nodes),
            "active_edges": len(active_edges),
            "visible_overlay_nodes": 0,
            "visible_overlay_edges": 0,
            "path_overlay_nodes": 0,
            "path_overlay_edges": 0,
            "blocking_items": 1,
            "warning_items": 0,
            "nodes": _candidate_counts(active_nodes),
            "edges": _candidate_counts(active_edges),
        }
        return {
            "project_id": project_id,
            "status": "blocked",
            "summary": _preflight_summary("blocked", counts),
            "counts": counts,
            "visible_overlay_node_ids": [],
            "visible_overlay_edge_ids": [],
            "path_overlay_node_ids": [],
            "path_overlay_edge_ids": [],
            "ignored_overlay_edge_ids": [],
            "shadowed_edge_ids": [],
            "cycle_edge_ids": [],
            "blocking_items": [{"kind": "snapshot_error", "message": str(exc)}],
            "warning_items": [],
            "project_graph_hash": None,
        }

    visible_overlay_nodes = _snapshot_overlay_nodes(enhanced_snapshot)
    visible_overlay_edges = _snapshot_overlay_edges(enhanced_snapshot)
    visible_overlay_node_ids = sorted(visible_overlay_nodes)
    visible_overlay_edge_ids = sorted(visible_overlay_edges)
    visible_edge_id_set = set(visible_overlay_edge_ids)
    planner_edge_ids = {edge.edge_id for edge in planner_edges}
    ignored_overlay_edge_ids = sorted(planner_edge_ids - visible_edge_id_set)

    baseline_keys = _baseline_edge_keys(baseline_snapshot)
    shadowed_edge_ids = sorted(
        edge.edge_id
        for edge in planner_edges
        if edge.edge_id in ignored_overlay_edge_ids
        and _edge_key(edge.source_node_id, edge.target_node_id, edge.relation_type) in baseline_keys
    )
    inactive_edge_ids = sorted(set(ignored_overlay_edge_ids) - set(shadowed_edge_ids))
    cycle_edge_ids = _cycle_overlay_edge_ids(enhanced_snapshot)

    latest_plan = await get_latest_plan(db, project_id)
    path_node_ids = set(extract_plan_node_ids(latest_plan.plan_json if latest_plan else None))
    path_overlay_node_ids = sorted(node_id for node_id in visible_overlay_node_ids if node_id in path_node_ids)
    path_overlay_edge_ids = _path_overlay_edge_ids(visible_overlay_edges, path_node_ids)

    node_counts = _candidate_counts(active_nodes)
    edge_counts = _candidate_counts(active_edges)
    if node_counts["pending_review"] or edge_counts["pending_review"]:
        warning_items.append({"kind": "pending_review", "message": "存在已校验但尚未人工确认的 overlay 候选。"})
    if node_counts["planning_disabled"] or edge_counts["planning_disabled"]:
        warning_items.append({"kind": "planning_disabled", "message": "存在已确认但未开启规划的 overlay 候选。"})
    if node_counts["invalid"] or edge_counts["invalid"]:
        warning_items.append({"kind": "invalid_candidates", "message": "存在校验失败或需要复核的 overlay 候选。"})
    if shadowed_edge_ids:
        warning_items.append({"kind": "shadowed_edges", "edge_ids": shadowed_edge_ids, "message": "部分 overlay 关系已被基线图谱覆盖。"})
    if inactive_edge_ids:
        warning_items.append({"kind": "inactive_edges", "edge_ids": inactive_edge_ids, "message": "部分已确认关系未进入增强图谱，可能端点不可用或关系重复。"})
    if cycle_edge_ids:
        blocking_items.append({"kind": "requires_cycle", "edge_ids": cycle_edge_ids, "message": "增强图谱存在 REQUIRES 环依赖。"})

    status = "blocked" if blocking_items else "warning" if warning_items else "ok"
    counts = {
        "active_nodes": len(active_nodes),
        "active_edges": len(active_edges),
        "planner_visible_nodes": len(planner_nodes),
        "planner_visible_edges": len(planner_edges),
        "visible_overlay_nodes": len(visible_overlay_node_ids),
        "visible_overlay_edges": len(visible_overlay_edge_ids),
        "path_overlay_nodes": len(path_overlay_node_ids),
        "path_overlay_edges": len(path_overlay_edge_ids),
        "ignored_overlay_edges": len(ignored_overlay_edge_ids),
        "shadowed_edges": len(shadowed_edge_ids),
        "cycle_edges": len(cycle_edge_ids),
        "blocking_items": len(blocking_items),
        "warning_items": len(warning_items),
        "nodes": node_counts,
        "edges": edge_counts,
    }
    return {
        "project_id": project_id,
        "status": status,
        "summary": _preflight_summary(status, counts),
        "counts": counts,
        "visible_overlay_node_ids": visible_overlay_node_ids,
        "visible_overlay_edge_ids": visible_overlay_edge_ids,
        "path_overlay_node_ids": path_overlay_node_ids,
        "path_overlay_edge_ids": path_overlay_edge_ids,
        "ignored_overlay_edge_ids": ignored_overlay_edge_ids,
        "shadowed_edge_ids": shadowed_edge_ids,
        "cycle_edge_ids": cycle_edge_ids,
        "blocking_items": blocking_items,
        "warning_items": warning_items,
        "project_graph_hash": enhanced_snapshot.project_graph_hash,
    }
