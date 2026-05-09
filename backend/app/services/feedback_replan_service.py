from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppError, NotFoundError
from app.models.sqlite_models import (
    FeedbackPreviewSession,
    KnownNodeConfirmationDraft,
    TrackingEvent,
)
from app.repositories.plan_repository import (
    extract_plan_node_ids,
    get_latest_plan,
    get_plan_by_id,
    get_plan_version_count,
    save_plan,
)
from app.repositories.profile_repository import get_latest_profile
from app.repositories.project_repository import get_project
from app.services.formal_path_audit_service import enrich_formal_path_audit
from app.services.goal_service import UnsupportedGoalTypeError
from app.services.planner_service import plan_with_profile
from app.services.project_graph_snapshot_service import build_project_graph_snapshot
from app.services.replan_service import (
    _build_confirmed_goal_result,
    _profile_row_to_dict,
    _replan_progress_aware,
)


_UNSUPPORTED_KEYWORDS = {
    "goal_change_not_supported": ["换目标", "改目标", "重新定目标", "学别的", "目标改成"],
    "hard_prerequisite_skip_not_supported": ["跳过前置", "不要前置", "删除依赖", "硬前置", "跳过依赖"],
    "overlay_visibility_not_supported": ["overlay", "图谱可见", "planning_enabled", "草稿可见", "审核草稿"],
    "cross_domain_not_supported": ["vue", "react", "前端", "英语", "考研", "公务员", "会计"],
}

_INTENT_KEYWORDS = {
    "mark_known_nodes": ["已经会", "已掌握", "我会", "学过", "不用学"],
    "compress_time": ["太长", "压缩", "缩短", "更短", "时间不够", "赶时间", "少一点"],
    "increase_practice": ["多一点实践", "更多实践", "练习", "项目", "动手", "实战"],
    "increase_theory": ["多一点理论", "更多理论", "推导", "原理", "证明", "理论"],
}

_CHINESE_NUMBERS = {
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
}


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _profile_with_practice(profile_row: Any) -> dict[str, Any]:
    profile = _profile_row_to_dict(profile_row)
    profile["practice_weight"] = getattr(profile_row, "practice_weight", 1.0 - profile.get("theory_weight", 0.5))
    return profile


def _parse_number(value: str) -> int | None:
    if value.isdigit():
        return int(value)
    return _CHINESE_NUMBERS.get(value)


def _parse_deadline_weeks(text: str) -> int | None:
    match = re.search(r"(\d+|[一二两三四五六七八九十])\s*周", text)
    if not match:
        return None
    weeks = _parse_number(match.group(1))
    return weeks if weeks and weeks > 0 else None


def _parse_feedback_intent(feedback_text: str) -> tuple[str, dict[str, Any], float]:
    text = feedback_text.strip().lower()
    blocked = [reason for reason, words in _UNSUPPORTED_KEYWORDS.items() if any(word in text for word in words)]
    if blocked:
        raise AppError(
            code=422,
            message="UNSUPPORTED_FEEDBACK_INTENT",
            details={"blocked_actions": blocked},
        )

    deadline_weeks = _parse_deadline_weeks(text)
    if deadline_weeks is not None and any(word in text for word in ["周", "截止", "只剩", "deadline", "期限"]):
        return "adjust_deadline", {"deadline_weeks": deadline_weeks}, 0.86

    for intent, words in _INTENT_KEYWORDS.items():
        if any(word in text for word in words):
            return intent, {}, 0.82

    raise AppError(
        code=422,
        message="UNSUPPORTED_FEEDBACK_INTENT",
        details={"blocked_actions": ["low_confidence_or_unknown_intent"]},
    )


def _node_search_values(node_id: str, node: dict[str, Any]) -> list[str]:
    values = [node_id, str(node.get("name") or "")]
    for field_name in ("aliases", "keywords"):
        values.extend(str(item) for item in node.get(field_name, []) or [])
    return [value.strip().lower() for value in values if value and value.strip()]


def _match_known_nodes(feedback_text: str, plan_node_ids: list[str], nodes_by_id: dict[str, dict[str, Any]]) -> tuple[list[str], list[dict[str, Any]]]:
    text = feedback_text.lower()
    matched: list[str] = []
    evidence: list[dict[str, Any]] = []
    for node_id in plan_node_ids:
        node = nodes_by_id.get(node_id)
        if not node:
            continue
        matched_value = next((value for value in _node_search_values(node_id, node) if value and value in text), None)
        if matched_value is None:
            continue
        matched.append(node_id)
        evidence.append({"node_id": node_id, "node_name": node.get("name") or node_id, "matched_text": matched_value})
    return matched, evidence


