"""
端到端流程验证 & 演示场景数据初始化脚本

用法:
    python scripts/e2e_demo.py [--base-url http://localhost:8000/api/v1]

覆盖三类典型场景:
    场景 A: 领域型目标 — "我想系统学习机器学习基础"
    场景 B: 问题型目标 — "我想搞懂逻辑回归为什么能做分类"
    场景 C: 概念型目标 — "理解梯度下降"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

import httpx

DEFAULT_BASE = "http://localhost:8000/api/v1"


def _extract_plan_node_ids(plan_payload: dict) -> set[str]:
    return {
        task["node_id"]
        for stage in plan_payload["stages"]
        for task in stage["tasks"]
    }


def _print_latest_plan_summary_contract(summary: dict, plan_payload: dict):
    total = len(_extract_plan_node_ids(plan_payload))
    print(
        "    tracking summary 口径: latest plan"
        f"（total_nodes={summary['total_nodes']} / latest_plan_nodes={total}）"
    )


def _assert_summary_matches_plan(
    summary: dict,
    plan_payload: dict,
    *,
    completed_ids=(),
    in_progress_ids=(),
    skipped_ids=(),
):
    plan_ids = _extract_plan_node_ids(plan_payload)
    completed = len(plan_ids & set(completed_ids))
    in_progress = len(plan_ids & set(in_progress_ids))
    skipped = len(plan_ids & set(skipped_ids))
    total = len(plan_ids)
    pending = total - completed - in_progress - skipped
    completion_rate = round(completed / total, 3) if total else 0.0

    assert summary["total_nodes"] == total
    assert summary["completed"] == completed
    assert summary["in_progress"] == in_progress
    assert summary["skipped"] == skipped
    assert summary["pending"] == pending
    assert summary["completion_rate"] == completion_rate

# ── 画像模板 ─────────────────────────────────────────────────────────
PROFILE_BEGINNER = {
    "math_level": 2, "coding_level": 2, "ml_level": 1,
    "theory_weight": 0.6, "practice_weight": 0.4,
    "weekly_hours": 10, "deadline_weeks": 12,
}

PROFILE_INTERMEDIATE = {
    "math_level": 3, "coding_level": 4, "ml_level": 2,
    "theory_weight": 0.4, "practice_weight": 0.6,
    "weekly_hours": 15, "deadline_weeks": 8,
}

PROFILE_FOCUSED = {
    "math_level": 3, "coding_level": 3, "ml_level": 1,
    "theory_weight": 0.7, "practice_weight": 0.3,
    "weekly_hours": 8, "deadline_weeks": 6,
}

# ── 场景定义 ─────────────────────────────────────────────────────────
SCENARIOS = [
    {
        "name": "场景A: 领域型目标",
        "project": {
            "title": "机器学习基础学习计划",
            "goal_text": "我想系统学习机器学习基础",
            "goal_type": "domain",
            "domain": "machine_learning",
        },
        "profile": PROFILE_BEGINNER,
    },
    {
        "name": "场景B: 问题型目标",
        "project": {
            "title": "逻辑回归分类原理探究",
            "goal_text": "我想搞懂逻辑回归为什么能做分类",
            "goal_type": "problem",
            "domain": "machine_learning",
        },
        "profile": PROFILE_INTERMEDIATE,
    },
    {
        "name": "场景C: 概念型目标",
        "project": {
            "title": "深入理解梯度下降",
            "goal_text": "理解梯度下降",
            "goal_type": "concept",
            "domain": "machine_learning",
        },
        "profile": PROFILE_FOCUSED,
    },
]


def _ok(label: str):
    print(f"  ✓ {label}")


def _fail(label: str, detail: str = ""):
    print(f"  ✗ {label}  {detail}")
    sys.exit(1)


def _check(resp: httpx.Response, label: str, expected: int = 200):
    if resp.status_code != expected:
        _fail(label, f"HTTP {resp.status_code}: {resp.text[:200]}")
    _ok(label)
    return resp.json()


async def run_scenario(client: httpx.AsyncClient, scenario: dict):
    name = scenario["name"]
    print(f"\n{'='*60}")
    print(f"▶ {name}")
    print(f"{'='*60}")

    # 1. 创建项目
    r = await client.post("/projects", json=scenario["project"])
    proj = _check(r, "创建项目")
    pid = proj["id"]
    print(f"    项目 ID: {pid}")

    # 2. 提交画像
    r = await client.post(f"/projects/{pid}/profiles", json=scenario["profile"])
    prof = _check(r, "提交画像")

    # 3. 生成路径
    r = await client.post(f"/projects/{pid}/plans")
    plan = _check(r, "生成路径")
    print(f"    节点数: {plan['node_count']}  总学时: {plan['total_hours']}h  预算: {plan['budget_status']}")
    for stage in plan["stages"]:
        n = len(stage["tasks"])
        h = stage["estimated_hours"]
        print(f"    {stage['stage_name']}: {n} 个知识点, {h}h")

    # 4. 查看解释
    r = await client.get(f"/projects/{pid}/explanation")
    expl = _check(r, "获取路径解释")
    print(f"    节点解释: {len(expl['node_explanations'])} 条")
    print(f"    排序解释: {len(expl['ordering_explanations'])} 条")
    print(f"    阶段解释: {len(expl['stage_explanations'])} 条")

    # 5. 追踪进度 (模拟完成第一阶段的第 1 个节点)
    first_node = plan["stages"][0]["tasks"][0]
    node_id = first_node["node_id"]
    node_name = first_node["name"]

    r = await client.post(
        f"/projects/{pid}/tracking/events",
        json={"node_id": node_id, "event_type": "start", "note": "开始学习"},
    )
    _check(r, f"开始学习: {node_name}")

    r = await client.post(
        f"/projects/{pid}/tracking/events",
        json={"node_id": node_id, "event_type": "complete", "note": "学完了"},
    )
    _check(r, f"完成学习: {node_name}")

    # 查看汇总（按 latest plan 口径统计）
    r = await client.get(f"/projects/{pid}/tracking/summary")
    summary = _check(r, "进度汇总")
    _assert_summary_matches_plan(summary, plan, completed_ids=[node_id])
    _print_latest_plan_summary_contract(summary, plan)
    print(f"    latest plan 口径: 完成 {summary['completed']}/{summary['total_nodes']}  完成率 {summary['completion_rate']*100:.1f}%")

    # 6. 进度感知重规划
    r = await client.post(
        f"/projects/{pid}/replans",
        json={"mode": "progress_aware", "reason": "进度更新后重规划"},
    )
    replan = _check(r, "进度感知重规划")
    diff = replan["diff"]
    print(f"    已完成(锁定): {len(diff.get('completed', []))} 个")
    print(f"    待重规划: {len(diff.get('pending', []))} 个")

    r = await client.get(f"/projects/{pid}/plans/latest")
    latest_plan = _check(r, "获取最新路径")
    r = await client.get(f"/projects/{pid}/tracking/summary")
    summary = _check(r, "重规划后进度汇总")
    _assert_summary_matches_plan(summary, latest_plan, completed_ids=[node_id])
    _print_latest_plan_summary_contract(summary, latest_plan)
    print(f"    重规划后 summary 与 latest plan 一致，已完成节点是否仍在新计划中: {node_id in _extract_plan_node_ids(latest_plan)}")

    # 7. 画像更新重规划
    r = await client.post(
        f"/projects/{pid}/replans",
        json={"mode": "profile_update", "reason": "画像参数调整"},
    )
    replan2 = _check(r, "画像更新重规划")
    diff2 = replan2["diff"]
    print(f"    新增: {len(diff2.get('added', []))} 个")
    print(f"    移除: {len(diff2.get('removed', []))} 个")
    print(f"    不变: {len(diff2.get('unchanged', []))} 个")

    print(f"\n  ★ {name} — 全链路通过")
    return pid


async def main(base_url: str):
    print(f"LearnPath-KG 端到端验证")
    print(f"API: {base_url}")

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        project_ids = []
        for scenario in SCENARIOS:
            pid = await run_scenario(client, scenario)
            project_ids.append(pid)

        # 验证项目列表
        r = await client.get("/projects")
        projects = _check(r, "\n全局: 项目列表查询")
        print(f"    共 {len(projects)} 个项目")

    print(f"\n{'='*60}")
    print(f"✅ 全部 {len(SCENARIOS)} 个场景端到端验证通过")
    print(f"{'='*60}")
    print(f"\n演示项目 ID:")
    for s, pid in zip(SCENARIOS, project_ids):
        print(f"  {s['name']}: {pid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E 验证 & 演示数据初始化")
    parser.add_argument("--base-url", default=DEFAULT_BASE, help="API base URL")
    args = parser.parse_args()
    asyncio.run(main(args.base_url))
