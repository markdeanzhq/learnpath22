"""LLM 画像采集服务：结构化问卷 + LLM生成 + 确定性映射 + 兜底"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_settings, get_llm_config

# ──────────────────────────────────────────────
# 静态问卷（兜底，无 LLM 也能用）
# ──────────────────────────────────────────────
STATIC_QUESTIONS: list[dict[str, Any]] = [
    {
        "id": "q_math",
        "field": "math_level",
        "question": "你的数学基础如何？",
        "options": [
            {"label": "几乎没学过", "value": 1},
            {"label": "知道一些概念但不能独立运用", "value": 2},
            {"label": "能理解基础公式与简单推导", "value": 3},
            {"label": "能独立完成常见推导与练习", "value": 4},
            {"label": "能熟练迁移到新问题", "value": 5},
        ],
    },
    {
        "id": "q_coding",
        "field": "coding_level",
        "question": "你的 Python 编程水平如何？",
        "options": [
            {"label": "不会 Python", "value": 1},
            {"label": "能运行简单示例", "value": 2},
            {"label": "能写简单脚本并调试", "value": 3},
            {"label": "能独立完成小项目", "value": 4},
            {"label": "能熟练实现和改造模型代码", "value": 5},
        ],
    },
    {
        "id": "q_ml",
        "field": "ml_level",
        "question": "你对机器学习的了解程度？",
        "options": [
            {"label": "几乎没接触过", "value": 1},
            {"label": "知道少数名词但链路不完整", "value": 2},
            {"label": "学过入门内容能理解基础模型", "value": 3},
            {"label": "能比较模型并完成基础实验", "value": 4},
            {"label": "能独立阅读和迁移机器学习知识", "value": 5},
        ],
    },
    {
        "id": "q_preference",
        "field": "theory_weight",
        "question": "你更倾向哪种学习方式？",
        "options": [
            {"label": "强调理论推导和原理", "value": 0.8},
            {"label": "偏理论但也要看案例", "value": 0.6},
            {"label": "理论与实践并重", "value": 0.5},
            {"label": "偏实践但也要懂原理", "value": 0.4},
            {"label": "尽快上手写代码", "value": 0.2},
        ],
    },
    {
        "id": "q_hours",
        "field": "weekly_hours",
        "question": "你每周能投入多少小时学习？",
        "options": [
            {"label": "3-5 小时", "value": 4},
            {"label": "5-10 小时", "value": 8},
            {"label": "10-15 小时", "value": 12},
            {"label": "15-20 小时", "value": 18},
            {"label": "20 小时以上", "value": 25},
        ],
    },
]

# 字段池：LLM 生成的问题只能映射到这些字段
ALLOWED_FIELDS = {"math_level", "coding_level", "ml_level", "theory_weight", "weekly_hours", "deadline_weeks"}


def get_static_questions() -> list[dict[str, Any]]:
    return STATIC_QUESTIONS


def map_answers_to_profile(answers: list[dict[str, Any]]) -> dict[str, Any]:
    """确定性映射：将 [{question_id, field, value}] 转为画像参数字典。

    支持两种格式：
    - 带 field 字段（LLM 问卷）：直接用 field 映射
    - 仅 question_id（静态问卷）：通过静态题库查找 field
    """
    profile: dict[str, Any] = {}
    static_field_map = {q["id"]: q["field"] for q in STATIC_QUESTIONS}

    # 值域约束
    field_constraints: dict[str, tuple[float, float]] = {
        "math_level": (1, 5),
        "coding_level": (1, 5),
        "ml_level": (1, 5),
        "theory_weight": (0.0, 1.0),
        "weekly_hours": (1, 60),
        "deadline_weeks": (1, 52),
    }

    for ans in answers:
        value = ans.get("value")
        if value is None:
            continue

        # 优先用 field（LLM 问卷），其次用 question_id 查静态映射
        field = ans.get("field") or static_field_map.get(ans.get("question_id", ""))
        if not field or field not in ALLOWED_FIELDS:
            continue

        # 值域校验
        if field in field_constraints:
            lo, hi = field_constraints[field]
            try:
                value = type(lo)(value)  # 强制类型转换
                value = max(lo, min(hi, value))
            except (TypeError, ValueError):
                continue

        profile[field] = value

    # 补默认值
    profile.setdefault("math_level", 1)
    profile.setdefault("coding_level", 1)
    profile.setdefault("ml_level", 1)
    profile.setdefault("theory_weight", 0.5)
    profile.setdefault("practice_weight", 1.0 - profile.get("theory_weight", 0.5))
    profile.setdefault("weekly_hours", 10.0)

    return profile


async def generate_llm_questions(
    goal_text: str,
    missing_fields: list[str] | None = None,
) -> list[dict[str, Any]] | None:
    """用 LLM 生成画像澄清问题。超时或 JSON 非法时返回 None（触发兜底）。"""
    settings = get_settings()
    llm_cfg = get_llm_config()
    if not llm_cfg["llm_api_key"]:
        return None

    if missing_fields is None:
        missing_fields = list(ALLOWED_FIELDS)

    prompt = f"""你是一个学习路径规划系统的画像采集助手。
用户的学习目标是："{goal_text}"

请根据目标，生成 3-5 个结构化问题来了解用户的学习基础。
每个问题必须映射到以下字段之一：{', '.join(missing_fields)}

严格按以下 JSON 格式输出，不要输出任何其他内容：
[
  {{
    "id": "llm_q1",
    "field": "字段名",
    "question": "问题文本",
    "options": [
      {{"label": "选项文本", "value": 数值}}
    ]
  }}
]"""

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{llm_cfg['llm_base_url']}/chat/completions",
                headers={
                    "Authorization": f"Bearer {llm_cfg['llm_api_key']}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": llm_cfg["llm_model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                },
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
            questions = json.loads(content)
            if isinstance(questions, list) and all(
                "field" in q and q["field"] in ALLOWED_FIELDS for q in questions
            ):
                return questions
    except Exception:
        pass

    return None


async def get_collector_questions(
    goal_text: str,
) -> tuple[list[dict[str, Any]], str]:
    """获取画像采集问题。返回 (questions, source)。"""
    llm_questions = await generate_llm_questions(goal_text)
    if llm_questions:
        return llm_questions, "llm"
    return get_static_questions(), "static"
