"""Graph review API 校验测试"""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.db.neo4j import Neo4jDriverError
from app.models.sqlite_models import (
    LearningPath,
    ProjectOverlayExtractionSession,
    ProjectOverlayEdge,
    ProjectOverlayNode,
)
from app.repositories.graph_review_repository import get_all_review_statuses
from app.services.domain_pack_service import get_domain_pack_service
from app.services.graph_service import (
    build_graph_entity_metadata_from_pack,
    build_path_graph_elements_from_snapshot,
)
from app.services.project_graph_snapshot_service import ProjectGraphSnapshot


def _snapshot_for_path_properties() -> ProjectGraphSnapshot:
    nodes_by_id = {
        "a": {"id": "a", "name": "A", "category": "foundation"},
        "b": {"id": "b", "name": "B", "category": "foundation"},
        "c": {"id": "c", "name": "C", "category": "foundation"},
        "d": {"id": "d", "name": "D", "category": "foundation"},
    }
    return ProjectGraphSnapshot(
        domain="machine_learning",
        manifest={},
        nodes=list(nodes_by_id.values()),
        nodes_by_id=nodes_by_id,
        requires_edges=[
            {"source": "a", "target": "b", "reason": "a before b"},
            {"source": "b", "target": "c", "reason": "b before c"},
            {"source": "a", "target": "d", "reason": "a before d"},
        ],
        related_edges=[{"source": "c", "target": "d", "type": "RELATED_TO"}],
        requires_adj={"a": ["b", "d"], "b": ["c"]},
        requires_rev_adj={"b": ["a"], "c": ["b"], "d": ["a"]},
        related_adj={"c": ["d"], "d": ["c"]},
        goal_templates=[],
        scoring_config={},
        stage_rules={},
        stages=[],
        resources=[],
        pack_hash="pack-hash",
        contract=None,
        removed_node_ids=set(),
        removed_edge_ids=set(),
        overlay_lineage={"nodes": {}, "edges": {}},
        project_graph_hash="graph-hash",
    )


def _element_by_id(elements, element_id):
    return next(
        element
        for element in elements
        if element["data"].get("id") == element_id
    )



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


async def test_seed_graph_endpoint_uses_registry_default_domain(client, monkeypatch):
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
    monkeypatch.setattr(
        "app.api.v1.graph.get_domain_pack_registry",
        lambda: SimpleNamespace(resolve_domain=lambda: "machine_learning"),
    )

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


async def test_seed_graph_endpoint_does_not_hardcode_machine_learning(client, monkeypatch):
    service = _sync_service(
        force_result={
            "domain": "demo_domain",
            "version": "1.0.0",
            "pack_hash": "hash-1",
            "synced": True,
            "forced": True,
            "reason": "forced",
            "nodes": 1,
            "edges": 0,
        }
    )
    monkeypatch.setattr("app.api.v1.graph.get_graph_sync_service", lambda neo4j: service)
    monkeypatch.setattr(
        "app.api.v1.graph.get_domain_pack_registry",
        lambda: SimpleNamespace(resolve_domain=lambda: "demo_domain"),
    )

    resp = await client.post("/api/v1/graph/seed")

    assert resp.status_code == 200
    assert resp.json()["domain"] == "demo_domain"
    service.force_sync_domain_pack.assert_awaited_once_with("demo_domain")


async def test_seed_graph_endpoint_handles_pack_error(client, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: _sync_service(force_error=ValueError("pack invalid")),
    )

    resp = await client.post("/api/v1/graph/seed")

    assert resp.status_code == 500
    assert resp.json() == {"error": "图谱同步失败: pack invalid", "code": 500}


