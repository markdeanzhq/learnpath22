"""资源推荐与绑定 API 集成测试"""

from unittest.mock import AsyncMock, patch


async def test_get_plan_resources_returns_static_stage_resources(client, project, plan):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["path_id"] == plan["id"]
    assert len(data["stages"]) == 3

    foundation_stage = next(
        stage for stage in data["stages"] if stage["stage_name"] == "基础准备"
    )
    assert any(item["source_type"] == "static" for item in foundation_stage["resources"])


async def test_recommend_plan_resources_persists_tavily_results(client, project, plan):
    mocked_results = [
        {
            "title": "逻辑回归学习资料",
            "url": "https://example.com/logistic-regression",
            "snippet": "覆盖逻辑回归、梯度下降与评估方法。",
            "score": 0.92,
        }
    ]

    with patch(
        "app.services.search_service.search",
        new=AsyncMock(return_value=mocked_results),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/recommend"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["path_id"] == plan["id"]
    assert len(data["stages"]) == 3
    assert any(
        any(item["source_type"] == "tavily_auto" for item in stage["resources"])
        for stage in data["stages"]
    )

    list_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources"
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(
        any(item["title"] == "逻辑回归学习资料" for item in stage["resources"])
        for stage in listed["stages"]
    )


async def test_bind_manual_resource_to_stage(client, project, plan):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/bind",
        json={
            "stage_name": "核心掌握",
            "title": "手动绑定：核心算法讲义",
            "url": "https://example.com/core-notes",
            "snippet": "用于答辩演示的手动绑定资源。",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "manual"
    assert data["stage_name"] == "核心掌握"

    list_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources"
    )
    assert list_resp.status_code == 200
    core_stage = next(
        stage
        for stage in list_resp.json()["stages"]
        if stage["stage_name"] == "核心掌握"
    )
    assert any(
        item["title"] == "手动绑定：核心算法讲义" and item["source_type"] == "manual"
        for item in core_stage["resources"]
    )
