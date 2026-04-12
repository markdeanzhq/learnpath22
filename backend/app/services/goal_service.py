"""学习目标解析服务：识别目标类型、模板匹配、目标节点定位

解析优先级：LLM 解析 > jieba 分词匹配 > 模板匹配 > 硬编码兜底
"""
from __future__ import annotations

import json
import logging
from typing import Any

import jieba

from app.core.config import get_llm_config

logger = logging.getLogger(__name__)

# 默认兜底目标节点
_FALLBACK_TARGETS = ["ml_c09", "ml_d08", "ml_e03"]


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


def _llm_match_nodes(
    goal_text: str,
    nodes_by_id: dict[str, dict[str, Any]],
) -> list[str] | None:
    """用 LLM 将目标文本映射到知识点 ID，失败返回 None。"""
    llm_cfg = get_llm_config()
    api_key = llm_cfg.get("llm_api_key", "")
    if not api_key:
        return None

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
                        "返回最相关的知识点ID（1-5个）。只返回 JSON 数组，如 [\"ml_c09\"]。"
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
        ids = json.loads(content)
        if isinstance(ids, list):
            valid = [nid for nid in ids if nid in nodes_by_id]
            if valid:
                logger.info("LLM 解析成功: %s -> %s", goal_text, valid)
                return valid
    except Exception as e:
        logger.warning("LLM 目标解析失败: %s", e)

    return None


def _jieba_match_nodes(
    text: str, nodes_by_id: dict[str, dict[str, Any]]
) -> list[str]:
    """用 jieba 分词做模糊匹配。"""
    tokens = set(jieba.cut(text))
    # 过滤掉太短的 token
    tokens = {t for t in tokens if len(t) > 1}

    scored: list[tuple[int, str]] = []
    for node in nodes_by_id.values():
        node_tokens = set(jieba.cut(node["name"]))
        node_tokens = {t for t in node_tokens if len(t) > 1}
        overlap = len(tokens & node_tokens)
        # 也检查节点名直接包含在目标文本中
        if node["name"] in text:
            overlap += 3
        if overlap > 0:
            scored.append((overlap, node["id"]))

    scored.sort(reverse=True)
    return [nid for _, nid in scored[:5]]


def resolve_goal(
    goal_text: str,
    goal_type_override: str | None,
    templates: list[dict[str, Any]],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    goal_type = goal_type_override or identify_goal_type(goal_text)

    llm_result = _llm_match_nodes(goal_text, nodes_by_id)
    if llm_result:
        target_node_ids = llm_result
        mode = "efficient"
        description = goal_text
        template = None
        source = "llm"
    else:
        jieba_result = _jieba_match_nodes(goal_text, nodes_by_id)
        if jieba_result:
            target_node_ids = jieba_result
            mode = "efficient"
            description = goal_text
            template = None
            source = "jieba"
        else:
            template = match_goal_template(goal_text, goal_type, templates)
            if template:
                target_node_ids = template["target_node_ids"]
                mode = template.get("mode", "steady")
                description = template.get("description", goal_text)
                source = "template"
            else:
                if goal_type == "domain":
                    target_node_ids = ["ml_c09", "ml_d08", "ml_e03", "ml_e07"]
                    mode = "steady"
                    source = "domain_default"
                else:
                    target_node_ids = _FALLBACK_TARGETS[:]
                    mode = "efficient"
                    source = "fallback"
                description = goal_text

    # 确保目标节点存在
    target_node_ids = [nid for nid in target_node_ids if nid in nodes_by_id]
    if not target_node_ids:
        target_node_ids = [nid for nid in _FALLBACK_TARGETS[:] if nid in nodes_by_id]
        source = "fallback"

    return {
        "goal_text": goal_text,
        "goal_type": goal_type,
        "target_node_ids": target_node_ids,
        "mode": mode,
        "description": description,
        "template_id": template["id"] if template else None,
        "resolve_source": source,
    }