async def test_sync_project_graph_uses_force_sync_semantics(client, project, monkeypatch):
    overlay_sync = AsyncMock(
        return_value={
            "project_id": project["id"],
            "synced": True,
            "status": "ok",
            "reason": "projected",
            "overlay_hash": "overlay-hash",
            "nodes": 0,
            "edges": 0,
        }
    )
    monkeypatch.setattr("app.api.v1.graph.sync_project_overlay_projection", overlay_sync)
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
        "overlay_projection": {
            "project_id": project["id"],
            "synced": True,
            "status": "ok",
            "reason": "projected",
            "overlay_hash": "overlay-hash",
            "nodes": 0,
            "edges": 0,
        },
    }
    service.force_sync_domain_pack.assert_awaited_once_with("machine_learning")
    overlay_sync.assert_awaited_once()
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
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05::REQUIRES",
        json={"status": "removed"},
    )

    graph_query = AsyncMock(side_effect=AssertionError("scope=domain must not query Neo4j graph"))
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )
    monkeypatch.setattr("app.services.graph_service.get_graph_elements", graph_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=domain")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "domain"
    assert data["is_empty"] is False
    node = _element_by_id(data["elements"], "ml_c01")
    edge = _element_by_id(data["elements"], "ml_a04->ml_c05::REQUIRES")
    assert node["data"]["origin"] == "baseline"
    assert node["data"]["scope"] == "domain"
    assert node["data"]["review_status"] == "confirmed"
    assert edge["data"]["origin"] == "baseline"
    assert edge["data"]["scope"] == "domain"
    assert edge["data"]["review_status"] == "removed"
    graph_query.assert_not_awaited()


async def test_get_graph_scope_project_returns_full_project_graph_without_latest_plan(client, project, monkeypatch):
    graph_query = AsyncMock()
    latest_plan_query = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )
    monkeypatch.setattr("app.services.graph_service.get_graph_elements", graph_query)
    monkeypatch.setattr("app.api.v1.graph.get_latest_plan", latest_plan_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=project")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "project"
    assert data["is_empty"] is False
    assert "empty_reason" not in data
    assert any(elem["data"]["origin"] == "baseline" for elem in data["elements"])
    assert all(elem["data"]["scope"] == "project" for elem in data["elements"])
    graph_query.assert_not_awaited()
    latest_plan_query.assert_not_awaited()


async def test_get_graph_scope_project_includes_overlay_lifecycle_metadata(client, project, db_session):
    session = ProjectOverlayExtractionSession(project_id=project["id"], session_status="validated")
    db_session.add(session)
    await db_session.flush()
    node = ProjectOverlayNode(
        project_id=project["id"],
        session_id=session.session_id,
        node_id=f"po:{project['id']}:n:test",
        name="Overlay 图节点",
        group="concept",
        category="foundation",
        difficulty_final=1,
        importance_final=5,
        estimated_hours=2,
        req_math=1,
        req_coding=1,
        req_ml=1,
        theory_weight=0.5,
        practice_weight=0.5,
        validation_status="valid",
        review_status="pending",
        planning_enabled=True,
        promotion_status="not_promoted",
        source_ids_json='["source-1"]',
        provenance_json='{"summary":"overlay summary"}',
        canonical_payload_hash="node-hash",
    )
    edge = ProjectOverlayEdge(
        project_id=project["id"],
        session_id=session.session_id,
        edge_id=f"po:{project['id']}:e:test",
        source_node_id="ml_a01",
        target_node_id=node.node_id,
        relation_type="RELATED_TO",
        validation_status="valid",
        review_status="pending",
        planning_enabled=False,
        promotion_status="not_promoted",
        source_ids_json='["source-1"]',
        canonical_payload_hash="edge-hash",
    )
    db_session.add_all([node, edge])
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=project")

    assert resp.status_code == 200
    data = resp.json()
    overlay_node = next(elem for elem in data["elements"] if elem["data"].get("id") == node.node_id)
    overlay_edge = next(elem for elem in data["elements"] if elem["data"].get("id") == edge.edge_id)
    assert overlay_node["data"]["origin"] == "overlay"
    assert overlay_node["data"]["validation_status"] == "valid"
    assert overlay_node["data"]["review_status"] == "pending"
    assert overlay_node["data"]["planning_enabled"] is True
    assert overlay_node["data"]["promotion_status"] == "not_promoted"
    assert overlay_edge["data"]["origin"] == "overlay"
    assert overlay_edge["data"]["planning_enabled"] is False


def test_path_graph_builder_is_deterministic_monotonic_and_induced():
    snapshot = _snapshot_for_path_properties()
    small = build_path_graph_elements_from_snapshot(snapshot, node_ids=["b", "a", "missing", "a"], path_id="p1")
    replay = build_path_graph_elements_from_snapshot(snapshot, node_ids=["a", "b", "a", "missing"], path_id="p1")
    large = build_path_graph_elements_from_snapshot(snapshot, node_ids=["a", "b", "c", "missing"], path_id="p1")

    assert small == replay
    assert small["node_ids"] == ["a", "b", "missing"]
    assert small["missing_node_ids"] == ["missing"]

    small_elements = {element["data"]["id"] for element in small["elements"]}
    large_elements = {element["data"]["id"] for element in large["elements"]}
    assert small_elements <= large_elements

    for graph in [small, large]:
        node_ids = {element["data"]["id"] for element in graph["elements"] if element["group"] == "nodes"}
        for edge in [element for element in graph["elements"] if element["group"] == "edges"]:
            assert edge["data"]["source"] in node_ids
            assert edge["data"]["target"] in node_ids

    small_edge_pairs = {
        (element["data"].get("source"), element["data"].get("target"))
        for element in small["elements"]
        if element["group"] == "edges"
    }
    assert small_edge_pairs == {("a", "b")}


async def test_get_graph_scope_path_uses_latest_plan_snapshot_authority(client, project, monkeypatch):
    latest_path = SimpleNamespace(
        id="path-latest-1",
        plan_json=json.dumps(
            {
                "阶段一": [
                    {"node_id": "ml_c01"},
                    {"node_id": "ml_a04"},
                ]
            },
            ensure_ascii=False,
        ),
    )
    snapshot_query = AsyncMock(return_value=SimpleNamespace())
    captured = {}

    def path_graph_builder(snapshot, *, node_ids, path_id):
        captured["snapshot"] = snapshot
        captured["node_ids"] = node_ids
        captured["path_id"] = path_id
        return {
            "scope": "path",
            "path_id": latest_path.id,
            "elements": [{"group": "nodes", "data": {"id": "ml_c01", "origin": "baseline", "scope": "path"}}],
            "node_ids": ["ml_a04", "ml_c01"],
            "missing_node_ids": [],
            "is_empty": False,
        }

    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )
    monkeypatch.setattr(
        "app.api.v1.graph.get_latest_plan",
        AsyncMock(return_value=latest_path),
    )
    monkeypatch.setattr("app.api.v1.graph.build_project_graph_snapshot", snapshot_query)
    monkeypatch.setattr("app.api.v1.graph.build_path_graph_elements_from_snapshot", path_graph_builder)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=path&path_id=latest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "path"
    assert data["path_id"] == latest_path.id
    assert data["missing_node_ids"] == []
    assert snapshot_query.await_count == 1
    assert snapshot_query.await_args.args[1] == project["id"]
    assert snapshot_query.await_args.kwargs == {"domain": project["domain"]}
    assert captured == {
        "snapshot": snapshot_query.return_value,
        "node_ids": ["ml_a04", "ml_c01"],
        "path_id": latest_path.id,
    }


