"""学习目标解析服务：识别目标类型、候选召回、统一排序。"""
from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from typing import Any

import jieba

from app.core.config import get_llm_config

logger = logging.getLogger(__name__)

_GENERIC_TERMS = ("系统学习", "基础", "入门", "全面", "完整")
_SOURCE_KEYS = ("template", "lexical", "llm")
_RESOLVE_SOURCE_PRIORITY = ("template", "jieba", "llm")
_MAX_LLM_CANDIDATES = 3
_MAX_LLM_NODES_PER_CANDIDATE = 5
_EMPTY_REASON_MAX_LENGTH = 120
_EMPTY_REASON_TIMEOUT_SECONDS = 8
_EMPTY_REASON_FALLBACK_TEXTS = {
    "negative_patterns_excluded_all": "当前目标文本命中了候选模板，但这些模板都被排除词命中，请改写目标描述后重试。",
    "no_rule_match": "当前目标未匹配到可确认的学习目标候选，请尝试改写目标描述或切换目标类型。",
    "llm_unavailable_after_rule_miss": "当前目标未命中规则候选，且 LLM 解析暂时不可用，请稍后重试或改写目标描述。",
    "llm_returned_no_legal_candidates": "规则层未找到稳定候选，且 LLM 没有返回可确认的合法候选，请改写目标描述后重试。",
    "no_supported_candidates": "当前目标未能匹配到可确认的学习目标候选，请尝试改写目标描述或切换目标类型。",
}
_LLM_UNAVAILABLE_WARNINGS = {"llm_unavailable", "llm_timeout", "llm_auth_failed"}


class UnsupportedGoalTypeError(ValueError):
    pass


def _normalize_supported_goal_types(
    supported_goal_types: set[str] | tuple[str, ...] | list[str],
) -> set[str]:
    normalized = {
        goal_type
        for goal_type in supported_goal_types
        if isinstance(goal_type, str) and goal_type
    }
    if not normalized:
        raise UnsupportedGoalTypeError("No supported goal types configured")
    return normalized


def _ensure_supported_goal_type(goal_type: str, supported_goal_types: set[str]) -> None:
    if goal_type not in supported_goal_types:
        raise UnsupportedGoalTypeError(f"Unsupported goal type: {goal_type}")


def build_empty_candidate_reason(
    evidence: dict[str, Any],
    *,
    allow_llm: bool = True,
    llm_client_factory=None,
) -> tuple[str, str]:
    reason_code = _classify_empty_candidate_reason(evidence)
    fallback_text = _EMPTY_REASON_FALLBACK_TEXTS[reason_code]
    if not allow_llm:
        return reason_code, fallback_text
    reason_text = _generate_empty_candidate_reason_text(
        reason_code,
        evidence,
        fallback_text,
        llm_client_factory=llm_client_factory,
    )
    return reason_code, reason_text or fallback_text


def identify_goal_type(goal_text: str) -> str:
    text = goal_text.lower()
    problem_keywords = ["为什么", "怎么", "如何", "搞懂", "推导", "区别", "不会"]
    concept_keywords = ["理解", "概念", "什么是", "了解"]
    domain_keywords = ["系统学习", "入门", "基础", "全面", "完整"]

    if any(k in text for k in problem_keywords):
        return "problem"
    if any(k in text for k in domain_keywords):
        return "domain"
    if any(k in text for k in concept_keywords):
        return "concept"
    return "domain"


