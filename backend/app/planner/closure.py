"""前置闭包与子图提取"""
from __future__ import annotations

from collections import defaultdict, deque


def get_prerequisite_closure(
    target_node_ids: list[str],
    requires_rev_adj: dict[str, list[str]],
) -> list[str]:
    """从目标节点递归收集所有前置依赖，返回闭包节点 id 列表（不含目标自身）。"""
    visited: set[str] = set()
    queue = deque(target_node_ids)

    while queue:
        node = queue.popleft()
        for prereq in requires_rev_adj.get(node, []):
            if prereq not in visited:
                visited.add(prereq)
                queue.append(prereq)

    return list(visited - set(target_node_ids))


def extract_subgraph(
    node_ids: list[str],
    requires_adj: dict[str, list[str]],
) -> tuple[dict[str, list[str]], dict[str, int]]:
    """提取子图邻接表和入度。"""
    id_set = set(node_ids)
    sub_adj: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = {nid: 0 for nid in node_ids}

    for src in node_ids:
        for tgt in requires_adj.get(src, []):
            if tgt in id_set:
                sub_adj[src].append(tgt)
                indegree[tgt] += 1

    return dict(sub_adj), indegree