async def test_get_graph_scope_path_returns_latest_plan_induced_snapshot_graph(client, project, db_session):
    session = ProjectOverlayExtractionSession(project_id=project["id"], session_status="validated")
    db_session.add(session)
    await db_session.flush()

    overlay_node = ProjectOverlayNode(
        project_id=project["id"],
        session_id=session.session_id,
        node_id=f"po:{project['id']}:n:path",
        name="Path Overlay 节点",
        group="concept",
        category="algorithm",
        difficulty_final=2,
        importance_final=4,
        estimated_hours=3,
        req_math=2,
        req_coding=2,
        req_ml=2,
        theory_weight=0.4,
        practice_weight=0.6,
        validation_status="valid",
        review_status="confirmed",
        planning_enabled=True,
        promotion_status="not_promoted",
        source_ids_json='["source-path"]',
        provenance_json='{"summary":"path overlay summary"}',
        validation_errors_json='[]',
        confidence=0.91,
        canonical_payload_hash="path-node-hash",
    )
    induced_edge = ProjectOverlayEdge(
        project_id=project["id"],
        session_id=session.session_id,
        edge_id=f"po:{project['id']}:e:path",
        source_node_id="ml_a02",
        target_node_id=overlay_node.node_id,
        relation_type="REQUIRES",
        validation_status="valid",
        review_status="confirmed",
        planning_enabled=True,
        promotion_status="not_promoted",
        source_ids_json='["source-path"]',
        provenance_json='{"evidence":"source-path"}',
        validation_errors_json='[]',
        legality_rationale="overlay path rationale",
        confidence=0.88,
        canonical_payload_hash="path-edge-hash",
    )
    leaked_edge = ProjectOverlayEdge(
        project_id=project["id"],
        session_id=session.session_id,
        edge_id=f"po:{project['id']}:e:leak",
        source_node_id="ml_a01",
        target_node_id=overlay_node.node_id,
        relation_type="RELATED_TO",
        validation_status="valid",
        review_status="confirmed",
        planning_enabled=True,
        promotion_status="not_promoted",
        canonical_payload_hash="leak-edge-hash",
    )
    path = LearningPath(
        project_id=project["id"],
        plan_json=json.dumps(
            {
                "阶段一": [
                    {"node_id": "ml_a02"},
                    {"node_id": overlay_node.node_id},
                    {"node_id": "missing-node"},
                ]
            },
            ensure_ascii=False,
        ),
    )
    db_session.add_all([overlay_node, induced_edge, leaked_edge, path])
    await db_session.commit()

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=path&path_id=latest")

    assert resp.status_code == 200
    data = resp.json()
    assert data["scope"] == "path"
    assert data["path_id"] == path.id
    assert data["node_ids"] == ["missing-node", "ml_a02", overlay_node.node_id]
    assert data["missing_node_ids"] == ["missing-node"]
    assert "empty_reason" not in data

    element_ids = {element["data"]["id"] for element in data["elements"]}
    assert "ml_a01" not in element_ids
    assert leaked_edge.edge_id not in element_ids
    assert "ml_a02->ml_c01::REQUIRES" not in element_ids
    assert overlay_node.node_id in element_ids
    assert induced_edge.edge_id in element_ids

    path_overlay_node = next(element for element in data["elements"] if element["data"]["id"] == overlay_node.node_id)
    path_overlay_edge = next(element for element in data["elements"] if element["data"]["id"] == induced_edge.edge_id)
    assert path_overlay_node["data"]["origin"] == "overlay"
    assert path_overlay_node["data"]["scope"] == "path"
    assert path_overlay_node["data"]["validation_status"] == "valid"
    assert path_overlay_node["data"]["review_status"] == "confirmed"
    assert path_overlay_node["data"]["planning_enabled"] is True
    assert path_overlay_node["data"]["promotion_status"] == "not_promoted"
    assert path_overlay_node["data"]["source_ids"] == ["source-path"]
    assert path_overlay_node["data"]["provenance"] == {"summary": "path overlay summary"}
    assert path_overlay_edge["data"]["origin"] == "overlay"
    assert path_overlay_edge["data"]["source"] == "ml_a02"
    assert path_overlay_edge["data"]["target"] == overlay_node.node_id
    assert path_overlay_edge["data"]["source_ids"] == ["source-path"]
    assert path_overlay_edge["data"]["provenance"] == {"evidence": "source-path"}
    assert path_overlay_edge["data"]["reason"] == "overlay path rationale"


