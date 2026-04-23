"""ablation.py 脚本测试"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import ablation, evaluate


def test_apply_weight_override_merges_keys():
    base = {"priority_weights": {"importance": 0.28, "goal_relevance": 0.22}}
    out = ablation.apply_weight_override(
        base, {"priority_weights": {"importance": 0.40}}
    )
    assert out["priority_weights"]["importance"] == 0.40
    assert out["priority_weights"]["goal_relevance"] == 0.22
    assert base["priority_weights"]["importance"] == 0.28  # 不可变


def test_compute_diff_identical():
    d = ablation.compute_diff(["a", "b", "c"], ["a", "b", "c"])
    assert d["kendall_tau"] == 1.0
    assert d["added_nodes"] == []
    assert d["removed_nodes"] == []
    assert d["top_position_shifts"] == []


def test_compute_diff_swap():
    d = ablation.compute_diff(["a", "b", "c"], ["b", "a", "c"])
    assert d["kendall_tau"] < 1.0
    assert {s["node_id"] for s in d["top_position_shifts"]} == {"a", "b"}


def test_compute_diff_add_remove():
    d = ablation.compute_diff(["a", "b"], ["a", "c"])
    assert d["added_nodes"] == ["c"]
    assert d["removed_nodes"] == ["b"]


def test_cli_end_to_end(tmp_path):
    exit_code = ablation.main([
        "--profile", "beginner",
        "--out", str(tmp_path),
    ])
    assert exit_code == 0
    reports = list(tmp_path.iterdir())
    assert len(reports) == 1
    out_dir = reports[0]
    assert (out_dir / "matrix.json").exists()
    assert (out_dir / "diff.md").exists()
    assert (out_dir / "kendall.md").exists()

    matrix = json.loads((out_dir / "matrix.json").read_text(encoding="utf-8"))
    assert set(matrix["results"]) == {"G1", "G2", "G3"}
    for goal_id, per_goal in matrix["results"].items():
        assert set(per_goal) == {"W1", "W2", "W3"}
        for w_id, result in per_goal.items():
            assert result["node_count"] >= len(result["target_node_ids"]), (
                f"{goal_id}/{w_id} 路径长度应 ≥ 目标节点数（PBT invariant）"
            )

    for goal_id, diff_map in matrix["diffs"].items():
        for w_id, diff in diff_map.items():
            assert -1.0 <= diff["kendall_tau"] <= 1.0


def test_all_variants_dependency_satisfied(tmp_path):
    """PBT: 所有权重变体下路径依赖满足率应保持 100%"""
    from app.services.domain_pack_service import DomainPackService
    pack = DomainPackService()
    pack.load()

    matrix = ablation.run_experiment(evaluate.PROFILE_PRESETS["beginner"])
    for goal_id, per_goal in matrix["results"].items():
        for w_id, result in per_goal.items():
            dep = evaluate.metric_dependency_satisfaction(
                result["ordered_ids"], pack.requires_edges
            )
            assert dep["satisfaction_rate"] == 1.0, (
                f"{goal_id}/{w_id} 依赖满足率 {dep['satisfaction_rate']} < 1.0"
            )


def test_kendall_tau_floor():
    """任务 7.1: 对 6 个 non-baseline 单元格断言 v1.1.0 接受底线 kendall_tau >= 0.75（目标仍尽量 >= 0.85）"""
    matrix = ablation.run_experiment(evaluate.PROFILE_PRESETS["beginner"])

    goals = ["G1", "G2", "G3"]
    non_baseline_weights = ["W2", "W3"]
    accepted_floor = 0.75

    for goal_id in goals:
        for w_id in non_baseline_weights:
            diff = matrix["diffs"][goal_id][w_id]
            assert diff["kendall_tau"] >= accepted_floor, (
                f"{goal_id}/{w_id} Kendall τ {diff['kendall_tau']} < {accepted_floor}"
            )


def test_baseline_kendall_tau_perfect():
    """任务 7.2: 对 3 个目标的 W1 baseline，断言 kendall_tau == 1.0"""
    matrix = ablation.run_experiment(evaluate.PROFILE_PRESETS["beginner"])

    goals = ["G1", "G2", "G3"]

    for goal_id in goals:
        # W1 是 baseline，与自身比较应为 1.0
        # 但 diffs 只包含 W2/W3（见 ablation.py:194-196）
        # 所以这个测试需要修改：W1 baseline 与自身的 tau 恒为 1.0（无需计算）
        baseline_result = matrix["results"][goal_id]["W1"]
        # 验证 baseline 存在即可，tau=1.0 是定义性质
        assert baseline_result is not None, f"{goal_id}/W1 baseline 不存在"
        # 如果需要显式验证，可以手动计算：
        tau, _ = ablation.kendall_tau(
            baseline_result["ordered_ids"],
            baseline_result["ordered_ids"]
        )
        assert tau == 1.0, f"{goal_id}/W1 自比较 Kendall τ {tau} != 1.0"
