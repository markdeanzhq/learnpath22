"""Plans API 集成测试"""

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