async def test_get_graph_scope_path_returns_empty_when_latest_plan_has_no_nodes(client, project, db_session, monkeypatch):
    snapshot_query = AsyncMock(side_effect=AssertionError("empty latest plan should not build snapshot"))
    path = LearningPath(
        project_id=project["id"],
        plan_json=json.dumps({"阶段一": []}, ensure_ascii=False),
    )
    db_session.add(path)
    await db_session.commit()

    monkeypatch.setattr("app.api.v1.graph.build_project_graph_snapshot", snapshot_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=path&path_id=latest")

    assert resp.status_code == 200
    assert resp.json() == {
        "scope": "path",
        "path_id": path.id,
        "elements": [],
        "node_ids": [],
        "missing_node_ids": [],
        "is_empty": True,
    }


async def test_get_graph_scope_path_returns_empty_when_latest_plan_missing(client, project, monkeypatch):
    snapshot_query = AsyncMock(side_effect=AssertionError("missing latest plan should not build snapshot"))
    monkeypatch.setattr(
        "app.api.v1.graph.get_latest_plan",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr("app.api.v1.graph.build_project_graph_snapshot", snapshot_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=path")

    assert resp.status_code == 200
    assert resp.json() == {
        "scope": "path",
        "path_id": None,
        "elements": [],
        "node_ids": [],
        "missing_node_ids": [],
        "is_empty": True,
        "empty_reason": "project_latest_plan_missing",
    }


async def test_get_graph_scope_path_rejects_non_latest_path_id(client, project):
    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=path&path_id=not-latest")

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_GRAPH_PATH_ID"


async def test_get_graph_rejects_invalid_scope(client, project):
    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=bogus")

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_GRAPH_SCOPE"


async def test_get_graph_requires_existing_project(client):
    resp = await client.get("/api/v1/projects/not-found/graph?scope=domain")
    assert resp.status_code == 404
    assert resp.json() == {"error": "项目不存在", "code": 404}


async def test_get_graph_scope_domain_does_not_use_neo4j_query(client, project, monkeypatch):
    graph_query = AsyncMock(side_effect=Neo4jDriverError("Neo4j 查询执行失败: boom"))
    monkeypatch.setattr("app.services.graph_service.get_graph_elements", graph_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=domain")

    assert resp.status_code == 200
    assert resp.json()["scope"] == "domain"
    graph_query.assert_not_awaited()


async def test_get_graph_entities_returns_read_only_stage_resource_view(client, project, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph/entities should not sync graph")),
    )
    expected = build_graph_entity_metadata_from_pack(get_domain_pack_service(project["domain"]))

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph/entities")

    assert resp.status_code == 200
    assert resp.json() == expected


async def test_get_graph_entities_requires_existing_project(client):
    resp = await client.get("/api/v1/projects/not-found/graph/entities")
    assert resp.status_code == 404
    assert resp.json() == {"error": "项目不存在", "code": 404}


async def test_get_graph_entities_is_independent_from_neo4j_query_failures(client, project, monkeypatch):
    monkeypatch.setattr(
        "app.services.graph_service.get_graph_entity_metadata",
        AsyncMock(side_effect=Neo4jDriverError("Neo4j 查询执行失败: entities boom")),
    )

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph/entities")

    assert resp.status_code == 200
    assert resp.json()["domain"] == project["domain"]


async def test_get_subgraph_injects_review_statuses_without_sync(client, project, monkeypatch):
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "removed"},
    )
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05::REQUIRES",
        json={"status": "confirmed"},
    )
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph/subgraph should not sync graph")),
    )

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/subgraph?node_ids=ml_c01,ml_a04,ml_c05"
    )

    assert resp.status_code == 200
    data = resp.json()
    node = _element_by_id(data["elements"], "ml_c01")
    edge = _element_by_id(data["elements"], "ml_a04->ml_c05::REQUIRES")
    assert data["scope"] == "path"
    assert data["node_ids"] == ["ml_a04", "ml_c01", "ml_c05"]
    assert node["data"]["review_status"] == "removed"
    assert edge["data"]["review_status"] == "confirmed"


