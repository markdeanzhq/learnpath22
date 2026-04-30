"""资源推荐与绑定 API 集成测试"""

import json
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.sqlite_models import LearnerProfile, LearningPath


async def _set_resource_preference(db_session, project_id: str, resource_preference: str) -> None:
    result = await db_session.execute(
        select(LearnerProfile).where(LearnerProfile.project_id == project_id)
    )
    for profile in result.scalars().all():
        profile.resource_preference = resource_preference
    await db_session.commit()


async def _replace_plan_with_single_missing_node(
    db_session,
    plan_id: str,
    *,
    node_id: str,
    node_name: str,
) -> None:
    result = await db_session.execute(select(LearningPath).where(LearningPath.id == plan_id))
    path = result.scalar_one()
    stages = json.loads(path.plan_json)
    first_stage_name = next(iter(stages))
    path.plan_json = json.dumps(
        {
            first_stage_name: [
                {
                    "node_id": node_id,
                    "name": node_name,
                    "difficulty": 1,
                    "importance": 1,
                    "estimated_hours": 1.0,
                    "order_in_stage": 0,
                }
            ],
            **{stage_name: [] for stage_name in list(stages.keys())[1:]},
        },
        ensure_ascii=False,
    )
    await db_session.commit()


async def test_get_plan_resources_returns_node_first_static_resources(client, project, plan):
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
    assert "stage_resources" in foundation_stage
    assert "nodes" in foundation_stage
    assert any(item["source_type"] == "static" for item in foundation_stage["stage_resources"])
    assert any(
        any(item["source_type"] == "static" and item["node_id"] == node["node_id"] for item in node["resources"])
        for node in foundation_stage["nodes"]
    )


async def test_recommend_plan_resources_persists_tavily_results(client, db_session, project, plan):
    result = await db_session.execute(select(LearningPath).where(LearningPath.id == plan["id"]))
    path = result.scalar_one()
    stages = json.loads(path.plan_json)
    first_stage_name = next(iter(stages))
    stages = {
        first_stage_name: [
            {
                "node_id": "resource_test_missing_node",
                "name": "测试缺资源知识点",
                "difficulty": 1,
                "importance": 1,
                "estimated_hours": 1.0,
                "order_in_stage": 0,
            }
        ],
        **{stage_name: [] for stage_name in list(stages.keys())[1:]},
    }
    path.plan_json = json.dumps(stages, ensure_ascii=False)
    await db_session.commit()

    mocked_results = [
        {
            "title": "测试缺资源知识点学习资料",
            "url": "https://example.com/resource-test-node",
            "snippet": "覆盖缺资源节点的自动补充资料。",
            "score": 0.92,
        }
    ]

    search_mock = AsyncMock(return_value=mocked_results)
    with patch("app.services.search_service.search", new=search_mock):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/recommend"
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["path_id"] == plan["id"]
    assert len(data["stages"]) == 3
    assert any(
        any(item["source_type"] == "tavily_auto" for item in node["resources"])
        for stage in data["stages"]
        for node in stage["nodes"]
    )

    list_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources"
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert any(
        any(item["title"] == "测试缺资源知识点学习资料" for item in node["resources"])
        for stage in listed["stages"]
        for node in stage["nodes"]
    )
    search_calls_after_first_run = search_mock.await_count

    with patch("app.services.search_service.search", new=search_mock):
        second_resp = await client.post(
            f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/recommend"
        )

    assert second_resp.status_code == 200
    assert search_mock.await_count == search_calls_after_first_run
    repeated_titles = [
        item["title"]
        for stage in second_resp.json()["stages"]
        for node in stage["nodes"]
        for item in node["resources"]
        if item["title"] == "测试缺资源知识点学习资料"
    ]
    assert repeated_titles == ["测试缺资源知识点学习资料"]


async def test_recommend_plan_resources_uses_resource_preference_query_and_label(
    client,
    db_session,
    project,
    plan,
):
    await _set_resource_preference(db_session, project["id"], "code")
    await _replace_plan_with_single_missing_node(
        db_session,
        plan["id"],
        node_id="resource_test_code_node",
        node_name="缺代码资源知识点",
    )
    mocked_results = [
        {
            "title": "Notebook 代码示例",
            "url": "https://example.com/notebook-code",
            "snippet": "用 Python Notebook 演示知识点。",
            "score": 0.5,
        }
    ]

    search_mock = AsyncMock(return_value=mocked_results)
    with patch("app.services.search_service.search", new=search_mock):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/recommend"
        )

    assert resp.status_code == 200
    query = search_mock.await_args.args[0]
    assert "代码示例" in query
    assert "Notebook" in query
    item = next(
        item
        for stage in resp.json()["stages"]
        for node in stage["nodes"]
        for item in node["resources"]
        if item["title"] == "Notebook 代码示例"
    )
    assert item["preference_match"] == "preferred"
    assert item["score"] == 0.58


async def test_recommend_plan_resources_keeps_nonmatching_preference_results(
    client,
    db_session,
    project,
    plan,
):
    await _set_resource_preference(db_session, project["id"], "paper")
    await _replace_plan_with_single_missing_node(
        db_session,
        plan["id"],
        node_id="resource_test_generic_node",
        node_name="缺通用资源知识点",
    )
    mocked_results = [
        {
            "title": "通用学习资料",
            "url": "https://example.com/general-resource",
            "snippet": "覆盖知识点但不是偏好资料形态。",
            "score": 0.5,
        }
    ]

    search_mock = AsyncMock(return_value=mocked_results)
    with patch("app.services.search_service.search", new=search_mock):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/recommend"
        )

    assert resp.status_code == 200
    query = search_mock.await_args.args[0]
    assert "paper" in query
    item = next(
        item
        for stage in resp.json()["stages"]
        for node in stage["nodes"]
        for item in node["resources"]
        if item["title"] == "通用学习资料"
    )
    assert item["preference_match"] == "available"
    assert item["score"] == 0.5


async def test_bind_manual_resource_to_node(client, project, plan):
    core_stage = next(stage for stage in plan["stages"] if stage["stage_name"] == "核心掌握")
    target_node = core_stage["tasks"][0]

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/bind",
        json={
            "stage_name": "核心掌握",
            "node_id": target_node["node_id"],
            "title": "手动绑定：核心算法讲义",
            "url": "https://example.com/core-notes",
            "snippet": "用于答辩演示的手动绑定资源。",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "manual"
    assert data["stage_name"] == "核心掌握"
    assert data["node_id"] == target_node["node_id"]

    list_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources"
    )
    assert list_resp.status_code == 200
    core_stage = next(
        stage
        for stage in list_resp.json()["stages"]
        if stage["stage_name"] == "核心掌握"
    )
    target_group = next(
        node
        for node in core_stage["nodes"]
        if node["node_id"] == target_node["node_id"]
    )
    assert any(
        item["title"] == "手动绑定：核心算法讲义" and item["source_type"] == "manual"
        for item in target_group["resources"]
    )


async def test_bind_manual_resource_rejects_unsafe_url(client, project, plan):
    core_stage = next(stage for stage in plan["stages"] if stage["stage_name"] == "核心掌握")
    target_node = core_stage["tasks"][0]

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/{plan['id']}/resources/bind",
        json={
            "stage_name": "核心掌握",
            "node_id": target_node["node_id"],
            "title": "危险链接资料",
            "url": "javascript:alert(1)",
            "snippet": "不应允许绑定到路径资源。",
        },
    )

    assert resp.status_code == 422
