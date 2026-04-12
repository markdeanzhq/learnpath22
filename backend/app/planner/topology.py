"""拓扑排序（带画像感知优先级）"""
from __future__ import annotations

from typing import Any

from app.planner.scoring import calc_gap, calc_priority_score


def topo_sort_with_profile_priority(
    sub_adj: dict[str, list[str]],
    indegree: dict[str, int],
    nodes_by_id: dict[str, dict[str, Any]],
    profile: dict[str, Any],
    goal_relevance_map: dict[str, float],
    mode: str,
    config: dict[str, Any] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """画像感知的拓扑排序：每轮从零入度节点中选优先级最高的。"""
    ready = [nid for nid, deg in indegree.items() if deg == 0]
    ordered: list[str] = []
    logs: dict[str, Any] = {}
    indegree = dict(indegree)  # 不改原始

    while ready:
        scored_ready: list[tuple[float, str, dict[str, float]]] = []
        for nid in ready:
            node = nodes_by_id[nid]
            gap = calc_gap(node, profile, config)
            score = calc_priority_score(
                node=node,
                profile=profile,
                gap=gap,
                goal_relevance=goal_relevance_map.get(nid, 0.0),
                mode=mode,
                config=config,
            )
            scored_ready.append((score, nid, gap))

        scored_ready.sort(reverse=True, key=lambda x: x[0])
        score, current, gap = scored_ready[0]
        ready.remove(current)
        ordered.append(current)

        logs[current] = {
            "decision_type": "ordered",
            "gap": gap,
            "goal_relevance": goal_relevance_map.get(current, 0.0),
            "priority_score": score,
            "reasons": ["topo_ready", "profile_aware_priority"],
        }

        for nxt in sub_adj.get(current, []):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                ready.append(nxt)

    if len(ordered) != len(indegree):
        raise ValueError("检测到环，无法完成拓扑排序")

    return ordered, logs
