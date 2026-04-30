"""Projects API 集成测试"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import app.services.goal_resolution_service as goal_resolution_service

from sqlalchemy import select, text

from app.models.sqlite_models import (
    GoalResolutionSession,
    GraphReviewStatus,
    KnowledgeSource,
    LearnerProfile,
    LearningPath,
    LearningProject,
    PathStage,
    PathTask,
    TrackingEvent,
)


async def _create_preview_session(client, *, goal_text: str = "我想系统学习机器学习基础", requested_goal_type: str | None = None):
    payload = {
        "goal_text": goal_text,
    }
    if requested_goal_type is not None:
        payload["requested_goal_type"] = requested_goal_type

    resp = await client.post("/api/v1/goal-resolution/preview", json=payload)
    assert resp.status_code == 200
    return resp.json()


async def test_create_project_from_resolution_session(client, db_session):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "ML入门"
    assert data["goal_type"] == preview["effective_goal_type"]
    assert data["goal_resolution"]["selected_candidate_id"] == preview["recommended_candidate_id"]
    assert data["goal_resolution"]["requested_goal_type"] is None
    assert data["goal_resolution"]["auto_detected_goal_type"] == preview["auto_detected_goal_type"]
    assert data["goal_resolution"]["confirmed_target_node_ids"] == preview["candidates"][0]["target_node_ids"]
    assert data["path_mode"] == "standard"

    session = await db_session.get(GoalResolutionSession, preview["session_id"])
    assert session is not None
    assert session.project_id == data["id"]
    assert session.status == "confirmed"


async def test_create_project_accepts_path_mode_preference(client):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML压缩路径",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
            "path_mode": "compressed",
        },
    )

    assert resp.status_code == 200
    assert resp.json()["path_mode"] == "compressed"


async def test_create_project_rejects_invalid_path_mode(client):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
            "path_mode": "unknown",
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_PATH_MODE"


async def test_create_project_rejects_invalid_resolution_candidate(client):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": "candidate-does-not-exist",
        },
    )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_RESOLUTION_CANDIDATE", "code": 422}


async def test_create_project_rejects_stale_resolution_session(client, db_session):
    preview = await _create_preview_session(client)
    session = await db_session.get(GoalResolutionSession, preview["session_id"])
    assert session is not None
    session.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )

    assert resp.status_code == 409
    assert resp.json() == {"error": "STALE_RESOLUTION_SESSION", "code": 409}


async def test_create_project_rejects_goal_text_hash_drift(client, db_session):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础，但换了文本",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )

    assert resp.status_code == 409
    assert resp.json() == {"error": "STALE_RESOLUTION_SESSION", "code": 409}


async def test_create_project_rejects_pack_hash_drift(client, db_session):
    preview = await _create_preview_session(client)
    session = await db_session.get(GoalResolutionSession, preview["session_id"])
    assert session is not None
    session.pack_hash = "stale-pack-hash"
    await db_session.commit()

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )

    assert resp.status_code == 409
    assert resp.json() == {
        "error": "STALE_RESOLUTION_SESSION",
        "code": 409,
        "reason_code": "PACK_HASH_DRIFT",
    }


async def test_create_project_invalid_legacy_goal_type_payload(client):
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "x", "goal_text": "x", "goal_type": "invalid"},
    )
    assert resp.status_code == 422


async def test_create_project_invalid_type(client):
    resp = await client.post(
        "/api/v1/projects",
        json={"title": "x", "goal_text": "x", "goal_type": "invalid"},
    )
    assert resp.status_code == 422


async def test_create_project_invalid_domain(client):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "x",
            "goal_text": "我想系统学习机器学习基础",
            "goal_type": "domain",
            "domain": "other_domain",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )
    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_DOMAIN", "code": 422}


async def test_create_project_accepts_explicit_default_domain_for_compatibility(client, db_session):
    preview = await _create_preview_session(client)

    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "ML入门",
            "goal_text": "我想系统学习机器学习基础",
            "domain": "machine_learning",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "ML入门"

    session = await db_session.get(GoalResolutionSession, preview["session_id"])
    assert session is not None
    assert session.project_id == data["id"]


async def test_create_project_rejects_non_default_enabled_domain_for_compatibility(client):
    preview = await _create_preview_session(client)
    original_registry = goal_resolution_service.get_domain_pack_registry

    def fake_registry():
        registry = original_registry()
        return SimpleNamespace(
            default_domain=registry.default_domain,
            enabled_domains=frozenset({registry.default_domain, "alt_domain"}),
            resolve_domain=lambda domain=None: registry.default_domain if domain is None else domain,
        )

    with patch("app.services.goal_resolution_service.get_domain_pack_registry", side_effect=fake_registry):
        resp = await client.post(
            "/api/v1/projects",
            json={
                "title": "ML入门",
                "goal_text": "我想系统学习机器学习基础",
                "domain": "alt_domain",
                "resolution_session_id": preview["session_id"],
                "selected_candidate_id": preview["recommended_candidate_id"],
            },
        )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_DOMAIN", "code": 422}


async def test_get_project(client, project):
    resp = await client.get(f"/api/v1/projects/{project['id']}")
    assert resp.status_code == 200
    assert resp.json()["id"] == project["id"]
    assert resp.json()["title"] == "测试项目"


async def test_get_project_not_found(client):
    resp = await client.get("/api/v1/projects/nonexistent-id")
    assert resp.status_code == 404


async def test_get_project_workflow_state_recommends_profile_collection(client, project):
    resp = await client.get(f"/api/v1/projects/{project['id']}/workflow-state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project["id"]
    assert data["goal"]["confirmed"] is True
    assert data["profile"]["completed"] is False
    assert data["path"]["exists"] is False
    assert data["recommended_next_action"]["action"] == "complete_profile"
    assert [step["key"] for step in data["steps"]] == ["goal", "profile", "overlay", "path", "tracking"]


async def test_get_project_workflow_state_links_generated_path(client, project, plan):
    resp = await client.get(f"/api/v1/projects/{project['id']}/workflow-state")

    assert resp.status_code == 200
    data = resp.json()
    assert data["profile"]["completed"] is True
    assert data["path"]["exists"] is True
    assert data["path"]["version"] == 1
    assert data["tracking"]["available"] is True
    assert data["recommended_next_action"]["action"] in {"start_tracking", "view_path"}


async def test_get_project_workflow_state_not_found(client):
    resp = await client.get("/api/v1/projects/nonexistent-id/workflow-state")

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


async def test_list_projects_normalizes_legacy_null_path_mode(client, db_session, project):
    await db_session.execute(
        text("UPDATE learning_projects SET path_mode = NULL WHERE id = :project_id"),
        {"project_id": project["id"]},
    )
    await db_session.commit()

    resp = await client.get("/api/v1/projects")

    assert resp.status_code == 200
    listed = next(item for item in resp.json() if item["id"] == project["id"])
    assert listed["path_mode"] == "standard"


async def test_upgrade_learning_projects_schema_adds_path_mode_without_invalid_default(client, db_session):
    from app.db.init_db import upgrade_learning_projects_schema

    await db_session.execute(text("DROP TABLE learning_projects"))
    await db_session.execute(
        text(
            """
            CREATE TABLE learning_projects (
                id VARCHAR(36) PRIMARY KEY,
                title VARCHAR(200),
                goal_text TEXT,
                goal_type VARCHAR(20),
                domain VARCHAR(50),
                status VARCHAR(20),
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        )
    )
    await db_session.commit()

    await upgrade_learning_projects_schema(await db_session.connection())
    await db_session.commit()

    columns = (
        await db_session.execute(text("PRAGMA table_info(learning_projects)"))
    ).mappings().all()
    column_names = {column["name"] for column in columns}
    path_mode_column = next(column for column in columns if column["name"] == "path_mode")

    assert "path_mode" in column_names
    assert path_mode_column["dflt_value"] == "'standard'"


