from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.core.config import get_settings
from app.core.exceptions import AppError
from app.models.sqlite_models import (
    ProjectOverlayEdge,
    ProjectOverlayNode,
    ProjectOverlayProjectionState,
    ProjectOverlayPromotionBatch,
    ProjectOverlayPromotionItem,
    ProjectOverlayResource,
)
from app.repositories.project_overlay_repository import (
    create_edge,
    create_extraction_session,
    create_node,
    create_resource,
    create_resource_binding,
    create_source,
    list_active_project_overlay_resources,
    update_promotion_status,
    update_review_status,
    update_validation_status,
)
from app.services import domain_pack_service as domain_pack_module
from app.services.project_graph_snapshot_service import build_project_graph_snapshot
from app.services.project_overlay_projection_service import (
    PROJECT_NODE_LABEL,
    PROJECT_RESOURCE_LABEL,
    PROJECTION_STATUS_EMPTY,
    build_project_overlay_projection_payload,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _node(node_id: str, name: str) -> dict:
    return {
        "id": node_id,
        "name": name,
        "group": "T",
        "category": "foundation",
        "description": f"{name} 描述",
        "difficulty_final": 1,
        "importance_final": 5,
        "estimated_hours": 1,
        "is_main_path": True,
        "is_foundation": True,
        "is_practice": False,
        "req_math": 1,
        "req_coding": 1,
        "req_ml": 1,
        "theory_weight": 0.5,
        "practice_weight": 0.5,
        "aliases": [],
        "keywords": [],
    }


def _install_temp_pack(tmp_path: Path, monkeypatch) -> Path:
    domain = "machine_learning"
    pack_dir = tmp_path / domain
    pack_dir.mkdir(parents=True)
    _write_json(
        pack_dir / "manifest.json",
        {
            "domain": domain,
            "version": "0.0.1",
            "node_count": 2,
            "stages": ["基础准备"],
            "supported_goal_types": ["domain", "concept", "problem"],
            "default_goal_policy": {
                "by_goal_type": {
                    "domain": {
                        "target_node_ids": ["n2"],
                        "mode": "steady",
                        "description": "默认领域目标",
                        "resolve_source": "domain_default",
                    }
                }
            },
        },
    )
    _write_json(pack_dir / "nodes.json", [_node("n1", "基础一"), _node("n2", "基础二")])
    _write_json(pack_dir / "requires_edges.json", [{"source": "n1", "target": "n2", "reason": "基础前置"}])
    _write_json(pack_dir / "related_edges.json", [])
    _write_json(pack_dir / "stage_rules.json", {"stages": ["基础准备"], "category_to_stage": {"foundation": "基础准备"}})
    _write_json(
        pack_dir / "stages.json",
        [
            {
                "id": "stage_foundation",
                "name": "基础准备",
                "order": 1,
                "description": "基础阶段",
                "category_keys": ["foundation"],
                "node_ids": ["n1", "n2"],
            }
        ],
    )
    _write_json(
        pack_dir / "resources.json",
        [
            {
                "id": "res1",
                "title": "示例资源",
                "resource_type": "article",
                "description": "示例资源描述",
                "node_ids": ["n1"],
                "stage_ids": ["stage_foundation"],
            }
        ],
    )
    _write_json(
        pack_dir / "goal_templates.json",
        [
            {
                "id": "tmpl1",
                "goal_type": "domain",
                "pattern": ["机器学习"],
                "target_node_ids": ["n2"],
                "mode": "steady",
                "description": "默认领域目标",
            }
        ],
    )
    _write_json(pack_dir / "scoring_config.json", {})
    _write_json(pack_dir / "calibration_overrides.json", {"anchors": []})
    monkeypatch.setattr(domain_pack_module, "PACK_DIR", tmp_path)
    domain_pack_module.get_domain_pack_service(domain, force_reload=True)
    return pack_dir


async def _create_source_and_session(db_session, project_id: str):
    source = await create_source(
        db_session,
        project_id=project_id,
        source_type="pasted_text",
        content_hash="phase8-source-hash",
        raw_text_excerpt="promotion source",
        commit=False,
    )
    session = await create_extraction_session(
        db_session,
        project_id=project_id,
        source_ids_json=json.dumps([source.source_id]),
        mode="default",
        commit=False,
    )
    await db_session.commit()
    return source, session


async def _mark_promotable(db_session, project_id: str, element_type: str, element_id: str) -> None:
    await update_validation_status(
        db_session,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
        validation_status="valid",
        commit=False,
    )
    await update_review_status(
        db_session,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
        review_status="confirmed",
        commit=False,
    )
    await update_promotion_status(
        db_session,
        project_id=project_id,
        element_type=element_type,
        element_id=element_id,
        promotion_status="promotion_ready",
        commit=False,
    )
    await db_session.commit()


async def _create_promotable_node(db_session, project_id: str, name: str = "新增节点") -> ProjectOverlayNode:
    source, session = await _create_source_and_session(db_session, project_id)
    node_id = f"po:{project_id}:n:phase8node{name}"
    node = await create_node(
        db_session,
        project_id=project_id,
        node_id=node_id,
        session_id=session.session_id,
        canonical_payload_hash=f"node-hash-{name}",
        name=name,
        group="T",
        category="foundation",
        difficulty_final=1,
        importance_final=4,
        estimated_hours=1,
        req_math=1,
        req_coding=1,
        req_ml=1,
        theory_weight=0.5,
        practice_weight=0.5,
        source_ids_json=json.dumps([source.source_id]),
        provenance_json=json.dumps({"summary": f"{name} 摘要"}, ensure_ascii=False),
        legality_rationale=f"{name} 合法",
        confidence=0.9,
        commit=False,
    )
    await db_session.commit()
    await _mark_promotable(db_session, project_id, "node", node_id)
    return node


async def _create_promotable_edge(
    db_session,
    project_id: str,
    session_id: str,
    target_id: str,
) -> ProjectOverlayEdge:
    edge_id = f"po:{project_id}:e:phase8edge"
    edge = await create_edge(
        db_session,
        project_id=project_id,
        edge_id=edge_id,
        session_id=session_id,
        source_node_id="n2",
        target_node_id=target_id,
        relation_type="REQUIRES",
        canonical_payload_hash="edge-hash-phase8",
        source_ids_json=json.dumps([]),
        provenance_json=json.dumps({"source_project_id": project_id}),
        legality_rationale="基础二前置新增节点",
        confidence=0.9,
        commit=False,
    )
    await db_session.commit()
    await _mark_promotable(db_session, project_id, "edge", edge_id)
    return edge


async def _create_promotable_resource(
    db_session,
    project_id: str,
    session_id: str,
    node_id: str,
) -> ProjectOverlayResource:
    resource_id = f"po:{project_id}:r:phase8resource"
    resource = await create_resource(
        db_session,
        project_id=project_id,
        resource_id=resource_id,
        session_id=session_id,
        canonical_payload_hash="resource-hash-phase8",
        title="新增资源",
        url="https://example.com/phase8",
        resource_type="article",
        summary="新增资源摘要",
        source_ids_json=json.dumps([]),
        provenance_json=json.dumps({"source_project_id": project_id}),
        confidence=0.9,
        commit=False,
    )
    await create_resource_binding(
        db_session,
        project_id=project_id,
        resource_id=resource_id,
        target_type="project_node",
        target_id=node_id,
        commit=False,
    )
    await db_session.commit()
    await _mark_promotable(db_session, project_id, "resource", resource_id)
    return resource


def _enable_promotion(monkeypatch, secret: str = "secret") -> None:
    monkeypatch.setenv("DOMAIN_PACK_PROMOTION_ENABLED", "true")
    monkeypatch.setenv("DOMAIN_PACK_PROMOTION_ADMIN_SECRET", secret)
    get_settings.cache_clear()


class ProjectionDriver:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.write_count = 0

    async def execute_write(self, operation):
        self.write_count += 1

        class Tx:
            async def run(inner_self, query: str, **params):
                if self.fail and (f":{PROJECT_NODE_LABEL}" in query or f":{PROJECT_RESOURCE_LABEL}" in query):
                    raise RuntimeError("overlay projection failed")

        return await operation(Tx())


async def test_promotion_commit_disabled_by_default(client, project, tmp_path, monkeypatch):
    _install_temp_pack(tmp_path, monkeypatch)

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/commit",
        json={"admin_secret": "secret"},
    )

    assert resp.status_code == 403
    assert resp.json()["error"] == "PROMOTION_DISABLED"


