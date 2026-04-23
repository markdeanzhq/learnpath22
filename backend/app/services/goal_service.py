"""学习目标解析服务：识别目标类型、候选召回、统一排序。"""
from __future__ import annotations

import json
import logging
from typing import Any

import jieba

from app.core.config import get_llm_config

logger = logging.getLogger(__name__)

_FALLBACK_TARGETS = ["ml_c09", "ml_d08", "ml_e03"]
_GOAL_TYPES = {"domain", "concept", "problem"}
_GENERIC_TERMS = ("系统学习", "基础", "入门", "全面", "完整")
_SOURCE_KEYS = ("template", "lexical", "llm")
_RESOLVE_SOURCE_PRIORITY = ("template", "jieba", "llm")
_MAX_LLM_CANDIDATES = 3
_MAX_LLM_NODES_PER_CANDIDATE = 5


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
) -> list[dict[str, Any]]:
    text = _normalize_text(goal_text)
    candidates: list[dict[str, Any]] = []

    for template in templates:
        if template.get("goal_type") not in allowed_goal_types:
            continue

        matched_patterns = [
            pattern for pattern in template.get("pattern", [])
            if isinstance(pattern, str) and pattern.lower() in text
        ]
        if not matched_patterns:
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

    return candidates



def _collect_lexical_candidates(
    goal_text: str,
    effective_goal_type: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    target_node_ids = _jieba_match_nodes(goal_text, nodes_by_id)
    if not target_node_ids:
        return []

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
    ]



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
) -> tuple[list[dict[str, Any]], list[str]]:
    if not allow_llm:
        return [], []

    raw_llm_candidates, llm_warning = _unwrap_llm_match_result(
        _llm_match_nodes(
            goal_text,
            nodes_by_id,
            return_warning=True,
        )
    )
    if raw_llm_candidates is None:
        return [], [llm_warning or "llm_unavailable"]

    valid_candidate_groups, warnings = _validate_llm_candidate_groups(
        raw_llm_candidates,
        nodes_by_id,
    )
    if not valid_candidate_groups:
        return [], warnings or ["llm_empty_result"]

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

    return candidates, warnings



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



def _legacy_empty_result(
    goal_text: str,
    goal_type: str,
    nodes_by_id: dict[str, dict[str, Any]],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    if goal_type == "domain":
        target_node_ids = ["ml_c09", "ml_d08", "ml_e03", "ml_e07"]
        mode = "steady"
        resolve_source = "domain_default"
    else:
        target_node_ids = _FALLBACK_TARGETS[:]
        mode = "efficient"
        resolve_source = "fallback"

    target_node_ids = [nid for nid in target_node_ids if nid in nodes_by_id]
    if not target_node_ids:
        target_node_ids = [nid for nid in _FALLBACK_TARGETS if nid in nodes_by_id]
        resolve_source = "fallback"

    merged_warnings = sorted({"empty_candidates", *(warnings or [])})

    return {
        "goal_text": goal_text,
        "goal_type": goal_type,
        "target_node_ids": target_node_ids,
        "mode": mode,
        "description": goal_text,
        "template_id": None,
        "resolve_source": resolve_source,
        "source_breakdown": _source_breakdown(**{resolve_source if resolve_source in _SOURCE_KEYS else "template": 1.0}),
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
    allow_llm: bool = True,
) -> dict[str, Any]:
    auto_detected_goal_type, effective_goal_type, goal_type_source = _resolve_goal_type_context(
        goal_text,
        goal_type_override,
    )
    allowed_goal_types = {effective_goal_type} if goal_type_override else _GOAL_TYPES

    raw_candidates: list[dict[str, Any]] = []
    raw_candidates.extend(
        _collect_template_candidates(goal_text, templates, nodes_by_id, allowed_goal_types)
    )
    raw_candidates.extend(
        _collect_lexical_candidates(goal_text, effective_goal_type, nodes_by_id)
    )
    llm_candidates, llm_warnings = _collect_llm_candidates(
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
        if candidate["goal_type"] in _GOAL_TYPES and candidate["target_node_ids"]
    ]
    ranked_candidates = sorted(scored_candidates, key=_candidate_sort_key)
    public_candidates = [_public_candidate(candidate) for candidate in ranked_candidates]

    return {
        "auto_detected_goal_type": auto_detected_goal_type,
        "effective_goal_type": effective_goal_type,
        "goal_type_source": goal_type_source,
        "recommended_candidate_id": public_candidates[0]["candidate_id"] if public_candidates else None,
        "candidates": public_candidates,
        "warnings": sorted(set(llm_warnings)),
    }



def resolve_goal(
    goal_text: str,
    goal_type_override: str | None,
    templates: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
    *,
    allow_llm: bool = True,
) -> dict[str, Any]:
    candidate_result = resolve_goal_candidates(
        goal_text=goal_text,
        goal_type_override=goal_type_override,
        templates=templates,
        nodes_by_id=nodes_by_id,
        allow_llm=allow_llm,
    )

    if not candidate_result["candidates"]:
        goal_type = goal_type_override or candidate_result["auto_detected_goal_type"]
        return _legacy_empty_result(
            goal_text,
            goal_type,
            nodes_by_id,
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