async def test_upgrade_learning_projects_schema_backfills_null_path_mode(client, db_session, project):
    from app.db.init_db import upgrade_learning_projects_schema

    await db_session.execute(
        text("UPDATE learning_projects SET path_mode = NULL WHERE id = :project_id"),
        {"project_id": project["id"]},
    )
    await db_session.commit()

    await upgrade_learning_projects_schema(await db_session.connection())
    await db_session.commit()

    value = (
        await db_session.execute(
            text("SELECT path_mode FROM learning_projects WHERE id = :project_id"),
            {"project_id": project["id"]},
        )
    ).scalar_one()
    assert value == "standard"


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


async def test_project_goal_resolution_preview_returns_project_scoped_session(client, db_session, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={
            "goal_text": "理解梯度下降",
            "requested_goal_type": "concept",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["effective_goal_type"] == "concept"
    assert data["recommended_candidate_id"] == data["candidates"][0]["candidate_id"]

    session = await db_session.get(GoalResolutionSession, data["session_id"])
    assert session is not None
    assert session.project_id == project["id"]
    assert session.status == "previewed"
    assert session.domain == project["domain"]
    assert session.pack_hash
    assert session.graph_hash


async def test_project_goal_resolution_preview_returns_404_for_missing_project(client):
    resp = await client.post(
        "/api/v1/projects/nonexistent-id/goal-resolution/preview",
        json={
            "goal_text": "理解梯度下降",
            "requested_goal_type": "concept",
        },
    )

    assert resp.status_code == 404


async def test_project_goal_resolution_preview_accepts_explicit_project_domain_for_compatibility(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={
            "goal_text": "理解梯度下降",
            "requested_goal_type": "concept",
            "domain": "machine_learning",
        },
    )

    assert resp.status_code == 200


async def test_project_goal_resolution_preview_rejects_non_default_enabled_domain_for_compatibility(client, project):
    original_registry = goal_resolution_service.get_domain_pack_registry

    def fake_registry():
        registry = original_registry()
        return SimpleNamespace(
            default_domain=registry.default_domain,
            enabled_domains=frozenset({registry.default_domain, "alt_domain"}),
            resolve_domain=lambda domain=None: registry.default_domain if domain is None else domain,
        )

    with patch("app.services.goal_resolution_service.get_domain_pack_registry", side_effect=fake_registry):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/goal-resolution/preview",
            json={
                "goal_text": "理解梯度下降",
                "requested_goal_type": "concept",
                "domain": "alt_domain",
            },
        )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_DOMAIN", "code": 422}


async def test_project_goal_resolution_confirm_updates_confirmed_resolution(client):
    project_preview = await _create_preview_session(client, goal_text="理解梯度下降", requested_goal_type="concept")
    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "概念学习",
            "goal_text": "理解梯度下降",
            "resolution_session_id": project_preview["session_id"],
            "selected_candidate_id": project_preview["recommended_candidate_id"],
        },
    )
    assert create_resp.status_code == 200
    created_project = create_resp.json()

    reconfirm_preview = await client.post(
        f"/api/v1/projects/{created_project['id']}/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "requested_goal_type": "domain",
        },
    )
    assert reconfirm_preview.status_code == 200
    preview_data = reconfirm_preview.json()

    confirm_resp = await client.put(
        f"/api/v1/projects/{created_project['id']}/goal-resolution",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview_data["session_id"],
            "selected_candidate_id": preview_data["recommended_candidate_id"],
        },
    )

    assert confirm_resp.status_code == 200
    data = confirm_resp.json()
    assert data["goal_type"] == "domain"
    assert data["goal_resolution"]["selected_candidate_id"] == preview_data["recommended_candidate_id"]
    assert data["goal_resolution"]["confirmed_target_node_ids"] == preview_data["candidates"][0]["target_node_ids"]


