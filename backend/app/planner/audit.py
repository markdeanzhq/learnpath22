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
    removed_node_ids: list[str] | None = None,
    removed_edge_ids: list[str] | None = None,
    filtered_requires_adj: dict[str, list[str]] | None = None,
    filtered_requires_rev_adj: dict[str, list[str]] | None = None,
    pack_version: str | None = None,
    closure_ids: list[str] | None = None,
    reinforced_ids: list[str] | None = None,
    final_ids: list[str] | None = None,
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
        "removed_node_ids": removed_node_ids or [],
        "removed_edge_ids": removed_edge_ids or [],
        "filtered_requires_adj": filtered_requires_adj or {},
        "filtered_requires_rev_adj": filtered_requires_rev_adj or {},
        "pack_version": pack_version,
        "closure_ids": closure_ids or [],
        "reinforced_ids": reinforced_ids or [],
        "final_ids": final_ids or [],
    }
