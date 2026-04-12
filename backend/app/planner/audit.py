"""审计日志构建"""
from __future__ import annotations

from typing import Any


def build_plan_audit(
    goal_result: dict[str, Any],
    profile: dict[str, Any],
    budget_summary: dict[str, Any],
    reinforcement_logs: dict[str, Any],
    ordering_logs: dict[str, Any],
    stage_logs: dict[str, Any],
) -> dict[str, Any]:
    return {
        "goal_result": goal_result,
        "profile_snapshot": {
            "math_level": profile.get("math_level"),
            "coding_level": profile.get("coding_level"),
            "ml_level": profile.get("ml_level"),
            "theory_weight": profile.get("theory_weight"),
            "practice_weight": 1.0 - profile.get("theory_weight", 0.5),
            "weekly_hours": profile.get("weekly_hours"),
            "deadline_weeks": profile.get("deadline_weeks"),
        },
        "budget_summary": budget_summary,
        "reinforcement_logs": reinforcement_logs,
        "ordering_logs": ordering_logs,
        "stage_logs": stage_logs,
    }
