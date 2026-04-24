"""Plans API 集成测试"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.sqlite_models import GoalResolutionSession, LearningProject
from app.services.domain_pack_service import get_domain_pack_service


async def test_generate_plan(client, project, profile):
    resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert resp.status_code == 200
    data = resp.json()
    assert "stages" in data
    assert data["node_count"] > 0
    assert data["budget_status"] in ("feasible", "tight", "insufficient")
    assert data["total_hours"] > 0


async def test_generate_plan_without_profile(client, project):
    resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert resp.status_code == 400


async def test_generate_plan_project_not_found(client):
    resp = await client.post("/api/v1/projects/nonexistent/plans")
    assert resp.status_code == 404


async def test_get_latest_plan(client, project, plan):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/latest"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "stages" in data
    assert data["version"] == plan["version"]


async def test_get_plan_not_found(client, project):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/latest"
    )
    assert resp.status_code == 404


async def test_plan_stages_structure(client, project, plan):
    expected_stage_names = get_domain_pack_service(project["domain"]).stage_rules["stages"]
    assert len(plan["stages"]) == len(expected_stage_names)
    stage_names = [s["stage_name"] for s in plan["stages"]]
    assert stage_names == expected_stage_names
    for idx, stage in enumerate(plan["stages"]):
        assert "tasks" in stage
        assert "estimated_hours" in stage
        assert "stage_index" in stage
        assert stage["stage_index"] == idx


async def test_plan_version_increments(client, project, profile):
    r1 = await client.post(f"/api/v1/projects/{project['id']}/plans")
    r2 = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert r2.json()["version"] == r1.json()["version"] + 1


async def test_generate_plan_passes_confirmed_resolution_to_planner(client, db_session, project, profile):
    from unittest.mock import patch

    from sqlalchemy import select

    from app.models.sqlite_models import LearningProject

    result = await db_session.execute(
        select(LearningProject).where(LearningProject.id == project["id"])
    )
    project_row = result.scalar_one()
    confirmed_target_node_ids = json.loads(project_row.confirmed_target_node_ids_json)
    captured = {}

    def fake_plan_with_profile(**kwargs):
        captured.update(kwargs)
        target_node_id = confirmed_target_node_ids[0]
        return {
            "goal_result": kwargs["confirmed_goal_result"],
            "ordered_ids": [target_node_id],
            "stage_plan": {
                "基础准备": [
                    {
                        "node_id": target_node_id,
                        "name": "测试节点",
                        "difficulty": 1,
                        "importance": 1,
                        "estimated_hours": 1.0,
                        "order_in_stage": 0,
                    }
                ],
                "核心掌握": [],
                "应用突破": [],
            },
            "reinforced_ids": [],
            "budget_summary": {"status": "feasible"},
            "audit": {"goal_result": kwargs["confirmed_goal_result"]},
            "text_output": "ok",
            "total_hours": 1.0,
            "node_count": 1,
        }

    with patch("app.api.v1.plans.plan_with_profile", side_effect=fake_plan_with_profile):
        resp = await client.post(f"/api/v1/projects/{project['id']}/plans")

    assert resp.status_code == 200
    assert captured["confirmed_goal_result"]["target_node_ids"] == confirmed_target_node_ids
    assert captured["confirmed_goal_result"]["selected_candidate_id"] == project["goal_resolution"]["selected_candidate_id"]
    assert captured["confirmed_goal_result"]["goal_type"] == project["goal_type"]


async def test_get_explanation(client, project, plan):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/explanation"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "node_explanations" in data
    assert "ordering_explanations" in data
    assert "stage_explanations" in data
    assert len(data["node_explanations"]) > 0


async def test_get_explanation_no_plan(client, project):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/explanation"
    )
    assert resp.status_code == 404


async def test_get_explanation_legacy_audit_fallback(client, db_session, project, plan):
    from sqlalchemy import select

    from app.models.sqlite_models import LearningPath

    result = await db_session.execute(
        select(LearningPath)
        .where(LearningPath.project_id == project["id"])
        .order_by(LearningPath.created_at.desc())
        .limit(1)
    )
    path = result.scalar_one()
    audit = json.loads(path.audit_json)
    audit.pop("filtered_requires_rev_adj", None)
    audit.pop("filtered_requires_adj", None)
    path.audit_json = json.dumps(audit, ensure_ascii=False)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/explanation"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "dependency_chain_explanations" in data
    assert len(data["node_explanations"]) > 0


async def test_search_returns_provider_source_on_success(client, project):
    from unittest.mock import patch

    with patch(
        "app.api.v1.search.search",
        return_value=[
            {
                "title": "逻辑回归教程",
                "url": "https://example.com/logreg",
                "snippet": "搜索结果摘要",
                "score": 0.91,
            }
        ],
    ):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/search",
            json={"query": "逻辑回归", "max_results": 5},
        )

    assert resp.status_code == 200
    assert resp.json() == {
        "query": "逻辑回归",
        "results": [
            {
                "title": "逻辑回归教程",
                "url": "https://example.com/logreg",
                "snippet": "搜索结果摘要",
                "score": 0.91,
            }
        ],
        "count": 1,
        "source": "tavily",
    }


async def test_search_returns_service_error(client, project):
    from unittest.mock import patch

    from app.core.exceptions import AppError

    with patch("app.api.v1.search.search", side_effect=AppError(code=503, message="搜索服务超时")):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/search",
            json={"query": "逻辑回归", "max_results": 5},
        )

    assert resp.status_code == 503
    assert resp.json()["error"] == "搜索服务超时"


async def test_generate_plan_returns_goal_targets_removed_when_confirmed_targets_all_removed(client, project, plan):
    for node_id in project["goal_resolution"]["confirmed_target_node_ids"]:
        review_resp = await client.patch(
            f"/api/v1/projects/{project['id']}/graph/nodes/{node_id}",
            json={"status": "removed"},
        )
        assert review_resp.status_code == 200

    latest_before = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_before.status_code == 200
    version_before = latest_before.json()["version"]

    resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert resp.status_code == 409
    assert resp.json()["error"] in {"GOAL_TARGETS_REMOVED", "GOAL_DEFAULT_TARGETS_UNAVAILABLE"}

    latest_after = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_after.status_code == 200
    assert latest_after.json()["version"] == version_before


async def test_generate_plan_reuses_confirmed_resolution_after_session_expiry(client, db_session, project, profile):
    project_row = (
        await db_session.execute(
            select(LearningProject).where(LearningProject.id == project["id"])
        )
    ).scalar_one()
    session_row = (
        await db_session.execute(
            select(GoalResolutionSession).where(GoalResolutionSession.project_id == project["id"])
        )
    ).scalar_one()
    session_row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert resp.status_code == 200

    latest_plan_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_plan_resp.status_code == 200
    goal_result = latest_plan_resp.json()["audit"]["goal_result"]
    assert goal_result["confirmed_target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]
    assert goal_result["selected_candidate_id"] == project_row.confirmed_candidate_id
