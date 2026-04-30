"""阶段划分：基础准备 → 核心掌握 → 应用突破"""
from __future__ import annotations

from typing import Any

from app.planner.scoring import calc_gap

DEFAULT_STAGES = ["基础准备", "核心掌握", "应用突破"]
DEFAULT_FALLBACK_STAGE = DEFAULT_STAGES[-1]
DEFAULT_CATEGORY_MAP = {
    "foundation": DEFAULT_STAGES[0],
    "math_foundation": DEFAULT_STAGES[0],
    "ml_core": DEFAULT_STAGES[0],
    "algorithm": DEFAULT_STAGES[1],
    "evaluation": DEFAULT_STAGES[2],
    "practice": DEFAULT_STAGES[2],
}
DEFAULT_EMPTY_STAGE_REASON = "当前目标范围没有匹配到该阶段的知识点；系统保留目标闭包和评分结果，不为填充版式加入无关节点。"


def get_stage_names(stage_rules: dict[str, Any] | None = None) -> list[str]:
    return list((stage_rules or {}).get("stages", DEFAULT_STAGES))


def get_fallback_stage(stage_rules: dict[str, Any] | None = None) -> str:
    stage_names = get_stage_names(stage_rules)
    return stage_names[-1] if stage_names else DEFAULT_FALLBACK_STAGE


def get_category_stage_map(stage_rules: dict[str, Any] | None = None) -> dict[str, str]:
    return (stage_rules or {}).get("category_to_stage", DEFAULT_CATEGORY_MAP)


def empty_stage_reason(stage_name: str, goal_type: str) -> str:
    return f"{stage_name}暂无任务：{DEFAULT_EMPTY_STAGE_REASON} goal_type={goal_type}。"


def assign_stage(
    node: dict[str, Any],
    goal_type: str,
    stage_rules: dict[str, Any] | None = None,
) -> str:
    cat_map = get_category_stage_map(stage_rules)
    category = node["category"]
    return cat_map.get(category, get_fallback_stage(stage_rules))


def stage_override(
    node: dict[str, Any],
    profile: dict[str, Any],
    gap: dict[str, float],
    stage: str,
    stage_rules: dict[str, Any] | None = None,
) -> str:
    overrides = (stage_rules or {}).get("override_rules", [])
    default_beginner_stage = get_stage_names(stage_rules)[0]
    for rule in overrides:
        if rule.get("condition") == "beginner_high_gap":
            if (
                profile.get("ml_level", 1) <= 1
                and gap["gap_total"] >= 0.5
                and node.get("is_foundation", False)
            ):
                return rule.get("target_stage", default_beginner_stage)
    return stage


def build_stage_plan(
    ordered_ids: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
    profile: dict[str, Any],
    goal_type: str,
    stage_rules: dict[str, Any] | None = None,
    scoring_config: dict[str, Any] | None = None,
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    stage_names = get_stage_names(stage_rules)
    stages: dict[str, list[dict[str, Any]]] = {name: [] for name in stage_names}
    stage_logs: dict[str, Any] = {}

    for idx, nid in enumerate(ordered_ids):
        node = nodes_by_id[nid]
        gap = calc_gap(node, profile, scoring_config)
        stage = assign_stage(node, goal_type, stage_rules)
        final_stage = stage_override(node, profile, gap, stage, stage_rules)

        stages[final_stage].append(
            {
                "node_id": nid,
                "name": node["name"],
                "difficulty": node["difficulty_final"],
                "importance": node["importance_final"],
                "estimated_hours": node["estimated_hours"],
                "order_in_stage": len(stages[final_stage]),
            }
        )

        stage_logs[nid] = {
            "decision_type": "stage_assignment",
            "assigned_stage": final_stage,
            "reasons": [
                f"category={node['category']}",
                f"goal_type={goal_type}",
                "beginner_override" if final_stage != stage else "default_stage_rule",
            ],
        }

    stage_logs["_stage_summaries"] = {
        stage_name: {
            "stage_name": stage_name,
            "task_count": len(tasks),
            "empty_reason": empty_stage_reason(stage_name, goal_type) if not tasks else None,
        }
        for stage_name, tasks in stages.items()
    }

    return stages, stage_logs
