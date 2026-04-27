from __future__ import annotations

import copy
import json
from unittest.mock import patch

from sqlalchemy import select

from app.services import domain_pack_service as domain_pack_module

from app.models.sqlite_models import GoalResolutionSession, LearningPath, LearningProject, ProjectOverlayExtractionSession
from app.repositories.graph_review_repository import upsert_review_status
from app.repositories.project_overlay_repository import update_extraction_session_status, update_planning_enabled
from app.services.project_graph_snapshot_service import build_project_graph_snapshot


async def _create_valid_overlay_target(client, project_id: str, *, name: str = "快照补充目标") -> dict:
    result = await _create_valid_overlay_target_with_edge(client, project_id, name=name, edge_payload=None)
    return result["node"]


async def _create_valid_overlay_target_with_edge(
    client,
    project_id: str,
    *,
    name: str,
    edge_payload: dict | None,
) -> dict:
    source_resp = await client.post(
        f"/api/v1/projects/{project_id}/graph/overlay/sources",
        json={
            "source_type": "pasted_text",
            "raw_text": f"{name} 是一个可规划的机器学习补充知识点。",
        },
    )
    assert source_resp.status_code == 200
    source = source_resp.json()

    extraction_resp = await client.post(
        f"/api/v1/projects/{project_id}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [
                    {
                        "name": name,
                        "group": "concept",
                        "category": "foundation",
                        "summary": f"{name} 的摘要",
                        "difficulty_final": 1,
                        "importance_final": 5,
                        "estimated_hours": 2,
                        "req_math": 1,
                        "req_coding": 1,
                        "req_ml": 1,
                        "theory_weight": 0.5,
                        "practice_weight": 0.5,
                        "confidence": 0.9,
                        "legality_rationale": f"{name} 字段完整，可作为补充节点",
                        "evidence_spans": [{"source_id": source["source_id"], "text": name}],
                    }
                ],
                "edges": [edge_payload] if edge_payload else [],
                "resources": [],
                "warnings": [],
            },
        },
    )
    assert extraction_resp.status_code == 200
    payload = extraction_resp.json()
    node = payload["nodes"][0]

    review_resp = await client.patch(
        f"/api/v1/projects/{project_id}/graph/overlay/nodes/{node['node_id']}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200

    edge = payload["edges"][0] if edge_payload else None
    if edge is not None:
        edge_review_resp = await client.patch(
            f"/api/v1/projects/{project_id}/graph/overlay/edges/{edge['edge_id']}/review",
            json={"review_status": "confirmed"},
        )
        assert edge_review_resp.status_code == 200

    return {"node": node, "edge": edge, "source": source}


async def test_project_graph_snapshot_includes_confirmed_overlay_node(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"])

    snapshot = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])

    assert node["node_id"] in snapshot.nodes_by_id
    assert snapshot.nodes_by_id[node["node_id"]]["name"] == "快照补充目标"
    assert snapshot.overlay_lineage["nodes"][node["node_id"]]["source_ids"]
    assert snapshot.project_graph_hash


async def test_goal_created_overlay_draft_is_hidden_until_review_confirmed(client, project, db_session):
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    with patch(
        "app.services.goal_resolution_service.resolve_goal_candidates",
        return_value={
            "auto_detected_goal_type": "concept",
            "effective_goal_type": "concept",
            "goal_type_source": "auto",
            "recommended_candidate_id": None,
            "candidates": [],
            "warnings": [],
        },
    ):
        preview_resp = await client.post(
            f"/api/v1/projects/{project['id']}/goal-resolution/preview",
            json={"goal_text": "我想学习随机森林"},
        )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["result_type"] == "review_extension_draft"

    draft_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/extension-drafts",
        json={"resolution_session_id": preview["session_id"]},
    )
    assert draft_resp.status_code == 200
    node = draft_resp.json()["nodes"][0]

    pending_snapshot = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] not in pending_snapshot.nodes_by_id
    assert pending_snapshot.project_graph_hash == before.project_graph_hash

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node['node_id']}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200

    confirmed_snapshot = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] in confirmed_snapshot.nodes_by_id
    assert confirmed_snapshot.overlay_lineage["nodes"][node["node_id"]]["provenance"]["origin"] == "goal_extension_draft"
    assert confirmed_snapshot.project_graph_hash != before.project_graph_hash

    refreshed_preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={"goal_text": "我想学习随机森林", "requested_goal_type": "concept"},
    )
    assert refreshed_preview_resp.status_code == 200
    refreshed_preview = refreshed_preview_resp.json()
    assert refreshed_preview["result_type"] == "select_candidate"
    assert refreshed_preview["coverage_status"] == "covered"
    assert any(
        node["node_id"] in candidate["target_node_ids"]
        for candidate in refreshed_preview["candidates"]
    )


