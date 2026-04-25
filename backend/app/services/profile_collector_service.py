"""LLM 画像采集服务：结构化问卷 + LLM生成 + 确定性映射 + 兜底"""
from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import get_llm_config

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
    {
        "id": "q_deadline",
        "field": "deadline_weeks",
        "question": "你希望多久完成这条学习路径？",
        "options": [
            {"label": "4 周内，需要非常紧凑", "value": 4},
            {"label": "6 周左右", "value": 6},
            {"label": "8 周左右", "value": 8},
            {"label": "12 周左右，稳步推进", "value": 12},
            {"label": "16 周以上，长期学习", "value": 16},
        ],
    },
    {
        "id": "q_path_mode",
        "field": "path_mode_preference",
        "question": "你更希望系统如何组织学习路径？",
        "options": [
            {"label": "标准路径，兼顾完整性和节奏", "value": "standard"},
            {"label": "压缩路径，只保留必要前置和目标", "value": "compressed"},
            {"label": "理论优先，先理解原理", "value": "theory_first"},
            {"label": "实践优先，尽快进入练习", "value": "practice_first"},
        ],
    },
]

# 字段池：LLM 生成的问题只能映射到这些字段
ALLOWED_FIELDS = {
    "math_level",
    "coding_level",
    "ml_level",
    "theory_weight",
    "weekly_hours",
    "deadline_weeks",
    "path_mode_preference",
}
ALLOWED_PATH_MODE_PREFERENCES = {"standard", "compressed", "theory_first", "practice_first"}


def get_static_questions() -> list[dict[str, Any]]:
    return STATIC_QUESTIONS


def is_valid_questionnaire_payload(payload: Any) -> bool:
    if not isinstance(payload, list) or not payload:
        return False

    for question in payload:
        if not isinstance(question, dict):
            return False
        if question.get("field") not in ALLOWED_FIELDS:
            return False
        if not question.get("id") or not question.get("question"):
            return False

        options = question.get("options")
        if not isinstance(options, list) or not options:
            return False
        if any(
            not isinstance(option, dict)
            or "label" not in option
            or "value" not in option
            for option in options
        ):
            return False

    return True


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
        elif field == "path_mode_preference":
            if value not in ALLOWED_PATH_MODE_PREFERENCES:
                continue

        profile[field] = value

    # 补默认值
    profile.setdefault("math_level", 1)
    profile.setdefault("coding_level", 1)
    profile.setdefault("ml_level", 1)
    profile.setdefault("theory_weight", 0.5)
    profile.setdefault("practice_weight", 1.0 - profile.get("theory_weight", 0.5))
    profile.setdefault("weekly_hours", 10.0)
    profile.setdefault("path_mode_preference", "standard")
    profile.update(build_persona_fields(profile))

    return profile


def build_persona_fields(profile: dict[str, Any]) -> dict[str, str]:
    math_level = int(profile.get("math_level") or 1)
    coding_level = int(profile.get("coding_level") or 1)
    ml_level = int(profile.get("ml_level") or 1)
    theory_weight = float(profile.get("theory_weight") or 0.5)
    weekly_hours = float(profile.get("weekly_hours") or 10.0)
    deadline_weeks = profile.get("deadline_weeks")
    path_mode = profile.get("path_mode_preference") or "standard"

    if ml_level <= 2 and math_level <= 2:
        label = "基础补齐型学习者"
    elif coding_level >= 4 and theory_weight <= 0.4:
        label = "实践驱动型学习者"
    elif theory_weight >= 0.7:
        label = "理论理解型学习者"
    elif weekly_hours <= 5 or path_mode == "compressed":
        label = "时间压缩型学习者"
    else:
        label = "均衡推进型学习者"

    evidence = {
        "math_level": math_level,
        "coding_level": coding_level,
        "ml_level": ml_level,
        "theory_weight": theory_weight,
        "weekly_hours": weekly_hours,
        "deadline_weeks": deadline_weeks,
        "path_mode_preference": path_mode,
    }
    deadline_text = f"，计划约 {deadline_weeks} 周完成" if deadline_weeks else ""
    summary = (
        f"{label}：当前数学/编程/机器学习基础为 "
        f"{math_level}/{coding_level}/{ml_level}，每周约 {weekly_hours:g} 小时{deadline_text}。"
    )
    return {
        "persona_label": label,
        "persona_summary": summary,
        "persona_evidence": json.dumps(evidence, ensure_ascii=False, sort_keys=True),
    }


async def generate_llm_questions(
    goal_text: str,
    missing_fields: list[str] | None = None,
) -> list[dict[str, Any]] | None:
    """用 LLM 生成画像澄清问题。超时或 JSON 非法时返回 None（触发兜底）。"""
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
            if is_valid_questionnaire_payload(questions):
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
