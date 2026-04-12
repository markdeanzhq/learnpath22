"""Tracking API 集成测试"""


async def test_add_tracking_event(client, project, plan):
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "start", "note": "开始学习"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["node_id"] == node_id
    assert data["event_type"] == "start"
    assert data["note"] == "开始学习"


async def test_add_complete_event(client, project, plan):
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "complete"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "complete"


async def test_list_tracking_events(client, project, plan):
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "start"},
    )
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/tracking/events"
    )
    assert resp.status_code == 200
    assert len(resp.json()) >= 1


async def test_tracking_summary(client, project, plan):
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "complete"},
    )
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/tracking/summary"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] >= 1
    assert data["total_nodes"] > 0
    assert 0 <= data["completion_rate"] <= 1


async def test_tracking_summary_keeps_completed_after_progress_aware_replan(client, project, plan):
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "complete"},
    )
    await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "测试进度统计稳定性"},
    )

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/tracking/summary"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["completed"] >= 1
    assert data["total_nodes"] >= plan["node_count"]


async def test_tracking_summary_no_plan(client, project):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/tracking/summary"
    )
    assert resp.status_code == 404


async def test_add_event_project_not_found(client):
    resp = await client.post(
        "/api/v1/projects/nonexistent/tracking/events",
        json={"node_id": "ml_c01", "event_type": "start"},
    )
    assert resp.status_code == 404


async def test_add_event_invalid_node_id(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": "invalid_node", "event_type": "start"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"] == "无效的知识点节点"


async def test_invalid_event_type(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": "ml_c01", "event_type": "invalid"},
    )
    assert resp.status_code == 422


async def test_skip_event(client, project, plan):
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "skip"},
    )
    assert resp.status_code == 200
    assert resp.json()["event_type"] == "skip"


async def test_list_tracking_events_project_not_found(client):
    resp = await client.get("/api/v1/projects/nonexistent/tracking/events")
    assert resp.status_code == 404


async def test_tracking_summary_project_not_found(client):
    resp = await client.get("/api/v1/projects/nonexistent/tracking/summary")
    assert resp.status_code == 404