async def test_get_graph_workspace_aggregates_knowledge_screen_reads(client, project, monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph/workspace should not sync graph")),
    )
    persisted_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "逻辑回归",
            "provider": "tavily",
            "url": "https://example.com/logistic",
            "title": "逻辑回归资料",
            "snippet": "classification",
        },
    )
    assert persisted_resp.status_code == 200

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/workspace"
        "?scope=path&path_id=latest&include_persisted_search_results=true&session_id=missing-session"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["project_id"] == project["id"]
    assert data["graph"]["scope"] == "path"
    assert data["graph"]["empty_reason"] == "project_latest_plan_missing"
    assert data["projection_status"]["project_id"] == project["id"]
    assert data["overlay_preflight"]["project_id"] == project["id"]
    assert data["persisted_search_results"][0]["title"] == "逻辑回归资料"
    assert data["overlay_session"] is None
    assert data["overlay_session_error"] == "overlay extraction session 不存在"


async def test_overlay_review_and_planning_endpoints_update_independent_fields(client, project, db_session):
    session = ProjectOverlayExtractionSession(
        session_id="overlay-api-session",
        project_id=project["id"],
    )
    node = ProjectOverlayNode(
        node_id="po:api:n:aaaaaaaaaaaaaaaaaaaaaaaa",
        project_id=project["id"],
        session_id="overlay-api-session",
        canonical_payload_hash="node-hash",
        validation_status="valid",
        planning_enabled=False,
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(node)
    await db_session.commit()

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node.node_id}/review",
        json={"review_status": "confirmed"},
    )

    assert review_resp.status_code == 200
    review_payload = review_resp.json()
    assert review_payload["review_status"] == "confirmed"
    assert review_payload["planning_enabled"] is False
    assert review_payload["validation_status"] == "valid"
    assert review_payload["promotion_status"] == "not_promoted"

    planning_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node.node_id}/planning",
        json={"planning_enabled": True},
    )

    assert planning_resp.status_code == 200
    planning_payload = planning_resp.json()
    assert planning_payload["review_status"] == "confirmed"
    assert planning_payload["planning_enabled"] is True
    assert planning_payload["validation_status"] == "valid"
    assert planning_payload["promotion_status"] == "not_promoted"


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [("pending", 200), ("confirmed", 200), ("removed", 200), ("rejected", 422)],
)
async def test_baseline_review_action_set_is_exact(client, project, status, expected_code):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": status},
    )

    assert resp.status_code == expected_code
    if expected_code == 200:
        assert resp.json()["status"] == status