async def test_promotion_commit_requires_admin_secret(client, project, tmp_path, monkeypatch):
    _install_temp_pack(tmp_path, monkeypatch)
    _enable_promotion(monkeypatch)

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/commit",
        json={"admin_secret": "wrong"},
    )

    assert resp.status_code == 403
    assert resp.json()["error"] == "PROMOTION_FORBIDDEN"


async def test_promotion_preview_validates_without_writing(client, project, db_session, tmp_path, monkeypatch):
    pack_dir = _install_temp_pack(tmp_path, monkeypatch)
    original_nodes = (pack_dir / "nodes.json").read_text(encoding="utf-8")
    original_resources = (pack_dir / "resources.json").read_text(encoding="utf-8")
    node = await _create_promotable_node(db_session, project["id"])
    node_id = node.node_id
    edge = await _create_promotable_edge(db_session, project["id"], node.session_id, node_id)
    edge_id = edge.edge_id
    resource = await _create_promotable_resource(db_session, project["id"], node.session_id, node_id)
    resource_id = resource.resource_id

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/preview",
        json={"element_ids": [node_id, edge_id, resource_id]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is True
    assert body["status"] == "ready"
    assert body["candidate_count"] == 3
    assert body["nodes"][0]["id"] == node_id
    assert body["edges"][0]["id"] == edge_id
    preview_resource = body["resources"][0]
    assert preview_resource["id"] == resource_id
    assert preview_resource["node_ids"] == [node_id]
    assert preview_resource["binding_decisions"][0]["target_id"] == node_id
    assert preview_resource["lineage"]["session_id"] == node.session_id
    assert preview_resource["lineage"]["review_status"] == "confirmed"
    assert (pack_dir / "nodes.json").read_text(encoding="utf-8") == original_nodes
    assert (pack_dir / "resources.json").read_text(encoding="utf-8") == original_resources
    batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    assert batches == []


async def test_resource_planning_disabled_excludes_resource_from_promotion_preview(
    client,
    project,
    db_session,
    tmp_path,
    monkeypatch,
):
    _install_temp_pack(tmp_path, monkeypatch)
    node = await _create_promotable_node(db_session, project["id"])
    resource = await _create_promotable_resource(db_session, project["id"], node.session_id, node.node_id)
    resource.planning_enabled = False
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/preview",
        json={"element_ids": [resource.resource_id]},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["valid"] is False
    assert body["resources"] == []
    assert f"candidate_not_promotable:{resource.resource_id}" in body["errors"]


async def test_invalid_promotion_commit_does_not_partially_write(
    client,
    project,
    db_session,
    tmp_path,
    monkeypatch,
):
    pack_dir = _install_temp_pack(tmp_path, monkeypatch)
    _enable_promotion(monkeypatch)
    original_nodes = (pack_dir / "nodes.json").read_text(encoding="utf-8")
    node = await _create_promotable_node(db_session, project["id"], name="基础一")
    node_id = node.node_id

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/commit",
        json={"admin_secret": "secret", "element_ids": [node_id]},
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "PROMOTION_PREVIEW_INVALID"
    assert "duplicate_node_name" in json.dumps(resp.json()["preview"]["errors"], ensure_ascii=False)
    assert (pack_dir / "nodes.json").read_text(encoding="utf-8") == original_nodes
    batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    assert batches == []
    refreshed = await db_session.get(ProjectOverlayNode, node_id)
    assert refreshed.promotion_status == "promotion_ready"


async def test_promotion_commit_rolls_back_pack_when_sync_fails(
    client,
    project,
    db_session,
    tmp_path,
    monkeypatch,
):
    pack_dir = _install_temp_pack(tmp_path, monkeypatch)
    _enable_promotion(monkeypatch)
    original_nodes = (pack_dir / "nodes.json").read_text(encoding="utf-8")
    sync_service = AsyncMock()
    sync_service.force_sync_domain_pack = AsyncMock(side_effect=RuntimeError("sync failed"))
    monkeypatch.setattr(
        "app.services.project_overlay_promotion_service.get_graph_sync_service",
        lambda driver: sync_service,
    )
    node = await _create_promotable_node(db_session, project["id"])
    node_id = node.node_id
    edge = await _create_promotable_edge(db_session, project["id"], node.session_id, node_id)

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/commit",
        json={"admin_secret": "secret", "element_ids": [node_id, edge.edge_id]},
    )

    assert resp.status_code == 500
    assert resp.json()["error"] == "PROMOTION_COMMIT_FAILED"
    assert "sync failed" in resp.json()["reason"]
    assert resp.json()["rollback"]["pack_restored"] is False
    assert resp.json()["rollback"]["cache_reload"]["ok"] is True
    assert resp.json()["rollback"]["baseline_sync"]["ok"] is False
    assert (pack_dir / "nodes.json").read_text(encoding="utf-8") == original_nodes
    batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    assert len(batches) == 1
    assert batches[0].status == "failed"
    assert "sync failed" in batches[0].error_message
    db_session.expire_all()
    refreshed = await db_session.get(ProjectOverlayNode, node_id)
    assert refreshed.promotion_status == "promotion_ready"


