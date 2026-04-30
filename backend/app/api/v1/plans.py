"""路径规划 API"""
import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core import error_codes
from app.core.exceptions import AppError, NotFoundError
from app.repositories.explanation_cache_repository import (
    get_explanation_cache,
    upsert_explanation_cache,
)
from app.repositories.plan_repository import (
    get_latest_plan,
    get_plan_by_id,
    get_plan_version_count,
    save_plan,
)
from app.repositories.profile_repository import get_latest_profile
from app.repositories.project_repository import get_project
from app.models.sqlite_models import VariantPreviewSession
from app.schemas.explanation import (
    ExplanationAskRequest,
    ExplanationAskResponse,
    ExplanationResponse,
)
from app.schemas.goal_resolution import VariantPreviewSessionResponse
from app.schemas.project import DEFAULT_PATH_MODE, validate_path_mode
from app.services.domain_pack_service import get_domain_pack_service
from app.services.explanation_service import (
    answer_explanation_question,
    build_explanation,
    polish_explanation,
)
from app.services.formal_path_audit_service import enrich_formal_path_audit
from app.services.goal_service import UnsupportedGoalTypeError, resolve_goal
from app.services.planner_service import plan_with_profile
from app.services.project_graph_snapshot_service import build_project_graph_snapshot

router = APIRouter()


class GeneratePlanRequest(BaseModel):
    path_mode: str | None = None


class VariantPreviewRequest(BaseModel):
    path_modes: list[str] | None = None


class GraphOptionPreviewRequest(BaseModel):
    path_mode: str | None = None


class VariantConfirmRequest(BaseModel):
    variant_id: str = Field(min_length=1)


def _validate_path_mode_or_raise(path_mode: str | None) -> str:
    try:
        return validate_path_mode(path_mode)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_PATH_MODE") from exc


def _safe_profile_path_mode(path_mode: Any) -> tuple[str | None, dict[str, Any]]:
    if not isinstance(path_mode, str) or not path_mode:
        return None, {}
    try:
        return validate_path_mode(path_mode), {"profile_path_mode_preference": path_mode}
    except ValueError:
        return None, {"invalid_profile_path_mode_preference": path_mode}