@pytest.mark.parametrize("status", ["pending", "confirmed", "removed", "rejected"])
async def test_overlay_review_action_set_is_exact_and_round_trip_stable(client, project, db_session, status):
    session = ProjectOverlayExtractionSession(
        session_id=f"overlay-review-{status}-session",
        project_id=project["id"],
    )
    node = ProjectOverlayNode(
        node_id=f"po:api:n:{status}exact",
        project_id=project["id"],
        session_id=session.session_id,
        canonical_payload_hash=f"{status}-exact-hash",
        validation_status="valid",
        review_status="pending",
        planning_enabled=True,
        promotion_status="not_promoted",
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(node)
    await db_session.commit()
    node_id = node.node_id

    first = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": status},
    )
    second = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": status},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["review_status"] == status
    assert second.json()["review_status"] == status
    assert second.json()["planning_enabled"] is True
    assert second.json()["validation_status"] == "valid"
    assert second.json()["promotion_status"] == "not_promoted"


async def test_overlay_review_endpoint_requires_existing_candidate(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/not-found/review",
        json={"review_status": "confirmed"},
    )
    assert resp.status_code == 404


async def test_origin_aware_review_action_sets_and_idempotency(client, project, db_session):
    baseline_rejected_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "rejected"},
    )
    assert baseline_rejected_resp.status_code == 422

    baseline_confirm_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "confirmed"},
    )
    baseline_repeat_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "confirmed"},
    )
    assert baseline_confirm_resp.status_code == 200
    assert baseline_repeat_resp.status_code == 200
    assert baseline_repeat_resp.json()["status"] == "confirmed"
    review_statuses = await get_all_review_statuses(db_session, project["id"])
    assert review_statuses["node"]["ml_c01"] == "confirmed"

    session = ProjectOverlayExtractionSession(
        session_id="overlay-review-contract-session",
        project_id=project["id"],
    )
    node = ProjectOverlayNode(
        node_id="po:api:n:reviewcontract",
        project_id=project["id"],
        session_id=session.session_id,
        canonical_payload_hash="review-contract-hash",
        validation_status="valid",
        planning_enabled=True,
        promotion_status="promotion_ready",
        source_ids_json='["source-1"]',
        provenance_json='{"summary":"keep me"}',
        confidence=0.8,
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(node)
    await db_session.commit()
    node_id = node.node_id

    overlay_rejected_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": "rejected"},
    )
    overlay_repeat_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": "rejected"},
    )
    assert overlay_rejected_resp.status_code == 200
    assert overlay_repeat_resp.status_code == 200
    assert overlay_repeat_resp.json()["review_status"] == "rejected"
    assert overlay_repeat_resp.json()["planning_enabled"] is True
    assert overlay_repeat_resp.json()["promotion_status"] == "promotion_ready"

    db_session.expire_all()
    refreshed = await db_session.get(ProjectOverlayNode, node_id)
    assert refreshed.review_status == "rejected"
    assert refreshed.planning_enabled is True
    assert refreshed.promotion_status == "promotion_ready"
    assert refreshed.validation_status == "valid"
    assert refreshed.source_ids_json == '["source-1"]'
    assert json.loads(refreshed.provenance_json) == {"summary": "keep me"}
    assert refreshed.confidence == 0.8