async def test_promotion_commit_rolls_back_pack_and_records_failed_batch_when_sqlite_write_fails(
    client,
    project,
    db_session,
    tmp_path,
    monkeypatch,
):
    pack_dir = _install_temp_pack(tmp_path, monkeypatch)
    _enable_promotion(monkeypatch)
    original_nodes = (pack_dir / "nodes.json").read_text(encoding="utf-8")
    sync_service = AsyncMock()
    sync_service.force_sync_domain_pack = AsyncMock(
        return_value={"domain": "machine_learning", "synced": True, "nodes": 3, "edges": 2}
    )
    monkeypatch.setattr(
        "app.services.project_overlay_promotion_service.get_graph_sync_service",
        lambda driver: sync_service,
    )
    node = await _create_promotable_node(db_session, project["id"])
    node_id = node.node_id
    await _create_promotable_edge(db_session, project["id"], node.session_id, node_id)

    async def fail_update_batch(*args, **kwargs):
        raise RuntimeError("sqlite failed")

    monkeypatch.setattr(
        "app.services.project_overlay_promotion_service.update_promotion_batch",
        fail_update_batch,
    )

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/commit",
        json={"admin_secret": "secret"},
    )

    assert resp.status_code == 500
    assert resp.json()["error"] == "PROMOTION_COMMIT_FAILED"
    assert "sqlite failed" in resp.json()["reason"]
    assert resp.json()["rollback"]["pack_restored"] is True
    assert resp.json()["rollback"]["cache_reload"]["ok"] is True
    assert resp.json()["rollback"]["baseline_sync"]["ok"] is True
    assert (pack_dir / "nodes.json").read_text(encoding="utf-8") == original_nodes
    batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    assert len(batches) == 1
    assert batches[0].status == "failed"
    assert "sqlite failed" in batches[0].error_message
    db_session.expire_all()
    refreshed = await db_session.get(ProjectOverlayNode, node_id)
    assert refreshed.promotion_status == "promotion_ready"
    assert sync_service.force_sync_domain_pack.await_count == 2