async def test_project_goal_resolution_confirm_rejects_non_default_enabled_domain_for_compatibility(client):
    project_preview = await _create_preview_session(client, goal_text="理解梯度下降", requested_goal_type="concept")
    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "概念学习",
            "goal_text": "理解梯度下降",
            "resolution_session_id": project_preview["session_id"],
            "selected_candidate_id": project_preview["recommended_candidate_id"],
        },
    )
    assert create_resp.status_code == 200
    created_project = create_resp.json()

    reconfirm_preview = await client.post(
        f"/api/v1/projects/{created_project['id']}/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "requested_goal_type": "domain",
        },
    )
    assert reconfirm_preview.status_code == 200
    preview_data = reconfirm_preview.json()

    original_registry = goal_resolution_service.get_domain_pack_registry

    def fake_registry():
        registry = original_registry()
        return SimpleNamespace(
            default_domain=registry.default_domain,
            enabled_domains=frozenset({registry.default_domain, "alt_domain"}),
            resolve_domain=lambda domain=None: registry.default_domain if domain is None else domain,
        )

    with patch("app.services.goal_resolution_service.get_domain_pack_registry", side_effect=fake_registry):
        confirm_resp = await client.put(
            f"/api/v1/projects/{created_project['id']}/goal-resolution",
            json={
                "goal_text": "我想系统学习机器学习基础",
                "domain": "alt_domain",
                "resolution_session_id": preview_data["session_id"],
                "selected_candidate_id": preview_data["recommended_candidate_id"],
            },
        )

    assert confirm_resp.status_code == 422
    assert confirm_resp.json() == {"error": "INVALID_DOMAIN", "code": 422}