async def test_invalid_overlay_draft_stays_hidden_even_if_review_confirmed(client, project, db_session):
    source_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/sources",
        json={"source_type": "pasted_text", "raw_text": "非法草稿节点"},
    )
    assert source_resp.status_code == 200
    source = source_resp.json()
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [{"name": "非法草稿节点", "summary": "缺少 planner 必填字段"}],
                "edges": [],
                "resources": [],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    node = create_resp.json()["nodes"][0]
    assert node["validation_status"] == "invalid"
    assert any(error.startswith("missing_fields:") for error in node["validation_errors"])

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node['node_id']}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200

    snapshot = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] not in snapshot.nodes_by_id


async def test_project_graph_hash_is_order_stable_and_ignores_non_planning_provenance(client, project, db_session):
    node_a = await _create_valid_overlay_target(client, project["id"], name="排序稳定节点A")
    node_b = await _create_valid_overlay_target(client, project["id"], name="排序稳定节点B")

    first = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    second = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])

    assert first.project_graph_hash == second.project_graph_hash
    assert sorted(first.overlay_lineage["nodes"]) == sorted([node_a["node_id"], node_b["node_id"]])

    from app.models.sqlite_models import ProjectOverlayNode

    result = await db_session.execute(select(ProjectOverlayNode).where(ProjectOverlayNode.node_id == node_a["node_id"]))
    row = result.scalar_one()
    row.provenance_json = json.dumps({"summary": f"{node_a['name']} 的摘要", "ui_note": "仅展示备注"}, ensure_ascii=False)
    await db_session.commit()

    after_ui_metadata = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert after_ui_metadata.project_graph_hash == first.project_graph_hash


async def test_project_graph_hash_ignores_pack_resource_only_changes(project, db_session):
    pack = domain_pack_module.get_domain_pack_service(project["domain"], force_reload=True)
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"], baseline_pack=pack)
    changed_pack = copy.copy(pack)
    changed_pack.pack_hash = "resource-only-pack-hash"
    changed_pack.resources = [
        *pack.resources,
        {"id": "resource_only_hash_probe", "title": "资源 Hash 探针"},
    ]

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"], baseline_pack=changed_pack)

    assert after.pack_hash == "resource-only-pack-hash"
    assert after.resources != before.resources
    assert after.project_graph_hash == before.project_graph_hash


async def test_project_graph_hash_changes_when_searchable_overlay_summary_changes(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"], name="摘要 Hash 节点")
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])

    from app.models.sqlite_models import ProjectOverlayNode

    result = await db_session.execute(select(ProjectOverlayNode).where(ProjectOverlayNode.node_id == node["node_id"]))
    row = result.scalar_one()
    row.provenance_json = json.dumps({"summary": "摘要会进入 description 并参与目标召回"}, ensure_ascii=False)
    await db_session.commit()

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert after.nodes_by_id[node["node_id"]]["description"] == "摘要会进入 description 并参与目标召回"
    assert after.project_graph_hash != before.project_graph_hash


async def test_archived_overlay_session_is_not_planner_visible(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"], name="归档会话节点")
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] in before.nodes_by_id

    await update_extraction_session_status(
        db_session,
        project_id=project["id"],
        session_id=node["session_id"],
        session_status="archived",
    )

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] not in after.nodes_by_id
    assert after.project_graph_hash != before.project_graph_hash


async def test_project_graph_hash_changes_when_planning_toggle_changes(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"], name="Toggle Hash 节点")
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])

    await update_planning_enabled(
        db_session,
        project_id=project["id"],
        element_type="node",
        element_id=node["node_id"],
        planning_enabled=False,
    )

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] in before.nodes_by_id
    assert node["node_id"] not in after.nodes_by_id
    assert after.project_graph_hash != before.project_graph_hash


async def test_project_graph_snapshot_preserves_baseline_removed_semantics(project, db_session):
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])

    await upsert_review_status(
        db_session,
        project_id=project["id"],
        element_type="node",
        element_id="ml_a01",
        status="removed",
    )

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert "ml_a01" in before.nodes_by_id
    assert "ml_a01" not in after.nodes_by_id
    assert "ml_a01" in after.removed_node_ids
    assert all(edge["source"] != "ml_a01" and edge["target"] != "ml_a01" for edge in after.requires_edges)
    assert after.project_graph_hash != before.project_graph_hash


async def test_project_plan_consumes_overlay_snapshot_for_confirmed_target(client, project):
    node = await _create_valid_overlay_target(client, project["id"], name="项目规划 Overlay 目标")

    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={"goal_text": "项目规划 Overlay 目标", "requested_goal_type": "concept"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    overlay_candidate = next(
        candidate for candidate in preview["candidates"]
        if node["node_id"] in candidate["target_node_ids"]
    )

    confirm_resp = await client.put(
        f"/api/v1/projects/{project['id']}/goal-resolution",
        json={
            "goal_text": "项目规划 Overlay 目标",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": overlay_candidate["candidate_id"],
        },
    )
    assert confirm_resp.status_code == 200

    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.5,
            "practice_weight": 0.5,
            "weekly_hours": 10,
            "deadline_weeks": 8,
        },
    )
    assert profile_resp.status_code == 200

    plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_resp.status_code == 200
    planned_ids = [task["node_id"] for stage in plan_resp.json()["stages"] for task in stage["tasks"]]
    assert node["node_id"] in planned_ids

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    audit = latest_resp.json()["audit"]
    assert audit["project_graph_hash"]
    assert node["node_id"] in audit["overlay_lineage"]["nodes"]