def match_goal_template(
    goal_text: str,
    goal_type: str,
    templates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    text = goal_text.lower()
    best: dict[str, Any] | None = None
    best_score = 0

    for tmpl in templates:
        if tmpl["goal_type"] != goal_type:
            continue
        score = sum(1 for p in tmpl["pattern"] if p.lower() in text)
        if score > best_score:
            best_score = score
            best = tmpl

    return best


def match_strong_goal_template(
    goal_text: str,
    goal_type: str,
    templates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    text = goal_text.lower()
    for tmpl in templates:
        if tmpl["goal_type"] != goal_type:
            continue
        if any(pattern.lower() in text for pattern in tmpl["pattern"]):
            return tmpl
    return None


def _classify_llm_failure(error: Exception) -> str:
    if isinstance(error, json.JSONDecodeError):
        return "llm_invalid_json"
    if isinstance(error, TimeoutError):
        return "llm_timeout"
    if isinstance(error, PermissionError):
        return "llm_auth_failed"
    return "llm_unavailable"



def _llm_match_nodes(
    goal_text: str,
    nodes_by_id: dict[str, dict[str, Any]],
    *,
    return_warning: bool = False,
) -> Any:
    """用 LLM 将目标文本映射到知识点候选，失败返回 None。"""
    llm_cfg = get_llm_config()
    api_key = llm_cfg.get("llm_api_key", "")
    if not api_key:
        return (None, "llm_unavailable") if return_warning else None

    try:
        from openai import OpenAI

        client = OpenAI(
            api_key=api_key,
            base_url=llm_cfg.get("llm_base_url", "https://api.openai.com/v1"),
        )

        node_list = "\n".join(
            f"- {n['id']}: {n['name']}" for n in nodes_by_id.values()
        )

        response = client.chat.completions.create(
            model=llm_cfg.get("llm_model", "gpt-3.5-turbo"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是一个知识点匹配助手。给定学习目标和知识点列表，"
                        "返回最多3个候选，每个候选包含1-5个知识点ID。"
                        "只返回 JSON 数组，如 [[\"ml_c09\"], [\"ml_d08\", \"ml_e03\"]]。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"学习目标：{goal_text}\n\n知识点列表：\n{node_list}",
                },
            ],
            temperature=0,
            max_tokens=200,
        )

        content = response.choices[0].message.content.strip()
        candidate_groups = _coerce_llm_candidate_groups(json.loads(content))
        if candidate_groups is not None:
            logger.info("LLM 解析成功: %s -> %s", goal_text, candidate_groups)
            return (candidate_groups, None) if return_warning else candidate_groups

        warning = "llm_invalid_response"
        return (None, warning) if return_warning else None
    except Exception as e:
        logger.warning("LLM 目标解析失败: %s", e)
        warning = _classify_llm_failure(e)
        return (None, warning) if return_warning else None


def _normalize_text(text: str) -> str:
    return text.strip().lower()



def _tokenize_text(text: str) -> set[str]:
    normalized = _normalize_text(text)
    return {token.strip() for token in jieba.cut(normalized) if len(token.strip()) > 1}



def _node_search_texts(node: dict[str, Any]) -> list[str]:
    texts = [node.get("name", "")]
    texts.extend(node.get("aliases", []))
    texts.extend(node.get("keywords", []))
    texts.append(node.get("description", ""))
    return [text for text in texts if isinstance(text, str) and text]



def _unique_valid_node_ids(
    node_ids: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    seen: set[str] = set()
    valid: list[str] = []
    for node_id in node_ids:
        if node_id in nodes_by_id and node_id not in seen:
            seen.add(node_id)
            valid.append(node_id)
    return valid



def _coerce_llm_candidate_groups(raw_result: Any) -> list[list[str]] | None:
    if isinstance(raw_result, dict):
        raw_result = raw_result.get("candidates")

    if not isinstance(raw_result, list):
        return None

    if not raw_result:
        return []

    if all(isinstance(node_id, str) for node_id in raw_result):
        return [raw_result]

    candidate_groups: list[list[str]] = []
    for item in raw_result:
        if isinstance(item, dict):
            item = item.get("target_node_ids", item.get("node_ids"))
        if not isinstance(item, list) or not all(isinstance(node_id, str) for node_id in item):
            return None
        candidate_groups.append(item)

    return candidate_groups



def _validate_llm_candidate_groups(
    raw_result: Any,
    nodes_by_id: dict[str, dict[str, Any]],
) -> tuple[list[list[str]], list[str]]:
    candidate_groups = _coerce_llm_candidate_groups(raw_result)
    if candidate_groups is None:
        return [], ["llm_invalid_response"]
    if not candidate_groups:
        return [], ["llm_empty_result"]

    warnings: set[str] = set()
    if len(candidate_groups) > _MAX_LLM_CANDIDATES:
        warnings.add("llm_too_many_candidates")

    valid_groups: list[list[str]] = []
    seen_groups: set[tuple[str, ...]] = set()
    for node_ids in candidate_groups:
        if not node_ids:
            warnings.add("llm_empty_result")
            continue
        if any(node_id not in nodes_by_id for node_id in node_ids):
            warnings.add("llm_invalid_nodes")
            continue

        deduped_node_ids = _unique_valid_node_ids(node_ids, nodes_by_id)
        if not deduped_node_ids:
            warnings.add("llm_empty_result")
            continue
        if len(deduped_node_ids) > _MAX_LLM_NODES_PER_CANDIDATE:
            warnings.add("llm_candidate_too_large")
            continue

        group_key = tuple(deduped_node_ids)
        if group_key in seen_groups:
            continue
        seen_groups.add(group_key)
        valid_groups.append(deduped_node_ids)
        if len(valid_groups) >= _MAX_LLM_CANDIDATES:
            break

    return valid_groups, sorted(warnings)



def _resolve_goal_type_context(goal_text: str, goal_type_override: str | None) -> tuple[str, str, str]:
    auto_detected_goal_type = identify_goal_type(goal_text)
    effective_goal_type = goal_type_override or auto_detected_goal_type
    goal_type_source = "user" if goal_type_override else "auto"
    return auto_detected_goal_type, effective_goal_type, goal_type_source



def _source_breakdown(*, template: float = 0.0, lexical: float = 0.0, llm: float = 0.0) -> dict[str, float]:
    return {
        "template": template,
        "lexical": lexical,
        "llm": llm,
    }


def _empty_evidence_payload(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "requested_goal_type": evidence.get("requested_goal_type"),
        "effective_goal_type": evidence.get("effective_goal_type"),
        "template_match_count": int(evidence.get("template_match_count", 0)),
        "negative_excluded_count": int(evidence.get("negative_excluded_count", 0)),
        "lexical_match_count": int(evidence.get("lexical_match_count", 0)),
        "llm_status": evidence.get("llm_status", "not_invoked"),
    }



def _classify_empty_candidate_reason(evidence: dict[str, Any]) -> str:
    template_match_count = int(evidence.get("template_match_count", 0))
    negative_excluded_count = int(evidence.get("negative_excluded_count", 0))
    llm_status = str(evidence.get("llm_status", "not_invoked"))

    if template_match_count > 0 and negative_excluded_count >= template_match_count:
        return "negative_patterns_excluded_all"
    if llm_status in _LLM_UNAVAILABLE_WARNINGS:
        return "llm_unavailable_after_rule_miss"
    if llm_status in {"llm_empty_result", "llm_invalid_response", "llm_invalid_nodes", "llm_candidate_too_large"}:
        return "llm_returned_no_legal_candidates"
    if template_match_count == 0 and int(evidence.get("lexical_match_count", 0)) == 0:
        return "no_rule_match"
    return "no_supported_candidates"



def _generate_empty_candidate_reason_text(
    reason_code: str,
    evidence: dict[str, Any],
    fallback_text: str,
    llm_client_factory=None,
) -> str:
    llm_cfg = get_llm_config()
    if not llm_cfg.get("llm_api_key"):
        return fallback_text

    try:
        if llm_client_factory is None:
            from openai import OpenAI

            client = OpenAI(
                api_key=llm_cfg["llm_api_key"],
                base_url=llm_cfg.get("llm_base_url", "https://api.openai.com/v1"),
                timeout=_EMPTY_REASON_TIMEOUT_SECONDS,
            )
        else:
            client = llm_client_factory(llm_cfg)

        payload = json.dumps(
            {
                "reason_code": reason_code,
                "evidence": _empty_evidence_payload(evidence),
                "fallback_text": fallback_text,
            },
            ensure_ascii=False,
        )
        response = client.chat.completions.create(
            model=llm_cfg.get("llm_model", "gpt-3.5-turbo"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是学习目标解析失败说明器。"
                        "只基于输入中的 reason_code、结构化证据和 fallback_text，"
                        "输出一句中文解释，不超过120个中文字符，"
                        "不得引入任何未提供的新节点、新领域、新规则。"
                    ),
                },
                {"role": "user", "content": payload},
            ],
            temperature=0,
            max_tokens=120,
        )
        content = response.choices[0].message.content.strip()
        if not content or len(content) > _EMPTY_REASON_MAX_LENGTH:
            return fallback_text
        return content
    except Exception as exc:
        logger.warning("LLM 空候选原因生成失败，回退规则文案: %s", exc)
        return fallback_text



