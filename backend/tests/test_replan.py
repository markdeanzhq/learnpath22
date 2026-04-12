"""重规划双模式 API 测试"""


async def test_replan_profile_update(client, project, plan):
    """画像更新模式：全量重生成 + diff"""
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "更新画像参数"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "profile_update"
    assert "stages" in data
    assert "diff" in data
    assert "added" in data["diff"]
    assert "removed" in data["diff"]
    assert "unchanged" in data["diff"]


async def test_replan_progress_aware(client, project, plan):
    """进度感知模式：锁定已完成节点且不再参与重排"""
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "complete"},
    )
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "进度更新"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "progress_aware"
    assert "diff" in data
    assert "completed" in data["diff"]
    assert node_id in data["diff"]["completed"]
    all_ids = [task["node_id"] for stage in data["stages"] for task in stage["tasks"]]
    assert node_id not in all_ids


async def test_replan_progress_aware_uses_previous_plan_profile_snapshot(client, project, profile, plan):
    """进度感知模式应沿用上一版路径的画像快照，而不是最新画像。"""
    update_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 5,
            "coding_level": 5,
            "ml_level": 5,
            "theory_weight": 0.2,
            "practice_weight": 0.8,
            "weekly_hours": 20,
            "deadline_weeks": 6,
        },
    )
    assert update_resp.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "仅同步进度"},
    )
    assert resp.status_code == 200

    latest_plan_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/latest"
    )
    assert latest_plan_resp.status_code == 200
    audit = latest_plan_resp.json()["audit"]
    snapshot = audit["profile_snapshot"]
    assert snapshot["math_level"] == profile["math_level"]
    assert snapshot["coding_level"] == profile["coding_level"]
    assert snapshot["ml_level"] == profile["ml_level"]
    assert snapshot["theory_weight"] == profile["theory_weight"]
    assert snapshot["weekly_hours"] == profile["weekly_hours"]
    assert snapshot["deadline_weeks"] == profile["deadline_weeks"]


async def test_replan_progress_aware_excludes_descendants_of_skipped_nodes(client, project, plan):
    """跳过前置节点后，依赖它的后续节点不应继续保留在 pending 路径中"""
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": "ml_c09", "event_type": "skip"},
    )
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "跳过逻辑回归"},
    )
    assert resp.status_code == 200
    data = resp.json()
    all_ids = [task["node_id"] for stage in data["stages"] for task in stage["tasks"]]
    assert "ml_c09" not in all_ids
    assert "ml_d01" not in all_ids
    assert "ml_d03" not in all_ids
    assert "ml_c10" not in all_ids
    assert "ml_e07" not in all_ids


async def test_replan_progress_aware_recalculates_budget(client, project, plan):
    """进度感知模式应基于剩余任务重新计算总学时与预算状态"""
    completed_ids = []
    total_completed_hours = 0
    for stage in plan["stages"]:
        for task in stage["tasks"][:2]:
            completed_ids.append(task["node_id"])
            total_completed_hours += task["estimated_hours"]
        if len(completed_ids) >= 2:
            break

    for node_id in completed_ids:
        await client.post(
            f"/api/v1/projects/{project['id']}/tracking/events",
            json={"node_id": node_id, "event_type": "complete"},
        )

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "完成部分节点后重规划"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_hours"] == round(plan["total_hours"] - total_completed_hours, 1)


async def test_replan_without_profile(client):
    """无画像时重规划应返回 400"""
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "空项目", "goal_text": "测试", "goal_type": "domain"},
    )
    pid = resp.json()["id"]
    resp = await client.post(
        f"/api/v1/projects/{pid}/replans",
        json={"mode": "profile_update"},
    )
    assert resp.status_code == 400


async def test_replan_version_increments(client, project, plan):
    """重规划版本号递增"""
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] > plan["version"]


async def test_replan_invalid_mode(client, project, plan):
    """非法 mode 应返回 422"""
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "invalid_mode"},
    )
    assert resp.status_code == 422
