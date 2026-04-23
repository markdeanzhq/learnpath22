"""论文验证指标评估脚本

用法:
    python -m scripts.evaluate --goal "我想系统学习机器学习基础" [--profile beginner|intermediate|focused]
                                [--baseline scripts/baselines/zhouzhihua_index.json]
                                [--out reports/]

产出（在 reports/{timestamp}/ 下）:
    metrics.json  — 5 项指标结构化结果
    summary.md    — 人类可读报表
    raw_path.json — 路径快照
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from app.services.domain_pack_service import DomainPackService
from app.services.planner_service import plan_with_profile

PROFILE_PRESETS: dict[str, dict[str, Any]] = {
    "beginner": {
        "math_level": 2, "coding_level": 2, "ml_level": 1,
        "theory_weight": 0.6, "practice_weight": 0.4,
        "weekly_hours": 10, "deadline_weeks": 12,
    },
    "intermediate": {
        "math_level": 3, "coding_level": 4, "ml_level": 2,
        "theory_weight": 0.4, "practice_weight": 0.6,
        "weekly_hours": 15, "deadline_weeks": 8,
    },
    "focused": {
        "math_level": 3, "coding_level": 3, "ml_level": 1,
        "theory_weight": 0.7, "practice_weight": 0.3,
        "weekly_hours": 8, "deadline_weeks": 6,
    },
}

GROUP_LABELS = {
    "A": "数学与编程基础",
    "B": "机器学习概念",
    "C": "监督学习算法",
    "D": "模型评估",
    "E": "实践入门",
}


def kendall_tau(seq_a: list[str], seq_b: list[str]) -> tuple[float, int]:
    """在 seq_a 与 seq_b 的交集节点上计算 Kendall τ。

    返回 (tau, 交集大小)。交集 <2 返回 (0.0, n)。
    """
    common = [x for x in seq_a if x in seq_b]
    n = len(common)
    if n < 2:
        return 0.0, n

    rank_b = {x: i for i, x in enumerate([y for y in seq_b if y in common])}
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            ai, aj = rank_b[common[i]], rank_b[common[j]]
            if ai < aj:
                concordant += 1
            elif ai > aj:
                discordant += 1

    total = n * (n - 1) / 2
    tau = (concordant - discordant) / total if total else 0.0
    return round(tau, 4), n


def metric_dependency_satisfaction(
    ordered_ids: list[str],
    requires_edges: list[dict[str, str]],
) -> dict[str, Any]:
    position = {nid: i for i, nid in enumerate(ordered_ids)}
    violations: list[dict[str, str]] = []
    checked = 0
    for edge in requires_edges:
        src, tgt = edge["source"], edge["target"]
        if src in position and tgt in position:
            checked += 1
            if position[src] >= position[tgt]:
                violations.append({
                    "source": src,
                    "target": tgt,
                    "reason": edge.get("reason", ""),
                })
    satisfied = checked - len(violations)
    rate = satisfied / checked if checked else 1.0
    return {
        "checked_edges": checked,
        "satisfied": satisfied,
        "violations": violations,
        "satisfaction_rate": round(rate, 4),
    }


def metric_cycle_check(pack: DomainPackService) -> dict[str, Any]:
    try:
        is_dag = pack.validate_dag()
        return {"is_dag": is_dag, "error": None}
    except Exception as exc:
        return {"is_dag": False, "error": str(exc)}


def metric_kendall_vs_baseline(
    ordered_ids: list[str],
    baseline_sequence: list[str],
) -> dict[str, Any]:
    tau, common = kendall_tau(ordered_ids, baseline_sequence)
    return {
        "tau": tau,
        "common_nodes": common,
        "baseline_size": len(baseline_sequence),
        "path_size": len(ordered_ids),
    }


def metric_type_coverage(
    ordered_ids: list[str],
    nodes_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    per_group_total: dict[str, int] = {}
    per_group_covered: dict[str, int] = {}
    backbone_total = backbone_covered = 0
    main_path_total = main_path_covered = 0

    for nid, node in nodes_by_id.items():
        g = node.get("group", "?")
        per_group_total[g] = per_group_total.get(g, 0) + 1
        if node.get("importance_final", 0) >= 4:
            backbone_total += 1
        if node.get("is_main_path", False):
            main_path_total += 1

    covered_set = set(ordered_ids)
    for nid in covered_set:
        node = nodes_by_id.get(nid)
        if node is None:
            continue
        g = node.get("group", "?")
        per_group_covered[g] = per_group_covered.get(g, 0) + 1
        if node.get("importance_final", 0) >= 4:
            backbone_covered += 1
        if node.get("is_main_path", False):
            main_path_covered += 1

    per_group = {
        g: {
            "label": GROUP_LABELS.get(g, g),
            "total": per_group_total[g],
            "covered": per_group_covered.get(g, 0),
            "rate": round(per_group_covered.get(g, 0) / per_group_total[g], 4)
            if per_group_total[g] else 0.0,
        }
        for g in sorted(per_group_total)
    }
    backbone_rate = (
        round(backbone_covered / backbone_total, 4) if backbone_total else 0.0
    )
    main_path_coverage = (
        round(main_path_covered / main_path_total, 4) if main_path_total else 0.0
    )
    return {
        "per_group": per_group,
        "backbone_total": backbone_total,
        "backbone_covered": backbone_covered,
        "backbone_rate": backbone_rate,
        "main_path_total": main_path_total,
        "main_path_covered": main_path_covered,
        "main_path_coverage": main_path_coverage,
    }


def metric_stage_closure(
    stage_plan: dict[str, list[dict[str, Any]]],
    requires_edges: list[dict[str, str]],
) -> dict[str, Any]:
    stage_order = list(stage_plan.keys())
    node_stage: dict[str, int] = {}
    for idx, stage in enumerate(stage_order):
        for task in stage_plan[stage]:
            node_stage[task["node_id"]] = idx

    violations: list[dict[str, Any]] = []
    checked = 0
    for edge in requires_edges:
        src, tgt = edge["source"], edge["target"]
        if src in node_stage and tgt in node_stage:
            checked += 1
            if node_stage[src] > node_stage[tgt]:
                violations.append({
                    "source": src,
                    "source_stage": stage_order[node_stage[src]],
                    "target": tgt,
                    "target_stage": stage_order[node_stage[tgt]],
                })
    satisfied = checked - len(violations)
    rate = satisfied / checked if checked else 1.0
    return {
        "stages": stage_order,
        "checked_edges": checked,
        "violations": violations,
        "closure_completeness_rate": round(rate, 4),
    }


def run_evaluation(
    goal: str,
    profile: dict[str, Any],
    baseline_path: Path,
) -> dict[str, Any]:
    pack = DomainPackService()
    pack.load()

    baseline_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    baseline_sequence = baseline_data["sequence"]

    plan = plan_with_profile(
        goal_text=goal,
        goal_type=None,
        profile=profile,
        pack=pack,
    )

    ordered_ids = plan["ordered_ids"]
    stage_plan = plan["stage_plan"]

    metrics = {
        "M1_dependency_satisfaction": metric_dependency_satisfaction(
            ordered_ids, pack.requires_edges
        ),
        "M2_cycle_check": metric_cycle_check(pack),
        "M3_kendall_vs_baseline": metric_kendall_vs_baseline(
            ordered_ids, baseline_sequence
        ),
        "M4_type_coverage": metric_type_coverage(ordered_ids, pack.nodes_by_id),
        "M5_stage_closure": metric_stage_closure(stage_plan, pack.requires_edges),
    }

    return {
        "plan": {
            "goal": goal,
            "profile": profile,
            "ordered_ids": ordered_ids,
            "stage_plan": stage_plan,
            "total_hours": plan["total_hours"],
            "node_count": plan["node_count"],
            "reinforced_ids": plan["reinforced_ids"],
            "target_node_ids": plan["goal_result"]["target_node_ids"],
            "mode": plan["goal_result"]["mode"],
        },
        "baseline": {
            "name": baseline_data.get("name", ""),
            "source": baseline_data.get("source", ""),
        },
        "metrics": metrics,
    }


def render_summary(result: dict[str, Any]) -> str:
    m = result["metrics"]
    p = result["plan"]
    lines: list[str] = []
    lines.append("# 学习路径规划 — 验证指标报表\n")
    lines.append(f"- 目标：{p['goal']}")
    lines.append(f"- 目标节点：{', '.join(p['target_node_ids'])}")
    lines.append(f"- 画像：{p['profile']}")
    lines.append(f"- 路径长度：{p['node_count']} 个节点，预计 {p['total_hours']} 小时\n")

    lines.append("## M1 依赖满足率")
    m1 = m["M1_dependency_satisfaction"]
    lines.append(
        f"- 检查边数 {m1['checked_edges']}，违反 {len(m1['violations'])} 条，"
        f"满足率 **{m1['satisfaction_rate'] * 100:.1f}%**\n"
    )

    lines.append("## M2 环检查")
    m2 = m["M2_cycle_check"]
    status = "通过 (DAG)" if m2["is_dag"] else f"失败：{m2['error']}"
    lines.append(f"- {status}\n")

    lines.append("## M3 Kendall τ 教材顺序对比")
    m3 = m["M3_kendall_vs_baseline"]
    lines.append(
        f"- 交集节点 {m3['common_nodes']} / 教材基线 {m3['baseline_size']} / 路径 {m3['path_size']}"
    )
    lines.append(f"- Kendall τ = **{m3['tau']:+.4f}**（1 = 完全一致；-1 = 完全相反）\n")

    lines.append("## M4 类型覆盖矩阵")
    m4 = m["M4_type_coverage"]
    lines.append("| 组 | 标签 | 覆盖/总数 | 覆盖率 |")
    lines.append("|---|---|---|---|")
    for g, info in m4["per_group"].items():
        lines.append(
            f"| {g} | {info['label']} | {info['covered']}/{info['total']} | {info['rate'] * 100:.1f}% |"
        )
    lines.append(
        f"\n- 主干节点（importance ≥ 4）：{m4['backbone_covered']}/{m4['backbone_total']}，"
        f"覆盖率 **{m4['backbone_rate'] * 100:.1f}%**"
    )
    lines.append(
        f"- 主路径节点（is_main_path = true）：{m4['main_path_covered']}/{m4['main_path_total']}，"
        f"覆盖率 **{m4['main_path_coverage'] * 100:.1f}%**\n"
    )

    lines.append("## M5 阶段依赖闭包完整率")
    m5 = m["M5_stage_closure"]
    lines.append(f"- 阶段序列：{' → '.join(m5['stages'])}")
    lines.append(
        f"- 跨阶段边 {m5['checked_edges']}，违反 {len(m5['violations'])} 条，"
        f"完整率 **{m5['closure_completeness_rate'] * 100:.1f}%**"
    )
    if m5["violations"]:
        lines.append("- 违规边：")
        for v in m5["violations"][:10]:
            lines.append(
                f"  - `{v['source']}` ({v['source_stage']}) → `{v['target']}` ({v['target_stage']})"
            )
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Thesis 验证指标评估")
    parser.add_argument("--goal", required=True, help="学习目标文本")
    parser.add_argument(
        "--profile",
        default="beginner",
        choices=sorted(PROFILE_PRESETS),
        help="画像预设",
    )
    default_baseline = Path(__file__).parent / "baselines" / "zhouzhihua_index.json"
    parser.add_argument(
        "--baseline",
        default=str(default_baseline),
        help="教材基线 JSON 路径",
    )
    parser.add_argument(
        "--out",
        default="reports",
        help="输出根目录（实际会在其下创建时间戳子目录）",
    )
    args = parser.parse_args(argv)

    try:
        result = run_evaluation(
            goal=args.goal,
            profile=PROFILE_PRESETS[args.profile],
            baseline_path=Path(args.baseline),
        )
    except FileNotFoundError as exc:
        print(f"[evaluate] 数据文件缺失: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"[evaluate] 算法异常: {exc}", file=sys.stderr)
        return 2

    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path(args.out) / timestamp
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "metrics.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "raw_path.json").write_text(
        json.dumps(result["plan"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "summary.md").write_text(render_summary(result), encoding="utf-8")

    print(f"[evaluate] 报表已输出到 {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
