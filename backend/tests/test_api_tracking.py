"""Tracking API 集成测试"""


def _flatten_plan_node_ids(plan_payload):
    return [
        task["node_id"]
        for stage in plan_payload["stages"]
        for task in stage["tasks"]
    ]


def _extract_plan_node_ids(plan_payload):
    return set(_flatten_plan_node_ids(plan_payload))


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


async def _get_latest_plan(client, project_id: str):
    resp = await client.get(f"/api/v1/projects/{project_id}/plans/latest")
    assert resp.status_code == 200
    return resp.json()


async def _get_tracking_summary(client, project_id: str):
    resp = await client.get(f"/api/v1/projects/{project_id}/tracking/summary")
    assert resp.status_code == 200
    return resp.json()


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


async def test_tracking_summary_matches_initial_plan(client, project, plan):
    completed_node_id = plan["stages"][0]["tasks"][0]["node_id"]
    in_progress_node_id = plan["stages"][0]["tasks"][1]["node_id"]
    skipped_node_id = plan["stages"][0]["tasks"][2]["node_id"]

    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": completed_node_id, "event_type": "complete"},
    )
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": in_progress_node_id, "event_type": "start"},
    )
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": skipped_node_id, "event_type": "skip"},
    )

    summary = await _get_tracking_summary(client, project["id"])
    _assert_summary_matches_plan(
        summary,
        plan,
        completed_ids=[completed_node_id],
        in_progress_ids=[in_progress_node_id],
        skipped_ids=[skipped_node_id],
    )


async def test_tracking_summary_matches_latest_progress_aware_replan(client, project, plan):
    completed_node_id = plan["stages"][0]["tasks"][0]["node_id"]

    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": completed_node_id, "event_type": "complete"},
    )
    replan_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "测试进度统计稳定性"},
    )
    assert replan_resp.status_code == 200

    latest_plan = await _get_latest_plan(client, project["id"])
    summary = await _get_tracking_summary(client, project["id"])

    _assert_summary_matches_plan(
        summary,
        latest_plan,
        completed_ids=[completed_node_id],
        extra_node_ids=[completed_node_id],
    )
    assert completed_node_id not in _extract_plan_node_ids(latest_plan)


async def test_tracking_summary_uses_latest_profile_update_plan(client, project, plan):
    removed_node_id = plan["stages"][0]["tasks"][0]["node_id"]
    kept_node_id = plan["stages"][0]["tasks"][1]["node_id"]

    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": removed_node_id, "event_type": "complete"},
    )
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": kept_node_id, "event_type": "start"},
    )
    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/{removed_node_id}",
        json={"status": "removed"},
    )
    assert review_resp.status_code == 200

    replan_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "移除已完成旧节点后重规划"},
    )
    assert replan_resp.status_code == 200

    latest_plan = await _get_latest_plan(client, project["id"])
    latest_plan_ids = _extract_plan_node_ids(latest_plan)
    summary = await _get_tracking_summary(client, project["id"])

    _assert_summary_matches_plan(
        summary,
        latest_plan,
        in_progress_ids=[kept_node_id],
    )
    assert removed_node_id not in latest_plan_ids
    assert summary["completed"] == 0


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