def _diff_node_ids(old_node_ids: list[str], new_node_ids: list[str]) -> dict[str, list[str]]:
    old_set = set(old_node_ids)
    new_set = set(new_node_ids)
    return {
        "added": sorted(new_set - old_set),
        "removed": sorted(old_set - new_set),
        "unchanged": sorted(old_set & new_set),
    }


def _build_plan_node_name_map(plan_result: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(plan_result, dict):
        return {}
    stage_plan = plan_result.get("stage_plan")
    if not isinstance(stage_plan, dict):
        return {}

    node_names: dict[str, str] = {}
    for tasks in stage_plan.values():
        if not isinstance(tasks, list):
            continue
        for task in tasks:
            if not isinstance(task, dict):
                continue
            node_id = task.get("node_id")
            node_name = task.get("name")
            if isinstance(node_id, str) and node_id and node_name:
                node_names[node_id] = str(node_name)
    return node_names


def _node_name_from_snapshot(node_id: str, nodes_by_id: dict[str, Any] | None) -> str:
    if nodes_by_id:
        node = nodes_by_id.get(node_id)
        if isinstance(node, dict) and node.get("name"):
            return str(node["name"])
    return node_id


def _build_diff_details(
    diff: dict[str, Any] | None,
    *,
    plan_result: dict[str, Any] | None = None,
    nodes_by_id: dict[str, Any] | None = None,
) -> dict[str, list[dict[str, str]]]:
    if not isinstance(diff, dict) or not diff:
        return {}

    plan_node_names = _build_plan_node_name_map(plan_result)
    details: dict[str, list[dict[str, str]]] = {}
    for key, node_ids in diff.items():
        if not isinstance(key, str) or not isinstance(node_ids, list) or not node_ids:
            continue
        items: list[dict[str, str]] = []
        for node_id in node_ids:
            if not isinstance(node_id, str) or not node_id:
                continue
            items.append({
                "node_id": node_id,
                "node_name": plan_node_names.get(node_id) or _node_name_from_snapshot(node_id, nodes_by_id),
            })
        if items:
            details[key] = items
    return details


def _budget_delta(old_plan: Any, plan_result: dict[str, Any]) -> dict[str, Any]:
    previous_total = old_plan.total_hours or 0
    preview_total = plan_result["total_hours"]
    return {
        "previous_total_hours": previous_total,
        "preview_total_hours": preview_total,
        "delta_hours": round(preview_total - previous_total, 1),
        "previous_budget_status": old_plan.budget_status,
        "preview_budget_status": plan_result["budget_summary"].get("status"),
    }


def _controlled_parameters(intent_type: str, raw_parameters: dict[str, Any], current_path_mode: str | None) -> tuple[dict[str, Any], str]:
    path_mode = current_path_mode or "standard"
    parameters = dict(raw_parameters)
    if intent_type == "compress_time":
        path_mode = "compressed"
        parameters["path_mode"] = path_mode
    elif intent_type == "increase_practice":
        path_mode = "practice_first"
        parameters["path_mode"] = path_mode
        parameters["theory_weight"] = 0.35
        parameters["practice_weight"] = 0.65
    elif intent_type == "increase_theory":
        path_mode = "theory_first"
        parameters["path_mode"] = path_mode
        parameters["theory_weight"] = 0.7
        parameters["practice_weight"] = 0.3
    elif intent_type == "adjust_deadline":
        parameters["deadline_weeks"] = raw_parameters["deadline_weeks"]
    return parameters, path_mode


def _apply_controlled_parameters(profile: dict[str, Any], controlled_parameters: dict[str, Any]) -> dict[str, Any]:
    updated = dict(profile)
    if "deadline_weeks" in controlled_parameters:
        updated["deadline_weeks"] = controlled_parameters["deadline_weeks"]
    if "theory_weight" in controlled_parameters:
        updated["theory_weight"] = controlled_parameters["theory_weight"]
        updated["practice_weight"] = controlled_parameters.get("practice_weight", 1.0 - controlled_parameters["theory_weight"])
    return updated


def _blocked_actions_for_plan(plan_result: dict[str, Any]) -> list[str]:
    if plan_result["budget_summary"].get("status") == "over_budget_required_closure":
        return ["hard_prerequisites_not_removed"]
    return []


def _node_refs_from_evidence(node_ids: list[str], evidence: list[Any]) -> list[dict[str, str]]:
    evidence_names = {
        item["node_id"]: item.get("node_name")
        for item in evidence
        if isinstance(item, dict) and item.get("node_id") and item.get("node_name")
    }
    return [
        {
            "node_id": node_id,
            "node_name": str(evidence_names.get(node_id) or node_id),
        }
        for node_id in node_ids
        if isinstance(node_id, str) and node_id
    ]


def _known_node_draft_response(draft: KnownNodeConfirmationDraft) -> dict[str, Any]:
    raw_node_ids = _json_loads(draft.node_ids_json, [])
    node_ids = [node_id for node_id in raw_node_ids if isinstance(node_id, str)] if isinstance(raw_node_ids, list) else []
    evidence = _json_loads(draft.evidence_json, [])
    evidence = evidence if isinstance(evidence, list) else []
    return {
        "draft_id": draft.draft_id,
        "feedback_preview_id": draft.feedback_preview_id,
        "project_id": draft.project_id,
        "node_ids": node_ids,
        "nodes": _node_refs_from_evidence(node_ids, evidence),
        "evidence": evidence,
        "status": draft.status,
        "expires_at": draft.expires_at,
    }


def _feedback_response(session: FeedbackPreviewSession, draft: KnownNodeConfirmationDraft | None = None) -> dict[str, Any]:
    history = _json_loads(session.decision_history_json, {})
    history = history if isinstance(history, dict) else {}
    diff = _json_loads(session.diff_json, {})
    diff_details = history.get("diff_details")
    if not isinstance(diff_details, dict):
        plan_result = history.get("plan_result")
        diff_details = _build_diff_details(diff, plan_result=plan_result if isinstance(plan_result, dict) else None)

    return {
        "feedback_preview_id": session.feedback_preview_id,
        "project_id": session.project_id,
        "intent_type": session.intent_type,
        "confidence": session.confidence,
        "controlled_parameters": _json_loads(session.controlled_parameters_json, {}),
        "diff": diff,
        "diff_details": diff_details,
        "budget_delta": _json_loads(session.budget_delta_json, {}),
        "blocked_actions": _json_loads(session.blocked_actions_json, []),
        "requires_confirmation": session.requires_confirmation,
        "requires_second_confirm": session.requires_second_confirm,
        "variant_preview_id": session.variant_preview_id,
        "known_node_draft": _known_node_draft_response(draft) if draft is not None else None,
        "status": session.status,
        "expires_at": session.expires_at,
        "pack_hash": session.pack_hash,
        "project_graph_hash": session.project_graph_hash,
    }


def _plan_response(path: Any, plan_result: dict[str, Any], session: FeedbackPreviewSession, *, idempotent: bool) -> dict[str, Any]:
    history = _json_loads(session.decision_history_json, {})
    history = history if isinstance(history, dict) else {}
    diff = _json_loads(session.diff_json, {})
    diff_details = history.get("diff_details")
    if not isinstance(diff_details, dict):
        diff_details = _build_diff_details(diff, plan_result=plan_result)

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "mode": "feedback_confirm",
        "intent_type": session.intent_type,
        "feedback_preview_id": session.feedback_preview_id,
        "stages": [
            {
                "stage_index": index,
                "stage_name": stage_name,
                "tasks": tasks,
                "estimated_hours": sum(task.get("estimated_hours", 0) for task in tasks),
            }
            for index, (stage_name, tasks) in enumerate(plan_result["stage_plan"].items())
        ],
        "budget_status": plan_result["budget_summary"].get("status"),
        "path_mode": plan_result.get("path_mode"),
        "total_hours": plan_result["total_hours"],
        "diff": diff,
        "diff_details": diff_details,
        "budget_delta": _json_loads(session.budget_delta_json, {}),
        "idempotent": idempotent,
    }


