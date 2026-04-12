"""Projects API 集成测试"""

from sqlalchemy import select

from app.models.sqlite_models import (
    GraphReviewStatus,
    KnowledgeSource,
    LearnerProfile,
    LearningPath,
    LearningProject,
    PathStage,
    PathTask,
    TrackingEvent,
)


async def test_create_project(client):
    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "学习机器学习",
            "goal_type": "domain",
            "domain": "machine_learning",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "ML入门"
    assert data["goal_type"] == "domain"
    assert "id" in data


async def test_create_project_concept_type(client):
    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "理解梯度下降",
            "goal_text": "理解梯度下降",
            "goal_type": "concept",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["goal_type"] == "concept"


async def test_create_project_invalid_type(client):
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "x", "goal_text": "x", "goal_type": "invalid"},
    )
    assert resp.status_code == 422


async def test_get_project(client, project):
    resp = await client.get(f"/api/v1/projects/{project['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == project["id"]
    assert resp.json()["title"] == "测试项目"


async def test_get_project_not_found(client):
    resp = await client.get("/api/v1/projects/nonexistent-id")
    assert resp.status_code == 404


async def test_list_projects_empty(client):
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    assert resp.json() == []


async def test_list_projects(client, project):
    resp = await client.get("/api/v1/projects")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(p["id"] == project["id"] for p in data)


async def test_delete_project_success(client, db_session, project_with_dependents):
    project_id = project_with_dependents["project"]["id"]

    resp = await client.delete(f"/api/v1/projects/{project_id}")

    assert resp.status_code == 200
    assert resp.json() == {"id": project_id, "message": "项目已删除"}

    assert await db_session.get(LearningProject, project_id) is None

    dependency_checks = [
        (LearnerProfile, LearnerProfile.project_id == project_id),
        (KnowledgeSource, KnowledgeSource.project_id == project_id),
        (LearningPath, LearningPath.project_id == project_id),
        (TrackingEvent, TrackingEvent.project_id == project_id),
        (GraphReviewStatus, GraphReviewStatus.project_id == project_id),
        (PathStage, PathStage.path_id == project_with_dependents["path_id"]),
        (PathTask, PathTask.stage_id == project_with_dependents["stage_id"]),
    ]
    for model, condition in dependency_checks:
        result = await db_session.execute(select(model).where(condition))
        assert result.scalar_one_or_none() is None


async def test_delete_project_then_get_returns_404(client, project):
    project_id = project["id"]

    delete_resp = await client.delete(f"/api/v1/projects/{project_id}")
    get_resp = await client.get(f"/api/v1/projects/{project_id}")

    assert delete_resp.status_code == 200
    assert get_resp.status_code == 404


async def test_delete_project_not_found(client):
    resp = await client.delete("/api/v1/projects/nonexistent-id")

    assert resp.status_code == 404


async def test_delete_project_removes_from_list(client, project):
    project_id = project["id"]

    delete_resp = await client.delete(f"/api/v1/projects/{project_id}")
    list_resp = await client.get("/api/v1/projects")

    assert delete_resp.status_code == 200
    assert list_resp.status_code == 200
    assert all(item["id"] != project_id for item in list_resp.json())