def _candidate_signature(candidate: dict[str, Any]) -> tuple[str, tuple[str, ...], str]:
    return (
        candidate["goal_type"],
        tuple(sorted(candidate["target_node_ids"])),
        candidate["mode"],
    )



def _dominant_resolve_source(source_breakdown: dict[str, float]) -> str:
    if source_breakdown.get("template", 0.0) > 0:
        return "template"
    if source_breakdown.get("lexical", 0.0) > 0:
        return "jieba"
    if source_breakdown.get("llm", 0.0) > 0:
        return "llm"
    return "template"



def _build_candidate(
    *,
    candidate_id: str,
    goal_type: str,
    target_node_ids: list[str],
    mode: str,
    description: str,
    template_id: str | None,
    resolve_source: str,
    source_breakdown: dict[str, float],
    explanation: str,
    warnings: list[str] | None = None,
    template_priority: int = 50,
    matched_patterns: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id,
        "goal_type": goal_type,
        "target_node_ids": target_node_ids,
        "mode": mode,
        "description": description,
        "template_id": template_id,
        "resolve_source": resolve_source,
        "source_breakdown": source_breakdown,
        "score": 0.0,
        "score_breakdown": {},
        "explanation": explanation,
        "warnings": warnings or [],
        "_template_priority": template_priority,
        "_matched_patterns": matched_patterns or [],
    }