async def preview_feedback_replan(db: AsyncSession, *, project_id: str, feedback_text: str) -> dict[str, Any]:
    project = await get_project(db, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    latest_plan = await get_latest_plan(db, project_id)
    if latest_plan is None:
        raise NotFoundError("暂无学习路径")
    latest_profile_row = await get_latest_profile(db, project_id)
    if latest_profile_row is None:
        raise AppError(code=400, message="请先提交画像")

    intent_type, raw_parameters, confidence = _parse_feedback_intent(feedback_text)
    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)
    old_node_ids = extract_plan_node_ids(latest_plan.plan_json)
    controlled_parameters, path_mode = _controlled_parameters(intent_type, raw_parameters, getattr(project, "path_mode", None))

    if intent_type == "mark_known_nodes":
        node_ids, evidence = _match_known_nodes(feedback_text, old_node_ids, snapshot.nodes_by_id)
        if not node_ids:
            raise AppError(
                code=422,
                message="KNOWN_NODE_CANDIDATE_REQUIRED",
                details={"blocked_actions": ["known_node_not_found_in_latest_plan"]},
            )
        session = FeedbackPreviewSession(
            project_id=project_id,
            path_id=latest_plan.id,
            intent_type=intent_type,
            controlled_parameters_json=_json_dumps({"node_ids": node_ids}),
            confidence=confidence,
            diff_json=_json_dumps({}),
            budget_delta_json=_json_dumps({}),
            blocked_actions_json=_json_dumps(["known_node_confirmation_required"]),
            requires_confirmation=True,
            requires_second_confirm=True,
            pack_hash=snapshot.pack_hash,
            project_graph_hash=snapshot.project_graph_hash,
            status="active",
            decision_history_json=_json_dumps({"event": "feedback_preview_created", "feedback_text": feedback_text}),
        )
        db.add(session)
        await db.flush()
        draft = KnownNodeConfirmationDraft(
            feedback_preview_id=session.feedback_preview_id,
            project_id=project_id,
            node_ids_json=_json_dumps(node_ids),
            evidence_json=_json_dumps(evidence),
            status="draft",
            pack_hash=snapshot.pack_hash,
            project_graph_hash=snapshot.project_graph_hash,
            decision_history_json=_json_dumps({"event": "known_node_draft_created"}),
        )
        db.add(draft)
        await db.commit()
        await db.refresh(session)
        await db.refresh(draft)
        return _feedback_response(session, draft)

    profile = _apply_controlled_parameters(_profile_with_practice(latest_profile_row), controlled_parameters)
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
        )
    except ValueError as exc:
        if str(exc) == "INVALID_PATH_MODE":
            raise AppError(code=422, message="INVALID_PATH_MODE") from exc
        raise
    except UnsupportedGoalTypeError as exc:
        raise AppError(code=409, message="GOAL_DEFAULT_TARGETS_UNAVAILABLE", details={"reason": str(exc)}) from exc
    if confirmed_goal_result and not plan_result["goal_result"]["target_node_ids"]:
        raise AppError(code=409, message="GOAL_TARGETS_REMOVED")

    plan_result.setdefault("audit", {})["feedback"] = {
        "intent_type": intent_type,
        "controlled_parameters": controlled_parameters,
    }
    diff = _diff_node_ids(old_node_ids, plan_result["ordered_ids"])
    diff_details = _build_diff_details(diff, plan_result=plan_result, nodes_by_id=snapshot.nodes_by_id)
    budget_delta = _budget_delta(latest_plan, plan_result)
    blocked_actions = _blocked_actions_for_plan(plan_result)
    session = FeedbackPreviewSession(
        project_id=project_id,
        path_id=latest_plan.id,
        intent_type=intent_type,
        controlled_parameters_json=_json_dumps(controlled_parameters),
        confidence=confidence,
        diff_json=_json_dumps(diff),
        budget_delta_json=_json_dumps(budget_delta),
        blocked_actions_json=_json_dumps(blocked_actions),
        requires_confirmation=True,
        requires_second_confirm=False,
        pack_hash=snapshot.pack_hash,
        project_graph_hash=snapshot.project_graph_hash,
        status="active",
        decision_history_json=_json_dumps({
            "event": "feedback_preview_created",
            "feedback_text": feedback_text,
            "diff_details": diff_details,
            "plan_result": plan_result,
        }),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return _feedback_response(session)


async def confirm_known_node_draft(db: AsyncSession, *, project_id: str, draft_id: str) -> dict[str, Any]:
    draft = await db.get(KnownNodeConfirmationDraft, draft_id)
    if draft is None or draft.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
    if draft.status == "confirmed":
        return _known_node_draft_response(draft)
    if draft.status != "draft" or draft.expires_at < _naive_utc_now():
        raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
    session = await db.get(FeedbackPreviewSession, draft.feedback_preview_id)
    if session is None or session.project_id != project_id or session.status != "active":
        raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
    snapshot = await build_project_graph_snapshot(db, project_id)
    if draft.pack_hash != snapshot.pack_hash or session.pack_hash != snapshot.pack_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_FEEDBACK_PREVIEW,
            details={"reason_code": error_codes.PACK_HASH_DRIFT},
        )
    if draft.project_graph_hash != snapshot.project_graph_hash or session.project_graph_hash != snapshot.project_graph_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_FEEDBACK_PREVIEW,
            details={"reason_code": error_codes.PROJECT_GRAPH_DRIFT},
        )
    draft.status = "confirmed"
    draft.decision_history_json = _json_dumps({"event": "known_node_draft_confirmed"})
    await db.commit()
    await db.refresh(draft)
    return _known_node_draft_response(draft)


