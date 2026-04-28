from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import ClarificationSession, GoalResolutionSession

_LLM_FALLBACK_WARNINGS = {
    "llm_unavailable",
    "llm_timeout",
    "llm_auth_failed",
    "llm_invalid_json",
    "llm_schema_violation",
    "llm_policy_violation",
}


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _json_list(value: str | None) -> list[str]:
    data = _json_loads(value, [])
    return [item for item in data if isinstance(item, str) and item]


def _iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return None


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


async def _latest_resolution_session(db: AsyncSession, project_id: str) -> GoalResolutionSession | None:
    result = await db.execute(
        select(GoalResolutionSession)
        .where(
            GoalResolutionSession.project_id == project_id,
            GoalResolutionSession.status == "confirmed",
        )
        .order_by(GoalResolutionSession.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _clarification_trace(db: AsyncSession, resolution_session_id: str | None, project_id: str) -> dict[str, Any]:
    if not resolution_session_id:
        result = await db.execute(
            select(ClarificationSession)
            .where(ClarificationSession.project_id == project_id)
            .order_by(ClarificationSession.updated_at.desc())
            .limit(1)
        )
    else:
        result = await db.execute(
            select(ClarificationSession)
            .where(ClarificationSession.goal_resolution_session_id == resolution_session_id)
            .order_by(
                (ClarificationSession.project_id == project_id).desc(),
                ClarificationSession.updated_at.desc(),
            )
            .limit(1)
        )
    session = result.scalar_one_or_none()
    if session is None:
        return {"clarification_session_ids": [], "clarification_trace": None}
    return {
        "clarification_session_ids": [session.clarification_session_id],
        "clarification_trace": {
            "clarification_session_id": session.clarification_session_id,
            "status": session.status,
            "turn_count": session.turn_count,
            "max_turns": session.max_turns,
            "controlled_answers": _json_loads(session.controlled_answers_json, []),
            "decision_history": _json_loads(session.decision_history_json, []),
            "completed_at": _iso(session.completed_at),
        },
    }


def _selected_candidate(project: Any, session: GoalResolutionSession | None) -> dict[str, Any]:
    candidate_id = getattr(project, "confirmed_candidate_id", None)
    candidates = _json_loads(session.candidates_json if session else None, [])
    if isinstance(candidates, list):
        for candidate in candidates:
            if isinstance(candidate, dict) and candidate.get("candidate_id") == candidate_id:
                return deepcopy(candidate)
    return {
        "candidate_id": candidate_id,
        "goal_type": getattr(project, "goal_type", None),
        "target_node_ids": _json_list(getattr(project, "confirmed_target_node_ids_json", None)),
        "mode": getattr(project, "confirmed_mode", None),
        "description": getattr(project, "confirmed_description", None) or getattr(project, "goal_text", None),
        "template_id": getattr(project, "confirmed_template_id", None),
        "resolve_source": getattr(project, "confirmed_resolve_source", None),
        "source_breakdown": _json_loads(getattr(project, "confirmed_source_breakdown_json", None), {}),
        "warnings": [],
    }


def _coverage_decision(project: Any, session: GoalResolutionSession | None, audit: dict[str, Any]) -> dict[str, Any]:
    response = _json_loads(session.coverage_response_json if session else None, {})
    if not isinstance(response, dict):
        response = {}
    confirmed_targets = _json_list(getattr(project, "confirmed_target_node_ids_json", None))
    coverage_status = response.get("coverage_status") or ("partial" if getattr(project, "partial_accepted", False) else "covered")
    result_type = response.get("result_type") or ("confirm_partial" if coverage_status == "partial" else "select_candidate")
    return {
        "resolution_session_id": session.session_id if session else None,
        "coverage_status": coverage_status,
        "result_type": result_type,
        "selected_candidate_id": getattr(project, "confirmed_candidate_id", None),
        "confirmed_target_node_ids": confirmed_targets,
        "covered_target_node_ids": response.get("covered_target_node_ids") or confirmed_targets,
        "missing_concepts": response.get("missing_concepts") or _json_list(getattr(project, "missing_concepts_json", None)),
        "target_authority": response.get("target_authority"),
        "pack_hash": getattr(session, "pack_hash", None),
        "project_graph_hash": getattr(session, "project_graph_hash", None) or audit.get("project_graph_hash"),
    }


def _derived_planner_parameters(audit: dict[str, Any], goal_frame: dict[str, Any] | None) -> dict[str, Any]:
    planner_parameters = goal_frame.get("planner_parameters", {}) if isinstance(goal_frame, dict) else {}
    if not isinstance(planner_parameters, dict):
        planner_parameters = {}
    profile = audit.get("profile_snapshot") if isinstance(audit.get("profile_snapshot"), dict) else {}
    budget = audit.get("budget_summary") if isinstance(audit.get("budget_summary"), dict) else {}
    return {
        "path_mode": audit.get("path_mode") or planner_parameters.get("path_mode") or budget.get("path_mode") or "standard",
        "theory_weight": profile.get("theory_weight", planner_parameters.get("theory_weight")),
        "practice_weight": profile.get("practice_weight", planner_parameters.get("practice_weight")),
        "weekly_hours": profile.get("weekly_hours", planner_parameters.get("weekly_hours")),
        "deadline_weeks": profile.get("deadline_weeks", planner_parameters.get("deadline_weeks")),
        "explanation_focus": planner_parameters.get("explanation_focus", []),
        "source": "goal_frame_normalized_then_profile_snapshot",
    }


def _overlay_draft_lineage(audit: dict[str, Any]) -> dict[str, Any]:
    overlay_lineage = audit.get("overlay_lineage")
    overlay_nodes = overlay_lineage.get("nodes", {}) if isinstance(overlay_lineage, dict) else {}
    overlay_edges = overlay_lineage.get("edges", {}) if isinstance(overlay_lineage, dict) else {}
    draft_nodes: list[dict[str, Any]] = []
    for node_id, lineage in overlay_nodes.items():
        if not isinstance(lineage, dict):
            continue
        provenance = lineage.get("provenance") if isinstance(lineage.get("provenance"), dict) else {}
        if provenance.get("origin") != "goal_extension_draft":
            continue
        draft_nodes.append({
            "node_id": node_id,
            "origin": provenance.get("origin"),
            "goal_trace": provenance.get("goal_trace"),
            "missing_concept": provenance.get("missing_concept"),
            "review_status": lineage.get("review_status"),
            "validation_status": lineage.get("validation_status"),
        })
    return {
        "draft_node_count": len(draft_nodes),
        "draft_edge_count": sum(1 for item in overlay_edges.values() if isinstance(item, dict)),
        "draft_nodes": draft_nodes,
    }


def _llm_fallback_status(goal_frame: dict[str, Any] | None, selected_candidate: dict[str, Any], coverage_decision: dict[str, Any]) -> dict[str, Any]:
    sources = goal_frame.get("sources", []) if isinstance(goal_frame, dict) else []
    source_breakdown = selected_candidate.get("source_breakdown") if isinstance(selected_candidate, dict) else {}
    warnings = _dedupe_strings([
        *list(selected_candidate.get("warnings") or []),
        *list(coverage_decision.get("warnings") or []),
    ])
    llm_used = bool(isinstance(source_breakdown, dict) and source_breakdown.get("llm")) or any(
        isinstance(source, dict) and source.get("source") == "llm"
        for source in sources
    )
    fallback_reasons = [warning for warning in warnings if warning in _LLM_FALLBACK_WARNINGS]
    return {
        "authority": "rules_first",
        "llm_used": llm_used,
        "fallback_used": bool(fallback_reasons),
        "fallback_reasons": fallback_reasons,
        "warnings": warnings,
    }


def _authority_labels(audit: dict[str, Any], llm_status: dict[str, Any], overlay_drafts: dict[str, Any]) -> list[dict[str, Any]]:
    labels = [
        {
            "kind": "rules_authority",
            "label": "规则权威",
            "description": "正式路径由已确认目标、知识图谱硬前置闭包、拓扑排序和画像规则生成。",
            "source": "audit.planner_inputs",
        },
        {
            "kind": "ai_assisted_understanding",
            "label": "AI 辅助理解",
            "description": "LLM 只可辅助目标理解或解释润色；不能替代确认目标、删除硬前置或写入正式路径。",
            "source": "audit.llm_fallback_status",
            "active": bool(llm_status.get("llm_used")),
        },
        {
            "kind": "overlay_drafts",
            "label": "项目扩展草稿",
            "description": "项目 overlay 只有在校验通过、人工确认并允许规划后才会进入路径快照。",
            "source": "audit.overlay_draft_lineage",
            "active": bool(overlay_drafts.get("draft_node_count")),
        },
        {
            "kind": "polish",
            "label": "解释润色",
            "description": "自然语言润色是解释层可选能力，不参与路径正确性判定。",
            "source": "explanation.meta.polish",
        },
    ]
    if audit.get("variant"):
        labels.append({
            "kind": "variant_preview",
            "label": "变体确认",
            "description": "本正式路径来自用户确认的单个 TTL 变体预览。",
            "source": "audit.variant",
            "active": True,
        })
    graph_option = audit.get("graph_option")
    if isinstance(graph_option, dict):
        labels.append({
            "kind": "graph_option_preview",
            "label": graph_option.get("option_label") or "图谱方案确认",
            "description": "用户在基础图谱与已审核扩展图谱之间选择后，正式路径仍由图算法生成。",
            "source": "audit.graph_option",
            "active": True,
        })
    if audit.get("feedback"):
        labels.append({
            "kind": "feedback_preview",
            "label": "反馈确认",
            "description": "本正式路径来自用户确认的受控反馈意图。",
            "source": "audit.feedback",
            "active": True,
        })
    return labels


def _planner_inputs(audit: dict[str, Any], derived_parameters: dict[str, Any]) -> dict[str, Any]:
    goal = audit.get("goal_result") if isinstance(audit.get("goal_result"), dict) else {}
    return {
        "confirmed_target_node_ids": goal.get("confirmed_target_node_ids") or goal.get("target_node_ids") or [],
        "effective_target_node_ids": goal.get("effective_target_node_ids") or goal.get("target_node_ids") or [],
        "path_mode": derived_parameters.get("path_mode"),
        "profile_snapshot": audit.get("profile_snapshot") or {},
        "removed_node_ids": audit.get("removed_node_ids") or [],
        "removed_edge_ids": audit.get("removed_edge_ids") or [],
        "derived_parameters": derived_parameters,
    }


def _decision_chain(audit: dict[str, Any]) -> list[dict[str, str]]:
    chain = [
        {"step": "goal_frame", "source": "audit.goal_frame"},
        {"step": "coverage_decision", "source": "audit.coverage_decision"},
        {"step": "user_confirmation", "source": "audit.user_confirmation"},
        {"step": "planner_inputs", "source": "audit.planner_inputs"},
        {"step": "closure", "source": "audit.closure_ids"},
        {"step": "topological_ordering", "source": "audit.ordering_logs"},
        {"step": "budget", "source": "audit.budget_summary"},
    ]
    if audit.get("clarification_trace_ids"):
        chain.insert(2, {"step": "clarification", "source": "audit.clarification_trace"})
    if audit.get("overlay_draft_lineage", {}).get("draft_node_count"):
        chain.insert(3, {"step": "overlay_lineage", "source": "audit.overlay_draft_lineage"})
    if audit.get("variant"):
        chain.append({"step": "variant_confirm", "source": "audit.variant"})
    if audit.get("graph_option"):
        chain.append({"step": "graph_option_confirm", "source": "audit.graph_option"})
    if audit.get("feedback"):
        chain.append({"step": "feedback_confirm", "source": "audit.feedback"})
    return chain


async def enrich_formal_path_audit(
    db: AsyncSession,
    *,
    project: Any,
    plan_result: dict[str, Any],
) -> dict[str, Any]:
    audit = plan_result.setdefault("audit", {})
    session = await _latest_resolution_session(db, project.id)
    goal_frame = _json_loads(session.goal_frame_json if session else None, None)
    if not isinstance(goal_frame, dict):
        goal_frame = None
    selected_candidate = _selected_candidate(project, session)
    coverage_decision = _coverage_decision(project, session, audit)
    clarification = await _clarification_trace(db, session.session_id if session else None, project.id)
    derived_parameters = _derived_planner_parameters(audit, goal_frame)
    overlay_drafts = _overlay_draft_lineage(audit)
    llm_status = _llm_fallback_status(goal_frame, selected_candidate, coverage_decision)

    audit["audit_schema_version"] = "formal_path_audit_v2"
    audit["goal_frame"] = goal_frame
    audit["derived_planner_parameters"] = derived_parameters
    audit["coverage_decision"] = coverage_decision
    audit["selected_candidate"] = selected_candidate
    audit["user_confirmation"] = {
        "resolution_session_id": session.session_id if session else None,
        "selected_candidate_id": getattr(project, "confirmed_candidate_id", None),
        "confirmed_target_node_ids": _json_list(getattr(project, "confirmed_target_node_ids_json", None)),
        "confirmed_at": _iso(getattr(project, "resolution_confirmed_at", None)),
        "partial_accepted": bool(getattr(project, "partial_accepted", False)),
        "missing_concepts": _json_list(getattr(project, "missing_concepts_json", None)),
    }
    audit["partial_acceptance"] = {
        "partial_accepted": bool(getattr(project, "partial_accepted", False)),
        "missing_concepts": _json_list(getattr(project, "missing_concepts_json", None)),
    }
    audit["clarification_trace_ids"] = clarification["clarification_session_ids"]
    audit["clarification_trace"] = clarification["clarification_trace"]
    audit["overlay_draft_lineage"] = overlay_drafts
    audit["llm_fallback_status"] = llm_status
    audit["planner_inputs"] = _planner_inputs(audit, derived_parameters)
    audit["authority_labels"] = _authority_labels(audit, llm_status, overlay_drafts)
    audit["decision_chain"] = _decision_chain(audit)
    return plan_result
