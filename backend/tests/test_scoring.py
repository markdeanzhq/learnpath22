"""优先级评分 decomposer 与 calc_priority_score 一致性测试"""
import random

from app.planner.scoring import (
    DEFAULT_MODE_ADJUSTMENTS,
    DEFAULT_PRIORITY_WEIGHTS,
    calc_gap,
    calc_preference_fit,
    calc_priority_score,
    calc_reinforce_score,
    decompose_priority_score,
    decompose_reinforce_score,
)
from app.services.domain_pack_service import get_domain_pack_service


PROFILE = {
    "math_level": 2,
    "coding_level": 2,
    "ml_level": 1,
    "theory_weight": 0.6,
    "practice_weight": 0.4,
}


def _reference_priority_score(node, profile, gap, goal_relevance, mode):
    """独立硬编码实现，作为 oracle 防止 decomposer/calc 共同跑偏（对照 git HEAD 前的 calc_priority_score）。"""
    pw = DEFAULT_PRIORITY_WEIGHTS
    ma = DEFAULT_MODE_ADJUSTMENTS
    importance_norm = node["importance_final"] / 5
    difficulty_norm = node["difficulty_final"] / 5
    time_cost_norm = min(node["estimated_hours"] / 5, 1.0)
    preference_fit = calc_preference_fit(node, profile)
    main_path_bonus = 1 if node.get("is_main_path", False) else 0
    bridge_value = node.get("bridge_value", 0)

    mode_adjust = 0.0
    if mode == "steady":
        adj = ma["steady"]
        mode_adjust = adj["difficulty_reduction"] * (1 - difficulty_norm) + adj[
            "foundation_bonus"
        ] * int(node.get("is_foundation", False))
    elif mode == "efficient":
        adj = ma["efficient"]
        mode_adjust = adj["goal_relevance_bonus"] * goal_relevance + adj[
            "time_saving_bonus"
        ] * (1 - time_cost_norm)
    elif mode == "practice":
        adj = ma["practice"]
        mode_adjust = adj["practice_weight_bonus"] * node.get("practice_weight", 0) + adj[
            "practice_flag_bonus"
        ] * int(node.get("is_practice", False))

    score = (
        pw["importance"] * importance_norm
        + pw["goal_relevance"] * goal_relevance
        + pw["preference_fit"] * preference_fit
        + pw["main_path_bonus"] * main_path_bonus
        + pw["bridge_value"] * bridge_value
        + pw["difficulty_penalty"] * difficulty_norm
        + pw["gap_penalty"] * gap["gap_total"]
        + pw["time_cost_penalty"] * time_cost_norm
        + mode_adjust
    )
    return round(score, 3)


def test_decompose_sums_to_priority_score():
    pack = get_domain_pack_service()
    nodes = list(pack.nodes_by_id.values())
    random.seed(42)
    sample = random.sample(nodes, 5)

    for mode in ("steady", "efficient", "practice"):
        for node in sample:
            gap = calc_gap(node, PROFILE)
            goal_relevance = 0.7

            contribs = decompose_priority_score(
                node=node,
                profile=PROFILE,
                gap=gap,
                goal_relevance=goal_relevance,
                mode=mode,
                weights=DEFAULT_PRIORITY_WEIGHTS,
                mode_adjustments=DEFAULT_MODE_ADJUSTMENTS,
            )
            summed = round(sum(contribs.values()), 3)
            score = calc_priority_score(
                node=node,
                profile=PROFILE,
                gap=gap,
                goal_relevance=goal_relevance,
                mode=mode,
            )
            oracle = _reference_priority_score(node, PROFILE, gap, goal_relevance, mode)

            assert abs(summed - score) < 1e-6, (
                f"decomposer sum vs calc_priority_score mismatch: "
                f"node={node['id']} mode={mode} sum={summed} score={score}"
            )
            assert abs(score - oracle) < 1e-6, (
                f"calc_priority_score vs oracle reference mismatch (decomposer may have drifted): "
                f"node={node['id']} mode={mode} score={score} oracle={oracle}"
            )


def test_decompose_sums_to_reinforce_score():
    pack = get_domain_pack_service()
    node = pack.nodes_by_id["ml_a01"]
    gap = calc_gap(node, PROFILE)

    contribs = decompose_reinforce_score(node, PROFILE, gap, pack.scoring_config)
    summed = round(sum(contribs.values()), 3)
    score = calc_reinforce_score(node, PROFILE, gap, pack.scoring_config)

    assert summed == score
    assert contribs["foundation"] > 0
    assert contribs["bridge"] > 0
    assert contribs["main_path"] > 0