async def test_overlay_review_endpoint_rejects_unknown_status_safely(client, project, db_session):
    session = ProjectOverlayExtractionSession(
        session_id="overlay-review-unknown-session",
        project_id=project["id"],
    )
    node = ProjectOverlayNode(
        node_id="po:api:n:unknownreview",
        project_id=project["id"],
        session_id=session.session_id,
        canonical_payload_hash="unknown-review-hash",
        validation_status="valid",
        review_status="pending",
        planning_enabled=True,
        promotion_status="not_promoted",
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(node)
    await db_session.commit()
    node_id = node.node_id

    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": "maybe"},
    )

    assert resp.status_code == 422
    db_session.expire_all()
    refreshed = await db_session.get(ProjectOverlayNode, node_id)
    assert refreshed.review_status == "pending"
    assert refreshed.planning_enabled is True
    assert refreshed.promotion_status == "not_promoted"


async def test_review_node_validates_against_project_domain(client, project, monkeypatch):
    captured = {}

    def fake_get_domain_pack_service(domain=None):
        captured["domain"] = domain
        return SimpleNamespace(nodes_by_id={}, requires_edges=[], related_edges=[])

    monkeypatch.setattr("app.api.v1.graph.get_domain_pack_service", fake_get_domain_pack_service)

    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/not-a-real-node",
        json={"status": "removed"},
    )

    assert resp.status_code == 404
    assert captured["domain"] == project["domain"]


async def test_review_node_requires_existing_node(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/not-a-real-node",
        json={"status": "removed"},
    )
    assert resp.status_code == 404


async def test_get_graph_scope_domain_applies_review_status_per_typed_edge_id(client, project, monkeypatch):
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_c05->ml_c06::RELATED_TO",
        json={"status": "confirmed"},
    )
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_c05->ml_c06::REQUIRES",
        json={"status": "removed"},
    )

    graph_query = AsyncMock(side_effect=AssertionError("scope=domain must not query Neo4j graph"))
    monkeypatch.setattr(
        "app.api.v1.graph.get_graph_sync_service",
        lambda neo4j: (_ for _ in ()).throw(AssertionError("GET /graph should not sync graph")),
    )
    monkeypatch.setattr("app.services.graph_service.get_graph_elements", graph_query)

    resp = await client.get(f"/api/v1/projects/{project['id']}/graph?scope=domain")

    assert resp.status_code == 200
    data = resp.json()
    related_edge = _element_by_id(data["elements"], "ml_c05->ml_c06::RELATED_TO")
    requires_edge = _element_by_id(data["elements"], "ml_c05->ml_c06::REQUIRES")
    assert related_edge["data"]["review_status"] == "confirmed"
    assert requires_edge["data"]["review_status"] == "removed"
    graph_query.assert_not_awaited()


async def test_review_edge_validates_against_project_domain(client, project, monkeypatch):
    captured = {}

    def fake_get_domain_pack_service(domain=None):
        captured["domain"] = domain
        return SimpleNamespace(nodes_by_id={}, requires_edges=[], related_edges=[])

    monkeypatch.setattr("app.api.v1.graph.get_domain_pack_service", fake_get_domain_pack_service)

    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/not-a-real-edge",
        json={"status": "removed"},
    )

    assert resp.status_code == 404
    assert captured["domain"] == project["domain"]


async def test_review_edge_requires_existing_typed_edge(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/not-a-real-edge",
        json={"status": "removed"},
    )
    assert resp.status_code == 404


async def test_review_edge_rejects_legacy_untyped_edge_id(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05",
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


async def test_review_edge_accepts_valid_typed_edge(client, project):
    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05::REQUIRES",
        json={"status": "confirmed"},
    )
    assert resp.status_code == 200
    assert resp.json()["element_id"] == "ml_a04->ml_c05::REQUIRES"
    assert resp.json()["status"] == "confirmed"
