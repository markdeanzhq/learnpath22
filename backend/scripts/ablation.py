"""权重消融实验脚本

覆盖 3 组权重 × 3 个典型目标 = 9 组实验，用于分析评分权重对路径生成的影响。

用法:
    python -m scripts.ablation [--profile beginner|intermediate|focused]
                                [--out reports/ablation/]
"""
from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from app.services.domain_pack_service import DomainPackService
from app.services.planner_service import plan_with_profile
from scripts.evaluate import PROFILE_PRESETS, kendall_tau

GOALS: list[dict[str, str]] = [
    {"id": "G1", "label": "领域型 · 机器学习基础", "text": "我想系统学习机器学习基础"},
    {"id": "G2", "label": "概念型 · 梯度下降", "text": "理解梯度下降"},
    {"id": "G3", "label": "问题型 · 逻辑回归", "text": "我想搞懂逻辑回归为什么能做分类"},
]

WEIGHT_GROUPS: list[dict[str, Any]] = [
    {
        "id": "W1",
        "label": "baseline（默认）",
        "overrides": {},
    },
    {
        "id": "W2",
        "label": "importance-heavy",
        "overrides": {
            "priority_weights": {"importance": 0.35, "goal_relevance": 0.15},
        },
    },
    {
        "id": "W3",
        "label": "relevance-heavy",
        "overrides": {
            "priority_weights": {"importance": 0.15, "goal_relevance": 0.35},
        },
    },
]


def apply_weight_override(
    base_config: dict[str, Any],
    overrides: dict[str, Any],
) -> dict[str, Any]:
    cfg = copy.deepcopy(base_config)
    for section, section_overrides in overrides.items():
        if section not in cfg or not isinstance(cfg[section], dict):
            cfg[section] = section_overrides
            continue
        cfg[section].update(section_overrides)
    return cfg


def run_single(
    pack: DomainPackService,
    goal_text: str,
    profile: dict[str, Any],
    config_override: dict[str, Any],
) -> dict[str, Any]:
    original_config = pack.scoring_config
    pack.scoring_config = apply_weight_override(original_config, config_override)
    try:
        plan = plan_with_profile(
            goal_text=goal_text,
            goal_type=None,
            profile=profile,
            pack=pack,
        )
    finally:
        pack.scoring_config = original_config

    return {
        "ordered_ids": plan["ordered_ids"],
        "stage_plan": {
            stage: [task["node_id"] for task in tasks]
            for stage, tasks in plan["stage_plan"].items()
        },
        "node_count": plan["node_count"],
        "total_hours": plan["total_hours"],
        "reinforced_ids": plan["reinforced_ids"],
        "target_node_ids": plan["goal_result"]["target_node_ids"],
    }


def compute_diff(baseline: list[str], variant: list[str]) -> dict[str, Any]:
    common = [x for x in baseline if x in variant]
    base_pos = {nid: i for i, nid in enumerate(baseline)}
    var_pos = {nid: i for i, nid in enumerate(variant)}

    position_shifts = [
        {
            "node_id": nid,
            "baseline_index": base_pos[nid],
            "variant_index": var_pos[nid],
            "delta": var_pos[nid] - base_pos[nid],
        }
        for nid in common
        if base_pos[nid] != var_pos[nid]
    ]
    position_shifts.sort(key=lambda x: abs(x["delta"]), reverse=True)

    added = [nid for nid in variant if nid not in baseline]
    removed = [nid for nid in baseline if nid not in variant]
    tau, _ = kendall_tau(baseline, variant)
    return {
        "kendall_tau": tau,
        "common_count": len(common),
        "added_nodes": added,
        "removed_nodes": removed,
        "top_position_shifts": position_shifts[:10],
    }


