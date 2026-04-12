"""Graph review API 校验测试"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.db.neo4j import Neo4jDriverError


def _sync_service(*, force_result=None, project_result=None, force_error=None, project_error=None):
    force_sync_domain_pack = AsyncMock()
    sync_domain_pack = AsyncMock()

    if force_error is not None:
        force_sync_domain_pack.side_effect = force_error
    else:
        force_sync_domain_pack.return_value = force_result

    if project_error is not None:
        sync_domain_pack.side_effect = project_error
    else:
        sync_domain_pack.return_value = project_result

    return SimpleNamespace(
        force_sync_domain_pack=force_sync_domain_pack,
        sync_domain_pack=sync_domain_pack,
    )


async def test_seed_graph_endpoint_returns_force_sync_result(client, monkeypatch):
    service = _sync_service(
        force_result={
            "domain": "machine_learning",
            "version": "1.0.0",
            "pack_hash": "hash-1",
            "synced": True,
            "forced": True,
            "reason": "forced",
            "nodes": 48,
            "edges": 96,
        }
    )
    monkeypatch.setattr("app.api.v1.graph.get_graph_sync_service", lambda neo4j: service)

    resp = await client.post("/api/v1/graph/seed")

    assert resp.status_code == 200
    assert resp.json() == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "nodes": 48,
        "edges": 96,
        "message": "Graph synced successfully",
        "reason": "forced",
    }
    service.force_sync_domain_pack.assert_awaited_once_with("machine_learning")
    service.sync_domain_pack.assert_not_awaited()


async def test_seed_graph_endpoint_handles_pack_error(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: _sync_service(force_error=ValueError("pack invalid")),
    )

    resp = await client.post("/api/v1/graph/seed")

    assert resp.status_code == 500
    assert resp.json() == {"error": "图谱同步失败: pack invalid", "code": 500}


async def test_sync_project_graph_uses_force_sync_semantics(client, project, monkeypatch):
    service = _sync_service(
        force_result={
            "domain": "machine_learning",
            "version": "1.1.0",
            "pack_hash": "hash-2",
            "synced": True,
            "forced": True,
            "reason": "forced",
            "nodes": 46,
            "edges": 92,
        }
    )
    monkeypatch.setattr("app.api.v1.graph.get_graph_sync_service", lambda neo4j: service)

    resp = await client.post(f"/api/v1/projects/{project['id']}/graph/sync")

    assert resp.status_code == 200
    assert resp.json() == {
        "domain": "machine_learning",
        "version": "1.1.0",
        "pack_hash": "hash-2",
        "synced": True,
        "forced": True,
        "reason": "forced",
        "nodes": 46,
        "edges": 92,
    }
    service.force_sync_domain_pack.assert_awaited_once_with("machine_learning")
    service.sync_domain_pack.assert_not_awaited()


async def test_sync_project_graph_maps_neo4j_runtime_error(client, project, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: _sync_service(
            force_error=Neo4jDriverError("Neo4j 查询执行失败: database unavailable")
        ),
    )

    resp = await client.post(f"/api/v1/projects/{project['id']}/graph/sync")

    assert resp.status_code == 500
    assert resp.json() == {
        "error": "图谱同步失败: Neo4j 查询执行失败: database unavailable",
        "code": 500,
    }


async def test_get_graph_scope_domain_injects_review_statuses_without_sync(client, project, monkeypatch):
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "confirmed"},
    )
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05",
        json={"status": "removed"},
    )

    graph_query = AsyncMock(
        return_value={
            "scope": "domain",
            "elements": [
                {"group": "nodes", "data": {"id": "ml_c01", "label": "监督学习"}},
                {
                    "group": "edges",
                    "data": {"source": "ml_a04", "target": "ml_c05", "type": "REQUIRES"},
                },
            ],
            "is_empty": False,
        }
    )
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )
    monkeypatch.setattr("app.api.v1.graph.get_graph_elements", graph_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=domain")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "domain"
    assert data["elements"][0]["data"]["review_status"] == "confirmed"
    assert data["elements"][1]["data"]["review_status"] == "removed"
    graph_query.assert_awaited_once_with(None, scope="domain")


async def test_get_graph_scope_project_returns_empty_reason_without_latest_plan(client, project, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=project")

    assert resp.status_code == 200
    assert resp.json() == {
        "scope": "project",
        "elements": [],
        "is_empty": True,
        "empty_reason": "project_latest_plan_missing",
        "message": "项目尚未生成学习路径，暂时无法返回项目相关子图",
    }


async def test_get_graph_scope_project_uses_latest_plan_node_ids(client, project, monkeypatch):
    graph_query = AsyncMock(
        return_value={
            "scope": "project",
            "elements": [{"group": "nodes", "data": {"id": "ml_c01"}}],
            "node_ids": ["ml_a04", "ml_c01"],
            "is_empty": False,
        }
    )
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )
    monkeypatch.setattr(
        "app.api.v1.graph.get_latest_plan_node_ids",
        AsyncMock(return_value=["ml_c01", "ml_a04"]),
    )
    monkeypatch.setattr("app.api.v1.graph.get_graph_elements", graph_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=project")

    assert resp.status_code == 200
    assert resp.json()["scope"] == "project"
    graph_query.assert_awaited_once_with(
        None,
        scope="project",
        node_ids=["ml_c01", "ml_a04"],
    )


async def test_get_graph_requires_existing_project(client):
    resp = await client.get("/api/v1/projects/not-found/graph?scope=domain")
    assert resp.status_code == 404
    assert resp.json() == {"error": "项目不存在", "code": 404}


async def test_get_graph_maps_neo4j_runtime_error(client, project, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_elements",
        AsyncMock(side_effect=Neo4jDriverError("Neo4j 查询执行失败: boom")),
    )

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=domain")

    assert resp.status_code == 500
    assert resp.json() == {
        "error": "图谱查询失败: Neo4j 查询执行失败: boom",
        "code": 500,
    }


async def test_get_subgraph_injects_review_statuses_without_sync(client, project, monkeypatch):
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "removed"},
    )
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05",
        json={"status": "confirmed"},
    )

    subgraph_query = AsyncMock(
        return_value={
            "scope": "project",
            "elements": [
                {"group": "nodes", "data": {"id": "ml_c01"}},
                {
                    "group": "edges",
                    "data": {"source": "ml_a04", "target": "ml_c05", "type": "REQUIRES"},
                },
            ],
            "is_empty": False,
        }
    )
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph/subgraph should not sync graph")),
    )
    monkeypatch.setattr("app.api.v1.graph.get_path_subgraph", subgraph_query)

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/subgraph?node_ids=ml_c01,ml_c05"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["elements"][0]["data"]["review_status"] == "removed"
    assert data["elements"][1]["data"]["review_status"] == "confirmed"
    subgraph_query.assert_awaited_once_with(None, ["ml_c01", "ml_c05"])


async def test_review_node_requires_existing_node(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/not-a-real-node",
        json={"status": "removed"},
    )
    assert resp.status_code == 404


async def test_review_edge_requires_existing_edge(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/not-a-real-edge",
        json={"status": "removed"},
    )
    assert resp.status_code == 404


async def test_review_node_accepts_valid_node(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "confirmed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"


async def test_review_edge_accepts_valid_edge(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05",
        json={"status": "confirmed"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "confirmed"
