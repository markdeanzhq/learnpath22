"""路径文本渲染"""
from __future__ import annotations

from typing import Any

from app.planner.staging import DEFAULT_STAGES


def render_path_text(
    stage_plan: dict[str, list[dict[str, Any]]],
    budget_summary: dict[str, Any],
    reinforced_ids: list[str],
) -> str:
    lines: list[str] = []
    lines.append("=" * 50)
    lines.append("学习路径规划结果")
    lines.append("=" * 50)

    total_hours = 0.0
    total_nodes = 0
    stage_names = list(stage_plan.keys()) or DEFAULT_STAGES

    for i, stage_name in enumerate(stage_names, 1):
        tasks = stage_plan.get(stage_name, [])
        if not tasks:
            continue
        stage_hours = sum(t["estimated_hours"] for t in tasks)
        total_hours += stage_hours
        total_nodes += len(tasks)

        lines.append(f"\n--- 阶段 {i}: {stage_name} ({len(tasks)} 个知识点, ~{stage_hours:.0f}h) ---")
        for j, task in enumerate(tasks, 1):
            marker = " [补强]" if task["node_id"] in reinforced_ids else ""
            lines.append(
                f"  {j}. {task['name']} "
                f"(难度:{task['difficulty']} 重要性:{task['importance']} "
                f"~{task['estimated_hours']}h){marker}"
            )

    lines.append(f"\n总计: {total_nodes} 个知识点, 预计 {total_hours:.0f} 小时")
    lines.append(f"时间预算: {budget_summary['status']} — {budget_summary['suggestion']}")
    lines.append("=" * 50)

    return "\n".join(lines)