def render_diff_md(matrix: dict[str, Any]) -> str:
    lines: list[str] = ["# 权重消融 — 路径差异分析\n"]
    for goal in GOALS:
        lines.append(f"## {goal['id']} · {goal['label']}")
        lines.append(f"目标：{goal['text']}\n")
        baseline_result = matrix["results"][goal["id"]]["W1"]
        lines.append(
            f"- **W1 baseline**：{baseline_result['node_count']} 节点，"
            f"{baseline_result['total_hours']} 小时"
        )
        for w in WEIGHT_GROUPS[1:]:
            variant_result = matrix["results"][goal["id"]][w["id"]]
            diff = matrix["diffs"][goal["id"]][w["id"]]
            lines.append(
                f"- **{w['id']} {w['label']}**：{variant_result['node_count']} 节点，"
                f"{variant_result['total_hours']} 小时，"
                f"Kendall τ vs W1 = **{diff['kendall_tau']:+.4f}**"
            )
            if diff["added_nodes"]:
                lines.append(f"  - 新增节点：{', '.join(diff['added_nodes'])}")
            if diff["removed_nodes"]:
                lines.append(f"  - 移除节点：{', '.join(diff['removed_nodes'])}")
            if diff["top_position_shifts"]:
                lines.append("  - 主要位置变化（top 5）：")
                for shift in diff["top_position_shifts"][:5]:
                    arrow = "↑" if shift["delta"] < 0 else "↓"
                    lines.append(
                        f"    - `{shift['node_id']}` "
                        f"位 {shift['baseline_index']} → {shift['variant_index']} "
                        f"({arrow}{abs(shift['delta'])})"
                    )
        lines.append("")
    return "\n".join(lines)


def render_kendall_md(matrix: dict[str, Any]) -> str:
    lines: list[str] = ["# 权重消融 — Kendall τ 矩阵\n"]
    lines.append("Kendall τ ∈ [-1, 1]，**1 表示与 baseline 完全一致**，-1 表示完全相反。\n")
    lines.append("| 目标 | W1 baseline | W2 importance-heavy | W3 relevance-heavy |")
    lines.append("|---|---|---|---|")
    for goal in GOALS:
        row = [f"{goal['id']} · {goal['label']}", "1.0000"]
        for w in WEIGHT_GROUPS[1:]:
            tau = matrix["diffs"][goal["id"]][w["id"]]["kendall_tau"]
            row.append(f"{tau:+.4f}")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return "\n".join(lines)


def run_experiment(profile: dict[str, Any]) -> dict[str, Any]:
    pack = DomainPackService()
    pack.load()

    results: dict[str, dict[str, Any]] = {}
    diffs: dict[str, dict[str, Any]] = {}

    for goal in GOALS:
        per_goal: dict[str, Any] = {}
        for w in WEIGHT_GROUPS:
            per_goal[w["id"]] = run_single(
                pack=pack,
                goal_text=goal["text"],
                profile=profile,
                config_override=w["overrides"],
            )
        results[goal["id"]] = per_goal

        baseline_ids = per_goal["W1"]["ordered_ids"]
        diffs[goal["id"]] = {
            w["id"]: compute_diff(baseline_ids, per_goal[w["id"]]["ordered_ids"])
            for w in WEIGHT_GROUPS[1:]
        }

    return {
        "profile": profile,
        "goals": GOALS,
        "weight_groups": WEIGHT_GROUPS,
        "results": results,
        "diffs": diffs,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="评分权重消融实验")
    parser.add_argument(
        "--profile",
        default="beginner",
        choices=sorted(PROFILE_PRESETS),
        help="画像预设",
    )
    parser.add_argument(
        "--out",
        default="reports/ablation",
        help="输出根目录",
    )
    args = parser.parse_args(argv)

    matrix = run_experiment(PROFILE_PRESETS[args.profile])

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "matrix.json").write_text(
        json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "diff.md").write_text(render_diff_md(matrix), encoding="utf-8")
    (out_dir / "kendall.md").write_text(render_kendall_md(matrix), encoding="utf-8")

    print(f"[ablation] 消融矩阵已输出到 {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