async def confirm_feedback_replan(db: AsyncSession, *, project_id: str, feedback_preview_id: str) -> dict[str, Any]:
    session = await db.get(FeedbackPreviewSession, feedback_preview_id)
    if session is None or session.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
    history = _json_loads(session.decision_history_json, {})
    history = history if isinstance(history, dict) else {}
    if session.status == "confirmed":
        path_id = history.get("applied_path_id")
        path = await get_plan_by_id(db, path_id) if isinstance(path_id, str) else None
        plan_result = history.get("plan_result")
        if path is None or not isinstance(plan_result, dict):
            raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
        return _plan_response(path, plan_result, session, idempotent=True)
    if session.status != "active" or session.expires_at < _naive_utc_now():
        raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)

    project = await get_project(db, project_id)
    if project is None:
        raise NotFoundError("项目不存在")
    latest_plan = await get_latest_plan(db, project_id)
    if latest_plan is None or latest_plan.id != session.path_id:
        raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
    snapshot = await build_project_graph_snapshot(db, project_id, domain=project.domain)
    if session.pack_hash != snapshot.pack_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_FEEDBACK_PREVIEW,
            details={"reason_code": error_codes.PACK_HASH_DRIFT},
        )
    if session.project_graph_hash != snapshot.project_graph_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_FEEDBACK_PREVIEW,
            details={"reason_code": error_codes.PROJECT_GRAPH_DRIFT},
        )

    if session.intent_type == "mark_known_nodes":
        draft = await _get_confirmed_known_node_draft(db, session)
        node_ids = _json_loads(draft.node_ids_json, [])
        for node_id in node_ids:
            db.add(TrackingEvent(project_id=project_id, node_id=node_id, event_type="complete", note="feedback_mark_known"))
        await db.flush()
        latest_profile_row = await get_latest_profile(db, project_id)
        latest_profile = _profile_with_practice(latest_profile_row) if latest_profile_row else None
        confirmed_goal_result = _build_confirmed_goal_result(project)
        result = await _replan_progress_aware(
            db,
            project,
            latest_profile,
            snapshot,
            snapshot.removed_node_ids,
            snapshot.removed_edge_ids,
            confirmed_goal_result=confirmed_goal_result,
            path_mode=getattr(project, "path_mode", None) or "standard",
        )
        plan_result = result["plan_result"]
        plan_result.setdefault("audit", {})["feedback"] = {
            "intent_type": session.intent_type,
            "known_node_draft_id": draft.draft_id,
            "node_ids": node_ids,
        }
        diff = result.get("diff", {})
        diff_details = _build_diff_details(diff, plan_result=plan_result, nodes_by_id=snapshot.nodes_by_id)
        session.diff_json = _json_dumps(diff)
        session.budget_delta_json = _json_dumps(_budget_delta(latest_plan, plan_result))
    else:
        plan_result = history.get("plan_result")
        if not isinstance(plan_result, dict):
            raise AppError(code=409, message=error_codes.STALE_FEEDBACK_PREVIEW)
        diff_details = history.get("diff_details")
        if not isinstance(diff_details, dict):
            diff_details = _build_diff_details(
                _json_loads(session.diff_json, {}),
                plan_result=plan_result,
                nodes_by_id=snapshot.nodes_by_id,
            )

    await enrich_formal_path_audit(db, project=project, plan_result=plan_result)
    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, plan_result, version=version, commit=False)
    session.status = "confirmed"
    session.decision_history_json = _json_dumps({
        **history,
        "event": "feedback_confirmed",
        "applied_path_id": path.id,
        "diff_details": diff_details,
        "plan_result": plan_result,
    })
    await db.commit()
    await db.refresh(path)
    await db.refresh(session)
    return _plan_response(path, plan_result, session, idempotent=False)


async def _get_confirmed_known_node_draft(db: AsyncSession, session: FeedbackPreviewSession) -> KnownNodeConfirmationDraft:
    from sqlalchemy import select

    result = await db.execute(
        select(KnownNodeConfirmationDraft)
        .where(KnownNodeConfirmationDraft.feedback_preview_id == session.feedback_preview_id)
        .limit(1)
    )
    draft = result.scalar_one_or_none()
    if draft is None or draft.status != "confirmed":
        raise AppError(
            code=409,
            message=error_codes.STALE_FEEDBACK_PREVIEW,
            details={"reason_code": "KNOWN_NODE_DRAFT_CONFIRMATION_REQUIRED"},
        )
    return draft