def _merge_candidates(existing: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    merged["source_breakdown"] = {
        key: max(existing["source_breakdown"].get(key, 0.0), incoming["source_breakdown"].get(key, 0.0))
        for key in _SOURCE_KEYS
    }
    merged["warnings"] = sorted(set(existing.get("warnings", [])) | set(incoming.get("warnings", [])))
    merged["_matched_patterns"] = sorted(
        set(existing.get("_matched_patterns", [])) | set(incoming.get("_matched_patterns", []))
    )
    merged["_template_priority"] = max(
        existing.get("_template_priority", 50),
        incoming.get("_template_priority", 50),
    )

    if existing.get("template_id") is None and incoming.get("template_id") is not None:
        merged["candidate_id"] = incoming["candidate_id"]
        merged["template_id"] = incoming["template_id"]
        merged["description"] = incoming["description"]
        merged["mode"] = incoming["mode"]
        merged["goal_type"] = incoming["goal_type"]

    merged["resolve_source"] = _dominant_resolve_source(merged["source_breakdown"])
    return merged



def _collect_template_candidates(
    goal_text: str,
    templates: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    allowed_goal_types: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    text = _normalize_text(goal_text)
    candidates: list[dict[str, Any]] = []
    template_match_count = 0
    negative_excluded_count = 0

    for template in templates:
        if template.get("goal_type") not in allowed_goal_types:
            continue

        matched_patterns = [
            pattern for pattern in template.get("pattern", [])
            if isinstance(pattern, str) and pattern.lower() in text
        ]
        if not matched_patterns:
            continue

        template_match_count += 1
        negative_patterns = [
            pattern for pattern in template.get("negative_patterns", [])
            if isinstance(pattern, str) and pattern.lower() in text
        ]
        if negative_patterns:
            negative_excluded_count += 1
            continue

        target_node_ids = _unique_valid_node_ids(
            list(template.get("target_node_ids", [])),
            nodes_by_id,
        )
        if not target_node_ids:
            continue

        candidates.append(
            _build_candidate(
                candidate_id=f"template:{template['id']}",
                goal_type=template["goal_type"],
                target_node_ids=target_node_ids,
                mode=template.get("mode", "steady"),
                description=template.get("description", goal_text),
                template_id=template["id"],
                resolve_source="template",
                source_breakdown=_source_breakdown(template=1.0),
                explanation=f"命中模板 {template['id']}",
                template_priority=int(template.get("priority", 50)),
                matched_patterns=matched_patterns,
            )
        )

    return candidates, {
        "template_match_count": template_match_count,
        "negative_excluded_count": negative_excluded_count,
    }



def _collect_lexical_candidates(
    goal_text: str,
    effective_goal_type: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> tuple[list[dict[str, Any]], int]:
    target_node_ids = _jieba_match_nodes(goal_text, nodes_by_id)
    if not target_node_ids:
        return [], 0

    candidate_id = f"lexical:{effective_goal_type}:{'+'.join(target_node_ids)}"
    return [
        _build_candidate(
            candidate_id=candidate_id,
            goal_type=effective_goal_type,
            target_node_ids=target_node_ids,
            mode="efficient",
            description=goal_text,
            template_id=None,
            resolve_source="jieba",
            source_breakdown=_source_breakdown(lexical=1.0),
            explanation="基于节点名、别名、关键词和描述的词面召回",
        )
    ], len(target_node_ids)



def _unwrap_llm_match_result(raw_result: Any) -> tuple[Any, str | None]:
    if isinstance(raw_result, tuple) and len(raw_result) == 2:
        return raw_result
    return raw_result, None



def _collect_llm_candidates(
    goal_text: str,
    effective_goal_type: str,
    nodes_by_id: dict[str, dict[str, Any]],
    *,
    allow_llm: bool,
) -> tuple[list[dict[str, Any]], list[str], str]:
    if not allow_llm:
        return [], [], "not_invoked"

    raw_llm_candidates, llm_warning = _unwrap_llm_match_result(
        _llm_match_nodes(
            goal_text,
            nodes_by_id,
            return_warning=True,
        )
    )
    if raw_llm_candidates is None:
        warning = llm_warning or "llm_unavailable"
        return [], [warning], warning

    valid_candidate_groups, warnings = _validate_llm_candidate_groups(
        raw_llm_candidates,
        nodes_by_id,
    )
    if not valid_candidate_groups:
        normalized_warnings = warnings or ["llm_empty_result"]
        return [], normalized_warnings, normalized_warnings[0]

    candidates = []
    for target_node_ids in valid_candidate_groups:
        candidate_id = f"llm:{effective_goal_type}:{'+'.join(target_node_ids)}"
        candidates.append(
            _build_candidate(
                candidate_id=candidate_id,
                goal_type=effective_goal_type,
                target_node_ids=target_node_ids,
                mode="efficient",
                description=goal_text,
                template_id=None,
                resolve_source="llm",
                source_breakdown=_source_breakdown(llm=1.0),
                explanation="LLM 补充召回候选",
            )
        )

    return candidates, warnings, "ok"



def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[tuple[str, tuple[str, ...], str], dict[str, Any]] = {}
    for candidate in candidates:
        signature = _candidate_signature(candidate)
        if signature in merged:
            merged[signature] = _merge_candidates(merged[signature], candidate)
        else:
            merged[signature] = candidate
    return list(merged.values())



def _compute_template_score(candidate: dict[str, Any], templates: list[dict[str, Any]]) -> float:
    if not candidate.get("template_id"):
        return 0.0

    template = next(
        (item for item in templates if item.get("id") == candidate["template_id"]),
        None,
    )
    if template is None:
        return 0.0

    patterns = template.get("pattern", [])
    matched_patterns = candidate.get("_matched_patterns", [])
    coverage = len(matched_patterns) / len(patterns) if patterns else 0.0
    priority_score = candidate.get("_template_priority", 50) / 100
    return min(1.0, 0.7 * coverage + 0.3 * priority_score)



def _compute_lexical_score(
    goal_text: str,
    candidate: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> float:
    goal_tokens = _tokenize_text(goal_text)
    if not goal_tokens:
        return 0.0

    normalized_goal_text = _normalize_text(goal_text)
    candidate_tokens: set[str] = set()
    exact_hits = 0

    for node_id in candidate["target_node_ids"]:
        node = nodes_by_id.get(node_id)
        if not node:
            continue
        for value in _node_search_texts(node):
            lowered = _normalize_text(value)
            candidate_tokens.update(_tokenize_text(lowered))
            if lowered and lowered in normalized_goal_text:
                exact_hits += 1

    overlap_count = len(goal_tokens & candidate_tokens)
    overlap_ratio = overlap_count / len(goal_tokens)
    exact_bonus = min(0.4, exact_hits * 0.1)
    return min(1.0, 0.6 * overlap_ratio + exact_bonus)



def _compute_llm_score(candidate: dict[str, Any]) -> float:
    return 1.0 if candidate["source_breakdown"].get("llm", 0.0) > 0 else 0.0



def _compute_specificity_score(candidate: dict[str, Any]) -> float:
    if candidate["goal_type"] == "domain":
        return 0.60
    if candidate.get("template_id"):
        return 0.80
    target_count = len(candidate["target_node_ids"])
    return 1.0 if target_count == 1 else 0.85



def _compute_generic_penalty(goal_text: str, candidate: dict[str, Any]) -> float:
    if candidate["goal_type"] != "domain":
        return 0.0

    matched_patterns = candidate.get("_matched_patterns", [])
    generic_match_count = sum(
        1 for pattern in matched_patterns
        if any(term in pattern for term in _GENERIC_TERMS)
    )
    if matched_patterns:
        if generic_match_count == len(matched_patterns):
            return 0.10
        if generic_match_count / len(matched_patterns) > 0.5:
            return 0.05

    if any(term in goal_text for term in _GENERIC_TERMS):
        return 0.05
    return 0.0



def _signal_strength(score: float) -> str:
    if score >= 0.65:
        return "strong"
    if score >= 0.35:
        return "medium"
    return "weak"



def _candidate_node_names(
    candidate: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    names: list[str] = []
    for node_id in candidate.get("target_node_ids", []):
        node = nodes_by_id.get(str(node_id))
        if node and node.get("name"):
            names.append(str(node["name"]))
    return names



def _candidate_match_signals(candidate: dict[str, Any]) -> list[dict[str, str]]:
    breakdown = candidate.get("score_breakdown", {})
    signals: list[dict[str, str]] = []
    template_score = float(breakdown.get("template_score") or 0.0)
    lexical_score = float(breakdown.get("lexical_score") or 0.0)
    llm_score = float(breakdown.get("llm_score") or 0.0)

    if template_score > 0:
        signals.append({
            "type": "template",
            "label": "目标模板",
            "strength": _signal_strength(template_score),
            "detail": "命中预设学习目标模板，适合作为正式学习路径目标。",
        })
    if lexical_score > 0:
        signals.append({
            "type": "lexical",
            "label": "关键词匹配",
            "strength": _signal_strength(lexical_score),
            "detail": "根据目标描述与知识点名称、别名、关键词的重合度召回。",
        })
    if llm_score > 0:
        signals.append({
            "type": "llm",
            "label": "LLM 语义匹配",
            "strength": "strong",
            "detail": "LLM 在当前知识图谱节点范围内补充了语义候选。",
        })
    if candidate.get("target_node_ids"):
        signals.append({
            "type": "graph",
            "label": "知识图谱校验",
            "strength": "medium",
            "detail": "候选知识点均来自当前已审核的机器学习基础图谱。",
        })
    return signals



def _candidate_confidence_level(candidate: dict[str, Any]) -> str:
    breakdown = candidate.get("score_breakdown", {})
    template_score = float(breakdown.get("template_score") or 0.0)
    lexical_score = float(breakdown.get("lexical_score") or 0.0)
    llm_score = float(breakdown.get("llm_score") or 0.0)
    final_score = float(breakdown.get("final_score") or candidate.get("score") or 0.0)
    has_template = bool(candidate.get("template_id")) or template_score > 0
    has_llm = llm_score > 0

    if has_template and template_score >= 0.45:
        return "high"
    if has_llm and (lexical_score >= 0.25 or final_score >= 0.35):
        return "high"
    if has_template or has_llm:
        return "medium"
    if candidate.get("resolve_source") == "jieba":
        if final_score < 0.30:
            return "low"
        return "medium"
    return "medium" if final_score >= 0.35 else "low"



def _candidate_confidence_reason(candidate: dict[str, Any], confidence_level: str) -> str:
    breakdown = candidate.get("score_breakdown", {})
    template_score = float(breakdown.get("template_score") or 0.0)
    llm_score = float(breakdown.get("llm_score") or 0.0)
    lexical_score = float(breakdown.get("lexical_score") or 0.0)

    if confidence_level == "high" and template_score > 0:
        return "命中预设目标模板，并通过当前知识图谱节点校验。"
    if confidence_level == "high" and llm_score > 0:
        return "LLM 语义匹配与规则信号共同支持该候选，并通过图谱节点校验。"
    if confidence_level == "medium":
        return "系统找到了可用候选，但匹配依据仍需要你确认是否符合真实目标。"
    if lexical_score > 0:
        return "主要来自关键词匹配，未命中稳定目标模板或 LLM 语义确认，请谨慎确认。"
    return "当前候选依据较弱，请先澄清或改写学习目标。"



def _candidate_recommended_action(confidence_level: str) -> str:
    if confidence_level == "high":
        return "confirm"
    if confidence_level == "medium":
        return "review"
    return "clarify"



def _candidate_user_explanation(
    candidate: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
    confidence_level: str,
) -> str:
    node_names = _candidate_node_names(candidate, nodes_by_id)
    if node_names:
        preview_names = "、".join(node_names[:3])
        if len(node_names) > 3:
            preview_names = f"{preview_names}等 {len(node_names)} 个知识点"
    else:
        preview_names = "当前候选知识点"

    if confidence_level == "high":
        return f"系统较可靠地将你的目标映射到{preview_names}，确认后可用于生成正式学习路径。"
    if confidence_level == "medium":
        return f"系统找到了一组可能匹配的目标知识点：{preview_names}，请确认是否符合你的真实意图。"
    return f"系统仅找到弱匹配候选：{preview_names}，建议先澄清或改写目标后再创建项目。"



def _attach_candidate_ui_metadata(
    candidate: dict[str, Any],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    confidence_level = _candidate_confidence_level(candidate)
    recommended_action = _candidate_recommended_action(confidence_level)
    return {
        **candidate,
        "confidence_level": confidence_level,
        "confidence_reason": _candidate_confidence_reason(candidate, confidence_level),
        "user_explanation": _candidate_user_explanation(candidate, nodes_by_id, confidence_level),
        "debug_explanation": candidate.get("explanation", ""),
        "match_signals": _candidate_match_signals(candidate),
        "recommended_action": recommended_action,
        "is_recommended": recommended_action == "confirm",
    }



def _score_candidate(
    goal_text: str,
    candidate: dict[str, Any],
    templates: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    template_score = _compute_template_score(candidate, templates)
    lexical_score = _compute_lexical_score(goal_text, candidate, nodes_by_id)
    llm_score = _compute_llm_score(candidate)
    specificity_score = _compute_specificity_score(candidate)
    generic_penalty = _compute_generic_penalty(goal_text, candidate)
    final_score = max(
        0.0,
        min(
            1.0,
            0.35 * template_score
            + 0.30 * lexical_score
            + 0.20 * llm_score
            + 0.15 * specificity_score
            - generic_penalty,
        ),
    )

    scored_candidate = dict(candidate)
    scored_candidate["score"] = round(final_score, 6)
    scored_candidate["score_breakdown"] = {
        "template_score": round(template_score, 6),
        "lexical_score": round(lexical_score, 6),
        "llm_score": round(llm_score, 6),
        "specificity_score": round(specificity_score, 6),
        "generic_penalty": round(generic_penalty, 6),
        "template_priority": candidate.get("_template_priority", 50),
        "final_score": round(final_score, 6),
    }
    scored_candidate["resolve_source"] = _dominant_resolve_source(candidate["source_breakdown"])
    scored_candidate["explanation"] = (
        f"{scored_candidate['resolve_source']} 候选，"
        f"template={template_score:.2f} lexical={lexical_score:.2f} "
        f"llm={llm_score:.2f} specificity={specificity_score:.2f} "
        f"penalty={generic_penalty:.2f}"
    )
    return scored_candidate



def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[float, float, int, int, str]:
    return (
        -candidate["score"],
        -candidate["score_breakdown"]["specificity_score"],
        len(candidate["target_node_ids"]),
        -candidate["score_breakdown"]["template_priority"],
        candidate["candidate_id"],
    )



def _public_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in candidate.items()
        if not key.startswith("_")
    }



def _select_legacy_candidate(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    for source in _RESOLVE_SOURCE_PRIORITY:
        source_candidates = [candidate for candidate in candidates if candidate["resolve_source"] == source]
        if source_candidates:
            return max(source_candidates, key=lambda candidate: candidate["score"])
    return candidates[0] if candidates else None



def _get_default_goal_policy_entry(
    goal_type: str,
    default_goal_policy: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(default_goal_policy, Mapping):
        return None
    by_goal_type = default_goal_policy.get("by_goal_type")
    if not isinstance(by_goal_type, Mapping):
        return None
    policy = by_goal_type.get(goal_type)
    return dict(policy) if isinstance(policy, Mapping) else None



def _legacy_empty_result(
    goal_text: str,
    goal_type: str,
    nodes_by_id: dict[str, dict[str, Any]],
    *,
    default_goal_policy: Mapping[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    policy = _get_default_goal_policy_entry(goal_type, default_goal_policy)
    if policy is None:
        raise UnsupportedGoalTypeError(f"No default goal policy configured for goal type: {goal_type}")

    requested_target_node_ids = list(policy.get("target_node_ids") or [])
    missing_target_node_ids = [
        node_id for node_id in requested_target_node_ids
        if node_id not in nodes_by_id
    ]
    if missing_target_node_ids:
        raise UnsupportedGoalTypeError(
            f"Default goal policy references unavailable target nodes for goal type: {goal_type}: {missing_target_node_ids}"
        )

    target_node_ids = [node_id for node_id in requested_target_node_ids if node_id in nodes_by_id]
    if not target_node_ids:
        raise UnsupportedGoalTypeError(f"Default goal policy has no valid target nodes for goal type: {goal_type}")

    resolve_source = str(policy.get("resolve_source") or "domain_default")
    merged_warnings = sorted({"empty_candidates", *(warnings or [])})

    return {
        "goal_text": goal_text,
        "goal_type": goal_type,
        "target_node_ids": target_node_ids,
        "mode": str(policy.get("mode") or "steady"),
        "description": str(policy.get("description") or goal_text),
        "template_id": None,
        "resolve_source": resolve_source,
        "source_breakdown": _source_breakdown(),
        "score_breakdown": {
            "template_score": 0.0,
            "lexical_score": 0.0,
            "llm_score": 0.0,
            "specificity_score": 0.60 if goal_type == "domain" else 0.85,
            "generic_penalty": 0.0,
            "template_priority": 50,
            "final_score": 0.0,
        },
        "warnings": merged_warnings,
    }



def _jieba_match_nodes(
    text: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    """用 jieba 分词做词面匹配。"""
    normalized_text = _normalize_text(text)
    goal_tokens = _tokenize_text(text)

    scored: list[tuple[float, str]] = []
    for node in nodes_by_id.values():
        search_tokens: set[str] = set()
        exact_bonus = 0.0
        for value in _node_search_texts(node):
            lowered = _normalize_text(value)
            search_tokens.update(_tokenize_text(lowered))
            if lowered and lowered in normalized_text:
                exact_bonus += 1.0 if value == node.get("name") else 0.5

        overlap = len(goal_tokens & search_tokens)
        if overlap <= 0 and exact_bonus <= 0:
            continue

        score = overlap + exact_bonus
        scored.append((score, node["id"]))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [node_id for _, node_id in scored[:5]]



def resolve_goal_candidates(
    goal_text: str,
    goal_type_override: str | None,
    templates: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    *,
    supported_goal_types: set[str] | tuple[str, ...] | list[str],
    allow_llm: bool = True,
) -> dict[str, Any]:
    auto_detected_goal_type, effective_goal_type, goal_type_source = _resolve_goal_type_context(
        goal_text,
        goal_type_override,
    )
    runtime_supported_goal_types = _normalize_supported_goal_types(supported_goal_types)
    _ensure_supported_goal_type(effective_goal_type, runtime_supported_goal_types)
    allowed_goal_types = {effective_goal_type} if goal_type_override else runtime_supported_goal_types

    raw_candidates: list[dict[str, Any]] = []
    template_candidates, template_stats = _collect_template_candidates(
        goal_text,
        templates,
        nodes_by_id,
        allowed_goal_types,
    )
    raw_candidates.extend(template_candidates)
    lexical_candidates, lexical_match_count = _collect_lexical_candidates(
        goal_text,
        effective_goal_type,
        nodes_by_id,
    )
    raw_candidates.extend(lexical_candidates)
    llm_candidates, llm_warnings, llm_status = _collect_llm_candidates(
        goal_text,
        effective_goal_type,
        nodes_by_id,
        allow_llm=allow_llm,
    )
    raw_candidates.extend(llm_candidates)

    if llm_warnings:
        for candidate in raw_candidates:
            candidate["warnings"] = sorted(set(candidate.get("warnings", [])) | set(llm_warnings))

    deduped_candidates = _dedupe_candidates(raw_candidates)
    scored_candidates = [
        _score_candidate(goal_text, candidate, templates, nodes_by_id)
        for candidate in deduped_candidates
        if candidate["goal_type"] in runtime_supported_goal_types and candidate["target_node_ids"]
    ]
    ranked_candidates = sorted(scored_candidates, key=_candidate_sort_key)
    enriched_candidates = [
        _attach_candidate_ui_metadata(candidate, nodes_by_id)
        for candidate in ranked_candidates
    ]
    public_candidates = [_public_candidate(candidate) for candidate in enriched_candidates]
    empty_evidence = {
        "requested_goal_type": goal_type_override,
        "effective_goal_type": effective_goal_type,
        "template_match_count": template_stats["template_match_count"],
        "negative_excluded_count": template_stats["negative_excluded_count"],
        "lexical_match_count": lexical_match_count,
        "llm_status": llm_status,
    }
    reason_code = None
    reason_text = None
    if not public_candidates:
        reason_code, reason_text = build_empty_candidate_reason(
            empty_evidence,
            allow_llm=allow_llm,
        )

    return {
        "auto_detected_goal_type": auto_detected_goal_type,
        "effective_goal_type": effective_goal_type,
        "goal_type_source": goal_type_source,
        "recommended_candidate_id": public_candidates[0]["candidate_id"] if public_candidates else None,
        "candidates": public_candidates,
        "warnings": sorted(set(llm_warnings)),
        "empty_evidence": empty_evidence,
        "reason_code": reason_code,
        "reason_text": reason_text,
    }



def resolve_goal(
    goal_text: str,
    goal_type_override: str | None,
    templates: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    *,
    supported_goal_types: set[str] | tuple[str, ...] | list[str],
    allow_llm: bool = True,
    allow_default_policy_fallback: bool = True,
    default_goal_policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    candidate_result = resolve_goal_candidates(
        goal_text=goal_text,
        goal_type_override=goal_type_override,
        templates=templates,
        nodes_by_id=nodes_by_id,
        supported_goal_types=supported_goal_types,
        allow_llm=allow_llm,
    )

    if not candidate_result["candidates"]:
        if not allow_default_policy_fallback:
            raise UnsupportedGoalTypeError("Default goal policy fallback is disabled")
        goal_type = goal_type_override or candidate_result["auto_detected_goal_type"]
        return _legacy_empty_result(
            goal_text,
            goal_type,
            nodes_by_id,
            default_goal_policy=default_goal_policy,
            warnings=candidate_result.get("warnings", []),
        )

    selected_candidate = _select_legacy_candidate(candidate_result["candidates"])
    assert selected_candidate is not None
    return {
        "goal_text": goal_text,
        "goal_type": selected_candidate["goal_type"],
        "target_node_ids": selected_candidate["target_node_ids"],
        "mode": selected_candidate["mode"],
        "description": selected_candidate["description"],
        "template_id": selected_candidate["template_id"],
        "resolve_source": selected_candidate["resolve_source"],
        "candidate_id": selected_candidate["candidate_id"],
        "recommended_candidate_id": candidate_result["recommended_candidate_id"],
        "auto_detected_goal_type": candidate_result["auto_detected_goal_type"],
        "effective_goal_type": candidate_result["effective_goal_type"],
        "goal_type_source": candidate_result["goal_type_source"],
        "source_breakdown": selected_candidate["source_breakdown"],
        "score_breakdown": selected_candidate["score_breakdown"],
        "warnings": selected_candidate["warnings"],
    }
