"""多因子评分：差距、偏好匹配、补强、优先级、目标相关度"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any


def calc_gap(
    node: dict[str, Any],
    profile: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> dict[str, float]:
    gw = (config or {}).get("gap_weights", {"ml": 0.40, "math": 0.35, "coding": 0.25})
    gap_math = max(0, node["req_math"] - profile["math_level"]) / 4
    gap_code = max(0, node["req_coding"] - profile["coding_level"]) / 4
    gap_ml = max(0, node["req_ml"] - profile["ml_level"]) / 4

    gap_total = gw["ml"] * gap_ml + gw["math"] * gap_math + gw["coding"] * gap_code
    return {
        "gap_math": round(gap_math, 3),
        "gap_code": round(gap_code, 3),
        "gap_ml": round(gap_ml, 3),
        "gap_total": round(gap_total, 3),
    }


def calc_preference_fit(node: dict[str, Any], profile: dict[str, Any]) -> float:
    theory = profile.get("theory_weight", 0.5)
    practice = 1.0 - theory
    fit = node["theory_weight"] * theory + node["practice_weight"] * practice
    return round(fit, 3)


def calc_reinforce_score(
    node: dict[str, Any],
    profile: dict[str, Any],
    gap: dict[str, float],
    config: dict[str, Any] | None = None,
) -> float:
    rw = (config or {}).get("reinforce_weights", {
        "gap_total": 0.45, "foundation_bonus": 0.20, "bridge_value": 0.15,
        "main_path_bonus": 0.10, "beginner_bonus": 0.10,
    })
    beginner_bonus = 1 if profile.get("ml_level", 1) <= 1 else 0
    foundation_bonus = 1 if node.get("is_foundation", False) else 0
    main_path_bonus = 1 if node.get("is_main_path", False) else 0

    score = (
        rw["gap_total"] * gap["gap_total"]
        + rw["foundation_bonus"] * foundation_bonus
        + rw["bridge_value"] * node.get("bridge_value", 0)
        + rw["main_path_bonus"] * main_path_bonus
        + rw["beginner_bonus"] * beginner_bonus
    )
    return round(score, 3)


def should_reinforce(
    node: dict[str, Any],
    profile: dict[str, Any],
    config: dict[str, Any] | None = None,
) -> tuple[bool, dict[str, float], float]:
    threshold = (config or {}).get("reinforce_threshold", 0.45)
    gap = calc_gap(node, profile, config)
    score = calc_reinforce_score(node, profile, gap, config)
    return score >= threshold, gap, score


DEFAULT_PRIORITY_WEIGHTS: dict[str, float] = {
    "importance": 0.28,
    "goal_relevance": 0.22,
    "preference_fit": 0.15,
    "main_path_bonus": 0.10,
    "bridge_value": 0.10,
    "difficulty_penalty": -0.10,
    "gap_penalty": -0.10,
    "time_cost_penalty": -0.05,
}

DEFAULT_MODE_ADJUSTMENTS: dict[str, dict[str, float]] = {
    "steady": {"difficulty_reduction": 0.08, "foundation_bonus": 0.05},
    "efficient": {"goal_relevance_bonus": 0.08, "time_saving_bonus": 0.05},
    "practice": {"practice_weight_bonus": 0.08, "practice_flag_bonus": 0.05},
}


def decompose_priority_score(
    node: dict[str, Any],
    profile: dict[str, Any],
    gap: dict[str, float],
    goal_relevance: float,
    mode: str,
    weights: dict[str, float],
    mode_adjustments: dict[str, dict[str, float]],
) -> dict[str, float]:
    """将优先级评分拆为每个 signed contribution；sum(values) ≈ calc_priority_score 结果。"""
    importance_norm = node["importance_final"] / 5
    difficulty_norm = node["difficulty_final"] / 5
    time_cost_norm = min(node["estimated_hours"] / 5, 1.0)
    preference_fit = calc_preference_fit(node, profile)
    main_path_bonus = 1 if node.get("is_main_path", False) else 0
    bridge_value = node.get("bridge_value", 0)

    contribs: dict[str, float] = {
        "importance": weights["importance"] * importance_norm,
        "goal_relevance": weights["goal_relevance"] * goal_relevance,
        "preference_fit": weights["preference_fit"] * preference_fit,
        "main_path_bonus": weights["main_path_bonus"] * main_path_bonus,
        "bridge_value": weights["bridge_value"] * bridge_value,
        "difficulty_penalty": weights["difficulty_penalty"] * difficulty_norm,
        "gap_penalty": weights["gap_penalty"] * gap["gap_total"],
        "time_cost_penalty": weights["time_cost_penalty"] * time_cost_norm,
    }

    if mode == "steady" and "steady" in mode_adjustments:
        adj = mode_adjustments["steady"]
        contribs["mode.steady.difficulty_reduction"] = adj["difficulty_reduction"] * (1 - difficulty_norm)
        contribs["mode.steady.foundation_bonus"] = adj["foundation_bonus"] * int(node.get("is_foundation", False))
    elif mode == "efficient" and "efficient" in mode_adjustments:
        adj = mode_adjustments["efficient"]
        contribs["mode.efficient.goal_relevance_bonus"] = adj["goal_relevance_bonus"] * goal_relevance
        contribs["mode.efficient.time_saving_bonus"] = adj["time_saving_bonus"] * (1 - time_cost_norm)
    elif mode == "practice" and "practice" in mode_adjustments:
        adj = mode_adjustments["practice"]
        contribs["mode.practice.practice_weight_bonus"] = adj["practice_weight_bonus"] * node.get("practice_weight", 0)
        contribs["mode.practice.practice_flag_bonus"] = adj["practice_flag_bonus"] * int(node.get("is_practice", False))

    return contribs


def calc_priority_score(
    node: dict[str, Any],
    profile: dict[str, Any],
    gap: dict[str, float],
    goal_relevance: float,
    mode: str,
    config: dict[str, Any] | None = None,
) -> float:
    pw = (config or {}).get("priority_weights", DEFAULT_PRIORITY_WEIGHTS)
    ma = (config or {}).get("mode_adjustments", DEFAULT_MODE_ADJUSTMENTS)

    contribs = decompose_priority_score(node, profile, gap, goal_relevance, mode, pw, ma)
    return round(sum(contribs.values()), 3)


def compute_goal_relevance(
    closure_ids: list[str],
    target_node_ids: list[str],
    requires_adj: dict[str, list[str]],
) -> dict[str, float]:
    """反向 BFS 估计每个节点离目标的距离，距离越近 relevance 越高。"""
    closure_set = set(closure_ids)
    reverse_local: dict[str, list[str]] = defaultdict(list)

    for src, tgts in requires_adj.items():
        if src not in closure_set:
            continue
        for tgt in tgts:
            if tgt in closure_set:
                reverse_local[tgt].append(src)

    dist: dict[str, float] = {nid: float("inf") for nid in closure_ids}
    queue: deque[str] = deque()

    for tgt in target_node_ids:
        if tgt in dist:
            dist[tgt] = 0
            queue.append(tgt)

    while queue:
        cur = queue.popleft()
        for prev in reverse_local.get(cur, []):
            if dist[prev] > dist[cur] + 1:
                dist[prev] = dist[cur] + 1
                queue.append(prev)

    finite = [d for d in dist.values() if d != float("inf")]
    max_dist = max(finite, default=1)

    relevance: dict[str, float] = {}
    for nid, d in dist.items():
        if d == float("inf"):
            relevance[nid] = 0.0
        else:
            relevance[nid] = round(1 - d / (max_dist + 1), 3)

    return relevance


def select_profile_reinforcements(
    nodes_by_id: dict[str, dict[str, Any]],
    target_node_ids: list[str],
    closure_ids: list[str],
    profile: dict[str, Any],
    config: dict[str, Any] | None = None,
    max_count: int | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """从基础节点中挑选画像补强节点。"""
    if max_count is None:
        max_count = (config or {}).get("reinforce_max_count", 6)

    selected: list[str] = []
    logs: dict[str, Any] = {}

    existing = set(closure_ids) | set(target_node_ids)
    candidate_ids = sorted(
        node_id
        for node_id, node in nodes_by_id.items()
        if node.get("is_foundation", False) and node_id not in existing
    )

    scored: list[tuple[float, str, dict[str, float]]] = []
    for node_id in candidate_ids:
        node = nodes_by_id[node_id]
        ok, gap, reinforce_score = should_reinforce(node, profile, config)
        if ok:
            scored.append((reinforce_score, node_id, gap))

    scored.sort(key=lambda item: (-item[0], item[1]))

    for reinforce_score, node_id, gap in scored[:max_count]:
        selected.append(node_id)
        logs[node_id] = {
            "decision_type": "reinforced",
            "gap": gap,
            "reinforce_score": reinforce_score,
            "reasons": ["profile_reinforcement", "foundation_support"],
        }

    return selected, logs
