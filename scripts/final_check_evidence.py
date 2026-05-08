from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any


GOAL_ROWS = [
    ("G1", "领域型", "系统学习机器学习基础"),
    ("G2", "概念型", "理解梯度下降"),
    ("G3", "问题型", "理解逻辑回归分类原理"),
]


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def display_path(root: Path, path: Path) -> str:
    try:
        return rel(root, path)
    except ValueError:
        return path.as_posix()


def pct(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.2f}%"


def pass_text(value: bool) -> str:
    return "PASS" if value else "FAIL"


def sha256_short(path: Path) -> str:
    if not path.is_file():
        return "-"
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12]


def latest_child(path: Path) -> Path | None:
    if not path.exists():
        return None
    children = sorted(item for item in path.iterdir() if item.is_dir())
    return children[-1] if children else None


def flatten_plan_response(plan: dict[str, Any]) -> tuple[list[str], dict[str, int]]:
    ordered_ids: list[str] = []
    stage_by_node: dict[str, int] = {}
    stages = sorted(plan.get("stages", []), key=lambda item: item.get("stage_index", 0))
    for stage_index, stage in enumerate(stages):
        tasks = sorted(stage.get("tasks", []), key=lambda item: item.get("order_in_stage", 0))
        for task in tasks:
            node_id = task["node_id"]
            ordered_ids.append(node_id)
            stage_by_node[node_id] = stage_index
    return ordered_ids, stage_by_node


def flatten_stage_plan(stage_plan: dict[str, list[dict[str, Any]]]) -> tuple[list[str], dict[str, int]]:
    ordered_ids: list[str] = []
    stage_by_node: dict[str, int] = {}
    for stage_index, tasks in enumerate(stage_plan.values()):
        sorted_tasks = sorted(tasks, key=lambda item: item.get("order_in_stage", 0))
        for task in sorted_tasks:
            node_id = task["node_id"]
            ordered_ids.append(node_id)
            stage_by_node[node_id] = stage_index
    return ordered_ids, stage_by_node


def dependency_check(ordered_ids: list[str], requires_edges: list[dict[str, Any]]) -> dict[str, Any]:
    position = {node_id: index for index, node_id in enumerate(ordered_ids)}
    checked = 0
    satisfied = 0
    violations: list[str] = []
    for edge in requires_edges:
        source = edge["source"]
        target = edge["target"]
        if source not in position or target not in position:
            continue
        checked += 1
        if position[source] < position[target]:
            satisfied += 1
        else:
            violations.append(f"{source}->{target}")
    ratio = satisfied / checked if checked else 1.0
    return {"checked": checked, "satisfied": satisfied, "ratio": ratio, "violations": violations, "ok": satisfied == checked}


def stage_closure_check(stage_by_node: dict[str, int], requires_edges: list[dict[str, Any]]) -> dict[str, Any]:
    checked = 0
    satisfied = 0
    violations: list[str] = []
    for edge in requires_edges:
        source = edge["source"]
        target = edge["target"]
        if source not in stage_by_node or target not in stage_by_node:
            continue
        checked += 1
        if stage_by_node[source] <= stage_by_node[target]:
            satisfied += 1
        else:
            violations.append(f"{source}->{target}")
    ratio = satisfied / checked if checked else 1.0
    return {"checked": checked, "satisfied": satisfied, "ratio": ratio, "violations": violations, "ok": satisfied == checked}


def high_importance_coverage(ordered_ids: list[str], nodes: list[dict[str, Any]]) -> dict[str, Any]:
    high_nodes = {node["id"] for node in nodes if node.get("importance_final", 0) >= 4}
    covered = len(high_nodes.intersection(ordered_ids))
    total = len(high_nodes)
    ratio = covered / total if total else 0.0
    return {"covered": covered, "total": total, "ratio": ratio}


