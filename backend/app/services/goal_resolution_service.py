from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppError
from app.models.sqlite_models import ClarificationSession, GoalResolutionSession
from app.schemas.project import validate_path_mode
from app.services.domain_pack_service import (
    DomainPackContract,
    get_domain_pack_registry,
    get_domain_pack_service,
)
from app.services.goal_service import UnsupportedGoalTypeError, identify_goal_type, resolve_goal_candidates
from app.services.llm_goal_interpreter_service import interpret_goal_with_llm
from app.services.project_goal_extension_draft_service import build_goal_extension_draft_proposal
from app.services.project_graph_snapshot_service import build_project_graph_snapshot

_AMBIGUOUS_TERMS = ("ai", "人工智能", "学ai", "学习ai", "智能")
_IN_DOMAIN_UNCOVERED_TERMS = (
    "随机森林",
    "svm",
    "支持向量机",
    "集成学习",
    "bagging",
    "boosting",
    "xgboost",
    "深度学习",
)
_OUT_OF_DOMAIN_TERMS = (
    "vue",
    "react",
    "前端",
    "会计",
    "法律",
    "医学",
    "英语",
    "考研政治",
    "量子力学",
    "相对论",
    "其他方向",
)
_ADJACENT_DOMAIN_MAPPINGS = {
    "python": ["ml_a01"],
    "numpy": ["ml_a01"],
    "编程": ["ml_a01"],
    "线性代数": ["ml_a02"],
    "矩阵": ["ml_a02"],
    "向量": ["ml_a02"],
    "微积分": ["ml_a04"],
    "导数": ["ml_a04"],
    "概率": ["ml_a06"],
    "统计": ["ml_a09", "ml_a10"],
    "大模型应用": ["ml_a01"],
}
_MAX_WEEKLY_HOURS = 40.0
_MAX_DEADLINE_WEEKS = 52
_MIN_IN_DOMAIN_CONFIDENCE = 0.65
_ALLOWED_IN_DOMAIN_ML_RELEVANCE = {"core", "prerequisite"}
_CHINESE_NUMBER_VALUES = {
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


def _build_goal_text_hash(goal_text: str) -> str:
    return hashlib.sha256(goal_text.strip().encode("utf-8")).hexdigest()


def resolve_compatible_domain(
    domain: str | None,
    *,
    expected_domain: str | None = None,
) -> str:
    registry = get_domain_pack_registry()
    try:
        canonical_domain = registry.resolve_domain(expected_domain)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_DOMAIN") from exc

    if domain is None:
        return canonical_domain

    try:
        requested_domain = registry.resolve_domain(domain)
    except ValueError as exc:
        raise AppError(code=422, message="INVALID_DOMAIN") from exc

    if requested_domain != canonical_domain:
        raise AppError(code=422, message="INVALID_DOMAIN")
    return canonical_domain



def _resolve_pack(domain: str | None, *, expected_domain: str | None = None):
    return get_domain_pack_service(resolve_compatible_domain(domain, expected_domain=expected_domain))



def _validate_requested_goal_type(
    requested_goal_type: Optional[str],
    contract: DomainPackContract,
) -> None:
    if requested_goal_type is None:
        return
    if requested_goal_type not in set(contract.supported_goal_types):
        raise AppError(code=422, message="INVALID_GOAL_TYPE")


async def build_project_graph_hash(db: AsyncSession, project_id: str, pack_hash: str) -> str:
    snapshot = await build_project_graph_snapshot(db, project_id)
    if snapshot.pack_hash != pack_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_RESOLUTION_SESSION,
            details={"reason_code": error_codes.PACK_HASH_DRIFT},
        )
    return snapshot.project_graph_hash


def _ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _node_name(node_id: str, nodes_by_id: dict[str, dict[str, object]]) -> str:
    node = nodes_by_id.get(node_id)
    name = node.get("name") if isinstance(node, dict) else None
    return str(name) if isinstance(name, str) and name.strip() else node_id