async def test_project_goal_resolution_confirm_rejects_graph_hash_drift(client, db_session):
    project_preview = await _create_preview_session(client, goal_text="理解梯度下降", requested_goal_type="concept")
    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "概念学习",
            "goal_text": "理解梯度下降",
            "resolution_session_id": project_preview["session_id"],
            "selected_candidate_id": project_preview["recommended_candidate_id"],
        },
    )
    assert create_resp.status_code == 200
    created_project = create_resp.json()

    reconfirm_preview = await client.post(
        f"/api/v1/projects/{created_project['id']}/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "requested_goal_type": "domain",
        },
    )
    assert reconfirm_preview.status_code == 200
    preview_data = reconfirm_preview.json()

    session = await db_session.get(GoalResolutionSession, preview_data["session_id"])
    assert session is not None
    session.graph_hash = "stale-graph-hash"
    await db_session.commit()

    confirm_resp = await client.put(
        f"/api/v1/projects/{created_project['id']}/goal-resolution",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview_data["session_id"],
            "selected_candidate_id": preview_data["recommended_candidate_id"],
        },
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json() == {
        "error": "STALE_RESOLUTION_SESSION",
        "code": 409,
        "reason_code": "PROJECT_GRAPH_DRIFT",
    }


async def test_project_goal_resolution_confirm_rejects_missing_graph_hash(client, db_session):
    project_preview = await _create_preview_session(client, goal_text="理解梯度下降", requested_goal_type="concept")
    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "概念学习",
            "goal_text": "理解梯度下降",
            "resolution_session_id": project_preview["session_id"],
            "selected_candidate_id": project_preview["recommended_candidate_id"],
        },
    )
    assert create_resp.status_code == 200
    created_project = create_resp.json()

    reconfirm_preview = await client.post(
        f"/api/v1/projects/{created_project['id']}/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "requested_goal_type": "domain",
        },
    )
    assert reconfirm_preview.status_code == 200
    preview_data = reconfirm_preview.json()

    session = await db_session.get(GoalResolutionSession, preview_data["session_id"])
    assert session is not None
    session.graph_hash = None
    session.project_graph_hash = None
    await db_session.commit()

    confirm_resp = await client.put(
        f"/api/v1/projects/{created_project['id']}/goal-resolution",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": preview_data["session_id"],
            "selected_candidate_id": preview_data["recommended_candidate_id"],
        },
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json() == {
        "error": "STALE_RESOLUTION_SESSION",
        "code": 409,
        "reason_code": "PROJECT_GRAPH_DRIFT",
    }