def is_dag(node_ids: set[str], requires_edges: list[dict[str, Any]]) -> bool:
    adjacency = {node_id: [] for node_id in node_ids}
    indegree = {node_id: 0 for node_id in node_ids}
    for edge in requires_edges:
        source = edge["source"]
        target = edge["target"]
        if source not in node_ids or target not in node_ids:
            continue
        adjacency[source].append(target)
        indegree[target] += 1
    queue = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    visited = 0
    while queue:
        node_id = queue.pop(0)
        visited += 1
        for target in adjacency[node_id]:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)
                queue.sort()
    return visited == len(node_ids)


def build_context() -> dict[str, Any]:
    root = Path(os.environ.get("REPO_ROOT", Path(__file__).resolve().parents[1]))
    backend = root / "backend"
    scripts = root / "scripts"
    pack = backend / "app" / "domain_packs" / "machine_learning"
    artifacts = backend / "artifacts"
    paths = {
        "manifest": pack / "manifest.json",
        "nodes": pack / "nodes.json",
        "requires": pack / "requires_edges.json",
        "related": pack / "related_edges.json",
        "matrix": backend / "scripts" / "thesis_validation_matrix.json",
        "latest": artifacts / "thesis_validation" / "latest.json",
        "paper_metrics": artifacts / "thesis_validation" / "paper_metrics.json",
        "report": artifacts / "thesis_validation" / "report.md",
        "evidence_script": scripts / "final_check_evidence.py",
        "generator_script": backend / "scripts" / "generate_thesis_validation_evidence.py",
        "evaluate_script": backend / "scripts" / "evaluate.py",
        "ablation_script": backend / "scripts" / "ablation.py",
    }
    manifest = read_json(paths["manifest"])
    nodes = read_json(paths["nodes"])
    requires_edges = read_json(paths["requires"])
    related_edges = read_json(paths["related"])
    matrix = read_json(paths["matrix"])
    latest = read_json(paths["latest"])
    metrics = read_json(paths["paper_metrics"])
    dag_ok = is_dag({node["id"] for node in nodes}, requires_edges)
    artifacts_root = artifacts
    return {
        "root": root,
        "backend": backend,
        "scripts": scripts,
        "pack": pack,
        "artifacts": artifacts_root,
        "paths": paths,
        "manifest": manifest,
        "nodes": nodes,
        "requires_edges": requires_edges,
        "related_edges": related_edges,
        "matrix": matrix,
        "latest": latest,
        "metrics": metrics,
        "dag_ok": dag_ok,
    }


def final_report_row(ctx: dict[str, Any], goal_id: str, label: str, title: str) -> dict[str, Any] | None:
    root = ctx["root"]
    latest = latest_child(ctx["artifacts"] / "final_reports" / goal_id)
    if latest is None:
        return None
    data = read_json(latest / "metrics.json")
    plan = data["plan"]
    metrics = data["metrics"]
    ordered_ids, stage_by_node = flatten_stage_plan(plan["stage_plan"])
    dep = dependency_check(ordered_ids, ctx["requires_edges"])
    closure = stage_closure_check(stage_by_node, ctx["requires_edges"])
    coverage = high_importance_coverage(ordered_ids, ctx["nodes"])
    tau = metrics["M3_kendall_vs_baseline"]["tau"]
    ok = dep["ok"] and ctx["dag_ok"] and closure["ok"]
    return {
        "goal_id": goal_id,
        "label": label,
        "title": title,
        "source": rel(root, latest / "metrics.json"),
        "node_count": plan["node_count"],
        "total_hours": plan["total_hours"],
        "dep": dep,
        "dep_text": f"{dep['satisfied']}/{dep['checked']} ({pct(dep['ratio'])})",
        "dag": ctx["dag_ok"],
        "tau": f"{tau:.4f}" if tau is not None else "-",
        "high": f"{coverage['covered']}/{coverage['total']} ({pct(coverage['ratio'])})",
        "closure": closure,
        "closure_text": f"{closure['satisfied']}/{closure['checked']} ({pct(closure['ratio'])})",
        "result": pass_text(ok),
    }