def _resolve_effective_path_mode(
    *,
    requested_path_mode: str | None,
    project_path_mode: str | None,
    profile: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    if requested_path_mode is not None:
        path_mode = _validate_path_mode_or_raise(requested_path_mode)
        return path_mode, "explicit_request", {"requested_path_mode": requested_path_mode}

    if project_path_mode and project_path_mode != DEFAULT_PATH_MODE:
        path_mode = _validate_path_mode_or_raise(project_path_mode)
        return path_mode, "project_path_mode", {"project_path_mode": project_path_mode}

    profile_mode, profile_resolution = _safe_profile_path_mode(profile.get("path_mode_preference"))
    if profile_mode is not None:
        return profile_mode, "learner_profile_preference", profile_resolution

    return DEFAULT_PATH_MODE, "standard_fallback", profile_resolution


def _stage_empty_reason(audit: dict[str, Any] | None, stage_name: str, tasks: list[dict[str, Any]]) -> str | None:
    stage_logs = audit.get("stage_logs") if isinstance(audit, dict) else {}
    stage_summaries = stage_logs.get("_stage_summaries") if isinstance(stage_logs, dict) else {}
    summary = stage_summaries.get(stage_name) if isinstance(stage_summaries, dict) else {}
    if isinstance(summary, dict) and summary.get("empty_reason"):
        return summary["empty_reason"]
    if not tasks:
        return "当前目标范围没有匹配到该阶段的知识点；系统不会为填充版式加入无关节点。"
    return None


def _dict_stages_to_list(stage_dict: dict, audit: dict[str, Any] | None = None) -> list[dict]:
    result = []
    for idx, (name, tasks) in enumerate(stage_dict.items()):
        stage = {
            "stage_index": idx,
            "stage_name": name,
            "tasks": tasks,
            "estimated_hours": sum(t.get("estimated_hours", 0) for t in tasks),
        }
        empty_reason = _stage_empty_reason(audit, name, tasks)
        if empty_reason:
            stage["empty_reason"] = empty_reason
        result.append(stage)
    return result


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _profile_to_dict(profile_row) -> dict[str, Any]:
    return {
        "math_level": profile_row.math_level,
        "coding_level": profile_row.coding_level,
        "ml_level": profile_row.ml_level,
        "theory_weight": profile_row.theory_weight,
        "practice_weight": profile_row.practice_weight,
        "weekly_hours": profile_row.weekly_hours,
        "deadline_weeks": profile_row.deadline_weeks,
        "path_mode_preference": profile_row.path_mode_preference,
        "learning_goal_orientation": profile_row.learning_goal_orientation,
        "resource_preference": profile_row.resource_preference,
        "practice_intensity": profile_row.practice_intensity,
        "persona_label": profile_row.persona_label,
        "persona_summary": profile_row.persona_summary,
        "persona_evidence": profile_row.persona_evidence,
    }


def _variant_modes(requested_modes: list[str] | None = None) -> list[str]:
    modes = requested_modes or ["standard", "compressed", "theory_first", "practice_first"]
    result: list[str] = []
    for mode in modes:
        normalized = _validate_path_mode_or_raise(mode)
        if normalized not in result:
            result.append(normalized)
    if not result:
        raise AppError(code=422, message="VARIANT_PATH_MODE_REQUIRED")
    return result


def _variant_id(path_mode: str, parameter_hash: str) -> str:
    return f"{path_mode}:{parameter_hash[:12]}"


def _build_variant_summary(path_mode: str, plan_result: dict[str, Any], parameter_hash: str) -> dict[str, Any]:
    audit = plan_result.get("audit") or {}
    budget = plan_result.get("budget_summary") or {}
    return {
        "variant_id": _variant_id(path_mode, parameter_hash),
        "path_mode": path_mode,
        "path_mode_source": audit.get("path_mode_source"),
        "budget_summary": budget,
        "included_node_ids": list(plan_result.get("ordered_ids") or []),
        "excluded_node_ids": [
            item["node_id"]
            for item in audit.get("excluded_nodes", [])
            if isinstance(item, dict) and isinstance(item.get("node_id"), str)
        ],
        "audit_summary": {
            "path_mode": path_mode,
            "path_mode_source": audit.get("path_mode_source"),
            "budget_status": budget.get("status"),
            "total_hours": plan_result.get("total_hours"),
            "node_count": plan_result.get("node_count"),
            "included_nodes": audit.get("included_nodes", []),
            "excluded_nodes": audit.get("excluded_nodes", []),
            "project_graph_hash": audit.get("project_graph_hash"),
        },
        "plan_result": plan_result,
    }


def _graph_option_variant_id(graph_option: str, path_mode: str, parameter_hash: str) -> str:
    return f"{graph_option}:{path_mode}:{parameter_hash[:12]}"


def _graph_option_labels(graph_option: str) -> tuple[str, str]:
    if graph_option == "baseline":
        return (
            "基础图谱路径",
            "只使用当前领域基线与项目中已移除/恢复的审核状态，不纳入项目级扩展草稿。",
        )
    return (
        "增强图谱路径",
        "使用领域基线，并纳入已确认、校验通过且开启规划的项目级 overlay 节点和关系。",
    )


def _overlay_ids_from_snapshot(snapshot) -> tuple[list[str], list[str]]:
    overlay_lineage = getattr(snapshot, "overlay_lineage", {}) or {}
    overlay_nodes = overlay_lineage.get("nodes") if isinstance(overlay_lineage, dict) else {}
    overlay_edges = overlay_lineage.get("edges") if isinstance(overlay_lineage, dict) else {}
    node_ids = sorted(overlay_nodes) if isinstance(overlay_nodes, dict) else []
    edge_ids = sorted(overlay_edges) if isinstance(overlay_edges, dict) else []
    return node_ids, edge_ids


def _path_overlay_edge_ids_from_snapshot(snapshot, included_node_ids: list[str]) -> list[str]:
    included = set(included_node_ids)
    if not included:
        return []
    overlay_lineage = getattr(snapshot, "overlay_lineage", {}) or {}
    overlay_edges = overlay_lineage.get("edges") if isinstance(overlay_lineage, dict) else {}
    if not isinstance(overlay_edges, dict):
        return []

    edge_ids: list[str] = []
    for edge_id, edge in overlay_edges.items():
        if not isinstance(edge_id, str) or not isinstance(edge, dict):
            continue
        edge_snapshot = edge.get("edge_snapshot") if isinstance(edge.get("edge_snapshot"), dict) else {}
        source = edge.get("source_node_id") or edge_snapshot.get("source")
        target = edge.get("target_node_id") or edge_snapshot.get("target")
        if source in included and target in included:
            edge_ids.append(edge_id)
    return sorted(edge_ids)


def _path_overlay_ids_from_snapshot(snapshot, included_node_ids: list[str]) -> tuple[list[str], list[str]]:
    visible_node_ids, _ = _overlay_ids_from_snapshot(snapshot)
    included = set(included_node_ids)
    path_node_ids = sorted(node_id for node_id in visible_node_ids if node_id in included)
    path_edge_ids = _path_overlay_edge_ids_from_snapshot(snapshot, included_node_ids)
    return path_node_ids, path_edge_ids


def _build_graph_option_goal_result(project, snapshot, confirmed_goal_result: dict[str, Any] | None) -> dict[str, Any] | None:
    try:
        resolved = resolve_goal(
            goal_text=project.goal_text,
            goal_type_override=project.goal_type,
            templates=snapshot.goal_templates,
            nodes_by_id=snapshot.nodes_by_id,
            supported_goal_types=snapshot.contract.supported_goal_types if snapshot.contract is not None else (),
            default_goal_policy=snapshot.contract.default_goal_policy if snapshot.contract is not None else None,
        )
    except UnsupportedGoalTypeError:
        resolved = None

    if confirmed_goal_result is None:
        return resolved
    if not resolved or not resolved.get("target_node_ids"):
        return deepcopy(confirmed_goal_result)

    merged = deepcopy(confirmed_goal_result)
    merged_target_ids: list[str] = []
    for node_id in list(confirmed_goal_result.get("target_node_ids") or []) + list(resolved.get("target_node_ids") or []):
        if node_id in snapshot.nodes_by_id and node_id not in merged_target_ids:
            merged_target_ids.append(node_id)
    merged["target_node_ids"] = merged_target_ids
    merged["confirmed_target_node_ids"] = merged_target_ids
    merged["effective_target_node_ids"] = merged_target_ids
    merged["resolve_source"] = "confirmed_plus_graph_option"
    merged["source_breakdown"] = resolved.get("source_breakdown") or merged.get("source_breakdown") or {}
    merged["warnings"] = sorted(set(merged.get("warnings", [])) | {"graph_option_target_merge"})
    return merged


def _build_unavailable_graph_option(
    *,
    graph_option: str,
    path_mode: str,
    parameter_hash: str,
    snapshot,
    blocked_reason: str,
) -> dict[str, Any]:
    option_label, option_description = _graph_option_labels(graph_option)
    overlay_node_ids, overlay_edge_ids = _overlay_ids_from_snapshot(snapshot)
    return {
        "variant_id": _graph_option_variant_id(graph_option, path_mode, parameter_hash),
        "path_mode": path_mode,
        "preview_kind": "graph_option",
        "graph_option": graph_option,
        "option_label": option_label,
        "option_description": option_description,
        "status": "unavailable",
        "blocked_reason": blocked_reason,
        "budget_summary": {},
        "included_node_ids": [],
        "excluded_node_ids": [],
        "added_node_ids": [],
        "removed_node_ids": [],
        "visible_overlay_node_ids": overlay_node_ids,
        "visible_overlay_edge_ids": overlay_edge_ids,
        "path_overlay_node_ids": [],
        "path_overlay_edge_ids": [],
        "overlay_node_ids": overlay_node_ids,
        "overlay_edge_ids": overlay_edge_ids,
        "order_changed": False,
        "order_changed_node_ids": [],
        "stage_changed": False,
        "stage_changed_node_ids": [],
        "budget_changed": False,
        "budget_delta": {"changed": False},
        "project_graph_hash": snapshot.project_graph_hash,
        "audit_summary": {
            "path_mode": path_mode,
            "graph_option": graph_option,
            "project_graph_hash": snapshot.project_graph_hash,
            "blocked_reason": blocked_reason,
            "visible_overlay_node_ids": overlay_node_ids,
            "visible_overlay_edge_ids": overlay_edge_ids,
            "path_overlay_node_ids": [],
            "path_overlay_edge_ids": [],
        },
    }


def _build_graph_option_summary(
    *,
    graph_option: str,
    path_mode: str,
    plan_result: dict[str, Any],
    parameter_hash: str,
    snapshot,
) -> dict[str, Any]:
    option_label, option_description = _graph_option_labels(graph_option)
    plan_result.setdefault("audit", {})["graph_option"] = {
        "preview_kind": "graph_option",
        "graph_option": graph_option,
        "option_label": option_label,
        "project_graph_hash": snapshot.project_graph_hash,
    }
    summary = _build_variant_summary(path_mode, plan_result, parameter_hash)
    overlay_node_ids, overlay_edge_ids = _overlay_ids_from_snapshot(snapshot)
    path_overlay_node_ids, path_overlay_edge_ids = _path_overlay_ids_from_snapshot(
        snapshot,
        summary["included_node_ids"],
    )
    summary.update({
        "variant_id": _graph_option_variant_id(graph_option, path_mode, parameter_hash),
        "preview_kind": "graph_option",
        "graph_option": graph_option,
        "option_label": option_label,
        "option_description": option_description,
        "status": "available",
        "blocked_reason": None,
        "added_node_ids": [],
        "removed_node_ids": [],
        "visible_overlay_node_ids": overlay_node_ids,
        "visible_overlay_edge_ids": overlay_edge_ids,
        "path_overlay_node_ids": path_overlay_node_ids,
        "path_overlay_edge_ids": path_overlay_edge_ids,
        "overlay_node_ids": overlay_node_ids,
        "overlay_edge_ids": overlay_edge_ids,
        "order_changed": False,
        "order_changed_node_ids": [],
        "stage_changed": False,
        "stage_changed_node_ids": [],
        "budget_changed": False,
        "budget_delta": {"changed": False},
        "project_graph_hash": snapshot.project_graph_hash,
    })
    summary["audit_summary"].update({
        "graph_option": graph_option,
        "option_label": option_label,
        "project_graph_hash": snapshot.project_graph_hash,
        "visible_overlay_node_ids": overlay_node_ids,
        "visible_overlay_edge_ids": overlay_edge_ids,
        "path_overlay_node_ids": path_overlay_node_ids,
        "path_overlay_edge_ids": path_overlay_edge_ids,
        "overlay_node_ids": overlay_node_ids,
        "overlay_edge_ids": overlay_edge_ids,
    })
    return summary


def _stage_assignment_map(plan_result: dict[str, Any]) -> dict[str, str]:
    stage_plan = plan_result.get("stage_plan") or {}
    if not isinstance(stage_plan, dict):
        return {}

    result: dict[str, str] = {}
    for stage_name, tasks in stage_plan.items():
        if not isinstance(stage_name, str) or not isinstance(tasks, list):
            continue
        for task in tasks:
            if isinstance(task, dict) and isinstance(task.get("node_id"), str):
                result[task["node_id"]] = stage_name
    return result


def _changed_order_node_ids(baseline_order: list[str], enhanced_order: list[str]) -> list[str]:
    baseline_positions = {node_id: index for index, node_id in enumerate(baseline_order)}
    enhanced_positions = {node_id: index for index, node_id in enumerate(enhanced_order)}
    common_ids = set(baseline_positions) & set(enhanced_positions)
    return sorted(
        node_id
        for node_id in common_ids
        if baseline_positions[node_id] != enhanced_positions[node_id]
    )


def _numeric_delta(before: Any, after: Any) -> float | int | None:
    if isinstance(before, bool) or isinstance(after, bool):
        return None
    if isinstance(before, (int, float)) and isinstance(after, (int, float)):
        return after - before
    return None


def _graph_option_budget_delta(baseline: dict[str, Any], enhanced: dict[str, Any]) -> dict[str, Any]:
    baseline_budget = baseline.get("budget_summary") or {}
    enhanced_budget = enhanced.get("budget_summary") or {}
    result: dict[str, Any] = {"changed": False}
    for field in ("total_hours", "estimated_weeks", "status"):
        before = baseline_budget.get(field)
        after = enhanced_budget.get(field)
        if before == after:
            continue
        entry = {"from": before, "to": after}
        delta = _numeric_delta(before, after)
        if delta is not None:
            entry["delta"] = delta
        result[field] = entry
        result["changed"] = True
    return result


def _apply_graph_option_diff(variants: list[dict[str, Any]]) -> None:
    for variant in variants:
        variant.setdefault("order_changed", False)
        variant.setdefault("order_changed_node_ids", [])
        variant.setdefault("stage_changed", False)
        variant.setdefault("stage_changed_node_ids", [])
        variant.setdefault("budget_changed", False)
        variant.setdefault("budget_delta", {"changed": False})

    by_option = {variant.get("graph_option"): variant for variant in variants}
    baseline = by_option.get("baseline")
    enhanced = by_option.get("enhanced")
    baseline_ids = set((baseline or {}).get("included_node_ids") or [])
    enhanced_ids = set((enhanced or {}).get("included_node_ids") or [])
    added_by_enhanced = sorted(enhanced_ids - baseline_ids)
    removed_by_enhanced = sorted(baseline_ids - enhanced_ids)
    if baseline:
        baseline.setdefault("audit_summary", {})["nodes_missing_vs_enhanced"] = added_by_enhanced
    if not enhanced:
        return

    baseline_order = list((baseline or {}).get("included_node_ids") or [])
    enhanced_order = list(enhanced.get("included_node_ids") or [])
    baseline_stage_map = _stage_assignment_map((baseline or {}).get("plan_result") or {})
    enhanced_stage_map = _stage_assignment_map(enhanced.get("plan_result") or {})
    common_stage_ids = set(baseline_stage_map) & set(enhanced_stage_map)
    stage_changed_node_ids = sorted(
        node_id
        for node_id in common_stage_ids
        if baseline_stage_map[node_id] != enhanced_stage_map[node_id]
    )
    budget_delta = _graph_option_budget_delta(baseline or {}, enhanced)

    enhanced["added_node_ids"] = added_by_enhanced
    enhanced["removed_node_ids"] = removed_by_enhanced
    enhanced["order_changed"] = baseline_order != enhanced_order
    enhanced["order_changed_node_ids"] = _changed_order_node_ids(baseline_order, enhanced_order)
    enhanced["stage_changed"] = bool(stage_changed_node_ids)
    enhanced["stage_changed_node_ids"] = stage_changed_node_ids
    enhanced["budget_changed"] = bool(budget_delta.get("changed"))
    enhanced["budget_delta"] = budget_delta

    audit_summary = enhanced.setdefault("audit_summary", {})
    audit_summary["nodes_added_vs_baseline"] = added_by_enhanced
    audit_summary["nodes_removed_vs_baseline"] = removed_by_enhanced
    audit_summary["graph_option_diff"] = {
        "order_changed": enhanced["order_changed"],
        "order_changed_node_ids": enhanced["order_changed_node_ids"],
        "stage_changed": enhanced["stage_changed"],
        "stage_changed_node_ids": stage_changed_node_ids,
        "budget_changed": enhanced["budget_changed"],
        "budget_delta": budget_delta,
        "path_overlay_node_ids": enhanced.get("path_overlay_node_ids", []),
        "path_overlay_edge_ids": enhanced.get("path_overlay_edge_ids", []),
    }


def _public_variant(variant: dict[str, Any]) -> dict[str, Any]:
    response = {
        "variant_id": variant["variant_id"],
        "path_mode": variant["path_mode"],
        "path_mode_source": variant.get("path_mode_source"),
        "budget_summary": variant.get("budget_summary", {}),
        "included_node_ids": variant.get("included_node_ids", []),
        "excluded_node_ids": variant.get("excluded_node_ids", []),
        "audit_summary": variant.get("audit_summary", {}),
    }
    for key in (
        "preview_kind",
        "graph_option",
        "option_label",
        "option_description",
        "status",
        "blocked_reason",
        "added_node_ids",
        "removed_node_ids",
        "visible_overlay_node_ids",
        "visible_overlay_edge_ids",
        "path_overlay_node_ids",
        "path_overlay_edge_ids",
        "overlay_node_ids",
        "overlay_edge_ids",
        "order_changed",
        "order_changed_node_ids",
        "stage_changed",
        "stage_changed_node_ids",
        "budget_changed",
        "budget_delta",
        "project_graph_hash",
    ):
        if key in variant:
            response[key] = variant[key]
    return response


def _variant_session_response(session: VariantPreviewSession) -> dict[str, Any]:
    variants = _load_json_list_or_dicts(session.variants_json)
    return {
        "variant_preview_id": session.variant_preview_id,
        "project_id": session.project_id,
        "status": session.status,
        "expires_at": session.expires_at,
        "pack_hash": session.pack_hash,
        "project_graph_hash": session.project_graph_hash,
        "profile_hash": session.profile_hash,
        "parameter_hash": session.parameter_hash,
        "variants": [_public_variant(variant) for variant in variants],
    }


def _load_json_list_or_dicts(raw_value: str | None) -> list[dict[str, Any]]:
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _load_plan_stages(plan_json: str | None, audit: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    raw_stages = json.loads(plan_json) if plan_json else {}
    if isinstance(raw_stages, dict):
        return _dict_stages_to_list(raw_stages, audit)
    return raw_stages if isinstance(raw_stages, list) else []


def _build_explanation_nodes_by_id(
    pack,
    audit: dict[str, Any],
    stages: list[dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    nodes_by_id = dict(pack.nodes_by_id)
    fallback_reasons: list[str] = []
    live_pack_fields: list[str] = []
    planned_node_ids: set[str] = set()

    for stage in stages:
        for task in stage.get("tasks", []):
            if not isinstance(task, dict) or not task.get("node_id"):
                continue
            node_id = task["node_id"]
            planned_node_ids.add(node_id)
            snapshot_node = dict(nodes_by_id.get(node_id, {"id": node_id}))
            if task.get("name"):
                snapshot_node["name"] = task["name"]
            if task.get("difficulty") is not None:
                snapshot_node["difficulty_final"] = task["difficulty"]
            if task.get("importance") is not None:
                snapshot_node["importance_final"] = task["importance"]
            if task.get("estimated_hours") is not None:
                snapshot_node["estimated_hours"] = task["estimated_hours"]
            nodes_by_id[node_id] = snapshot_node

    for node_id in audit.get("ordering_logs", {}):
        if node_id not in planned_node_ids:
            fallback_reasons.append(f"node_snapshot_missing:{node_id}")
            live_pack_fields.append("nodes_by_id")

    overlay_lineage = audit.get("overlay_lineage")
    overlay_nodes = (
        overlay_lineage.get("nodes")
        if isinstance(overlay_lineage, dict) and isinstance(overlay_lineage.get("nodes"), dict)
        else {}
    )
    for node_id, lineage in overlay_nodes.items():
        node_snapshot = lineage.get("node_snapshot") if isinstance(lineage, dict) else None
        if isinstance(node_snapshot, dict):
            nodes_by_id[node_id] = dict(node_snapshot)

    if not isinstance(overlay_lineage, dict):
        fallback_reasons.append("overlay_lineage_missing")

    return nodes_by_id, {
        "fallback_reasons": fallback_reasons,
        "live_pack_fields": live_pack_fields,
    }


def _load_json_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [item for item in data if isinstance(item, str) and item]


def _load_json_dict(raw_value: str | None) -> dict[str, Any]:
    if not raw_value:
        return {}
    try:
        data = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _build_confirmed_goal_result(project) -> dict[str, Any] | None:
    confirmed_target_node_ids = _load_json_list(project.confirmed_target_node_ids_json)
    if not confirmed_target_node_ids:
        return None
    missing_concepts = _load_json_list(getattr(project, "missing_concepts_json", None))
    return {
        "goal_text": project.goal_text,
        "goal_type": project.goal_type,
        "target_node_ids": list(confirmed_target_node_ids),
        "confirmed_target_node_ids": list(confirmed_target_node_ids),
        "effective_target_node_ids": list(confirmed_target_node_ids),
        "mode": project.confirmed_mode or "steady",
        "description": project.confirmed_description or project.goal_text,
        "template_id": project.confirmed_template_id,
        "resolve_source": project.confirmed_resolve_source or "confirmed",
        "candidate_id": project.confirmed_candidate_id,
        "selected_candidate_id": project.confirmed_candidate_id,
        "recommended_candidate_id": project.confirmed_candidate_id,
        "requested_goal_type": project.requested_goal_type,
        "auto_detected_goal_type": project.auto_detected_goal_type,
        "effective_goal_type": project.goal_type,
        "goal_type_source": "confirmed_resolution",
        "partial_accepted": bool(getattr(project, "partial_accepted", False)),
        "missing_concepts": missing_concepts,
        "source_breakdown": _load_json_dict(project.confirmed_source_breakdown_json),
        "score_breakdown": {},
        "warnings": [],
    }


def _variant_parameter_hash(project, confirmed_goal_result: dict[str, Any] | None, path_modes: list[str]) -> str:
    return _hash_json({
        "goal_text": project.goal_text,
        "goal_type": project.goal_type,
        "path_modes": path_modes,
        "confirmed_goal_result": confirmed_goal_result or {},
    })


def _variant_session_path_modes(session: VariantPreviewSession) -> list[str]:
    history = _load_json_dict(session.decision_history_json)
    path_modes = history.get("path_modes")
    if isinstance(path_modes, list):
        normalized = [mode for mode in path_modes if isinstance(mode, str)]
        if normalized:
            return normalized
    return [
        variant["path_mode"]
        for variant in _load_json_list_or_dicts(session.variants_json)
        if isinstance(variant.get("path_mode"), str)
    ]


def _selected_variant(session: VariantPreviewSession, variant_id: str) -> dict[str, Any]:
    variants = _load_json_list_or_dicts(session.variants_json)
    for variant in variants:
        if variant.get("variant_id") == variant_id:
            return variant
    raise AppError(code=422, message="INVALID_VARIANT_ID")


def _plan_response(path, plan_result: dict[str, Any], path_mode: str, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    audit = plan_result.get("audit") or {}
    response = {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": _dict_stages_to_list(plan_result["stage_plan"], audit),
        "budget_status": plan_result["budget_summary"]["status"],
        "path_mode": plan_result.get("path_mode", path_mode),
        "path_mode_source": audit.get("path_mode_source"),
        "total_hours": plan_result["total_hours"],
        "node_count": plan_result["node_count"],
        "reinforced_ids": plan_result["reinforced_ids"],
        "text_output": plan_result["text_output"],
    }
    if extra:
        response.update(extra)
    return response


def _confirmed_variant_id(session: VariantPreviewSession) -> str | None:
    history = _load_json_dict(session.decision_history_json)
    selected = history.get("selected_variant_id")
    return selected if isinstance(selected, str) else None


async def _return_confirmed_variant(session: VariantPreviewSession, variant_id: str, db: AsyncSession) -> dict[str, Any]:
    confirmed_variant_id = _confirmed_variant_id(session)
    if confirmed_variant_id and confirmed_variant_id != variant_id:
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    selected = _selected_variant(session, variant_id)
    if not session.path_id:
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    path = await get_plan_by_id(db, session.path_id)
    if path is None or path.project_id != session.project_id:
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    plan_result = selected.get("plan_result")
    if not isinstance(plan_result, dict):
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    return _plan_response(
        path,
        plan_result,
        selected["path_mode"],
        {
            "variant_preview_id": session.variant_preview_id,
            "variant_id": variant_id,
            "idempotent": True,
        },
    )


async def _ensure_active_variant_session(
    db: AsyncSession,
    *,
    project_id: str,
    preview_id: str,
    variant_id: str,
) -> VariantPreviewSession:
    session = await db.get(VariantPreviewSession, preview_id)
    if session is None or session.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    if session.status == "confirmed":
        return session
    if session.status != "active" or session.expires_at < _naive_utc_now():
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    _selected_variant(session, variant_id)
    return session


@router.post(
    "/projects/{project_id}/plans/variants/preview",
    response_model=VariantPreviewSessionResponse,
)
async def preview_plan_variants(
    project_id: str,
    req: VariantPreviewRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    profile_row = await get_latest_profile(db, project_id)
    if not profile_row:
        raise AppError(code=400, message="请先完成画像测评再生成路径")

    path_modes = _variant_modes(req.path_modes if req else None)
    profile = _profile_to_dict(profile_row)
    profile_hash = _hash_json(profile)
    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)
    confirmed_goal_result = _build_confirmed_goal_result(project)
    parameter_hash = _variant_parameter_hash(project, confirmed_goal_result, path_modes)

    variants: list[dict[str, Any]] = []
    for path_mode in path_modes:
        try:
            plan_result = plan_with_profile(
                goal_text=project.goal_text,
                goal_type=project.goal_type,
                profile=profile,
                pack=snapshot,
                removed_node_ids=snapshot.removed_node_ids,
                removed_edge_ids=snapshot.removed_edge_ids,
                confirmed_goal_result=deepcopy(confirmed_goal_result) if confirmed_goal_result else None,
                path_mode=path_mode,
                path_mode_source="variant_preview",
                path_mode_resolution={"preview_path_mode": path_mode},
            )
        except UnsupportedGoalTypeError as exc:
            raise AppError(code=409, message="GOAL_DEFAULT_TARGETS_UNAVAILABLE", details={"reason": str(exc)}) from exc
        if confirmed_goal_result and not plan_result["goal_result"]["target_node_ids"]:
            raise AppError(code=409, message="GOAL_TARGETS_REMOVED")
        variants.append(_build_variant_summary(path_mode, plan_result, parameter_hash))

    session = VariantPreviewSession(
        project_id=project_id,
        pack_hash=snapshot.pack_hash,
        project_graph_hash=snapshot.project_graph_hash,
        profile_hash=profile_hash,
        parameter_hash=parameter_hash,
        variants_json=_canonical_json(variants),
        status="active",
        decision_history_json=_canonical_json({
            "event": "preview_created",
            "path_modes": path_modes,
        }),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _variant_session_response(session)


@router.post(
    "/projects/{project_id}/plans/graph-options/preview",
    response_model=VariantPreviewSessionResponse,
)
async def preview_graph_options(
    project_id: str,
    req: GraphOptionPreviewRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    profile_row = await get_latest_profile(db, project_id)
    if not profile_row:
        raise AppError(code=400, message="请先完成画像测评再生成路径")

    profile = _profile_to_dict(profile_row)
    path_mode, path_mode_source, path_mode_resolution = _resolve_effective_path_mode(
        requested_path_mode=req.path_mode if req else None,
        project_path_mode=getattr(project, "path_mode", None),
        profile=profile,
    )
    profile_hash = _hash_json(profile)
    confirmed_goal_result = _build_confirmed_goal_result(project)
    parameter_hash = _variant_parameter_hash(project, confirmed_goal_result, [path_mode])

    variants: list[dict[str, Any]] = []
    snapshots = {}
    for graph_option, include_overlay in (("baseline", False), ("enhanced", True)):
        snapshot = await build_project_graph_snapshot(
            db,
            project_id,
            domain=project.domain,
            include_overlay=include_overlay,
        )
        snapshots[graph_option] = snapshot
        option_goal_result = _build_graph_option_goal_result(project, snapshot, confirmed_goal_result)
        try:
            plan_result = plan_with_profile(
                goal_text=project.goal_text,
                goal_type=project.goal_type,
                profile=profile,
                pack=snapshot,
                removed_node_ids=snapshot.removed_node_ids,
                removed_edge_ids=snapshot.removed_edge_ids,
                confirmed_goal_result=deepcopy(option_goal_result) if option_goal_result else None,
                path_mode=path_mode,
                path_mode_source=path_mode_source,
                path_mode_resolution=path_mode_resolution,
            )
        except UnsupportedGoalTypeError:
            variants.append(_build_unavailable_graph_option(
                graph_option=graph_option,
                path_mode=path_mode,
                parameter_hash=parameter_hash,
                snapshot=snapshot,
                blocked_reason="GOAL_DEFAULT_TARGETS_UNAVAILABLE",
            ))
            continue
        if option_goal_result and not plan_result["goal_result"]["target_node_ids"]:
            variants.append(_build_unavailable_graph_option(
                graph_option=graph_option,
                path_mode=path_mode,
                parameter_hash=parameter_hash,
                snapshot=snapshot,
                blocked_reason="GOAL_TARGETS_REMOVED",
            ))
            continue
        variants.append(_build_graph_option_summary(
            graph_option=graph_option,
            path_mode=path_mode,
            plan_result=plan_result,
            parameter_hash=parameter_hash,
            snapshot=snapshot,
        ))

    _apply_graph_option_diff(variants)
    enhanced_snapshot = snapshots["enhanced"]
    session = VariantPreviewSession(
        project_id=project_id,
        pack_hash=enhanced_snapshot.pack_hash,
        project_graph_hash=enhanced_snapshot.project_graph_hash,
        profile_hash=profile_hash,
        parameter_hash=parameter_hash,
        variants_json=_canonical_json(variants),
        status="active",
        decision_history_json=_canonical_json({
            "event": "graph_option_preview_created",
            "preview_kind": "graph_option",
            "path_modes": [path_mode],
            "graph_options": ["baseline", "enhanced"],
            "option_graph_hashes": {
                "baseline": snapshots["baseline"].project_graph_hash,
                "enhanced": enhanced_snapshot.project_graph_hash,
            },
        }),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _variant_session_response(session)


@router.post("/projects/{project_id}/plans/variants/{preview_id}/confirm")
async def confirm_plan_variant(
    project_id: str,
    preview_id: str,
    req: VariantConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    session = await _ensure_active_variant_session(
        db,
        project_id=project_id,
        preview_id=preview_id,
        variant_id=req.variant_id,
    )
    if session.status == "confirmed":
        return await _return_confirmed_variant(session, req.variant_id, db)

    profile_row = await get_latest_profile(db, project_id)
    if not profile_row:
        raise AppError(code=400, message="请先完成画像测评再生成路径")
    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)
    profile_hash = _hash_json(_profile_to_dict(profile_row))
    if session.pack_hash != snapshot.pack_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_VARIANT_PREVIEW,
            details={"reason_code": error_codes.PACK_HASH_DRIFT},
        )
    if session.project_graph_hash != snapshot.project_graph_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_VARIANT_PREVIEW,
            details={"reason_code": error_codes.PROJECT_GRAPH_DRIFT},
        )
    if session.profile_hash != profile_hash:
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW, details={"reason_code": "PROFILE_DRIFT"})

    confirmed_goal_result = _build_confirmed_goal_result(project)
    current_parameter_hash = _variant_parameter_hash(
        project,
        confirmed_goal_result,
        _variant_session_path_modes(session),
    )
    if session.parameter_hash != current_parameter_hash:
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW, details={"reason_code": "PARAMETER_DRIFT"})

    selected = _selected_variant(session, req.variant_id)
    if selected.get("status") == "unavailable":
        raise AppError(
            code=409,
            message="GRAPH_OPTION_UNAVAILABLE",
            details={"blocked_reason": selected.get("blocked_reason")},
        )
    plan_result = selected.get("plan_result")
    if not isinstance(plan_result, dict):
        raise AppError(code=409, message=error_codes.STALE_VARIANT_PREVIEW)
    plan_result = deepcopy(plan_result)
    variant_audit = {
        "variant_preview_id": session.variant_preview_id,
        "variant_id": selected["variant_id"],
        "path_mode": selected["path_mode"],
        "parameter_hash": session.parameter_hash,
    }
    for key in ("preview_kind", "graph_option", "option_label", "project_graph_hash"):
        if selected.get(key) is not None:
            variant_audit[key] = selected[key]
    plan_result.setdefault("audit", {})["variant"] = variant_audit
    await enrich_formal_path_audit(db, project=project, plan_result=plan_result)

    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, plan_result, version=version, commit=False)
    session.status = "confirmed"
    session.path_id = path.id
    session.decision_history_json = _canonical_json({
        "event": "variant_confirmed",
        "selected_variant_id": req.variant_id,
        "path_id": path.id,
    })
    await db.commit()
    await db.refresh(path)
    await db.refresh(session)
    return _plan_response(
        path,
        plan_result,
        selected["path_mode"],
        {
            "variant_preview_id": session.variant_preview_id,
            "variant_id": req.variant_id,
            "idempotent": False,
        },
    )


@router.post("/projects/{project_id}/plans")
async def generate_plan(
    project_id: str,
    req: GeneratePlanRequest | None = None,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    profile_row = await get_latest_profile(db, project_id)
    if not profile_row:
        raise AppError(code=400, message="请先完成画像测评再生成路径")

    profile = {
        "math_level": profile_row.math_level,
        "coding_level": profile_row.coding_level,
        "ml_level": profile_row.ml_level,
        "theory_weight": profile_row.theory_weight,
        "practice_weight": profile_row.practice_weight,
        "weekly_hours": profile_row.weekly_hours,
        "deadline_weeks": profile_row.deadline_weeks,
        "path_mode_preference": profile_row.path_mode_preference,
        "learning_goal_orientation": profile_row.learning_goal_orientation,
        "resource_preference": profile_row.resource_preference,
        "practice_intensity": profile_row.practice_intensity,
        "persona_label": profile_row.persona_label,
        "persona_summary": profile_row.persona_summary,
        "persona_evidence": profile_row.persona_evidence,
    }
    requested_path_mode = req.path_mode if req and req.path_mode is not None else None
    path_mode, path_mode_source, path_mode_resolution = _resolve_effective_path_mode(
        requested_path_mode=requested_path_mode,
        project_path_mode=getattr(project, "path_mode", None),
        profile=profile,
    )
    project.path_mode = path_mode

    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)

    confirmed_goal_result = _build_confirmed_goal_result(project)
    try:
        plan_result = plan_with_profile(
            goal_text=project.goal_text,
            goal_type=project.goal_type,
            profile=profile,
            pack=snapshot,
            removed_node_ids=snapshot.removed_node_ids,
            removed_edge_ids=snapshot.removed_edge_ids,
            confirmed_goal_result=deepcopy(confirmed_goal_result) if confirmed_goal_result else None,
            path_mode=path_mode,
            path_mode_source=path_mode_source,
            path_mode_resolution=path_mode_resolution,
        )
    except ValueError as exc:
        if str(exc) == "INVALID_PATH_MODE":
            raise AppError(code=422, message="INVALID_PATH_MODE") from exc
        raise
    except UnsupportedGoalTypeError as exc:
        raise AppError(code=409, message="GOAL_DEFAULT_TARGETS_UNAVAILABLE", details={"reason": str(exc)}) from exc

    if confirmed_goal_result and not plan_result["goal_result"]["target_node_ids"]:
        raise AppError(code=409, message="GOAL_TARGETS_REMOVED")
    await enrich_formal_path_audit(db, project=project, plan_result=plan_result)

    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, plan_result, version=version)

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": _dict_stages_to_list(plan_result["stage_plan"], plan_result.get("audit")),
        "budget_status": plan_result["budget_summary"]["status"],
        "path_mode": plan_result.get("path_mode", path_mode),
        "path_mode_source": (plan_result.get("audit") or {}).get("path_mode_source"),
        "total_hours": plan_result["total_hours"],
        "node_count": plan_result["node_count"],
        "reinforced_ids": plan_result["reinforced_ids"],
        "text_output": plan_result["text_output"],
    }


@router.get("/projects/{project_id}/plans/latest")
async def get_latest_plan_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径")

    audit = json.loads(path.audit_json) if path.audit_json else None
    stages = _load_plan_stages(path.plan_json, audit)

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": stages,
        "budget_status": path.budget_status,
        "path_mode": (audit or {}).get("path_mode", "standard"),
        "path_mode_source": (audit or {}).get("path_mode_source"),
        "total_hours": path.total_hours,
        "audit": audit,
    }


