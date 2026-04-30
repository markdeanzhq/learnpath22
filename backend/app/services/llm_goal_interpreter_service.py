from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_llm_config
from app.services.goal_service import identify_goal_type

logger = logging.getLogger(__name__)

PROMPT_VERSION = "goal-understanding-v1"
DOMAIN_DECISIONS = {"in_domain", "cross_domain", "out_of_domain", "ambiguous"}
ML_RELEVANCE_VALUES = {"core", "prerequisite", "application", "none", "unclear"}
GOAL_TYPES = {"domain", "concept", "problem"}
MAX_CONCEPTS = 8
MAX_EVIDENCE = 6
TIMEOUT_SECONDS = 12.0


def _strip_code_fence(value: str | None) -> str:
    if not value:
        return ""
    text = value.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _dedupe_strings(values: Any, *, limit: int = MAX_CONCEPTS) -> list[str]:
    if not isinstance(values, list):
        return []
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not isinstance(value, str):
            continue
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        if re.fullmatch(r"ml_[a-z]\d+", normalized.lower()):
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= limit:
            break
    return result


def _coerce_goal_type(value: Any, fallback: str, supported_goal_types: set[str]) -> str | None:
    if isinstance(value, str) and value in GOAL_TYPES and value in supported_goal_types:
        return value
    if fallback in supported_goal_types:
        return fallback
    return next(iter(sorted(supported_goal_types)), None)


def _coerce_confidence(value: Any, default: float = 0.5) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, 0.0), 1.0)


def _coerce_evidence(values: Any) -> list[dict[str, str]]:
    if not isinstance(values, list):
        return []
    evidence: list[dict[str, str]] = []
    for item in values:
        if not isinstance(item, dict):
            continue
        span = str(item.get("span") or "").strip()
        label = str(item.get("label") or "evidence").strip()
        reason = str(item.get("reason") or "").strip()
        if not span or not reason:
            continue
        evidence.append({"span": span[:80], "label": label[:60], "reason": reason[:160]})
        if len(evidence) >= MAX_EVIDENCE:
            break
    return evidence


def _unavailable_understanding(
    *,
    goal_text: str,
    requested_goal_type: str | None,
    warning: str,
) -> dict[str, Any]:
    goal_type = requested_goal_type if requested_goal_type in GOAL_TYPES else None
    return {
        "schema_version": "v1",
        "raw_text": goal_text,
        "domain_decision": "ambiguous",
        "primary_domain": "unknown",
        "ml_relevance": "unclear",
        "goal_type": goal_type,
        "target_concepts": [],
        "constraints": {},
        "preferences": {},
        "uncertainties": [warning],
        "clarification_question": "目标理解服务暂不可用，请稍后重试或先确认学习目标是否属于机器学习基础。",
        "confidence": 0.0,
        "evidence": [],
        "prompt_version": PROMPT_VERSION,
        "model": None,
        "warnings": [warning],
    }


def _normalize_understanding(
    *,
    raw: dict[str, Any],
    goal_text: str,
    requested_goal_type: str | None,
    domain: str,
    supported_goal_types: set[str],
    model: str | None,
) -> dict[str, Any]:
    fallback_goal_type = requested_goal_type or identify_goal_type(goal_text)
    domain_decision = raw.get("domain_decision")
    if domain_decision not in DOMAIN_DECISIONS:
        domain_decision = "ambiguous"
    ml_relevance = raw.get("ml_relevance")
    if ml_relevance not in ML_RELEVANCE_VALUES:
        ml_relevance = "unclear"
    goal_type = _coerce_goal_type(raw.get("goal_type"), fallback_goal_type, supported_goal_types)
    primary_domain = str(raw.get("primary_domain") or (domain if domain_decision == "in_domain" else "unknown")).strip()
    if not primary_domain:
        primary_domain = "unknown"
    clarification_question = raw.get("clarification_question")
    if not isinstance(clarification_question, str) or not clarification_question.strip():
        clarification_question = None
    return {
        "schema_version": "v1",
        "raw_text": goal_text,
        "domain_decision": domain_decision,
        "primary_domain": primary_domain[:80],
        "ml_relevance": ml_relevance,
        "goal_type": goal_type,
        "target_concepts": _dedupe_strings(raw.get("target_concepts")),
        "constraints": raw.get("constraints") if isinstance(raw.get("constraints"), dict) else {},
        "preferences": raw.get("preferences") if isinstance(raw.get("preferences"), dict) else {},
        "uncertainties": _dedupe_strings(raw.get("uncertainties"), limit=6),
        "clarification_question": clarification_question[:160] if clarification_question else None,
        "confidence": _coerce_confidence(raw.get("confidence"), default=0.6),
        "evidence": _coerce_evidence(raw.get("evidence")),
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "warnings": [],
    }