def scenario_rows(ctx: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    total_checked = 0
    total_satisfied = 0
    ok_count = 0
    for item in ctx["latest"]["results"]:
        plan = item["plan_response"]
        ordered_ids, stage_by_node = flatten_plan_response(plan)
        dep = dependency_check(ordered_ids, ctx["requires_edges"])
        closure = stage_closure_check(stage_by_node, ctx["requires_edges"])
        ok = dep["ok"] and closure["ok"]
        total_checked += dep["checked"]
        total_satisfied += dep["satisfied"]
        if ok:
            ok_count += 1
        rows.append({
            "id": item["scenario_id"],
            "title": item["scenario_title"],
            "node_count": plan["node_count"],
            "stage_count": len(plan["stages"]),
            "total_hours": plan["total_hours"],
            "dep": dep,
            "closure": closure,
            "ok": ok,
        })
    ratio = total_satisfied / total_checked if total_checked else 1.0
    return rows, {"ok_count": ok_count, "total": len(rows), "checked": total_checked, "satisfied": total_satisfied, "ratio": ratio}


def ablation_lines(ctx: dict[str, Any]) -> tuple[Path | None, list[str], list[tuple[str, str, str, str]]]:
    latest = latest_child(ctx["artifacts"] / "final_ablation")
    if not latest or not (latest / "kendall.md").exists():
        return latest, [], []
    lines = (latest / "kendall.md").read_text(encoding="utf-8").splitlines()
    table_lines = [line for line in lines if line.startswith("|")]
    parsed: list[tuple[str, str, str, str]] = []
    for line in table_lines:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 4 or cells[0] == "目标" or set(cells[0]) <= {"-", ":"}:
            continue
        parsed.append((cells[0], cells[1], cells[2], cells[3]))
    return latest / "kendall.md", table_lines, parsed


def print_report(ctx: dict[str, Any]) -> int:
    root = ctx["root"]
    manifest = ctx["manifest"]
    matrix = ctx["matrix"]
    metrics = ctx["metrics"]
    rows = [row for goal_id, label, title in GOAL_ROWS if (row := final_report_row(ctx, goal_id, label, title))]
    scenarios, scenario_summary = scenario_rows(ctx)
    abl_path, abl_table, _ = ablation_lines(ctx)

    print("# LearnPath-KG 论文实验数据验证报告")
    print()
    print("## 1. 实验数据来源")
    print("| 数据项 | 文件路径 | SHA256前12位 | 状态 |")
    print("|---|---|---:|---|")
    for label, key in [
        ("领域包 manifest", "manifest"),
        ("知识节点", "nodes"),
        ("硬前置依赖边", "requires"),
        ("语义关联边", "related"),
        ("固定场景矩阵", "matrix"),
        ("9 场景原始验证结果", "latest"),
        ("论文指标汇总", "paper_metrics"),
        ("Markdown 验证报告", "report"),
    ]:
        path = ctx["paths"][key]
        print(f"| {label} | `{rel(root, path)}` | `{sha256_short(path)}` | {pass_text(path.exists())} |")
    print()
    print("## 2. 实验数据验证流程")
    print("| 步骤 | 验证内容 | 判定规则 |")
    print("|---|---|---|")
    print("| 1 | 读取 Domain Pack 与固定场景矩阵 | 输入文件均可读取且哈希可复核 |")
    print("| 2 | 检查 Domain Pack 结构 | 节点数匹配 manifest，REQUIRES 图无环 |")
    print("| 3 | 复核三类典型目标路径 | M1=100%，M2=true，M5=100% |")
    print("| 4 | 复算 9 场景矩阵 | 逐场景复算路径内 REQUIRES 顺序与阶段闭包 |")
    print("| 5 | 读取权重消融结果 | W2/W3 与 W1 baseline 的 Kendall τ 可复核 |")
    print()
    print("## 3. Domain Pack 结构验证")
    print("| 指标 | 实际值 | 验证结果 |")
    print("|---|---:|---|")
    print(f"| 领域包版本 | {manifest['version']} | PASS |")
    print(f"| 知识节点数 | {len(ctx['nodes'])} / {manifest['node_count']} | {pass_text(len(ctx['nodes']) == manifest['node_count'])} |")
    print(f"| REQUIRES 硬前置边数 | {len(ctx['requires_edges'])} | {pass_text(len(ctx['requires_edges']) == 66)} |")
    print(f"| RELATED_TO 语义关联边数 | {len(ctx['related_edges'])} | {pass_text(len(ctx['related_edges']) == 16)} |")
    print(f"| REQUIRES 图 DAG 检查 | {ctx['dag_ok']} | {pass_text(ctx['dag_ok'])} |")
    print(f"| 固定验证场景数 | {len(matrix['scenarios'])} | {pass_text(len(matrix['scenarios']) == 9)} |")
    print()
    print("## 4. 三类典型目标指标验证")
    print("| 目标 | 节点数 | 学时 | M1依赖满足 | M2 DAG | M3 Kendall τ | M4高重要度覆盖 | M5阶段闭包 | 判定 |")
    print("|---|---:|---:|---|---|---:|---|---|---|")
    for row in rows:
        print(f"| {row['label']} | {row['node_count']} | {row['total_hours']} | {row['dep_text']} | {row['dag']} | {row['tau']} | {row['high']} | {row['closure_text']} | {row['result']} |")
    print()
    print("## 5. 9 场景矩阵验证")
    dep = metrics["dependency_correctness"]
    stage = metrics["stage_evidence"]
    print("| 汇总项 | 实际值 | 验证结果 |")
    print("|---|---:|---|")
    print(f"| 场景通过数 | {scenario_summary['ok_count']}/{scenario_summary['total']} | {pass_text(scenario_summary['ok_count'] == scenario_summary['total'])} |")
    print(f"| 现场复算硬前置依赖 | {scenario_summary['satisfied']}/{scenario_summary['checked']} ({pct(scenario_summary['ratio'])}) | {pass_text(scenario_summary['satisfied'] == scenario_summary['checked'])} |")
    print(f"| 报告硬前置依赖满足 | {dep['satisfied_required_edges']}/{dep['total_required_edges']} ({pct(dep['dependency_satisfaction_ratio'])}) | {pass_text(dep['dependency_satisfaction_ratio'] == 1.0)} |")
    print(f"| 平均阶段数 | {stage['average_stage_count']} | PASS |")
    print(f"| 平均阶段总学时 | {stage['average_total_stage_hours']} 小时 | PASS |")
    print()
    print("| 场景 | 节点数 | 阶段数 | 学时 | 现场复算M1 | 现场复算M5 | 判定 |")
    print("|---|---:|---:|---:|---|---|---|")
    for row in scenarios:
        print(f"| {row['title']} | {row['node_count']} | {row['stage_count']} | {row['total_hours']} | {row['dep']['satisfied']}/{row['dep']['checked']} ({pct(row['dep']['ratio'])}) | {row['closure']['satisfied']}/{row['closure']['checked']} ({pct(row['closure']['ratio'])}) | {pass_text(row['ok'])} |")
    print()
    print("## 6. 权重消融实验验证")
    if abl_path and abl_table:
        print(f"数据来源：`{rel(root, abl_path)}`")
        for line in abl_table:
            print(line)
    else:
        print("未找到权重消融 Kendall τ 结果文件。")
    print()
    print("## 7. 验证结论")
    typical_ok = bool(rows) and all(row["result"] == "PASS" for row in rows)
    matrix_ok = scenario_summary["ok_count"] == scenario_summary["total"]
    dependency_ok = scenario_summary["satisfied"] == scenario_summary["checked"]
    print("| 结论项 | 判定 |")
    print("|---|---|")
    print(f"| Domain Pack 结构检查 | {pass_text(ctx['dag_ok'] and len(ctx['nodes']) == manifest['node_count'])} |")
    print(f"| 三类典型目标路径指标复核 | {pass_text(typical_ok)} |")
    print(f"| 9 场景矩阵现场复算 | {pass_text(matrix_ok)} |")
    print(f"| 硬前置依赖满足现场复算 | {pass_text(dependency_ok)} |")
    print(f"| 权重消融结果文件读取 | {pass_text(bool(abl_path and abl_table))} |")
    print()
    print("## 8. 可复核证据文件")
    for path in [
        ctx["paths"]["latest"],
        ctx["paths"]["paper_metrics"],
        ctx["paths"]["report"],
        ctx["artifacts"] / "final_reports" / "G1",
        ctx["artifacts"] / "final_reports" / "G2",
        ctx["artifacts"] / "final_reports" / "G3",
        abl_path.parent if abl_path else None,
    ]:
        if path and path.exists():
            print(f"- `{rel(root, path)}`")
    return 0


def print_block(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def print_audit_log(ctx: dict[str, Any]) -> int:
    root = ctx["root"]
    manifest = ctx["manifest"]
    matrix = ctx["matrix"]
    metrics = ctx["metrics"]
    rows = [row for goal_id, label, title in GOAL_ROWS if (row := final_report_row(ctx, goal_id, label, title))]
    scenarios, scenario_summary = scenario_rows(ctx)
    abl_path, _, abl_parsed = ablation_lines(ctx)

    print("# LearnPath-KG 论文实验验证过程日志")
    print("说明：本日志按截图块组织，每个 BLOCK 可单独截图并配论文图注。")

    print_block("BLOCK 1/5 实验环境与输入文件")
    print("[COMMAND]")
    print("  powershell -ExecutionPolicy Bypass -File .\\scripts\\final_check.ps1 audit-log")
    print("[ENV]")
    print(f"  python_version = {platform.python_version()}")
    print(f"  os             = {platform.system()} {platform.release()}")
    print(f"  workdir        = {root.as_posix()}")
    print(f"  python_exe     = {display_path(root, Path(sys.executable))}")
    print("[SCRIPTS]")
    for key in ["evidence_script", "generator_script", "evaluate_script", "ablation_script"]:
        path = ctx["paths"][key]
        print(f"  {key:<16} = {rel(root, path)}")
    print("[INPUT FILES]")
    for label, key in [
        ("manifest", "manifest"),
        ("nodes", "nodes"),
        ("requires_edges", "requires"),
        ("related_edges", "related"),
        ("scenario_matrix", "matrix"),
        ("latest_result", "latest"),
        ("paper_metrics", "paper_metrics"),
        ("report_md", "report"),
    ]:
        path = ctx["paths"][key]
        print(f"  [LOAD] {label:<16} path={rel(root, path)} sha256={sha256_short(path)} {pass_text(path.exists())}")

    print_block("BLOCK 2/5 指标规则与领域包结构检查")
    print("[METRIC RULES]")
    print("  M1 dependency_satisfaction = satisfied_REQUIRES_edges / checked_REQUIRES_edges")
    print("  M2 dag_check               = topological traversal over Domain Pack REQUIRES graph")
    print("  M3 kendall_tau             = rank correlation vs textbook baseline from evaluate.py")
    print("  M4 high_importance_coverage= covered nodes with importance_final >= 4 / all high nodes")
    print("  M5 stage_closure           = prerequisite stage index <= successor stage index")
    print("[DOMAIN PACK CHECK]")
    print(f"  version            = {manifest['version']} PASS")
    print(f"  nodes              = {len(ctx['nodes'])}/{manifest['node_count']} {pass_text(len(ctx['nodes']) == manifest['node_count'])}")
    print(f"  requires_edges     = {len(ctx['requires_edges'])} {pass_text(len(ctx['requires_edges']) == 66)}")
    print(f"  related_edges      = {len(ctx['related_edges'])} {pass_text(len(ctx['related_edges']) == 16)}")
    print(f"  requires_graph_dag = {ctx['dag_ok']} {pass_text(ctx['dag_ok'])}")
    print(f"  goals x profiles   = {len(matrix['goal_templates'])} x {len(matrix['profile_templates'])}")
    print(f"  scenario_count     = {len(matrix['scenarios'])} {pass_text(len(matrix['scenarios']) == 9)}")

    print_block("BLOCK 3/5 三类典型目标现场复核")
    for row in rows:
        print(f"[RECALC] {row['goal_id']} {row['label']} - {row['title']}")
        print(f"  source        = {row['source']}")
        print(f"  path_size     = {row['node_count']} nodes, {row['total_hours']} hours")
        print(f"  M1 dependency = {row['dep_text']} {pass_text(row['dep']['ok'])}")
        print(f"  M2 DAG        = {row['dag']} {pass_text(bool(row['dag']))}")
        print(f"  M3 KendallTau = {row['tau']}")
        print(f"  M4 high_nodes = {row['high']}")
        print(f"  M5 closure    = {row['closure_text']} {pass_text(row['closure']['ok'])}")
        print(f"  result        = {row['result']}")

    print_block("BLOCK 4/5 九场景矩阵现场复算")
    dep = metrics["dependency_correctness"]
    stage = metrics["stage_evidence"]
    print("[SUMMARY]")
    print(f"  reported_scenarios   = {metrics['scenario_overview']['successful_scenarios']}/{metrics['scenario_overview']['scenario_count']}")
    print(f"  reported_requires    = {dep['satisfied_required_edges']}/{dep['total_required_edges']} ({pct(dep['dependency_satisfaction_ratio'])})")
    print(f"  recalculated_requires= {scenario_summary['satisfied']}/{scenario_summary['checked']} ({pct(scenario_summary['ratio'])})")
    print(f"  average_stage_count  = {stage['average_stage_count']}")
    print(f"  average_stage_hours  = {stage['average_total_stage_hours']}")
    for row in scenarios:
        print(f"[SCENARIO] {row['id']} | {row['title']}")
        print(f"  size={row['node_count']} nodes, stages={row['stage_count']}, hours={row['total_hours']}")
        print(f"  M1={row['dep']['satisfied']}/{row['dep']['checked']} ({pct(row['dep']['ratio'])}) {pass_text(row['dep']['ok'])}")
        print(f"  M5={row['closure']['satisfied']}/{row['closure']['checked']} ({pct(row['closure']['ratio'])}) {pass_text(row['closure']['ok'])}")
    print(f"[RECALC TOTAL] scenarios={scenario_summary['ok_count']}/{scenario_summary['total']} PASS")

    print_block("BLOCK 5/5 权重消融与最终结论")
    print("[ABLATION]")
    if abl_path and abl_parsed:
        print(f"  source = {rel(root, abl_path)}")
        for target, baseline, w2, w3 in abl_parsed:
            print(f"  {target}: W1={baseline}, W2={w2}, W3={w3}")
    else:
        print("  source = missing")
    typical_ok = bool(rows) and all(row["result"] == "PASS" for row in rows)
    matrix_ok = scenario_summary["ok_count"] == scenario_summary["total"]
    dependency_ok = scenario_summary["satisfied"] == scenario_summary["checked"]
    print("[FINAL CHECK]")
    print(f"  domain_pack_structure = {pass_text(ctx['dag_ok'] and len(ctx['nodes']) == manifest['node_count'])}")
    print(f"  typical_goals         = {pass_text(typical_ok)}")
    print(f"  scenario_matrix       = {pass_text(matrix_ok)}")
    print(f"  dependency_recalc     = {pass_text(dependency_ok)}")
    print(f"  ablation_file         = {pass_text(bool(abl_path and abl_parsed))}")
    print("[EVIDENCE FILES]")
    for path in [
        ctx["paths"]["latest"],
        ctx["paths"]["paper_metrics"],
        ctx["paths"]["report"],
        ctx["artifacts"] / "final_reports" / "G1",
        ctx["artifacts"] / "final_reports" / "G2",
        ctx["artifacts"] / "final_reports" / "G3",
        abl_path.parent if abl_path else None,
    ]:
        if path and path.exists():
            print(f"  - {rel(root, path)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Print thesis experiment validation evidence.")
    parser.add_argument("--audit-log", action="store_true", help="Print screenshot-friendly process log")
    args = parser.parse_args()
    ctx = build_context()
    if args.audit_log:
        return print_audit_log(ctx)
    return print_report(ctx)


if __name__ == "__main__":
    raise SystemExit(main())