async def test_project_graph_snapshot_includes_effective_overlay_edge(client, project, db_session):
    result = await _create_valid_overlay_target_with_edge(
        client,
        project["id"],
        name="带边 Overlay 目标",
        edge_payload={
            "source_node_id": "ml_a01",
            "target_name_or_id": "带边 Overlay 目标",
            "relation_type": "REQUIRES",
            "confidence": 0.8,
            "legality_rationale": "基础节点是 overlay 目标的前置",
        },
    )
    node = result["node"]
    edge = result["edge"]
    assert edge is not None

    snapshot = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert node["node_id"] in snapshot.requires_rev_adj
    assert "ml_a01" in snapshot.requires_rev_adj[node["node_id"]]
    assert edge["edge_id"] in snapshot.overlay_lineage["edges"]
    assert any(
        item["source"] == "ml_a01" and item["target"] == node["node_id"] and item.get("origin") == "overlay"
        for item in snapshot.requires_edges
    )


async def test_project_plan_returns_409_when_confirmed_overlay_target_becomes_invisible(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"], name="失效 Overlay 目标")

    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={"goal_text": "失效 Overlay 目标", "requested_goal_type": "concept"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    overlay_candidate = next(
        candidate for candidate in preview["candidates"]
        if node["node_id"] in candidate["target_node_ids"]
    )

    confirm_resp = await client.put(
        f"/api/v1/projects/{project['id']}/goal-resolution",
        json={
            "goal_text": "失效 Overlay 目标",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": overlay_candidate["candidate_id"],
        },
    )
    assert confirm_resp.status_code == 200

    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.5,
            "practice_weight": 0.5,
            "weekly_hours": 10,
            "deadline_weeks": 8,
        },
    )
    assert profile_resp.status_code == 200

    project_row = await db_session.get(LearningProject, project["id"])
    assert project_row is not None
    project_row.confirmed_target_node_ids_json = json.dumps([node["node_id"]], ensure_ascii=False)
    await db_session.commit()

    await update_planning_enabled(
        db_session,
        project_id=project["id"],
        element_type="node",
        element_id=node["node_id"],
        planning_enabled=False,
    )

    plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_resp.status_code == 409
    assert plan_resp.json()["error"] == "GOAL_TARGETS_REMOVED"


async def test_project_resolution_session_becomes_stale_after_overlay_hash_change(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"], name="会话 Hash 目标")

    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={"goal_text": "会话 Hash 目标", "requested_goal_type": "concept"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    session = await db_session.get(GoalResolutionSession, preview["session_id"])
    assert session is not None
    assert session.graph_hash

    await update_planning_enabled(
        db_session,
        project_id=project["id"],
        element_type="node",
        element_id=node["node_id"],
        planning_enabled=False,
    )

    overlay_candidate = next(
        candidate for candidate in preview["candidates"]
        if node["node_id"] in candidate["target_node_ids"]
    )
    confirm_resp = await client.put(
        f"/api/v1/projects/{project['id']}/goal-resolution",
        json={
            "goal_text": "会话 Hash 目标",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": overlay_candidate["candidate_id"],
        },
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "STALE_RESOLUTION_SESSION"


async def test_replan_consumes_same_snapshot_and_audit_lineage(client, project, db_session):
    node = await _create_valid_overlay_target(client, project["id"], name="重规划 Overlay 目标")

    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/preview",
        json={"goal_text": "重规划 Overlay 目标", "requested_goal_type": "concept"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    overlay_candidate = next(
        candidate for candidate in preview["candidates"]
        if node["node_id"] in candidate["target_node_ids"]
    )
    confirm_resp = await client.put(
        f"/api/v1/projects/{project['id']}/goal-resolution",
        json={
            "goal_text": "重规划 Overlay 目标",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": overlay_candidate["candidate_id"],
        },
    )
    assert confirm_resp.status_code == 200

    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.5,
            "practice_weight": 0.5,
            "weekly_hours": 10,
            "deadline_weeks": 8,
        },
    )
    assert profile_resp.status_code == 200
    assert (await client.post(f"/api/v1/projects/{project['id']}/plans")).status_code == 200

    replan_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "overlay snapshot"},
    )
    assert replan_resp.status_code == 200
    replanned_ids = [task["node_id"] for stage in replan_resp.json()["stages"] for task in stage["tasks"]]
    assert node["node_id"] in replanned_ids

    result = await db_session.execute(
        select(LearningPath).where(LearningPath.project_id == project["id"]).order_by(LearningPath.version.desc())
    )
    latest_path = result.scalars().first()
    assert latest_path is not None
    audit = json.loads(latest_path.audit_json)
    assert node["node_id"] in audit["overlay_lineage"]["nodes"]
