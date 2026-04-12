"""Profiles API 集成测试"""


async def test_submit_profile(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 3,
            "coding_level": 4,
            "ml_level": 2,
            "theory_weight": 0.7,
            "practice_weight": 0.3,
            "weekly_hours": 15,
            "deadline_weeks": 8,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["math_level"] == 3
    assert data["coding_level"] == 4
    assert data["project_id"] == project["id"]


async def test_submit_profile_defaults(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles", json={}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["math_level"] == 1
    assert data["theory_weight"] == 0.5


async def test_get_latest_profile(client, project, profile):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/profiles/latest"
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == profile["id"]


async def test_get_profile_not_found(client, project):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/profiles/latest"
    )
    assert resp.status_code == 404


async def test_submit_profile_project_not_found(client):
    resp = await client.post(
        "/api/v1/projects/nonexistent/profiles",
        json={"math_level": 1, "coding_level": 1, "ml_level": 1},
    )
    assert resp.status_code == 404


async def test_profile_validation_out_of_range(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={"math_level": 6},
    )
    assert resp.status_code == 422
