"""Plans API 集成测试"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from sqlalchemy import select

from app.api.v1.plans import _apply_graph_option_diff, _dict_stages_to_list, _resolve_effective_path_mode
from app.models.sqlite_models import GoalResolutionSession, LearnerProfile, LearningPath, LearningProject, PlanExplanationCache, VariantPreviewSession
from app.services.domain_pack_service import get_domain_pack_service


async def _create_overlay_target(client, project_id: str, *, name: str, confirm_review: bool = True) -> dict:
    source_resp = await client.post(
        f"/api/v1/projects/{project_id}/graph/overlay/sources",
        json={"source_type": "pasted_text", "raw_text": f"{name} 是一个可规划的机器学习补充知识点。"},
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
                "edges": [],
                "resources": [],
                "warnings": [],
            },
        },
    )
    assert extraction_resp.status_code == 200
    node = extraction_resp.json()["nodes"][0]

    if confirm_review:
        review_resp = await client.patch(
            f"/api/v1/projects/{project_id}/graph/overlay/nodes/{node['node_id']}/review",
            json={"review_status": "confirmed"},
        )
        assert review_resp.status_code == 200
    return node


def test_apply_graph_option_diff_reports_order_stage_budget_and_path_overlay_hits():
    variants = [
        {
            "graph_option": "baseline",
            "included_node_ids": ["a", "b", "c"],
            "budget_summary": {"status": "feasible", "total_hours": 6, "estimated_weeks": 2},
            "audit_summary": {},
            "plan_result": {
                "stage_plan": {
                    "基础阶段": [{"node_id": "a"}, {"node_id": "b"}],
                    "进阶阶段": [{"node_id": "c"}],
                },
            },
        },
        {
            "graph_option": "enhanced",
            "included_node_ids": ["a", "c", "b"],
            "budget_summary": {"status": "tight", "total_hours": 8, "estimated_weeks": 2.7},
            "path_overlay_node_ids": [],
            "path_overlay_edge_ids": ["edge-overlay-001"],
            "audit_summary": {},
            "plan_result": {
                "stage_plan": {
                    "基础阶段": [{"node_id": "a"}],
                    "进阶阶段": [{"node_id": "c"}, {"node_id": "b"}],
                },
            },
        },
    ]

    _apply_graph_option_diff(variants)

    enhanced = variants[1]
    assert enhanced["added_node_ids"] == []
    assert enhanced["removed_node_ids"] == []
    assert enhanced["order_changed"] is True
    assert enhanced["order_changed_node_ids"] == ["b", "c"]
    assert enhanced["stage_changed"] is True
    assert enhanced["stage_changed_node_ids"] == ["b"]
    assert enhanced["budget_changed"] is True
    assert enhanced["budget_delta"]["total_hours"] == {"from": 6, "to": 8, "delta": 2}
    assert enhanced["budget_delta"]["status"] == {"from": "feasible", "to": "tight"}
    assert enhanced["audit_summary"]["graph_option_diff"]["path_overlay_edge_ids"] == ["edge-overlay-001"]


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


async def test_generate_plan_rejects_invalid_path_mode(client, project, profile):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans",
        json={"path_mode": "unknown"},
    )
    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_PATH_MODE"


async def test_generate_plan_accepts_compressed_path_mode(client, project, profile):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans",
        json={"path_mode": "compressed"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path_mode"] == "compressed"

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    assert latest["path_mode"] == "compressed"
    assert latest["path_mode_source"] == "explicit_request"
    assert latest["audit"]["path_mode"] == "compressed"
    assert latest["audit"]["path_mode_source"] == "explicit_request"
    assert latest["audit"]["included_nodes"]


async def test_generate_plan_uses_profile_path_mode_when_project_default(client, project):
    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.6,
            "practice_weight": 0.4,
            "weekly_hours": 10,
            "deadline_weeks": 12,
            "path_mode_preference": "compressed",
        },
    )
    assert profile_resp.status_code == 200

    resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert resp.status_code == 200
    data = resp.json()
    assert data["path_mode"] == "compressed"
    assert data["path_mode_source"] == "learner_profile_preference"

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    assert latest["audit"]["path_mode"] == "compressed"
    assert latest["audit"]["path_mode_source"] == "learner_profile_preference"
    assert latest["audit"]["path_mode_resolution"] == {"profile_path_mode_preference": "compressed"}
    assert latest["audit"]["derived_planner_parameters"]["path_mode_source"] == "learner_profile_preference"
    assert latest["audit"]["preference_sources"]["path_mode"] == "learner_profile_preference"


async def test_generate_plan_explicit_request_overrides_profile_path_preference(client, project):
    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.6,
            "practice_weight": 0.4,
            "weekly_hours": 10,
            "deadline_weeks": 12,
            "path_mode_preference": "compressed",
        },
    )
    assert profile_resp.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans",
        json={"path_mode": "standard"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["path_mode"] == "standard"
    assert data["path_mode_source"] == "explicit_request"

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    assert latest["audit"]["path_mode"] == "standard"
    assert latest["audit"]["path_mode_source"] == "explicit_request"
    assert latest["audit"]["path_mode_resolution"] == {"requested_path_mode": "standard"}


def test_stage_serialization_includes_empty_reason_metadata():
    stages = _dict_stages_to_list(
        {
            "基础准备": [
                {
                    "node_id": "ml_a04",
                    "name": "导数与偏导",
                    "estimated_hours": 2,
                }
            ],
            "核心掌握": [],
        },
        {
            "stage_logs": {
                "_stage_summaries": {
                    "核心掌握": {"empty_reason": "当前目标没有匹配核心阶段节点。"},
                }
            }
        },
    )

    assert "empty_reason" not in stages[0]
    assert stages[1]["empty_reason"] == "当前目标没有匹配核心阶段节点。"


def test_effective_path_mode_fallback_and_project_precedence():
    mode, source, resolution = _resolve_effective_path_mode(
        requested_path_mode=None,
        project_path_mode="standard",
        profile={"path_mode_preference": "invalid"},
    )
    assert mode == "standard"
    assert source == "standard_fallback"
    assert resolution == {"invalid_profile_path_mode_preference": "invalid"}

    mode, source, resolution = _resolve_effective_path_mode(
        requested_path_mode=None,
        project_path_mode="compressed",
        profile={"path_mode_preference": "standard"},
    )
    assert mode == "compressed"
    assert source == "project_path_mode"
    assert resolution == {"project_path_mode": "compressed"}


async def test_generate_plan_audit_includes_persona_snapshot(client, project):
    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 4,
            "coding_level": 5,
            "ml_level": 3,
            "theory_weight": 0.2,
            "practice_weight": 0.8,
            "weekly_hours": 18,
            "deadline_weeks": 6,
            "path_mode_preference": "compressed",
        },
    )
    assert profile_resp.status_code == 200

    plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_resp.status_code == 200

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    snapshot = latest["audit"]["profile_snapshot"]
    assert latest["audit"]["path_mode"] == "compressed"
    assert latest["audit"]["path_mode_source"] == "learner_profile_preference"
    assert snapshot["path_mode_preference"] == "compressed"
    assert snapshot["persona_label"] == "实践驱动型学习者"
    assert "实践驱动型学习者" in snapshot["persona_summary"]


async def test_generate_plan_project_not_found(client):
    resp = await client.post("/api/v1/projects/nonexistent/plans")
    assert resp.status_code == 404


async def test_variant_preview_creates_ttl_session_without_learning_path(client, db_session, project, profile):
    before_count = (
        await db_session.execute(select(LearningPath).where(LearningPath.project_id == project["id"]))
    ).scalars().all()

    resp = await client.post(f"/api/v1/projects/{project['id']}/plans/variants/preview")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert {variant["path_mode"] for variant in data["variants"]} == {
        "standard",
        "compressed",
        "theory_first",
        "practice_first",
    }
    assert all(variant["included_node_ids"] for variant in data["variants"])
    assert all(variant["audit_summary"]["project_graph_hash"] == data["project_graph_hash"] for variant in data["variants"])

    after_count = (
        await db_session.execute(select(LearningPath).where(LearningPath.project_id == project["id"]))
    ).scalars().all()
    assert len(after_count) == len(before_count)
    session = await db_session.get(VariantPreviewSession, data["variant_preview_id"])
    assert session is not None
    assert session.path_id is None


async def test_variant_preview_accepts_custom_modes_and_deduplicates(client, project, profile):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/preview",
        json={"path_modes": ["compressed", "standard", "compressed"]},
    )

    assert resp.status_code == 200
    assert [variant["path_mode"] for variant in resp.json()["variants"]] == ["compressed", "standard"]


async def test_variant_preview_rejects_invalid_path_mode(client, project, profile):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/preview",
        json={"path_modes": ["standard", "unknown"]},
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_PATH_MODE"


async def test_graph_option_preview_compares_baseline_and_enhanced_overlay(client, db_session, project, profile):
    overlay_node = await _create_overlay_target(client, project["id"], name="路径对比 Overlay 目标")
    project_row = await db_session.get(LearningProject, project["id"])
    assert project_row is not None
    baseline_target_ids = json.loads(project_row.confirmed_target_node_ids_json)
    project_row.goal_text = "路径对比 Overlay 目标"
    project_row.goal_type = "concept"
    project_row.confirmed_target_node_ids_json = json.dumps([baseline_target_ids[0]], ensure_ascii=False)
    await db_session.commit()

    before_paths = (
        await db_session.execute(select(LearningPath).where(LearningPath.project_id == project["id"]))
    ).scalars().all()
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/graph-options/preview",
        json={"path_mode": "standard"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "active"
    assert data["project_graph_hash"]
    variants = {variant["graph_option"]: variant for variant in data["variants"]}
    baseline = variants["baseline"]
    enhanced = variants["enhanced"]
    assert baseline["preview_kind"] == "graph_option"
    assert baseline["status"] == "available"
    assert enhanced["status"] == "available"
    assert overlay_node["node_id"] not in baseline["included_node_ids"]
    assert overlay_node["node_id"] in enhanced["included_node_ids"]
    assert overlay_node["node_id"] in enhanced["added_node_ids"]
    assert overlay_node["node_id"] in enhanced["overlay_node_ids"]
    assert overlay_node["node_id"] in enhanced["visible_overlay_node_ids"]
    assert overlay_node["node_id"] in enhanced["path_overlay_node_ids"]
    assert overlay_node["node_id"] in enhanced["audit_summary"]["nodes_added_vs_baseline"]
    assert enhanced["audit_summary"]["path_overlay_node_ids"] == enhanced["path_overlay_node_ids"]
    assert baseline["project_graph_hash"] != enhanced["project_graph_hash"]

    after_paths = (
        await db_session.execute(select(LearningPath).where(LearningPath.project_id == project["id"]))
    ).scalars().all()
    assert len(after_paths) == len(before_paths)


async def test_graph_option_preview_reports_visible_overlay_even_when_path_unchanged(client, project, profile):
    overlay_node = await _create_overlay_target(client, project["id"], name="未命中路径的 Overlay 目标")

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/graph-options/preview",
        json={"path_mode": "standard"},
    )

    assert resp.status_code == 200
    variants = {variant["graph_option"]: variant for variant in resp.json()["variants"]}
    baseline = variants["baseline"]
    enhanced = variants["enhanced"]
    assert overlay_node["node_id"] in enhanced["overlay_node_ids"]
    assert overlay_node["node_id"] in enhanced["visible_overlay_node_ids"]
    assert overlay_node["node_id"] not in baseline["overlay_node_ids"]
    assert overlay_node["node_id"] not in enhanced["included_node_ids"]
    assert overlay_node["node_id"] not in enhanced["path_overlay_node_ids"]
    assert enhanced["added_node_ids"] == []
    assert enhanced["path_overlay_edge_ids"] == []
    assert baseline["project_graph_hash"] != enhanced["project_graph_hash"]


async def test_graph_option_preview_ignores_unreviewed_overlay(client, db_session, project, profile):
    pending_node = await _create_overlay_target(
        client,
        project["id"],
        name="未审核路径对比 Overlay 目标",
        confirm_review=False,
    )
    project_row = await db_session.get(LearningProject, project["id"])
    assert project_row is not None
    baseline_target_ids = json.loads(project_row.confirmed_target_node_ids_json)
    project_row.goal_text = "未审核路径对比 Overlay 目标"
    project_row.goal_type = "concept"
    project_row.confirmed_target_node_ids_json = json.dumps([baseline_target_ids[0]], ensure_ascii=False)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/graph-options/preview",
        json={"path_mode": "standard"},
    )

    assert resp.status_code == 200
    variants = {variant["graph_option"]: variant for variant in resp.json()["variants"]}
    enhanced = variants["enhanced"]
    assert pending_node["node_id"] not in enhanced["included_node_ids"]
    assert pending_node["node_id"] not in enhanced["overlay_node_ids"]
    assert pending_node["node_id"] not in enhanced["visible_overlay_node_ids"]
    assert pending_node["node_id"] not in enhanced["path_overlay_node_ids"]
    assert enhanced["added_node_ids"] == []


async def test_graph_option_confirm_rejects_unavailable_option(client, db_session, project, profile):
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/graph-options/preview",
        json={"path_mode": "standard"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    baseline_variant_id = next(
        variant["variant_id"]
        for variant in preview["variants"]
        if variant["graph_option"] == "baseline"
    )
    session = await db_session.get(VariantPreviewSession, preview["variant_preview_id"])
    assert session is not None
    variants = json.loads(session.variants_json)
    for variant in variants:
        if variant["variant_id"] == baseline_variant_id:
            variant["status"] = "unavailable"
            variant["blocked_reason"] = "GOAL_TARGETS_REMOVED"
            variant.pop("plan_result", None)
    session.variants_json = json.dumps(variants, ensure_ascii=False, sort_keys=True)
    await db_session.commit()

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": baseline_variant_id},
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "GRAPH_OPTION_UNAVAILABLE"
    assert confirm_resp.json()["blocked_reason"] == "GOAL_TARGETS_REMOVED"


async def test_graph_option_confirm_rejects_project_graph_drift(client, project, profile):
    overlay_node = await _create_overlay_target(client, project["id"], name="漂移增强 Overlay 目标")
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/graph-options/preview",
        json={"path_mode": "standard"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    enhanced_variant_id = next(
        variant["variant_id"]
        for variant in preview["variants"]
        if variant["graph_option"] == "enhanced"
    )

    planning_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{overlay_node['node_id']}/planning",
        json={"planning_enabled": False},
    )
    assert planning_resp.status_code == 200

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": enhanced_variant_id},
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "STALE_VARIANT_PREVIEW"
    assert confirm_resp.json()["reason_code"] == "PROJECT_GRAPH_DRIFT"


async def test_graph_option_confirm_persists_selected_enhanced_path_audit(client, db_session, project, profile):
    overlay_node = await _create_overlay_target(client, project["id"], name="确认增强 Overlay 目标")
    project_row = await db_session.get(LearningProject, project["id"])
    assert project_row is not None
    baseline_target_ids = json.loads(project_row.confirmed_target_node_ids_json)
    project_row.goal_text = "确认增强 Overlay 目标"
    project_row.goal_type = "concept"
    project_row.confirmed_target_node_ids_json = json.dumps([baseline_target_ids[0]], ensure_ascii=False)
    await db_session.commit()

    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/graph-options/preview",
        json={"path_mode": "standard"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    enhanced_variant_id = next(
        variant["variant_id"]
        for variant in preview["variants"]
        if variant["graph_option"] == "enhanced"
    )

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": enhanced_variant_id},
    )
    duplicate_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": enhanced_variant_id},
    )

    assert confirm_resp.status_code == 200
    assert duplicate_resp.status_code == 200
    assert duplicate_resp.json()["idempotent"] is True
    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    latest_node_ids = [task["node_id"] for stage in latest["stages"] for task in stage["tasks"]]
    assert overlay_node["node_id"] in latest_node_ids
    assert latest["audit"]["graph_option"]["graph_option"] == "enhanced"
    assert latest["audit"]["variant"]["preview_kind"] == "graph_option"
    assert any(label["kind"] == "graph_option_preview" for label in latest["audit"]["authority_labels"])
    assert any(step["step"] == "graph_option_confirm" for step in latest["audit"]["decision_chain"])


async def test_variant_confirm_writes_one_learning_path_and_is_idempotent(client, db_session, project, profile):
    preview_resp = await client.post(f"/api/v1/projects/{project['id']}/plans/variants/preview")
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    variant_id = next(
        variant["variant_id"]
        for variant in preview["variants"]
        if variant["path_mode"] == "compressed"
    )

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": variant_id},
    )
    duplicate_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": variant_id},
    )

    assert confirm_resp.status_code == 200
    assert duplicate_resp.status_code == 200
    first = confirm_resp.json()
    duplicate = duplicate_resp.json()
    assert first["id"] == duplicate["id"]
    assert first["version"] == duplicate["version"]
    assert first["path_mode"] == "compressed"
    assert duplicate["idempotent"] is True

    paths = (
        await db_session.execute(select(LearningPath).where(LearningPath.project_id == project["id"]))
    ).scalars().all()
    assert len(paths) == 1
    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    latest = latest_resp.json()
    assert latest["id"] == first["id"]
    assert latest["audit"]["variant"]["variant_id"] == variant_id
    assert latest["audit"]["audit_schema_version"] == "formal_path_audit_v2"
    assert any(label["kind"] == "variant_preview" for label in latest["audit"]["authority_labels"])


async def test_variant_confirm_rejects_different_variant_after_confirmation(client, project, profile):
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/preview",
        json={"path_modes": ["standard", "compressed"]},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    first_variant = preview["variants"][0]["variant_id"]
    second_variant = preview["variants"][1]["variant_id"]
    assert (await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": first_variant},
    )).status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": second_variant},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "STALE_VARIANT_PREVIEW"


async def test_variant_confirm_rejects_expired_or_profile_drift(client, db_session, project, profile):
    preview_resp = await client.post(f"/api/v1/projects/{project['id']}/plans/variants/preview")
    preview = preview_resp.json()
    variant_id = preview["variants"][0]["variant_id"]
    session = await db_session.get(VariantPreviewSession, preview["variant_preview_id"])
    assert session is not None
    session.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    expired_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": variant_id},
    )
    assert expired_resp.status_code == 409
    assert expired_resp.json()["error"] == "STALE_VARIANT_PREVIEW"

    fresh_preview_resp = await client.post(f"/api/v1/projects/{project['id']}/plans/variants/preview")
    fresh_preview = fresh_preview_resp.json()
    db_session.add(LearnerProfile(
        project_id=project["id"],
        math_level=5,
        coding_level=5,
        ml_level=5,
        theory_weight=0.4,
        practice_weight=0.6,
        weekly_hours=12,
        deadline_weeks=10,
    ))
    await db_session.commit()

    drift_resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{fresh_preview['variant_preview_id']}/confirm",
        json={"variant_id": fresh_preview["variants"][0]["variant_id"]},
    )
    assert drift_resp.status_code == 409
    assert drift_resp.json()["error"] == "STALE_VARIANT_PREVIEW"
    assert drift_resp.json()["reason_code"] == "PROFILE_DRIFT"


async def test_variant_confirm_rejects_project_graph_drift(client, project, profile):
    preview_resp = await client.post(f"/api/v1/projects/{project['id']}/plans/variants/preview")
    assert preview_resp.status_code == 200
    preview = preview_resp.json()

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_a01",
        json={"status": "removed"},
    )
    assert review_resp.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": preview["variants"][0]["variant_id"]},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "STALE_VARIANT_PREVIEW"
    assert resp.json()["reason_code"] == "PROJECT_GRAPH_DRIFT"


async def test_variant_confirm_rejects_cross_project_preview(client, project, profile):
    preview_resp = await client.post(f"/api/v1/projects/{project['id']}/plans/variants/preview")
    preview = preview_resp.json()

    other_preview_resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={"goal_text": "理解梯度下降"},
    )
    assert other_preview_resp.status_code == 200
    other_preview = other_preview_resp.json()
    other_project_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "另一个项目",
            "goal_text": "理解梯度下降",
            "resolution_session_id": other_preview["session_id"],
            "selected_candidate_id": other_preview["recommended_candidate_id"],
        },
    )
    assert other_project_resp.status_code == 200
    other_project = other_project_resp.json()
    other_profile_resp = await client.post(
        f"/api/v1/projects/{other_project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.6,
            "practice_weight": 0.4,
            "weekly_hours": 10,
            "deadline_weeks": 12,
        },
    )
    assert other_profile_resp.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{other_project['id']}/plans/variants/{preview['variant_preview_id']}/confirm",
        json={"variant_id": preview["variants"][0]["variant_id"]},
    )

    assert resp.status_code == 409
    assert resp.json()["error"] == "STALE_VARIANT_PREVIEW"


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


async def test_generate_plan_audit_includes_formal_decision_chain(client, project, profile):
    plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_resp.status_code == 200

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    audit = latest_resp.json()["audit"]

    assert audit["audit_schema_version"] == "formal_path_audit_v2"
    assert audit["goal_frame"]["schema_version"] == "v1"
    assert audit["coverage_decision"]["coverage_status"] == "covered"
    assert audit["selected_candidate"]["candidate_id"] == project["goal_resolution"]["selected_candidate_id"]
    assert audit["user_confirmation"]["confirmed_target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]
    assert audit["planner_inputs"]["confirmed_target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]
    assert audit["derived_planner_parameters"]["path_mode"] == audit["path_mode"]
    assert audit["llm_fallback_status"]["authority"] == "rules_first"
    assert any(label["kind"] == "rules_authority" for label in audit["authority_labels"])
    assert [step["step"] for step in audit["decision_chain"]][:2] == ["goal_frame", "coverage_decision"]


async def test_generate_plan_audit_includes_clarification_trace(client):
    with patch(
        "app.services.goal_resolution_service.resolve_goal_candidates",
        return_value={
            "auto_detected_goal_type": "domain",
            "effective_goal_type": "domain",
            "goal_type_source": "auto",
            "recommended_candidate_id": None,
            "candidates": [],
            "warnings": [],
        },
    ):
        preview_resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "AI"})
    assert preview_resp.status_code == 200
    preview = preview_resp.json()

    answer_resp = await client.post(
        f"/api/v1/goal-resolution/clarifications/{preview['clarification_session_id']}/answers",
        json={"answers": [{"question_id": "goal_direction", "selected_option_id": "machine_learning_foundation"}]},
    )
    assert answer_resp.status_code == 200
    coverage = answer_resp.json()["coverage_response"]

    project_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "澄清审计",
            "goal_text": coverage["goal_frame"]["raw_text"],
            "resolution_session_id": coverage["session_id"],
            "selected_candidate_id": coverage["recommended_candidate_id"],
        },
    )
    assert project_resp.status_code == 200
    project_data = project_resp.json()
    profile_resp = await client.post(
        f"/api/v1/projects/{project_data['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.6,
            "practice_weight": 0.4,
            "weekly_hours": 10,
            "deadline_weeks": 12,
        },
    )
    assert profile_resp.status_code == 200

    plan_resp = await client.post(f"/api/v1/projects/{project_data['id']}/plans")
    assert plan_resp.status_code == 200
    latest_resp = await client.get(f"/api/v1/projects/{project_data['id']}/plans/latest")
    audit = latest_resp.json()["audit"]

    assert audit["clarification_trace_ids"] == [preview["clarification_session_id"]]
    assert audit["clarification_trace"]["status"] == "resolved"
    assert any(step["step"] == "clarification" for step in audit["decision_chain"])


async def test_generate_plan_audit_discloses_partial_acceptance(client):
    preview_resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "随机森林和监督学习"})
    assert preview_resp.status_code == 200
    preview = preview_resp.json()

    project_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "部分覆盖路径审计",
            "goal_text": "随机森林和监督学习",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["candidates"][0]["candidate_id"],
            "accept_partial": True,
        },
    )
    assert project_resp.status_code == 200
    project = project_resp.json()

    profile_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 2,
            "coding_level": 2,
            "ml_level": 1,
            "theory_weight": 0.6,
            "practice_weight": 0.4,
            "weekly_hours": 10,
            "deadline_weeks": 12,
        },
    )
    assert profile_resp.status_code == 200

    plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_resp.status_code == 200

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    goal_result = latest_resp.json()["audit"]["goal_result"]
    assert goal_result["partial_accepted"] is True
    assert "随机森林" in goal_result["missing_concepts"]
    assert goal_result["target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]


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

    legacy_keys = {
        "node_explanations",
        "ordering_explanations",
        "stage_explanations",
        "budget_explanation",
        "reinforcement_explanations",
        "dependency_chain_explanations",
    }
    legacy_projection = {key: data[key] for key in legacy_keys}
    assert set(legacy_projection) == legacy_keys
    assert isinstance(legacy_projection["node_explanations"], list)
    assert isinstance(legacy_projection["ordering_explanations"], list)
    assert isinstance(legacy_projection["stage_explanations"], list)
    assert "readability" not in legacy_projection
    assert "meta" not in legacy_projection

    trace = data["readability"]["trace_summary"]
    assert any(label["kind"] == "rules_authority" for label in trace["authority_labels"])
    assert any(label["kind"] == "ai_assisted_understanding" for label in trace["authority_labels"])
    assert [step["step"] for step in trace["decision_chain"]][:2] == ["goal_frame", "coverage_decision"]
    highlights = {item["key"]: item for item in data["readability"]["audit_highlights"]}
    assert "authority_labels" in highlights
    assert "decision_chain" in highlights

    assert data["meta"]["plan_version"] == plan["version"]
    assert data["meta"]["provenance"]["truth_source"] == "plan_audit_snapshot"
    assert data["meta"]["polish"]["requested"] is False
    assert data["meta"]["polish"]["applied"] is False


async def test_get_explanation_uses_cached_rule_response(client, db_session, project, plan):
    first_resp = await client.get(f"/api/v1/projects/{project['id']}/explanation")
    assert first_resp.status_code == 200
    first_data = first_resp.json()

    result = await db_session.execute(
        select(PlanExplanationCache).where(
            PlanExplanationCache.path_id == plan["id"],
            PlanExplanationCache.polish_requested.is_(False),
        )
    )
    assert result.scalar_one().plan_version == plan["version"]

    with patch("app.api.v1.plans.build_explanation") as build_mock:
        second_resp = await client.get(f"/api/v1/projects/{project['id']}/explanation")

    assert second_resp.status_code == 200
    assert second_resp.json() == first_data
    build_mock.assert_not_called()


async def test_get_explanation_uses_cached_successful_polish(client, db_session, project, plan):
    from app.schemas.explanation import PolishMeta

    def fake_polish(response, *, requested=True):
        meta = response.meta.model_copy(
            update={"polish": PolishMeta(requested=requested, applied=True, scope=["test"])}
        )
        return response.model_copy(update={"meta": meta})

    with patch("app.api.v1.plans.polish_explanation", side_effect=fake_polish) as polish_mock:
        first_resp = await client.get(f"/api/v1/projects/{project['id']}/explanation?polish=true")

    assert first_resp.status_code == 200
    assert first_resp.json()["meta"]["polish"]["applied"] is True
    assert polish_mock.call_count == 1

    result = await db_session.execute(
        select(PlanExplanationCache).where(
            PlanExplanationCache.path_id == plan["id"],
            PlanExplanationCache.polish_requested.is_(True),
        )
    )
    assert result.scalar_one().plan_version == plan["version"]

    with patch("app.api.v1.plans.polish_explanation") as second_polish_mock:
        second_resp = await client.get(f"/api/v1/projects/{project['id']}/explanation?polish=true")

    assert second_resp.status_code == 200
    assert second_resp.json() == first_resp.json()
    second_polish_mock.assert_not_called()


async def test_get_explanation_does_not_cache_failed_polish(client, db_session, project, plan, monkeypatch):
    from app.core.config import get_settings, replace_runtime_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    replace_runtime_settings({"llm_api_key": "", "llm_explanation_polish": "true"})

    resp = await client.get(f"/api/v1/projects/{project['id']}/explanation?polish=true")
    assert resp.status_code == 200
    assert resp.json()["meta"]["polish"]["fallback_reason"] == "missing_api_key"

    result = await db_session.execute(
        select(PlanExplanationCache).where(
            PlanExplanationCache.path_id == plan["id"],
            PlanExplanationCache.polish_requested.is_(True),
        )
    )
    assert result.scalar_one_or_none() is None


async def test_get_explanation_polish_metadata_reports_disabled(client, project, plan, monkeypatch):
    from app.core.config import get_settings, replace_runtime_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    get_settings.cache_clear()
    replace_runtime_settings({})

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/explanation?polish=true"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["meta"]["polish"]["requested"] is True
    assert data["meta"]["polish"]["applied"] is False
    assert data["meta"]["polish"]["scope"] == []
    assert data["meta"]["polish"]["fallback_reason"] == "disabled"


async def test_get_explanation_without_llm_key_still_returns_readability(client, project, plan, monkeypatch):
    from app.core.config import get_settings, replace_runtime_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    replace_runtime_settings({"llm_api_key": "", "llm_explanation_polish": "true"})

    resp = await client.get(
        f"/api/v1/projects/{project['id']}/explanation?polish=true"
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["readability"] is not None
    readability = data["readability"]
    assert readability["overview_summary"]["headline"]
    assert readability["overview_summary"]["node_count"] > 0
    assert [step["step_id"] for step in readability["generation_steps"]] == [
        "goal_resolution",
        "prerequisite_closure",
        "profile_reinforcement",
        "topological_ordering",
        "stage_assignment",
        "time_budget",
    ]
    assert readability["node_groups"]
    assert readability["ordering_summary"]["summary"]
    assert readability["stage_summary"]["summary"]
    assert readability["budget_summary"]["summary"]
    assert readability["audit_highlights"]
    assert data["meta"]["polish"]["requested"] is True
    assert data["meta"]["polish"]["applied"] is False
    assert data["meta"]["polish"]["fallback_reason"] == "missing_api_key"


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
    assert data["meta"]["provenance"]["fallback_used"] is True
    assert "filtered_requires_rev_adj_missing" in data["meta"]["provenance"]["fallback_reasons"]
    assert "requires_rev_adj" in data["meta"]["provenance"]["live_pack_fields"]


async def test_get_explanation_prefers_persisted_plan_snapshot(client, db_session, project, plan):
    from app.models.sqlite_models import LearningPath

    result = await db_session.execute(
        select(LearningPath)
        .where(LearningPath.project_id == project["id"])
        .order_by(LearningPath.created_at.desc())
        .limit(1)
    )
    path = result.scalar_one()
    plan_data = json.loads(path.plan_json)
    first_stage_tasks = next(tasks for tasks in plan_data.values() if tasks)
    node_id = first_stage_tasks[0]["node_id"]
    first_stage_tasks[0]["name"] = "持久化快照节点名"
    first_stage_tasks[0]["difficulty"] = 1
    first_stage_tasks[0]["importance"] = 5
    first_stage_tasks[0]["estimated_hours"] = 1.5
    path.plan_json = json.dumps(plan_data, ensure_ascii=False)
    await db_session.commit()

    baseline_resp = await client.get(f"/api/v1/projects/{project['id']}/explanation")
    assert baseline_resp.status_code == 200
    baseline_data = baseline_resp.json()
    baseline_node = next(item for item in baseline_data["node_explanations"] if item["node_id"] == node_id)
    baseline_order = next(item for item in baseline_data["ordering_explanations"] if item["node_id"] == node_id)
    baseline_stage = next(item for item in baseline_data["readability"]["stage_summary"]["stages"] if node_id in item["node_ids"])
    baseline_dependency_chains = baseline_data["dependency_chain_explanations"]
    baseline_dependency_highlight = next(
        item for item in baseline_data["readability"]["audit_highlights"]
        if item["key"] == "dependency_closure"
    )

    pack = get_domain_pack_service(project["domain"])
    original_node = dict(pack.nodes_by_id[node_id])
    original_scoring_config = pack.scoring_config
    original_requires_rev_adj = pack.requires_rev_adj
    pack.nodes_by_id[node_id]["name"] = "live pack 漂移节点名"
    pack.nodes_by_id[node_id]["difficulty_final"] = 5
    pack.nodes_by_id[node_id]["importance_final"] = 1
    pack.nodes_by_id[node_id]["estimated_hours"] = 99.0
    pack.scoring_config = {
        **pack.scoring_config,
        "priority_weights": {"importance": 10.0, "goal_relevance": 0.0},
    }
    pack.requires_rev_adj = {node_id: ["live_pack_only_dependency"]}
    try:
        resp = await client.get(f"/api/v1/projects/{project['id']}/explanation")
    finally:
        pack.nodes_by_id[node_id].clear()
        pack.nodes_by_id[node_id].update(original_node)
        pack.scoring_config = original_scoring_config
        pack.requires_rev_adj = original_requires_rev_adj

    assert resp.status_code == 200
    data = resp.json()
    node = next(item for item in data["node_explanations"] if item["node_id"] == node_id)
    order = next(item for item in data["ordering_explanations"] if item["node_id"] == node_id)
    stage = next(item for item in data["readability"]["stage_summary"]["stages"] if node_id in item["node_ids"])
    assert node["node_name"] == "持久化快照节点名"
    assert order["factors"] == baseline_order["factors"]
    assert stage["estimated_hours"] == baseline_stage["estimated_hours"]
    assert data["dependency_chain_explanations"] == baseline_dependency_chains
    assert next(
        item for item in data["readability"]["audit_highlights"]
        if item["key"] == "dependency_closure"
    ) == baseline_dependency_highlight
    assert data["readability"]["overview_summary"] == baseline_data["readability"]["overview_summary"]
    assert data["readability"]["ordering_summary"] == baseline_data["readability"]["ordering_summary"]
    assert data["readability"]["budget_summary"] == baseline_data["readability"]["budget_summary"]
    assert data["meta"]["provenance"] == baseline_data["meta"]["provenance"]


async def test_ask_explanation_requires_node_id_for_node_specific_question(client, project, plan):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "why_include_node"},
    )

    assert resp.status_code == 422


async def test_ask_explanation_invalid_node_id_returns_limitation(client, project, plan):
    latest_before = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_before.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "why_stage_assignment", "node_id": "missing_node"},
    )

    latest_after = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_after.status_code == 200

    assert resp.status_code == 200
    data = resp.json()
    assert data["question_id"] == "why_stage_assignment"
    assert data["ai_used"] is False
    assert data["fallback_reason"] == "invalid_node_id"
    assert data["limitations"] == ["node_not_in_latest_plan"]
    assert latest_after.json() == latest_before.json()


async def test_ask_explanation_invalid_question_does_not_mutate_latest_plan(client, project, plan):
    latest_before = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_before.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "not_a_question"},
    )

    latest_after = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_after.status_code == 200

    assert resp.status_code == 422
    assert latest_after.json() == latest_before.json()


async def test_ask_explanation_uses_plan_json_membership_not_audit_residue(client, db_session, project, plan):
    from app.models.sqlite_models import LearningPath

    result = await db_session.execute(
        select(LearningPath)
        .where(LearningPath.project_id == project["id"])
        .order_by(LearningPath.created_at.desc())
        .limit(1)
    )
    path = result.scalar_one()
    audit = json.loads(path.audit_json)
    audit.setdefault("ordering_logs", {})["audit_only_node"] = {
        "priority_score": 1.0,
        "goal_relevance": 1.0,
        "factor_details": {},
    }
    audit.setdefault("stage_logs", {})["audit_only_node"] = {
        "assigned_stage": "核心掌握",
        "reasons": ["default_stage_rule"],
    }
    path.audit_json = json.dumps(audit, ensure_ascii=False)
    await db_session.commit()

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "why_stage_assignment", "node_id": "audit_only_node"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ai_used"] is False
    assert data["fallback_reason"] == "invalid_node_id"
    assert data["limitations"] == ["node_not_in_latest_plan"]


async def test_ask_explanation_ai_success_does_not_override_rule_explanation(client, project, plan, monkeypatch):
    from types import SimpleNamespace

    from app.core.config import get_settings, replace_runtime_settings
    from app.services import explanation_service

    get_settings.cache_clear()
    replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
    })

    before_explanation = await client.get(f"/api/v1/projects/{project['id']}/explanation")
    assert before_explanation.status_code == 200
    before_data = before_explanation.json()
    node_id = before_data["node_explanations"][0]["node_id"]
    latest_before = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_before.status_code == 200

    def fake_llm_client(_llm_cfg, _llm_client_factory, *, timeout):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        content='{"answer":"这是 AI 辅助回答，但不改规则解释。","limitations":["ai_auxiliary"]}'
                    )
                )
            ]
        )
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **_kwargs: response)
            )
        )

    monkeypatch.setattr(explanation_service, "_build_llm_client", fake_llm_client)

    ask_resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "why_include_node", "node_id": node_id},
    )
    after_explanation = await client.get(f"/api/v1/projects/{project['id']}/explanation")
    latest_after = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")

    assert ask_resp.status_code == 200
    ask_data = ask_resp.json()
    assert ask_data["ai_used"] is True
    assert ask_data["fallback_reason"] is None
    assert after_explanation.status_code == 200
    after_data = after_explanation.json()
    assert after_data["node_explanations"] == before_data["node_explanations"]
    assert after_data["ordering_explanations"] == before_data["ordering_explanations"]
    assert after_data["stage_explanations"] == before_data["stage_explanations"]
    assert after_data["budget_explanation"] == before_data["budget_explanation"]
    assert latest_after.status_code == 200
    assert latest_after.json() == latest_before.json()


async def test_ask_explanation_is_stateless_and_keeps_latest_plan(client, project, plan, monkeypatch):
    from app.core.config import get_settings, replace_runtime_settings

    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    replace_runtime_settings({"llm_api_key": ""})

    latest_before = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_before.status_code == 200

    first_resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "why_path_order"},
    )
    second_resp = await client.post(
        f"/api/v1/projects/{project['id']}/explanation/ask",
        json={"question_id": "why_path_order"},
    )

    latest_after = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_after.status_code == 200

    first_data = first_resp.json()
    second_data = second_resp.json()
    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    assert first_data == second_data
    assert first_data["question_id"] == "why_path_order"
    assert first_data["ai_used"] is False
    assert first_data["fallback_reason"] == "missing_api_key"
    assert latest_after.json()["version"] == latest_before.json()["version"]
    assert latest_after.json()["stages"] == latest_before.json()["stages"]


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
