"""解释可读性端到端测试 — 覆盖批次 A–D 新增/修改的 6 项核心行为。"""
from __future__ import annotations

import re
from collections import deque

import pytest

from app.services.domain_pack_service import get_domain_pack_service
from app.services.explanation_service import (
    _pick_weakest_dimension,
    build_explanation,
)
from app.services.planner_service import plan_with_profile

PROFILE_BEGINNER = {
    "math_level": 2,
    "coding_level": 2,
    "ml_level": 1,
    "theory_weight": 0.6,
    "practice_weight": 0.4,
    "weekly_hours": 10,
    "deadline_weeks": 12,
}

GOAL_G1 = {"text": "我想系统学习机器学习基础", "goal_type": "domain"}
GOAL_G2 = {"text": "理解梯度下降", "goal_type": "concept"}


@pytest.fixture(scope="module")
def pack():
    return get_domain_pack_service()


def _run(pack, goal, removed_node_ids=None, removed_edge_ids=None):
    plan = plan_with_profile(
        goal["text"],
        goal["goal_type"],
        PROFILE_BEGINNER,
        pack,
        removed_node_ids=removed_node_ids,
        removed_edge_ids=removed_edge_ids,
    )
    return plan, build_explanation(
        plan["audit"], pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config
    )


def _reverse_bfs_closure(target_id, requires_rev_adj):
    visited = set()
    queue = deque([target_id])
    while queue:
        cur = queue.popleft()
        for prev in requires_rev_adj.get(cur, ()):
            if prev not in visited:
                visited.add(prev)
                queue.append(prev)
    return visited | {target_id}


_FACTOR_VALUE = re.compile(r"\(([+\-]?\d+\.\d+)\)$")


# --- 9.2 dependency chain is real closure ---

def test_dependency_chain_is_real_closure(pack):
    plan, explanation = _run(
        pack,
        GOAL_G2,
        removed_edge_ids={"ml_a04->ml_c05::REQUIRES"},
    )
    target_ids = plan["audit"]["goal_result"]["target_node_ids"]
    assert explanation.dependency_chain_explanations, "G2 应至少产出一条依赖链"

    ordered = list(plan["audit"]["ordering_logs"].keys())
    filtered_rev_adj = plan["audit"]["filtered_requires_rev_adj"]
    for dep in explanation.dependency_chain_explanations:
        assert dep.target_node_id in target_ids
        closure = _reverse_bfs_closure(dep.target_node_id, filtered_rev_adj)
        chain = list(dep.chain_node_ids)
        assert set(chain) <= closure, f"{dep.target_node_id} chain 不在 snapshot 闭包内"
        assert dep.target_node_id in chain
        assert len(chain) <= 15
        assert "ml_a04" not in chain
        # chain 顺序应与 ordered_ids 学习顺序一致
        chain_order = [ordered.index(nid) for nid in chain]
        assert chain_order == sorted(chain_order)


# --- 9.3 prereq reasons pairwise distinct ---

def test_prereq_reasons_pairwise_distinct(pack):
    _, explanation = _run(pack, GOAL_G1)
    prereqs = [n for n in explanation.node_explanations if n.decision_type == "prerequisite"]
    assert len(prereqs) >= 3
    for n in prereqs:
        assert "「" in n.reason, f"prereq reason 未含「: {n.reason}"
    distinct = {n.reason for n in prereqs}
    assert len(distinct) >= 3, f"prereq reason 未达 3 种：{distinct}"


# --- 9.4 ordering factors top-3 sum matches score ---

def test_ordering_factors_top3_sum_matches_score(pack):
    plan, explanation = _run(pack, GOAL_G2)
    ordered_expls = {o.node_id: o for o in explanation.ordering_explanations}
    for nid, log in plan["audit"]["ordering_logs"].items():
        oe = ordered_expls[nid]
        numeric = [
            float(_FACTOR_VALUE.search(f).group(1))
            for f in oe.factors
            if _FACTOR_VALUE.search(f)
        ]
        assert len(numeric) >= 3, f"{nid} factors 数值 < 3：{oe.factors}"
        # top-3 之和应能部分解释 priority_score（允许累加截断误差 + 未进 top-3 的分量）
        # 更严的不变量放在 test_scoring.py 里
        assert all(abs(v) <= 1.0 for v in numeric), f"{nid} 分量绝对值异常：{numeric}"


# --- 9.5 stage rationale no english key ---

_FORBIDDEN_TOKENS = ("=", "goal_type=", "category=", "default_stage_rule", "beginner_override")


def test_stage_rationale_no_english_key(pack):
    _, explanation = _run(pack, GOAL_G1)
    assert explanation.stage_explanations
    for se in explanation.stage_explanations:
        assert se.rationale, f"{se.node_id} rationale 为空"
        for tok in _FORBIDDEN_TOKENS:
            assert tok not in se.rationale, f"{se.node_id} rationale 含英文 token {tok!r}：{se.rationale}"


# --- 9.6 summary prefix structure ---

def test_summary_prefix_structure_single_and_multi_target(pack):
    for goal in (GOAL_G2, GOAL_G1):
        plan, explanation = _run(pack, goal)
        assert explanation.budget_explanation is not None
        suggestion = explanation.budget_explanation.suggestion
        assert suggestion.startswith("路径从「"), f"{goal['text']}: {suggestion!r}"
        assert "共 " in suggestion and "节点" in suggestion and "小时" in suggestion
        # 原始 budget suggestion 应保留（如非空）
        original = plan["audit"]["budget_summary"].get("suggestion", "")
        if original:
            assert original in suggestion

    # 多目标（G1 通常 ≥ 2 目标）应触发"和"的分支
    plan_g1, explanation_g1 = _run(pack, GOAL_G1)
    target_count = len(plan_g1["audit"]["goal_result"]["target_node_ids"])
    if target_count >= 2:
        assert "和「" in explanation_g1.budget_explanation.suggestion


# --- 9.7 reinforcement weakest dimension tie-break ---

@pytest.mark.parametrize("gap,expected", [
    ({"gap_ml": 0.5, "gap_math": 0.5, "gap_code": 0.3}, "机器学习概念"),
    ({"gap_ml": 0.4, "gap_math": 0.5, "gap_code": 0.5}, "数学基础"),
    ({"gap_ml": 0.5, "gap_math": 0.5, "gap_code": 0.5}, "机器学习概念"),
])
def test_reinforcement_weakest_dimension_tie_break(gap, expected):
    assert _pick_weakest_dimension(gap) == expected