async def test_promotion_commit_rolls_back_when_overlay_projection_fails(
    project,
    db_session,
    tmp_path,
    monkeypatch,
):
    pack_dir = _install_temp_pack(tmp_path, monkeypatch)
    _enable_promotion(monkeypatch)
    original_nodes = (pack_dir / "nodes.json").read_text(encoding="utf-8")
    sync_service = AsyncMock()
    sync_service.force_sync_domain_pack = AsyncMock(
        return_value={"domain": "machine_learning", "synced": True, "nodes": 3, "edges": 2}
    )
    monkeypatch.setattr(
        "app.services.project_overlay_promotion_service.get_graph_sync_service",
        lambda driver: sync_service,
    )
    node = await _create_promotable_node(db_session, project["id"])
    node_id = node.node_id
    edge = await _create_promotable_edge(db_session, project["id"], node.session_id, node_id)

    from app.services.project_overlay_promotion_service import commit_project_overlay_promotion

    try:
        await commit_project_overlay_promotion(
            db_session,
            ProjectionDriver(fail=True),
            project_id=project["id"],
            admin_secret="secret",
            requested_by="admin",
        )
        assert False, "expected promotion failure"
    except AppError as exc:
        assert exc.message == "PROMOTION_COMMIT_FAILED"

    assert (pack_dir / "nodes.json").read_text(encoding="utf-8") == original_nodes
    batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    assert len(batches) == 1
    assert batches[0].status == "failed"
    assert "overlay projection failed" in batches[0].error_message
    db_session.expire_all()
    refreshed = await db_session.get(ProjectOverlayNode, node_id)
    projection_state = await db_session.get(ProjectOverlayProjectionState, project["id"])
    assert refreshed.promotion_status == "promotion_ready"
    assert projection_state is None
    assert sync_service.force_sync_domain_pack.await_count == 2


