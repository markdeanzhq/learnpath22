"""evaluate.py 脚本单元测试"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import evaluate


@pytest.fixture(scope="module")
def pack():
    from app.services.domain_pack_service import DomainPackService
    p = DomainPackService()
    p.load()
    return p


@pytest.fixture(scope="module")
def sample_plan(pack):
    from app.services.planner_service import plan_with_profile
    return plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type=None,
        profile=evaluate.PROFILE_PRESETS["beginner"],
        pack=pack,
    )


def test_kendall_tau_identical():
    tau, n = evaluate.kendall_tau(["a", "b", "c"], ["a", "b", "c"])
    assert tau == 1.0
    assert n == 3


def test_kendall_tau_reversed():
    tau, n = evaluate.kendall_tau(["a", "b", "c"], ["c", "b", "a"])
    assert tau == -1.0
    assert n == 3


def test_kendall_tau_partial_overlap():
    tau, n = evaluate.kendall_tau(["x", "a", "y", "b"], ["a", "b", "z"])
    assert n == 2
    assert tau == 1.0


def test_kendall_tau_no_overlap():
    tau, n = evaluate.kendall_tau(["a"], ["b"])
    assert tau == 0.0
    assert n == 0


def test_metric_dependency_satisfaction_ok(sample_plan, pack):
    result = evaluate.metric_dependency_satisfaction(
        sample_plan["ordered_ids"], pack.requires_edges
    )
    assert result["satisfaction_rate"] == 1.0
    assert result["violations"] == []
    assert result["checked_edges"] > 0


def test_metric_dependency_satisfaction_detects_violation(pack):
    reversed_ids = list(reversed([e["source"] for e in pack.requires_edges[:2]] + [
        pack.requires_edges[0]["target"]
    ]))
    fake_order = reversed_ids + [
        nid for nid in pack.nodes_by_id if nid not in reversed_ids
    ]
    result = evaluate.metric_dependency_satisfaction(
        fake_order, pack.requires_edges
    )
    assert result["satisfaction_rate"] < 1.0


def test_metric_cycle_check_dag(pack):
    result = evaluate.metric_cycle_check(pack)
    assert result["is_dag"] is True
    assert result["error"] is None


def test_metric_type_coverage_bounds(sample_plan, pack):
    result = evaluate.metric_type_coverage(
        sample_plan["ordered_ids"], pack.nodes_by_id
    )
    for info in result["per_group"].values():
        assert 0.0 <= info["rate"] <= 1.0
    assert 0.0 <= result["backbone_rate"] <= 1.0


def test_metric_stage_closure_ok(sample_plan, pack):
    result = evaluate.metric_stage_closure(
        sample_plan["stage_plan"], pack.requires_edges
    )
    assert 0.0 <= result["closure_completeness_rate"] <= 1.0
    assert result["closure_completeness_rate"] == 1.0


def test_metric_kendall_bounds(sample_plan):
    baseline_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "baselines" / "zhouzhihua_index.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["sequence"]
    result = evaluate.metric_kendall_vs_baseline(sample_plan["ordered_ids"], baseline)
    assert -1.0 <= result["tau"] <= 1.0
    assert result["common_nodes"] >= 0


def test_cli_end_to_end(tmp_path):
    exit_code = evaluate.main([
        "--goal", "我想系统学习机器学习基础",
        "--profile", "beginner",
        "--out", str(tmp_path),
    ])
    assert exit_code == 0
    reports = list(tmp_path.iterdir())
    assert len(reports) == 1
    out_dir = reports[0]
    assert (out_dir / "metrics.json").exists()
    assert (out_dir / "summary.md").exists()
    assert (out_dir / "raw_path.json").exists()
    metrics = json.loads((out_dir / "metrics.json").read_text(encoding="utf-8"))
    assert "M1_dependency_satisfaction" in metrics["metrics"]
    assert metrics["metrics"]["M1_dependency_satisfaction"]["satisfaction_rate"] == 1.0


def test_g1_g2_g3_hard_metrics(pack):
    """任务 6.1: 对 G1/G2/G3 三个目标，断言 M1/M2/M5 均为 1.0"""
    goals = [
        {"id": "G1", "text": "我想系统学习机器学习基础"},
        {"id": "G2", "text": "理解梯度下降"},
        {"id": "G3", "text": "我想搞懂逻辑回归为什么能做分类"},
    ]
    profile = evaluate.PROFILE_PRESETS["beginner"]

    for goal in goals:
        plan = evaluate.plan_with_profile(
            goal_text=goal["text"],
            goal_type=None,
            profile=profile,
            pack=pack,
        )

        # M1: 依赖满足率
        m1 = evaluate.metric_dependency_satisfaction(
            plan["ordered_ids"], pack.requires_edges
        )
        assert m1["satisfaction_rate"] == 1.0, \
            f"{goal['id']} M1 依赖满足率不为 1.0: {m1['satisfaction_rate']}"

        # M2: DAG 校验
        m2 = evaluate.metric_cycle_check(pack)
        assert m2["is_dag"] is True, f"{goal['id']} M2 DAG 校验失败"

        # M5: 阶段闭包完整性
        m5 = evaluate.metric_stage_closure(plan["stage_plan"], pack.requires_edges)
        assert m5["closure_completeness_rate"] == 1.0, \
            f"{goal['id']} M5 阶段闭包完整性不为 1.0: {m5['closure_completeness_rate']}"


def test_pack_and_baseline_match_v130_47_nodes(pack):
    baseline_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "baselines" / "zhouzhihua_index.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert pack.manifest["version"] == "1.3.0"
    assert len(pack.nodes) == 47
    assert pack.manifest["node_count"] == 47
    assert "ml_b03" not in pack.nodes_by_id
    assert "ml_b03" not in baseline["sequence"]


def test_m3_positive(pack):
    """任务 6.2: 对 G1/G2/G3 三个目标，断言 M3 Kendall τ > 0"""
    goals = [
        {"id": "G1", "text": "我想系统学习机器学习基础"},
        {"id": "G2", "text": "理解梯度下降"},
        {"id": "G3", "text": "我想搞懂逻辑回归为什么能做分类"},
    ]
    profile = evaluate.PROFILE_PRESETS["beginner"]
    baseline_path = (
        Path(__file__).resolve().parent.parent / "scripts" / "baselines" / "zhouzhihua_index.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))["sequence"]

    for goal in goals:
        plan = evaluate.plan_with_profile(
            goal_text=goal["text"],
            goal_type=None,
            profile=profile,
            pack=pack,
        )

        m3 = evaluate.metric_kendall_vs_baseline(plan["ordered_ids"], baseline)
        assert m3["tau"] > 0, \
            f"{goal['id']} M3 Kendall τ 不为正值: {m3['tau']}"
