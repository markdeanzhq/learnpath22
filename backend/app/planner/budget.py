"""时间预算预估"""
from __future__ import annotations

from datetime import datetime
from typing import Any


def calc_weeks_until_deadline(deadline_weeks: int | None) -> float:
    if deadline_weeks is not None and deadline_weeks > 0:
        return float(deadline_weeks)
    return 12.0  # 默认 12 周


def calc_budget_summary(
    profile: dict[str, Any], planned_hours: float
) -> dict[str, Any]:
    weeks = calc_weeks_until_deadline(profile.get("deadline_weeks"))
    weekly_hours = profile.get("weekly_hours", 10.0)
    available_hours = round(weeks * weekly_hours, 1)
    feasibility_ratio = (
        round(available_hours / planned_hours, 3) if planned_hours > 0 else 0
    )

    if feasibility_ratio >= 1.0:
        status = "feasible"
        suggestion = "当前时间预算可支持完整路径"
    elif feasibility_ratio >= 0.8:
        status = "tight"
        suggestion = "时间较紧，建议后续提供压缩版路径"
    else:
        status = "insufficient"
        suggestion = "当前时间预算不足，建议切换 efficient 模式或裁剪扩展节点"

    weekly = profile.get("weekly_hours", 10.0)
    estimated_weeks = round(planned_hours / weekly, 1) if weekly > 0 else 0

    return {
        "total_hours": planned_hours,
        "weekly_hours": weekly,
        "estimated_weeks": estimated_weeks,
        "available_hours": available_hours,
        "feasibility_ratio": feasibility_ratio,
        "status": status,
        "suggestion": suggestion,
    }