def _dedupe_strings(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _node_search_values(node: dict[str, Any]) -> list[str]:
    values = [node.get("name"), *list(node.get("aliases") or []), *list(node.get("keywords") or [])]
    return [value for value in values if isinstance(value, str) and value.strip()]


def _extract_node_mentions(goal_text: str, nodes_by_id: dict[str, dict[str, Any]]) -> tuple[list[str], list[str]]:
    text = goal_text.lower()
    node_ids: list[str] = []
    concepts: list[str] = []
    for node_id, node in nodes_by_id.items():
        if any(value.lower() in text for value in _node_search_values(node)):
            node_ids.append(node_id)
            name = node.get("name")
            if isinstance(name, str):
                concepts.append(name)
    return node_ids[:5], _dedupe_strings(concepts)


def _parse_chinese_number(value: str) -> int | None:
    if value in _CHINESE_NUMBER_VALUES:
        return _CHINESE_NUMBER_VALUES[value]
    if value.startswith("十") and len(value) == 2:
        tail = _CHINESE_NUMBER_VALUES.get(value[1])
        return 10 + tail if tail is not None else None
    if value.endswith("十") and len(value) == 2:
        head = _CHINESE_NUMBER_VALUES.get(value[0])
        return head * 10 if head is not None else None
    if "十" in value and len(value) == 3:
        head = _CHINESE_NUMBER_VALUES.get(value[0])
        tail = _CHINESE_NUMBER_VALUES.get(value[2])
        return head * 10 + tail if head is not None and tail is not None else None
    return None


def _normalize_goalframe_parameters(goal_text: str) -> tuple[dict[str, Any], list[str]]:
    text = goal_text.lower()
    params: dict[str, Any] = {"path_mode": "standard"}
    focus: list[str] = []
    if any(term in text for term in ("速成", "快速", "压缩", "赶时间", "短时间")):
        params["path_mode"] = "compressed"
        focus.append("time_budget")
    elif any(term in text for term in ("多练", "实践", "实战", "项目", "练习")):
        params.update({"path_mode": "practice_first", "practice_weight": 0.65, "theory_weight": 0.35})
        focus.extend(["practice", "prerequisites"])
    elif any(term in text for term in ("原理", "理论", "推导", "证明", "为什么")):
        params.update({"path_mode": "theory_first", "theory_weight": 0.65, "practice_weight": 0.35})
        focus.extend(["theory", "concepts"])

    week_match = re.search(r"(\d{1,2}|[一二两三四五六七八九十]{1,3})\s*(?:周|星期)", text)
    if week_match:
        raw_weeks = week_match.group(1)
        parsed_weeks = int(raw_weeks) if raw_weeks.isdigit() else _parse_chinese_number(raw_weeks)
        if parsed_weeks is not None:
            params["deadline_weeks"] = min(max(parsed_weeks, 1), _MAX_DEADLINE_WEEKS)
            focus.append("time_budget")
    hour_match = re.search(r"每周\s*(\d{1,2}(?:\.\d+)?)\s*(?:小时|h)", text)
    if hour_match:
        weekly_hours = float(hour_match.group(1))
        params["weekly_hours"] = min(max(weekly_hours, 0.5), _MAX_WEEKLY_HOURS)
        focus.append("time_budget")

    if "theory_weight" in params or "practice_weight" in params:
        theory = float(params.get("theory_weight", 0.5))
        practice = float(params.get("practice_weight", 0.5))
        total = theory + practice
        params["theory_weight"] = round(theory / total, 3)
        params["practice_weight"] = round(practice / total, 3)
    params["path_mode"] = validate_path_mode(str(params.get("path_mode") or "standard"))
    if focus:
        params["explanation_focus"] = _dedupe_strings(focus)
    return params, []


def _build_goal_frame(
    *,
    goal_text: str,
    domain: str,
    result: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    goal_understanding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_node_ids, target_concepts = _extract_node_mentions(goal_text, nodes_by_id)
    planner_parameters, uncertainties = _normalize_goalframe_parameters(goal_text)
    if not target_node_ids:
        target_node_ids = [
            node_id
            for candidate in list(result.get("candidates") or [])[:2]
            for node_id in candidate.get("target_node_ids", [])
            if isinstance(node_id, str)
        ][:5]
        target_concepts = [_node_name(node_id, nodes_by_id) for node_id in target_node_ids]
    confidence = 0.75 if result.get("candidates") else 0.35
    if goal_understanding and not target_concepts:
        target_concepts = list(goal_understanding.get("target_concepts") or [])
    source = {"source": "rules", "evidence": "rules_first_goal_frame", "confidence": confidence}
    sources = [source]
    if goal_understanding:
        source_name = "fallback" if goal_understanding.get("model") is None and goal_understanding.get("warnings") else "llm"
        sources.append({
            "source": source_name,
            "evidence": f"domain_decision:{goal_understanding.get('domain_decision')}",
            "confidence": goal_understanding.get("confidence"),
        })
    return {
        "schema_version": "v1",
        "raw_text": goal_text,
        "domain": domain,
        "goal_type": result.get("effective_goal_type") or (goal_understanding or {}).get("goal_type"),
        "target_concepts": _dedupe_strings(target_concepts),
        "target_node_ids": _dedupe_strings(target_node_ids),
        "constraints": {
            key: planner_parameters[key]
            for key in ("deadline_weeks", "weekly_hours")
            if key in planner_parameters
        },
        "preferences": {
            key: planner_parameters[key]
            for key in ("path_mode", "theory_weight", "practice_weight")
            if key in planner_parameters
        },
        "planner_parameters": planner_parameters,
        "uncertainties": _dedupe_strings([*uncertainties, *list((goal_understanding or {}).get("uncertainties") or [])]),
        "confidence": max(confidence, float((goal_understanding or {}).get("confidence") or 0.0)),
        "sources": sources,
    }


def _in_domain_uncovered_terms(goal_text: str) -> list[str]:
    text = goal_text.lower()
    return _dedupe_strings([term for term in _IN_DOMAIN_UNCOVERED_TERMS if term in text])


def _candidate_targets_match_term(
    term: str,
    candidates: list[dict[str, object]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> bool:
    normalized_term = term.lower().strip()
    for candidate in candidates:
        for node_id in candidate.get("target_node_ids", []):
            if not isinstance(node_id, str):
                continue
            node = nodes_by_id.get(node_id)
            if not isinstance(node, dict):
                continue
            if any(normalized_term in value.lower() for value in _node_search_values(node)):
                return True
    return False


def _coverage_status(
    goal_text: str,
    candidates: list[dict[str, object]],
    nodes_by_id: dict[str, dict[str, Any]],
    result: dict[str, Any],
) -> str:
    text = goal_text.lower().strip()
    if any(term == text or term in text for term in _AMBIGUOUS_TERMS) and not candidates:
        return "ambiguous"
    if any(term in text for term in _OUT_OF_DOMAIN_TERMS):
        return "out_of_domain"
    uncovered_terms = _in_domain_uncovered_terms(goal_text)
    if candidates:
        unresolved_terms = [
            term for term in uncovered_terms
            if not _candidate_targets_match_term(term, candidates, nodes_by_id)
        ]
        return "partial" if unresolved_terms else "covered"
    if uncovered_terms:
        return "in_domain_uncovered"
    if _adjacent_node_ids(goal_text, nodes_by_id):
        return "adjacent_domain"
    if result.get("reason_code") or result.get("reason_text"):
        return "out_of_domain"
    return "ambiguous"


def _adjacent_node_ids(goal_text: str, nodes_by_id: dict[str, dict[str, Any]]) -> list[str]:
    text = goal_text.lower()
    node_ids: list[str] = []
    for term, mapped_ids in _ADJACENT_DOMAIN_MAPPINGS.items():
        if term in text:
            node_ids.extend(node_id for node_id in mapped_ids if node_id in nodes_by_id)
    return _dedupe_strings(node_ids)


def _missing_concepts(goal_text: str) -> list[str]:
    return _in_domain_uncovered_terms(goal_text) or ["当前机器学习知识包暂未覆盖的目标概念"]


def _goal_coverage_actions(coverage_status: str, *, has_project: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if coverage_status == "partial":
        actions.append({
            "action": "use_existing_graph",
            "label": "按已有图谱生成路径",
            "description": "只使用当前已覆盖的机器学习基础内容，缺失概念会写入审计记录。",
            "risk_level": "low",
            "requires_review": False,
            "enabled": True,
        })
    if coverage_status in {"partial", "in_domain_uncovered"}:
        actions.append({
            "action": "create_extension_draft",
            "label": "生成扩展草稿并审核",
            "description": "由 LLM/规则辅助补充缺失概念草稿，用户审核后才可用于增强路径。",
            "risk_level": "medium",
            "requires_review": True,
            "enabled": True,
            "disabled_reason": None,
        })
    actions.append({
        "action": "rewrite_goal",
        "label": "改写学习目标",
        "description": "把目标收敛到当前机器学习基础图谱已覆盖的概念后重新解析。",
        "risk_level": "low",
        "requires_review": False,
        "enabled": True,
    })
    return actions


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return _ensure_utc(value).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=_json_default)


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _audit_trace(
    trace_type: str,
    trace_id: str,
    pack_hash: str | None,
    project_graph_hash: str | None,
) -> dict[str, Any]:
    return {
        "trace_type": trace_type,
        "trace_id": trace_id,
        "pack_hash": pack_hash,
        "project_graph_hash": project_graph_hash,
    }


def _default_goal_understanding(
    *,
    goal_text: str,
    domain: str,
    requested_goal_type: str | None,
) -> dict[str, Any]:
    goal_type = requested_goal_type or identify_goal_type(goal_text)
    return {
        "schema_version": "v1",
        "raw_text": goal_text,
        "domain_decision": "in_domain",
        "primary_domain": domain,
        "ml_relevance": "core",
        "goal_type": goal_type,
        "target_concepts": [],
        "constraints": {},
        "preferences": {},
        "uncertainties": [],
        "clarification_question": None,
        "confidence": 0.5,
        "evidence": [],
        "prompt_version": None,
        "model": None,
        "warnings": [],
    }


def _controlled_questions(
    *,
    coverage_status: str = "ambiguous",
    goal_understanding: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if coverage_status == "cross_domain":
        prompt = goal_understanding.get("clarification_question") if goal_understanding else None
        if not isinstance(prompt, str) or not prompt.strip():
            prompt = "当前系统只覆盖机器学习基础，不覆盖外部应用领域专业知识。是否按机器学习基础部分创建学习路径？"
        return [
            {
                "question_id": "confirm_ml_scope",
                "field": "domain_scope",
                "prompt": prompt,
                "options": [
                    {
                        "option_id": "accept_ml_scope",
                        "label": "是，仅学习机器学习基础部分",
                        "value": {
                            "coverage_status": "covered",
                            "goal_text_suffix": "机器学习基础",
                            "replace_goal_text": True,
                        },
                    },
                    {
                        "option_id": "reject_scope",
                        "label": "否，我想学习其他领域专业知识",
                        "value": {
                            "coverage_status": "out_of_domain",
                            "goal_text_suffix": "其他方向",
                        },
                    },
                ],
                "allow_free_text": True,
            }
        ]
    return [
        {
            "question_id": "goal_direction",
            "field": "coverage_status",
            "prompt": "你更想学习机器学习基础、深度学习、大模型应用，还是其他方向？",
            "options": [
                {
                    "option_id": "machine_learning_foundation",
                    "label": "机器学习基础",
                    "value": {
                        "coverage_status": "covered",
                        "goal_text_suffix": "机器学习基础",
                    },
                },
                {
                    "option_id": "deep_learning_intro",
                    "label": "深度学习入门",
                    "value": {
                        "coverage_status": "in_domain_uncovered",
                        "goal_text_suffix": "深度学习入门",
                    },
                },
                {
                    "option_id": "llm_application",
                    "label": "大模型应用",
                    "value": {
                        "coverage_status": "adjacent_domain",
                        "goal_text_suffix": "大模型应用",
                    },
                },
                {
                    "option_id": "other",
                    "label": "其他方向",
                    "value": {
                        "coverage_status": "out_of_domain",
                        "goal_text_suffix": "其他方向",
                    },
                },
            ],
            "allow_free_text": True,
        }
    ]


def _build_admission_rewrite_suggestions(goal_understanding: dict[str, Any]) -> list[str]:
    suggestions = ["如果想学习机器学习，请改写为“系统学习机器学习基础”。"]
    primary_domain = goal_understanding.get("primary_domain")
    if isinstance(primary_domain, str) and primary_domain and primary_domain != "unknown":
        suggestions.append(f"如果想学习 {primary_domain} 中的机器学习应用，请明确说明机器学习方法或建模目标。")
    return suggestions


def _coerce_goal_understanding_confidence(goal_understanding: dict[str, Any]) -> float:
    try:
        return float(goal_understanding.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _requires_admission_clarification(goal_understanding: dict[str, Any]) -> bool:
    if goal_understanding.get("domain_decision") != "in_domain":
        return False
    if goal_understanding.get("ml_relevance") not in _ALLOWED_IN_DOMAIN_ML_RELEVANCE:
        return True
    if _coerce_goal_understanding_confidence(goal_understanding) < _MIN_IN_DOMAIN_CONFIDENCE:
        return True
    if goal_understanding.get("warnings"):
        return True
    return False


def _build_clarification_response(
    *,
    clarification: ClarificationSession,
    questions: list[dict[str, Any]],
    coverage_status: str,
    goal_frame: dict[str, Any],
    goal_understanding: dict[str, Any],
    session_pack_hash: str,
    graph_hash: str | None,
) -> dict[str, Any]:
    return {
        "result_type": "answer_clarification",
        "coverage_status": coverage_status,
        "goal_frame": goal_frame,
        "goal_understanding": goal_understanding,
        "pack_hash": session_pack_hash,
        "project_graph_hash": graph_hash,
        "audit_trace": _audit_trace(
            "clarification",
            clarification.clarification_session_id,
            session_pack_hash,
            graph_hash,
        ),
        "clarification_session_id": clarification.clarification_session_id,
        "expires_at": _ensure_utc(clarification.expires_at),
        "turn_count": clarification.turn_count,
        "max_turns": clarification.max_turns,
        "questions": questions,
    }


def _enrich_candidate_nodes(
    candidates: list[dict[str, object]],
    nodes_by_id: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    enriched: list[dict[str, object]] = []
    for candidate in candidates:
        target_node_ids = [str(node_id) for node_id in candidate.get("target_node_ids", [])]
        target_nodes = [
            {"node_id": node_id, "node_name": _node_name(node_id, nodes_by_id)}
            for node_id in target_node_ids
        ]
        enriched.append({
            **candidate,
            "target_node_names": [node["node_name"] for node in target_nodes],
            "target_nodes": target_nodes,
        })
    return enriched


def _question_by_id(questions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(question.get("question_id")): question
        for question in questions
        if isinstance(question, dict) and question.get("question_id")
    }


def _option_by_id(question: dict[str, Any]) -> dict[str, dict[str, Any]]:
    options = question.get("options") if isinstance(question, dict) else []
    return {
        str(option.get("option_id")): option
        for option in list(options or [])
        if isinstance(option, dict) and option.get("option_id")
    }


def _append_decision_history(session: ClarificationSession, event: dict[str, Any]) -> None:
    history = _json_loads(session.decision_history_json, [])
    if not isinstance(history, list):
        history = []
    history.append(event)
    session.decision_history_json = _json_dumps(history)


def _extract_clarified_goal_text(
    *,
    raw_text: str,
    questions: list[dict[str, Any]],
    answers: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    question_map = _question_by_id(questions)
    normalized_answers: list[dict[str, Any]] = []
    goal_parts: list[str] = []
    replace_goal_text = False
    for answer in answers:
        question_id = str(answer.get("question_id") or "").strip()
        question = question_map.get(question_id)
        if question is None:
            raise AppError(code=422, message="INVALID_CLARIFICATION_ANSWER")
        selected_option_id = answer.get("selected_option_id")
        free_text = str(answer.get("free_text") or "").strip()
        normalized: dict[str, Any] = {"question_id": question_id}
        if selected_option_id:
            option = _option_by_id(question).get(str(selected_option_id))
            if option is None:
                raise AppError(code=422, message="INVALID_CLARIFICATION_ANSWER")
            value = option.get("value") if isinstance(option.get("value"), dict) else {}
            suffix = value.get("goal_text_suffix") or option.get("label")
            if isinstance(suffix, str) and suffix.strip():
                goal_parts.append(suffix.strip())
            replace_goal_text = replace_goal_text or bool(value.get("replace_goal_text"))
            normalized.update({
                "selected_option_id": str(selected_option_id),
                "value": value,
            })
        if free_text:
            if not question.get("allow_free_text"):
                raise AppError(code=422, message="INVALID_CLARIFICATION_ANSWER")
            goal_parts.append(free_text)
            normalized["free_text"] = free_text
        if "selected_option_id" not in normalized and "free_text" not in normalized:
            raise AppError(code=422, message="INVALID_CLARIFICATION_ANSWER")
        normalized_answers.append(normalized)
    clarified_text = " ".join(_dedupe_strings(goal_parts if replace_goal_text else [raw_text, *goal_parts]))
    return clarified_text, normalized_answers


async def _validate_clarification_session(
    db: AsyncSession,
    session: ClarificationSession,
    *,
    project_id: str | None,
) -> None:
    if session.status != "active" or session.expires_at < _naive_utc_now():
        raise AppError(code=409, message=error_codes.STALE_CLARIFICATION_SESSION)
    if session.turn_count >= session.max_turns:
        raise AppError(code=409, message=error_codes.STALE_CLARIFICATION_SESSION)
    if project_id is not None and session.project_id != project_id:
        raise AppError(code=409, message=error_codes.STALE_CLARIFICATION_SESSION)
    if project_id is None and session.project_id is not None:
        raise AppError(code=409, message=error_codes.STALE_CLARIFICATION_SESSION)
    resolved_domain = resolve_compatible_domain(session.domain)
    pack = get_domain_pack_service(resolved_domain)
    if session.pack_hash != pack.contract.pack_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_CLARIFICATION_SESSION,
            details={"reason_code": error_codes.PACK_HASH_DRIFT},
        )
    if project_id is None:
        return
    snapshot = await build_project_graph_snapshot(db, project_id, domain=resolved_domain, baseline_pack=pack)
    if session.project_graph_hash != snapshot.project_graph_hash:
        raise AppError(
            code=409,
            message=error_codes.STALE_CLARIFICATION_SESSION,
            details={"reason_code": error_codes.PROJECT_GRAPH_DRIFT},
        )


async def answer_clarification_session(
    db: AsyncSession,
    *,
    clarification_session_id: str,
    answers: list[dict[str, Any]],
    project_id: str | None = None,
) -> dict[str, Any]:
    session = await db.get(ClarificationSession, clarification_session_id)
    if session is None:
        raise AppError(code=409, message=error_codes.STALE_CLARIFICATION_SESSION)
    await _validate_clarification_session(db, session, project_id=project_id)
    questions = _json_loads(session.controlled_questions_json, [])
    if not isinstance(questions, list):
        questions = []
    clarified_goal_text, normalized_answers = _extract_clarified_goal_text(
        raw_text=session.raw_text,
        questions=questions,
        answers=answers,
    )
    next_turn_count = session.turn_count + 1
    preview = await create_goal_resolution_preview(
        db,
        goal_text=clarified_goal_text,
        requested_goal_type=None,
        domain=session.domain,
        expected_domain=session.domain,
        project_id=project_id,
    )
    session.turn_count = next_turn_count
    session.controlled_answers_json = _json_dumps(normalized_answers)
    _append_decision_history(session, {
        "event": "clarification_answered",
        "turn_count": session.turn_count,
        "answers": normalized_answers,
    })
    if preview.get("result_type") in {"select_candidate", "confirm_partial"}:
        session.goal_resolution_session_id = str(preview.get("session_id") or "") or None
    session.status = "resolved"
    session.completed_at = _naive_utc_now()
    session.coverage_response_json = _json_dumps(preview)
    _append_decision_history(session, {
        "event": "clarification_resolved",
        "coverage_status": preview.get("coverage_status"),
        "result_type": preview.get("result_type"),
    })
    await db.commit()
    await db.refresh(session)
    return {
        "clarification_session_id": session.clarification_session_id,
        "status": session.status,
        "expires_at": _ensure_utc(session.expires_at),
        "turn_count": session.turn_count,
        "max_turns": session.max_turns,
        "questions": questions,
        "goal_frame": _json_loads(session.goal_frame_json, None),
        "coverage_response": preview,
    }


async def create_goal_resolution_preview(
    db: AsyncSession,
    *,
    goal_text: str,
    requested_goal_type: Optional[str],
    domain: str | None,
    expected_domain: str | None = None,
    project_id: str | None = None,
) -> dict[str, object]:
    pack = _resolve_pack(domain, expected_domain=expected_domain)
    pack_domain = getattr(pack, "domain", resolve_compatible_domain(domain, expected_domain=expected_domain))
    if project_id is not None:
        pack = await build_project_graph_snapshot(db, project_id, domain=pack_domain, baseline_pack=pack)
        pack_domain = getattr(pack, "domain", pack_domain)
    assert pack.contract is not None
    _validate_requested_goal_type(requested_goal_type, pack.contract)

    supported_goal_types = set(pack.contract.supported_goal_types)
    graph_hash = getattr(pack, "project_graph_hash", None) if project_id is not None else None
    session_pack_hash = (
        getattr(pack, "pack_hash", None)
        if project_id is not None
        else getattr(pack.contract, "pack_hash", getattr(pack, "pack_hash", "unknown-pack-hash"))
    )
    goal_understanding = await interpret_goal_with_llm(
        goal_text=goal_text,
        requested_goal_type=requested_goal_type,
        domain=pack_domain,
        supported_goal_types=supported_goal_types,
    )
    admission_goal_type = goal_understanding.get("goal_type") or requested_goal_type or identify_goal_type(goal_text)
    admission_result = {
        "auto_detected_goal_type": admission_goal_type,
        "effective_goal_type": requested_goal_type or admission_goal_type,
        "goal_type_source": "user" if requested_goal_type else "llm",
        "recommended_candidate_id": None,
        "candidates": [],
        "warnings": list(goal_understanding.get("warnings") or []),
    }
    goal_frame = _build_goal_frame(
        goal_text=goal_text,
        domain=pack_domain,
        result=admission_result,
        nodes_by_id=pack.nodes_by_id,
        goal_understanding=goal_understanding,
    )

    domain_decision = goal_understanding.get("domain_decision")
    if domain_decision == "out_of_domain":
        return {
            "result_type": "boundary_reject",
            "coverage_status": "out_of_domain",
            "goal_frame": goal_frame,
            "goal_understanding": goal_understanding,
            "pack_hash": session_pack_hash,
            "project_graph_hash": graph_hash,
            "reason_code": "OUT_OF_SUPPORTED_DOMAIN",
            "reason_text": "当前原型仅支持机器学习基础领域，不能为该目标生成正式路径。",
            "rewrite_suggestions": _build_admission_rewrite_suggestions(goal_understanding),
        }

    if domain_decision in {"cross_domain", "ambiguous"} or _requires_admission_clarification(goal_understanding):
        coverage_status = "cross_domain" if domain_decision == "cross_domain" else "ambiguous"
        questions = _controlled_questions(coverage_status=coverage_status, goal_understanding=goal_understanding)
        clarification = ClarificationSession(
            project_id=project_id,
            raw_text=goal_text,
            goal_text_hash=_build_goal_text_hash(goal_text),
            domain=pack_domain,
            pack_hash=session_pack_hash,
            project_graph_hash=graph_hash,
            status="active",
            controlled_questions_json=_json_dumps(questions),
            goal_frame_json=_json_dumps(goal_frame),
            decision_history_json=_json_dumps([{
                "event": "clarification_created",
                "coverage_status": coverage_status,
                "goal_understanding": goal_understanding,
            }]),
        )
        db.add(clarification)
        await db.commit()
        await db.refresh(clarification)
        return _build_clarification_response(
            clarification=clarification,
            questions=questions,
            coverage_status=coverage_status,
            goal_frame=goal_frame,
            goal_understanding=goal_understanding,
            session_pack_hash=session_pack_hash,
            graph_hash=graph_hash,
        )

    try:
        result = resolve_goal_candidates(
            goal_text=goal_text,
            goal_type_override=requested_goal_type,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
        )
    except UnsupportedGoalTypeError as exc:
        raise AppError(code=422, message="INVALID_GOAL_TYPE") from exc

    candidates = _enrich_candidate_nodes(list(result.get("candidates") or [])[:5], pack.nodes_by_id)
    goal_frame = _build_goal_frame(
        goal_text=goal_text,
        domain=pack_domain,
        result=result,
        nodes_by_id=pack.nodes_by_id,
        goal_understanding=goal_understanding,
    )
    coverage_status = _coverage_status(goal_text, candidates, pack.nodes_by_id, result)

    if coverage_status == "out_of_domain":
        return {
            "result_type": "boundary_reject",
            "coverage_status": "out_of_domain",
            "goal_frame": goal_frame,
            "goal_understanding": goal_understanding,
            "pack_hash": session_pack_hash,
            "project_graph_hash": graph_hash,
            "reason_code": "OUT_OF_DOMAIN_GOAL",
            "reason_text": "当前原型仅支持机器学习基础领域，不能为该目标生成正式路径。",
            "rewrite_suggestions": ["改写为机器学习基础内的概念或问题目标"],
        }

    if coverage_status == "in_domain_uncovered":
        missing_concepts = _missing_concepts(goal_text)
        response: dict[str, Any] = {
            "result_type": "review_extension_draft",
            "coverage_status": "in_domain_uncovered",
            "goal_frame": goal_frame,
            "goal_understanding": goal_understanding,
            "pack_hash": session_pack_hash,
            "project_graph_hash": graph_hash,
            "missing_concepts": missing_concepts,
            "draft_entry": {
                "action": "create_project_overlay_draft",
                "requires_explicit_request": True,
                "presentation": "draft_inbox",
            },
            "available_actions": _goal_coverage_actions("in_domain_uncovered", has_project=project_id is not None),
        }
        session = GoalResolutionSession(
            project_id=project_id,
            goal_text_hash=_build_goal_text_hash(goal_text),
            domain=pack_domain,
            requested_goal_type=requested_goal_type,
            auto_detected_goal_type=result["auto_detected_goal_type"],
            effective_goal_type=result["effective_goal_type"],
            pack_version=str(pack.manifest.get("version", "unknown")),
            pack_hash=session_pack_hash,
            graph_hash=graph_hash,
            project_graph_hash=graph_hash,
            goal_frame_json=_json_dumps(goal_frame),
            coverage_response_json=_json_dumps(response),
            candidates_json=_json_dumps([]),
            recommended_candidate_id=None,
            status="draft_previewed",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        audit_trace = _audit_trace("goal_resolution", session.session_id, session_pack_hash, graph_hash)
        response.update({
            "audit_trace": audit_trace,
            "session_id": session.session_id,
            "expires_at": _ensure_utc(session.expires_at),
        })
        response["draft_proposal"] = build_goal_extension_draft_proposal(
            goal_text=goal_text,
            missing_concepts=missing_concepts,
            coverage_response=response,
            trace=audit_trace,
            resolution_session_id=session.session_id,
        )
        session.coverage_response_json = _json_dumps(response)
        await db.commit()
        return response

    if coverage_status == "ambiguous" and not candidates:
        clarification = ClarificationSession(
            project_id=project_id,
            raw_text=goal_text,
            goal_text_hash=_build_goal_text_hash(goal_text),
            domain=pack_domain,
            pack_hash=session_pack_hash,
            project_graph_hash=graph_hash,
            status="active",
            controlled_questions_json=_json_dumps(_controlled_questions()),
            goal_frame_json=_json_dumps(goal_frame),
            decision_history_json=_json_dumps([{"event": "clarification_created", "coverage_status": "ambiguous"}]),
        )
        db.add(clarification)
        await db.commit()
        await db.refresh(clarification)
        questions = json.loads(clarification.controlled_questions_json or "[]")
        return {
            "result_type": "answer_clarification",
            "coverage_status": "ambiguous",
            "goal_frame": goal_frame,
            "goal_understanding": goal_understanding,
            "pack_hash": session_pack_hash,
            "project_graph_hash": graph_hash,
            "audit_trace": _audit_trace(
                "clarification",
                clarification.clarification_session_id,
                session_pack_hash,
                graph_hash,
            ),
            "clarification_session_id": clarification.clarification_session_id,
            "expires_at": _ensure_utc(clarification.expires_at),
            "turn_count": clarification.turn_count,
            "max_turns": clarification.max_turns,
            "questions": questions,
        }

    if coverage_status == "adjacent_domain" and not candidates:
        adjacent_ids = _adjacent_node_ids(goal_text, pack.nodes_by_id)
        if adjacent_ids:
            candidates = _enrich_candidate_nodes([
                {
                    "candidate_id": f"adjacent:{'+'.join(adjacent_ids)}",
                    "goal_type": "concept",
                    "target_node_ids": adjacent_ids,
                    "mode": "support",
                    "description": "邻近领域目标映射到机器学习图谱中的支撑节点",
                    "template_id": None,
                    "resolve_source": "coverage_router",
                    "source_breakdown": {"template": 0.0, "lexical": 1.0, "llm": 0.0},
                    "score": 0.7,
                    "score_breakdown": {"final_score": 0.7},
                    "explanation": "仅映射到当前机器学习图谱已有的前置/支撑节点",
                    "warnings": ["adjacent_domain_support_only"],
                }
            ], pack.nodes_by_id)

    if coverage_status == "partial":
        covered_ids = _dedupe_strings([
            node_id
            for candidate in candidates
            for node_id in candidate.get("target_node_ids", [])
            if isinstance(node_id, str)
        ])
        available_actions = _goal_coverage_actions("partial", has_project=project_id is not None)
        session = GoalResolutionSession(
            project_id=project_id,
            goal_text_hash=_build_goal_text_hash(goal_text),
            domain=pack_domain,
            requested_goal_type=requested_goal_type,
            auto_detected_goal_type=result["auto_detected_goal_type"],
            effective_goal_type=result["effective_goal_type"],
            pack_version=str(pack.manifest.get("version", "unknown")),
            pack_hash=session_pack_hash,
            graph_hash=graph_hash,
            project_graph_hash=graph_hash,
            goal_frame_json=_json_dumps(goal_frame),
            coverage_response_json=_json_dumps({
                "coverage_status": "partial",
                "result_type": "confirm_partial",
                "goal_understanding": goal_understanding,
                "covered_target_node_ids": covered_ids,
                "missing_concepts": _missing_concepts(goal_text),
                "available_actions": available_actions,
            }),
            candidates_json=_json_dumps(candidates),
            recommended_candidate_id=str(result.get("recommended_candidate_id") or candidates[0]["candidate_id"]),
            status="partial_previewed",
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        return {
            "result_type": "confirm_partial",
            "coverage_status": "partial",
            "goal_frame": goal_frame,
            "goal_understanding": goal_understanding,
            "pack_hash": session_pack_hash,
            "project_graph_hash": graph_hash,
            "audit_trace": _audit_trace("goal_resolution", session.session_id, session_pack_hash, graph_hash),
            "session_id": session.session_id,
            "expires_at": _ensure_utc(session.expires_at),
            "covered_target_node_ids": covered_ids,
            "missing_concepts": _missing_concepts(goal_text),
            "candidates": candidates,
            "available_actions": available_actions,
        }

    if not candidates:
        return {
            "result_type": "boundary_reject",
            "coverage_status": coverage_status if coverage_status == "adjacent_domain" else "out_of_domain",
            "goal_frame": goal_frame,
            "goal_understanding": goal_understanding,
            "pack_hash": session_pack_hash,
            "project_graph_hash": graph_hash,
            "reason_code": result.get("reason_code") or "NO_SAFE_MAPPING",
            "reason_text": result.get("reason_text") or "当前目标无法安全映射到机器学习基础图谱中的可规划节点。",
            "rewrite_suggestions": ["请提供更具体的机器学习概念或问题"],
        }

    recommended_candidate_id = str(result.get("recommended_candidate_id") or candidates[0]["candidate_id"])
    recommended_candidate = next(
        (candidate for candidate in candidates if candidate.get("candidate_id") == recommended_candidate_id),
        candidates[0],
    )
    goal_frame_target_ids = set(goal_frame.get("target_node_ids") or [])
    candidate_target_ids = set(recommended_candidate.get("target_node_ids") or [])
    target_authority = {
        "source": "confirmed_candidate",
        "goal_frame_target_node_ids": sorted(goal_frame_target_ids),
        "recommended_candidate_id": recommended_candidate_id,
        "recommended_candidate_target_node_ids": sorted(candidate_target_ids),
        "mismatch_recorded": goal_frame_target_ids != candidate_target_ids,
    }
    coverage_response = {
        "coverage_status": coverage_status,
        "result_type": "select_candidate",
        "goal_understanding": goal_understanding,
        "target_authority": target_authority,
    }
    session = GoalResolutionSession(
        project_id=project_id,
        goal_text_hash=_build_goal_text_hash(goal_text),
        domain=pack_domain,
        requested_goal_type=requested_goal_type,
        auto_detected_goal_type=result["auto_detected_goal_type"],
        effective_goal_type=result["effective_goal_type"],
        pack_version=str(pack.manifest.get("version", "unknown")),
        pack_hash=session_pack_hash,
        graph_hash=graph_hash,
        project_graph_hash=graph_hash,
        goal_frame_json=_json_dumps(goal_frame),
        coverage_response_json=_json_dumps(coverage_response),
        candidates_json=_json_dumps(candidates),
        recommended_candidate_id=recommended_candidate_id,
        status="previewed",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)

    return {
        "result_type": "select_candidate",
        "coverage_status": coverage_status,
        "goal_frame": goal_frame,
        "goal_understanding": goal_understanding,
        "pack_hash": session_pack_hash,
        "project_graph_hash": graph_hash,
        "audit_trace": _audit_trace("goal_resolution", session.session_id, session_pack_hash, graph_hash),
        "session_id": session.session_id,
        "expires_at": _ensure_utc(session.expires_at),
        "auto_detected_goal_type": result["auto_detected_goal_type"],
        "effective_goal_type": result["effective_goal_type"],
        "recommended_candidate_id": recommended_candidate_id,
        "candidates": candidates,
        "warnings": sorted(set(result.get("warnings") or [])),
    }
