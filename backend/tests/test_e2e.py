"""端到端流程集成测试：创建项目 → 画像 → 生成路径 → 解释 → 追踪 → 重规划"""

from app.services.domain_pack_service import get_domain_pack_service


def _extract_plan_node_ids(plan_payload):
    return {
        task["node_id"]
        for stage in plan_payload["stages"]
        for task in stage["tasks"]
    }


def _assert_summary_matches_plan(
    summary,
    plan_payload,
    *,
    completed_ids=(),
    in_progress_ids=(),
    skipped_ids=(),
    extra_node_ids=(),
):
    plan_ids = _extract_plan_node_ids(plan_payload) | set(extra_node_ids)
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


async def _create_project_via_preview(client, *, title, goal_text, goal_type=None):
    preview_payload = {
        "goal_text": goal_text,
        "domain": "machine_learning",
    }
    if goal_type is not None:
        preview_payload["requested_goal_type"] = goal_type

    preview_resp = await client.post("/api/v1/goal-resolution/preview", json=preview_payload)
    assert preview_resp.status_code == 200
    preview = preview_resp.json()

    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": title,
            "goal_text": goal_text,
            "domain": "machine_learning",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )
    assert create_resp.status_code == 200
    return create_resp.json()


async def test_e2e_domain_goal(client):
    """场景A: 领域型完整链路"""
    # 1. 预览 -> 选择推荐候选 -> 创建项目
    project = await _create_project_via_preview(
        client,
        title="机器学习基础学习计划",
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
    )
    pid = project["id"]

    # 2. 提交画像
    r = await client.post(f"/api/v1/projects/{pid}/profiles", json={
        "math_level": 2, "coding_level": 2, "ml_level": 1,
        "theory_weight": 0.6, "practice_weight": 0.4,
        "weekly_hours": 10, "deadline_weeks": 12,
    })
    assert r.status_code == 200

    # 3. 生成路径
    r = await client.post(f"/api/v1/projects/{pid}/plans")
    assert r.status_code == 200
    plan = r.json()
    expected_stage_names = get_domain_pack_service("machine_learning").stage_rules["stages"]
    assert plan["node_count"] > 0
    assert len(plan["stages"]) == len(expected_stage_names)
    assert [stage["stage_name"] for stage in plan["stages"]] == expected_stage_names

    # 4. 查看解释
    r = await client.get(f"/api/v1/projects/{pid}/explanation")
    assert r.status_code == 200
    expl = r.json()
    assert len(expl["node_explanations"]) > 0

    # 5. 追踪进度
    first_node_id = plan["stages"][0]["tasks"][0]["node_id"]
    r = await client.post(f"/api/v1/projects/{pid}/tracking/events", json={
        "node_id": first_node_id, "event_type": "start",
    })
    assert r.status_code == 200

    r = await client.post(f"/api/v1/projects/{pid}/tracking/events", json={
        "node_id": first_node_id, "event_type": "complete",
    })
    assert r.status_code == 200

    r = await client.get(f"/api/v1/projects/{pid}/tracking/summary")
    assert r.status_code == 200
    _assert_summary_matches_plan(r.json(), plan, completed_ids=[first_node_id])

    # 6. 进度感知重规划
    r = await client.post(f"/api/v1/projects/{pid}/replans", json={
        "mode": "progress_aware", "reason": "进度更新",
    })
    assert r.status_code == 200
    progress_replan = r.json()
    assert first_node_id in progress_replan["diff"]["completed"]

    latest_plan_resp = await client.get(f"/api/v1/projects/{pid}/plans/latest")
    assert latest_plan_resp.status_code == 200
    latest_plan = latest_plan_resp.json()

    r = await client.get(f"/api/v1/projects/{pid}/tracking/summary")
    assert r.status_code == 200
    _assert_summary_matches_plan(
        r.json(),
        latest_plan,
        completed_ids=[first_node_id],
        extra_node_ids=[first_node_id],
    )
    assert first_node_id not in _extract_plan_node_ids(latest_plan)

    # 7. 画像更新重规划
    removed_node_id = next(iter(progress_replan["diff"]["pending"]))
    r = await client.patch(f"/api/v1/projects/{pid}/graph/nodes/{removed_node_id}", json={
        "status": "removed",
    })
    assert r.status_code == 200

    r = await client.post(f"/api/v1/projects/{pid}/replans", json={
        "mode": "profile_update", "reason": "画像调整",
    })
    assert r.status_code == 200
    assert "unchanged" in r.json()["diff"]

    latest_plan_resp = await client.get(f"/api/v1/projects/{pid}/plans/latest")
    assert latest_plan_resp.status_code == 200
    latest_plan = latest_plan_resp.json()

    r = await client.get(f"/api/v1/projects/{pid}/tracking/summary")
    assert r.status_code == 200
    _assert_summary_matches_plan(r.json(), latest_plan, completed_ids=[first_node_id])
    assert removed_node_id not in _extract_plan_node_ids(latest_plan)


async def test_e2e_problem_goal(client):
    """场景B: 问题型完整链路"""
    project = await _create_project_via_preview(
        client,
        title="逻辑回归分类原理探究",
        goal_text="我想搞懂逻辑回归为什么能做分类",
        goal_type="problem",
    )
    pid = project["id"]

    await client.post(f"/api/v1/projects/{pid}/profiles", json={
        "math_level": 3, "coding_level": 4, "ml_level": 2,
        "theory_weight": 0.4, "practice_weight": 0.6,
        "weekly_hours": 15, "deadline_weeks": 8,
    })

    r = await client.post(f"/api/v1/projects/{pid}/plans")
    assert r.status_code == 200
    plan = r.json()
    assert plan["node_count"] >= 1
    assert plan["budget_status"] in ("feasible", "tight", "insufficient")


async def test_e2e_concept_goal(client):
    """场景C: 概念型完整链路"""
    project = await _create_project_via_preview(
        client,
        title="深入理解梯度下降",
        goal_text="理解梯度下降",
        goal_type="concept",
    )
    pid = project["id"]

    await client.post(f"/api/v1/projects/{pid}/profiles", json={
        "math_level": 3, "coding_level": 3, "ml_level": 1,
        "theory_weight": 0.7, "practice_weight": 0.3,
        "weekly_hours": 8, "deadline_weeks": 6,
    })

    r = await client.post(f"/api/v1/projects/{pid}/plans")
    assert r.status_code == 200
    assert r.json()["node_count"] >= 1

    r = await client.get(f"/api/v1/projects/{pid}/explanation")
    assert r.status_code == 200