def _build_messages(goal_text: str, requested_goal_type: str | None, domain: str) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "你是 LearnPath-KG 的目标解析器，不是学习顾问或聊天助手。当前系统只支持机器学习基础学习路径规划。"
                "你的任务只是在机器学习基础图谱边界内做结构化判定，不要生成学习路径，不要回答泛泛建议，不要编造知识图谱节点 ID。"
                "若目标明确属于机器学习基础概念、基础算法、基础问题，domain_decision=in_domain。"
                "若目标是医学、金融、前端等外部领域中的机器学习应用，domain_decision=cross_domain 且 ml_relevance=application。"
                "若目标主要是深度学习、大模型或当前基础图谱之外但仍相关的主题，domain_decision=in_domain 且 ml_relevance=application，并给出一个最小澄清问题。"
                "若目标与机器学习无关，domain_decision=out_of_domain。若信息太少才使用 ambiguous。"
                "clarification_question 只能在确实需要用户确认边界时出现，且必须只问一个问题。"
                "confidence 必须反映可映射把握：明确基础目标>=0.8，跨领域应用0.45-0.75，信息不足<0.45。"
                "只输出 JSON 对象，不要输出 Markdown。字段必须包含 schema_version, domain_decision, primary_domain, ml_relevance, goal_type, "
                "target_concepts, constraints, preferences, uncertainties, clarification_question, confidence, evidence。"
                "domain_decision 只能是 in_domain/cross_domain/out_of_domain/ambiguous。"
                "ml_relevance 只能是 core/prerequisite/application/none/unclear。"
                "goal_type 只能是 domain/concept/problem。"
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "goal_text": goal_text,
                    "requested_goal_type": requested_goal_type,
                    "supported_domain": domain,
                    "supported_scope": "机器学习基础单领域原型",
                    "classification_examples": [
                        {"goal_text": "我想系统学习机器学习基础", "domain_decision": "in_domain", "ml_relevance": "core", "confidence": 0.9},
                        {"goal_text": "理解逻辑回归为什么能分类", "domain_decision": "in_domain", "ml_relevance": "core", "confidence": 0.88},
                        {"goal_text": "我想学 AI", "domain_decision": "ambiguous", "ml_relevance": "unclear", "confidence": 0.35},
                        {"goal_text": "我想用机器学习做医学预测", "domain_decision": "cross_domain", "ml_relevance": "application", "confidence": 0.62},
                        {"goal_text": "我想学随机森林", "domain_decision": "in_domain", "ml_relevance": "application", "confidence": 0.7},
                        {"goal_text": "我想学 Vue", "domain_decision": "out_of_domain", "ml_relevance": "none", "confidence": 0.86},
                    ],
                },
                ensure_ascii=False,
            ),
        },
    ]


async def interpret_goal_with_llm(
    *,
    goal_text: str,
    requested_goal_type: str | None,
    domain: str,
    supported_goal_types: set[str],
) -> dict[str, Any]:
    llm_cfg = get_llm_config()
    api_key = llm_cfg.get("llm_api_key") or ""
    model = llm_cfg.get("llm_model") or "gpt-3.5-turbo"
    if not api_key:
        return _unavailable_understanding(
            goal_text=goal_text,
            requested_goal_type=requested_goal_type,
            warning="llm_goal_understanding_missing_api_key",
        )

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{llm_cfg.get('llm_base_url', 'https://api.openai.com/v1').rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": _build_messages(goal_text, requested_goal_type, domain),
                    "temperature": 0,
                    "max_tokens": 600,
                },
            )
            response.raise_for_status()
        content = _strip_code_fence(response.json()["choices"][0]["message"].get("content"))
        parsed = json.loads(content)
        if not isinstance(parsed, dict):
            raise ValueError("LLM goal understanding response must be an object")
        return _normalize_understanding(
            raw=parsed,
            goal_text=goal_text,
            requested_goal_type=requested_goal_type,
            domain=domain,
            supported_goal_types=supported_goal_types,
            model=model,
        )
    except Exception as exc:
        logger.warning("LLM 目标理解失败，继续使用保守目标理解: %s", exc)
        return _unavailable_understanding(
            goal_text=goal_text,
            requested_goal_type=requested_goal_type,
            warning="llm_goal_understanding_failed",
        )