def _should_cache_explanation(response: ExplanationResponse, *, polish: bool) -> bool:
    if not polish:
        return True
    return response.meta is not None and response.meta.polish.applied


async def _build_latest_explanation_response(
    project_id: str,
    db: AsyncSession,
    *,
    polish: bool = False,
    use_cache: bool = True,
) -> tuple[ExplanationResponse, set[str]]:
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径")

    audit = json.loads(path.audit_json) if path.audit_json else None
    if not audit:
        raise NotFoundError("暂无审计数据")

    stages = _load_plan_stages(path.plan_json, audit)
    latest_plan_node_ids = {
        task.get("node_id")
        for stage in stages
        for task in stage.get("tasks", [])
        if isinstance(task, dict) and isinstance(task.get("node_id"), str)
    }
    if use_cache:
        cached = await get_explanation_cache(db, path_id=path.id, polish_requested=polish)
        if cached is not None:
            return ExplanationResponse.model_validate_json(cached.explanation_json), latest_plan_node_ids

    pack = get_domain_pack_service(project.domain)
    nodes_by_id, context = _build_explanation_nodes_by_id(pack, audit, stages)
    pack_version = audit.get("pack_version") or pack.manifest.get("version")
    context.update(
        {
            "plan_version": path.version,
            "stages": stages,
            "total_hours": path.total_hours,
            "budget_status": path.budget_status,
            "path_mode": audit.get("path_mode") or getattr(project, "path_mode", None) or "standard",
            "pack_version": str(pack_version) if pack_version is not None else None,
            "pack_version_source": "audit" if audit.get("pack_version") else "live_pack",
            "project_graph_hash": audit.get("project_graph_hash"),
            "project_graph_hash_source": "audit" if audit.get("project_graph_hash") else "missing",
        }
    )
    scoring_config = audit.get("scoring_config") if isinstance(audit.get("scoring_config"), dict) else pack.scoring_config
    if "scoring_config" not in audit:
        context.setdefault("fallback_reasons", []).append("scoring_config_missing")
        context.setdefault("live_pack_fields", []).append("scoring_config")
    response = build_explanation(
        audit,
        nodes_by_id,
        pack.requires_rev_adj,
        scoring_config,
        context=context,
    )
    response = polish_explanation(response, requested=polish)
    if _should_cache_explanation(response, polish=polish):
        await upsert_explanation_cache(
            db,
            project_id=project_id,
            path_id=path.id,
            plan_version=path.version,
            polish_requested=polish,
            explanation_json=response.model_dump_json(),
        )
    return response, latest_plan_node_ids


@router.get("/projects/{project_id}/explanation", response_model=ExplanationResponse)
async def get_explanation(
    project_id: str,
    polish: bool = False,
    db: AsyncSession = Depends(get_db),
):
    """获取最新路径的结构化解释。`polish=true` 时只启用可选 LLM 自然语言润色。"""
    response, _latest_plan_node_ids = await _build_latest_explanation_response(project_id, db, polish=polish)
    return response


@router.post(
    "/projects/{project_id}/explanation/ask",
    response_model=ExplanationAskResponse,
)
async def ask_explanation(
    project_id: str,
    req: ExplanationAskRequest,
    db: AsyncSession = Depends(get_db),
):
    response, latest_plan_node_ids = await _build_latest_explanation_response(project_id, db, polish=False)
    return answer_explanation_question(
        response,
        req,
        latest_plan_node_ids=latest_plan_node_ids,
    )