async def test_promotion_commit_writes_pack_syncs_and_records_lineage(
    client,
    project,
    db_session,
    tmp_path,
    monkeypatch,
):
    pack_dir = _install_temp_pack(tmp_path, monkeypatch)
    _enable_promotion(monkeypatch)
    sync_service = AsyncMock()
    sync_service.force_sync_domain_pack = AsyncMock(
        return_value={"domain": "machine_learning", "synced": True, "nodes": 3, "edges": 2}
    )
    monkeypatch.setattr(
        "app.services.project_overlay_promotion_service.get_graph_sync_service",
        lambda driver: sync_service,
    )
    node = await _create_promotable_node(db_session, project["id"])
    node_id = node.node_id
    session_id = node.session_id
    edge = await _create_promotable_edge(db_session, project["id"], session_id, node_id)
    edge_id = edge.edge_id
    resource = await _create_promotable_resource(db_session, project["id"], session_id, node_id)
    resource_id = resource.resource_id

    from app.services.project_overlay_promotion_service import commit_project_overlay_promotion

    body = await commit_project_overlay_promotion(
        db_session,
        ProjectionDriver(),
        project_id=project["id"],
        admin_secret="secret",
        requested_by="admin",
    )
    assert body["synced"] is True
    assert body["batch"]["status"] == "promoted"
    assert body["batch"]["requested_by"] == "admin"
    assert body["resulting_pack_hash"]
    assert body["overlay_projection"]["status"] == PROJECTION_STATUS_EMPTY
    assert body["overlay_projection"]["projected_hash"] == body["overlay_projection"]["overlay_hash"]
    sync_service.force_sync_domain_pack.assert_awaited_once_with("machine_learning")

    projection_state = await db_session.get(ProjectOverlayProjectionState, project["id"])
    assert projection_state is not None
    assert projection_state.status == PROJECTION_STATUS_EMPTY

    nodes = json.loads((pack_dir / "nodes.json").read_text(encoding="utf-8"))
    requires_edges = json.loads((pack_dir / "requires_edges.json").read_text(encoding="utf-8"))
    resources = json.loads((pack_dir / "resources.json").read_text(encoding="utf-8"))
    assert node_id in {item["id"] for item in nodes}
    assert {"source": "n2", "target": node_id, "reason": "基础二前置新增节点"} in requires_edges
    promoted_resource = next(item for item in resources if item["id"] == resource_id)
    assert promoted_resource["node_ids"] == [node_id]
    assert "binding_decisions" not in promoted_resource
    assert "lineage" not in promoted_resource

    batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    items = (await db_session.execute(select(ProjectOverlayPromotionItem))).scalars().all()
    assert len(batches) == 1
    assert len(items) == 3
    assert {item.element_id for item in items} == {node_id, edge_id, resource_id}
    assert {item.status for item in items} == {"promoted"}
    provenance = json.loads(items[0].provenance_json)
    assert provenance["source_project_id"] == project["id"]
    assert provenance["baseline_pack_hash"] == body["baseline_pack_hash"]
    assert provenance["resulting_pack_hash"] == body["resulting_pack_hash"]

    db_session.expire_all()
    promoted_node = await db_session.get(ProjectOverlayNode, node_id)
    promoted_edge = await db_session.get(ProjectOverlayEdge, edge_id)
    promoted_resource = await db_session.get(ProjectOverlayResource, resource_id)
    assert promoted_node.promotion_status == "promoted"
    assert promoted_edge.promotion_status == "promoted"
    assert promoted_resource.promotion_status == "promoted"

    project_graph_resp = await client.get(f"/api/v1/projects/{project['id']}/graph", params={"scope": "project"})
    assert project_graph_resp.status_code == 200
    project_elements = project_graph_resp.json()["elements"]
    promoted_project_node = next(item for item in project_elements if item["data"]["id"] == node_id)
    promoted_project_edge = next(
        item
        for item in project_elements
        if item["data"].get("source") == "n2" and item["data"].get("target") == node_id
    )
    assert promoted_project_node["data"]["origin"] == "baseline"
    assert promoted_project_edge["data"]["origin"] == "baseline"

    session_resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions/{session_id}"
    )
    assert session_resp.status_code == 200
    assert session_resp.json()["nodes"] == []
    assert session_resp.json()["edges"] == []
    assert session_resp.json()["resources"] == []

    snapshot = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node_id in snapshot.nodes_by_id
    assert snapshot.nodes_by_id[node_id].get("origin") != "overlay"
    assert edge_id not in snapshot.overlay_lineage["edges"]

    projection_payload = await build_project_overlay_projection_payload(db_session, project["id"])
    assert node_id not in {item["id"] for item in projection_payload["nodes"]}
    assert edge_id not in {item["id"] for item in projection_payload["edges"]}
    assert resource_id not in {item["id"] for item in projection_payload["resources"]}
    assert await list_active_project_overlay_resources(db_session, project["id"]) == []

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": "rejected"},
    )
    planning_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/planning",
        json={"planning_enabled": False},
    )
    binding_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "project_node",
            "target_id": node_id,
        },
    )
    assert review_resp.status_code == 422
    assert review_resp.json()["error"] == "OVERLAY_CANDIDATE_PROMOTED_READ_ONLY"
    assert planning_resp.status_code == 422
    assert planning_resp.json()["error"] == "OVERLAY_CANDIDATE_PROMOTED_READ_ONLY"
    assert binding_resp.status_code == 422
    assert binding_resp.json()["error"] == "OVERLAY_CANDIDATE_PROMOTED_READ_ONLY"

    replay_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/promotion/commit",
        json={"admin_secret": "secret"},
    )

    assert replay_resp.status_code == 200
    assert replay_resp.json()["reason"] == "no_candidates"
    replay_batches = (await db_session.execute(select(ProjectOverlayPromotionBatch))).scalars().all()
    replay_items = (await db_session.execute(select(ProjectOverlayPromotionItem))).scalars().all()
    assert len(replay_batches) == 1
    assert len(replay_items) == 3
    assert {item.element_id for item in replay_items} == {node_id, edge_id, resource_id}
    assert {item.status for item in replay_items} == {"promoted"}
