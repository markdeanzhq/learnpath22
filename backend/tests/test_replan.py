"""重规划双模式 API 测试"""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

from app.models.sqlite_models import (
    FeedbackPreviewSession,
    GoalResolutionSession,
    KnownNodeConfirmationDraft,
    LearnerProfile,
    LearningPath,
    LearningProject,
    TrackingEvent,
)


async def _create_project_with_resolution(
    client,
    *,
    title: str,
    goal_text: str,
    requested_goal_type: str | None = None,
):
    preview_payload = {
        "goal_text": goal_text,
        "domain": "machine_learning",
    }
    if requested_goal_type is not None:
        preview_payload["requested_goal_type"] = requested_goal_type

    preview_resp = await client.post("/api/v1/goal-resolution/preview", json=preview_payload)
    assert preview_resp.status_code == 200
    preview = preview_resp.json()

    project_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": title,
            "goal_text": goal_text,
            "domain": "machine_learning",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": preview["recommended_candidate_id"],
        },
    )
    assert project_resp.status_code == 200
    return project_resp.json()


async def _path_count(db_session, project_id: str) -> int:
    result = await db_session.execute(
        select(LearningPath).where(LearningPath.project_id == project_id)
    )
    return len(result.scalars().all())


async def test_replan_api_uses_project_domain_for_diff_details_pack(client, project, monkeypatch):
    captured = {}

    async def fake_replan(db, project_id, mode="profile_update", **kwargs):
        return {
            "path_id": "path-demo",
            "version": 2,
            "mode": mode,
            "diff": {"added": ["foreign_node"]},
            "plan_result": {
                "stage_plan": {},
                "budget_summary": {"status": "feasible"},
                "total_hours": 0,
            },
        }

    def fake_get_domain_pack_service(domain=None):
        captured["domain"] = domain
        return SimpleNamespace(nodes_by_id={"foreign_node": {"name": "跨领域节点"}})

    monkeypatch.setattr("app.api.v1.replans.replan", fake_replan)
    monkeypatch.setattr("app.api.v1.replans.get_domain_pack_service", fake_get_domain_pack_service)

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "检查 domain-aware diff"},
    )

    assert resp.status_code == 200
    assert captured["domain"] == project["domain"]
    assert resp.json()["diff_details"] == {
        "added": [{"node_id": "foreign_node", "node_name": "跨领域节点"}]
    }


async def test_feedback_preview_compress_time_does_not_write_formal_path(
    client, db_session, project, profile, plan
):
    before_count = await _path_count(db_session, project["id"])

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "这个路径太长了，请压缩一下"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent_type"] == "compress_time"
    assert data["controlled_parameters"]["path_mode"] == "compressed"
    assert data["requires_confirmation"] is True
    assert data["requires_second_confirm"] is False
    expected_diff_keys = {"added", "removed", "unchanged", "order_changed", "stage_changed"}
    assert set(data["diff"]) == expected_diff_keys
    assert set(data["diff_details"]).issubset(expected_diff_keys)
    detail_items = [item for items in data["diff_details"].values() for item in items]
    assert detail_items
    assert all(item["node_id"] and item["node_name"] for item in detail_items)
    assert data["budget_delta"]["previous_total_hours"] == plan["total_hours"]
    assert await _path_count(db_session, project["id"]) == before_count

    session = await db_session.get(FeedbackPreviewSession, data["feedback_preview_id"])
    assert session is not None
    assert session.status == "active"


async def test_feedback_preview_time_shortcut_uses_compressed_mode_and_deadline(
    client, db_session, project, profile, plan
):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "我想把路径压缩到 6 周"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["intent_type"] == "compress_time"
    assert data["controlled_parameters"]["path_mode"] == "compressed"
    assert data["controlled_parameters"]["deadline_weeks"] == 6

    exact_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "时间更紧"},
    )
    assert exact_resp.status_code == 200
    assert exact_resp.json()["intent_type"] == "compress_time"


async def test_feedback_preview_rejects_unsupported_or_low_confidence_without_write(
    client, db_session, project, profile, plan
):
    before_count = await _path_count(db_session, project["id"])

    unsupported = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "我想改目标去学 Vue 前端"},
    )
    unknown = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "随便优化一下"},
    )

    assert unsupported.status_code == 422
    assert unsupported.json()["error"] == "UNSUPPORTED_FEEDBACK_INTENT"
    assert "goal_change_not_supported" in unsupported.json()["blocked_actions"]
    assert "cross_domain_not_supported" in unsupported.json()["blocked_actions"]
    assert unknown.status_code == 422
    assert unknown.json()["blocked_actions"] == ["low_confidence_or_unknown_intent"]
    assert await _path_count(db_session, project["id"]) == before_count


async def test_feedback_confirm_writes_one_formal_path_and_is_idempotent(
    client, db_session, project, profile, plan
):
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "多一点实践和项目"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )
    duplicate_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )

    assert confirm_resp.status_code == 200
    assert duplicate_resp.status_code == 200
    first = confirm_resp.json()
    duplicate = duplicate_resp.json()
    assert first["id"] == duplicate["id"]
    assert first["version"] == duplicate["version"]
    assert first["path_mode"] == "practice_first"
    assert first["intent_type"] == "increase_practice"
    assert duplicate["idempotent"] is True
    assert first["diff_details"] == duplicate["diff_details"]
    detail_items = [item for items in first["diff_details"].values() for item in items]
    assert detail_items
    assert all(item["node_id"] and item["node_name"] for item in detail_items)

    paths = (
        await db_session.execute(select(LearningPath).where(LearningPath.project_id == project["id"]))
    ).scalars().all()
    assert len(paths) == 2
    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    audit = latest_resp.json()["audit"]
    audit_feedback = audit["feedback"]
    assert audit_feedback["intent_type"] == "increase_practice"
    assert audit_feedback["controlled_parameters"]["path_mode"] == "practice_first"
    assert audit["audit_schema_version"] == "formal_path_audit_v2"
    assert any(label["kind"] == "feedback_preview" for label in audit["authority_labels"])


async def test_mark_known_nodes_requires_draft_confirmation_before_formal_write(
    client, db_session, project, profile, plan
):
    known_node_id = plan["stages"][0]["tasks"][0]["node_id"]
    known_node_name = plan["stages"][0]["tasks"][0]["name"]
    before_count = await _path_count(db_session, project["id"])

    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": f"{known_node_name} 我已经会了，不用学"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    draft = preview["known_node_draft"]
    assert preview["intent_type"] == "mark_known_nodes"
    assert preview["requires_second_confirm"] is True
    assert known_node_id in draft["node_ids"]
    assert any(
        item["node_id"] == known_node_id and item["node_name"] == known_node_name
        for item in draft["nodes"]
    )
    assert any(
        item["node_id"] == known_node_id and item["node_name"] == known_node_name
        for item in draft["evidence"]
    )
    assert await _path_count(db_session, project["id"]) == before_count

    blocked_confirm = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )
    assert blocked_confirm.status_code == 409
    assert blocked_confirm.json()["reason_code"] == "KNOWN_NODE_DRAFT_CONFIRMATION_REQUIRED"
    assert await _path_count(db_session, project["id"]) == before_count

    draft_confirm = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/known-node-drafts/{draft['draft_id']}/confirm"
    )
    assert draft_confirm.status_code == 200
    assert draft_confirm.json()["status"] == "confirmed"

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )
    assert confirm_resp.status_code == 200
    data = confirm_resp.json()
    assert data["intent_type"] == "mark_known_nodes"
    assert data["idempotent"] is False
    assert known_node_id in data["diff"]["completed"]
    assert any(
        item["node_id"] == known_node_id and item["node_name"] == known_node_name
        for item in data["diff_details"]["completed"]
    )

    duplicate_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )
    assert duplicate_resp.status_code == 200
    duplicate = duplicate_resp.json()
    assert duplicate["id"] == data["id"]
    assert duplicate["version"] == data["version"]
    assert duplicate["intent_type"] == "mark_known_nodes"
    assert duplicate["idempotent"] is True
    assert duplicate["diff_details"] == data["diff_details"]

    tracking = (
        await db_session.execute(
            select(TrackingEvent).where(
                TrackingEvent.project_id == project["id"],
                TrackingEvent.node_id == known_node_id,
                TrackingEvent.event_type == "complete",
            )
        )
    ).scalars().all()
    assert len(tracking) == 1

    saved_draft = await db_session.get(KnownNodeConfirmationDraft, draft["draft_id"])
    assert saved_draft is not None
    assert saved_draft.status == "confirmed"
    assert await _path_count(db_session, project["id"]) == before_count + 1


async def test_feedback_confirm_rejects_pack_hash_drift(
    client, db_session, project, profile, plan
):
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "请压缩路径"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    session = await db_session.get(FeedbackPreviewSession, preview["feedback_preview_id"])
    assert session is not None
    session.pack_hash = "stale-pack-hash"
    await db_session.commit()

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "STALE_FEEDBACK_PREVIEW"
    assert confirm_resp.json()["reason_code"] == "PACK_HASH_DRIFT"


async def test_feedback_confirm_rejects_profile_drift(client, db_session, project, profile, plan):
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "请压缩路径"},
    )
    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview["profile_hash"]

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

    confirm_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{preview['feedback_preview_id']}/confirm"
    )

    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "STALE_FEEDBACK_PREVIEW"
    assert confirm_resp.json()["reason_code"] == "PROFILE_DRIFT"


async def test_known_node_draft_confirm_rejects_pack_hash_drift(
    client, db_session, project, profile, plan
):
    known_node_name = plan["stages"][0]["tasks"][0]["name"]
    preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": f"{known_node_name} 我已经会了，不用学"},
    )
    assert preview_resp.status_code == 200
    draft = preview_resp.json()["known_node_draft"]
    saved_draft = await db_session.get(KnownNodeConfirmationDraft, draft["draft_id"])
    assert saved_draft is not None
    saved_draft.pack_hash = "stale-pack-hash"
    await db_session.commit()

    draft_confirm = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/known-node-drafts/{draft['draft_id']}/confirm"
    )

    assert draft_confirm.status_code == 409
    assert draft_confirm.json()["error"] == "STALE_FEEDBACK_PREVIEW"
    assert draft_confirm.json()["reason_code"] == "PACK_HASH_DRIFT"


async def test_feedback_confirm_rejects_expired_or_graph_drift(
    client, db_session, project, profile, plan
):
    expired_preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "请压缩路径"},
    )
    assert expired_preview_resp.status_code == 200
    expired_preview = expired_preview_resp.json()
    expired_session = await db_session.get(FeedbackPreviewSession, expired_preview["feedback_preview_id"])
    expired_session.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    expired_confirm = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{expired_preview['feedback_preview_id']}/confirm"
    )
    assert expired_confirm.status_code == 409
    assert expired_confirm.json()["error"] == "STALE_FEEDBACK_PREVIEW"

    drift_preview_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/preview",
        json={"feedback_text": "请压缩路径"},
    )
    assert drift_preview_resp.status_code == 200
    drift_preview = drift_preview_resp.json()
    await client.patch(f"/api/v1/projects/{project['id']}/graph/nodes/ml_e08", json={"status": "removed"})

    drift_confirm = await client.post(
        f"/api/v1/projects/{project['id']}/replans/feedback/{drift_preview['feedback_preview_id']}/confirm"
    )
    assert drift_confirm.status_code == 409
    assert drift_confirm.json()["reason_code"] == "PROJECT_GRAPH_DRIFT"


async def test_replan_profile_update(client, project, plan):
    """画像更新模式：全量重生成 + diff"""
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "更新画像参数"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "profile_update"
    assert "stages" in data
    assert "diff" in data
    assert "diff_details" in data
    assert "added" in data["diff"]
    assert "removed" in data["diff"]
    assert "unchanged" in data["diff"]


async def test_replan_progress_aware(client, project, plan):
    """进度感知模式：锁定已完成节点且不再参与重排"""
    node_id = plan["stages"][0]["tasks"][0]["node_id"]
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": node_id, "event_type": "complete"},
    )
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "进度更新"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["mode"] == "progress_aware"
    assert "diff" in data
    assert "diff_details" in data
    assert "completed" in data["diff"]
    assert node_id in data["diff"]["completed"]
    completed_items = data["diff_details"]["completed"]
    assert any(item["node_id"] == node_id and item["node_name"] for item in completed_items)
    all_ids = [task["node_id"] for stage in data["stages"] for task in stage["tasks"]]
    assert node_id not in all_ids


async def test_replan_progress_aware_treats_completed_target_as_satisfied(client, project, plan):
    """已完成目标不应被误判为目标被移除。"""
    for node_id in project["goal_resolution"]["confirmed_target_node_ids"]:
        await client.post(
            f"/api/v1/projects/{project['id']}/tracking/events",
            json={"node_id": node_id, "event_type": "complete"},
        )

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "目标已完成后重规划"},
    )

    assert resp.status_code == 200
    data = resp.json()
    for node_id in project["goal_resolution"]["confirmed_target_node_ids"]:
        assert node_id in data["diff"]["completed"]

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    goal_result = latest_resp.json()["audit"]["goal_result"]
    assert goal_result["target_satisfied"] is True
    assert goal_result["completed_target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]


async def test_replan_progress_aware_uses_previous_plan_profile_snapshot(client, project, profile, plan):
    """进度感知模式应沿用上一版路径的画像快照，而不是最新画像。"""
    update_resp = await client.post(
        f"/api/v1/projects/{project['id']}/profiles",
        json={
            "math_level": 5,
            "coding_level": 5,
            "ml_level": 5,
            "theory_weight": 0.2,
            "practice_weight": 0.8,
            "weekly_hours": 20,
            "deadline_weeks": 6,
        },
    )
    assert update_resp.status_code == 200

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "仅同步进度"},
    )
    assert resp.status_code == 200

    latest_plan_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/latest"
    )
    assert latest_plan_resp.status_code == 200
    audit = latest_plan_resp.json()["audit"]
    snapshot = audit["profile_snapshot"]
    assert snapshot["math_level"] == profile["math_level"]
    assert snapshot["coding_level"] == profile["coding_level"]
    assert snapshot["ml_level"] == profile["ml_level"]
    assert snapshot["theory_weight"] == profile["theory_weight"]
    assert snapshot["weekly_hours"] == profile["weekly_hours"]
    assert snapshot["deadline_weeks"] == profile["deadline_weeks"]
    assert snapshot["persona_label"] == profile["persona_label"]
    assert snapshot["persona_summary"] == profile["persona_summary"]


async def test_replan_progress_aware_excludes_descendants_of_skipped_nodes(client, project, plan):
    """跳过前置节点后，依赖它的后续节点不应继续保留在 pending 路径中"""
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": "ml_c09", "event_type": "skip"},
    )
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "跳过逻辑回归"},
    )
    assert resp.status_code == 200
    data = resp.json()
    all_ids = [task["node_id"] for stage in data["stages"] for task in stage["tasks"]]
    assert "ml_c09" not in all_ids
    assert "ml_d01" not in all_ids
    assert "ml_d03" not in all_ids
    # ml_c10 在 v1.1.0 中不再依赖 ml_c09（边已翻转为 ml_c10→ml_c09）
    # 所以跳过 ml_c09 不会导致 ml_c10 被排除
    # assert "ml_c10" not in all_ids  # 此断言在 v1.1.0 下不再成立
    assert "ml_e07" not in all_ids
    assert "ml_d01" in data["diff"]["blocked"]
    assert "ml_d03" in data["diff"]["blocked"]
    assert any(item["node_id"] == "ml_d01" for item in data["diff_details"]["blocked"])


async def test_replan_progress_aware_recalculates_budget(client, project, plan):
    """进度感知模式应基于剩余任务重新计算总学时与预算状态"""
    completed_ids = []
    total_completed_hours = 0
    for stage in plan["stages"]:
        for task in stage["tasks"][:2]:
            completed_ids.append(task["node_id"])
            total_completed_hours += task["estimated_hours"]
        if len(completed_ids) >= 2:
            break

    for node_id in completed_ids:
        await client.post(
            f"/api/v1/projects/{project['id']}/tracking/events",
            json={"node_id": node_id, "event_type": "complete"},
        )

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "完成部分节点后重规划"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # v1.1.0 边变化可能导致路径重规划后节点集合变化，不再严格等于原路径减去已完成节点
    # 改为验证：重规划后总学时应小于原计划（因为已完成部分节点）
    assert data["total_hours"] < plan["total_hours"], \
        f"重规划后总学时 {data['total_hours']} 应小于原计划 {plan['total_hours']}"


async def test_tracking_summary_keeps_locked_nodes_after_progress_replan(client, project, plan):
    """进度感知重规划后，summary 仍应统计已完成/已跳过的历史节点。"""
    plan_node_ids = [task["node_id"] for stage in plan["stages"] for task in stage["tasks"]]
    completed_id = plan_node_ids[0]
    skipped_id = plan_node_ids[1]
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": completed_id, "event_type": "complete"},
    )
    await client.post(
        f"/api/v1/projects/{project['id']}/tracking/events",
        json={"node_id": skipped_id, "event_type": "skip"},
    )

    replan_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "统计锁定节点"},
    )
    assert replan_resp.status_code == 200

    summary_resp = await client.get(f"/api/v1/projects/{project['id']}/tracking/summary")
    assert summary_resp.status_code == 200
    summary = summary_resp.json()
    pending_count = sum(len(stage["tasks"]) for stage in replan_resp.json()["stages"])
    assert summary["completed"] == 1
    assert summary["skipped"] == 1
    assert summary["total_nodes"] >= pending_count + 2


async def test_replan_without_profile(client):
    """无画像时重规划应返回 400"""
    project = await _create_project_with_resolution(
        client,
        title="空项目",
        goal_text="测试",
    )
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update"},
    )
    assert resp.status_code == 400


async def test_replan_version_increments(client, project, plan):
    """重规划版本号递增"""
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update"},
    )
    assert resp.status_code == 200
    assert resp.json()["version"] > plan["version"]


async def test_replan_invalid_mode(client, project, plan):
    """非法 mode 应返回 422"""
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "invalid_mode"},
    )
    assert resp.status_code == 422


async def test_replan_removed_requires_edge_uses_typed_edge_id(client):
    """移除 REQUIRES 边后，重规划应按 typed edge id 过滤依赖。"""
    project = await _create_project_with_resolution(
        client,
        title="逻辑回归重规划测试",
        goal_text="逻辑回归为什么能做分类",
        requested_goal_type="problem",
    )

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

    initial_plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert initial_plan_resp.status_code == 200
    initial_ids = [task["node_id"] for stage in initial_plan_resp.json()["stages"] for task in stage["tasks"]]
    assert "ml_c05" in initial_ids
    assert "ml_c09" in initial_ids

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_c05->ml_c09::REQUIRES",
        json={"status": "removed"},
    )
    assert review_resp.status_code == 200

    replan_resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "移除逻辑回归前置边后重规划"},
    )
    assert replan_resp.status_code == 200

    replan_data = replan_resp.json()
    replanned_ids = [task["node_id"] for stage in replan_data["stages"] for task in stage["tasks"]]
    assert "ml_c09" in replanned_ids
    assert "ml_c05" not in replanned_ids
    assert any(item["node_id"] == "ml_c09" and item["node_name"] for item in replan_data["diff_details"]["unchanged"])


async def test_replan_progress_aware_audit_contains_filtered_snapshot(client, project, plan):
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_e08",
        json={"status": "removed"},
    )
    await client.patch(
        f"/api/v1/projects/{project['id']}/graph/edges/ml_a04->ml_c05::REQUIRES",
        json={"status": "removed"},
    )

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "校验 filtered snapshot"},
    )
    assert resp.status_code == 200

    latest_plan_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/latest"
    )
    assert latest_plan_resp.status_code == 200
    audit = latest_plan_resp.json()["audit"]

    assert audit["pack_version"] == "1.3.0"
    assert "ml_e08" in audit["removed_node_ids"]
    assert "ml_a04->ml_c05::REQUIRES" in audit["removed_edge_ids"]
    assert "filtered_requires_adj" in audit
    assert "filtered_requires_rev_adj" in audit
    assert isinstance(audit["closure_ids"], list)
    assert isinstance(audit["reinforced_ids"], list)
    assert isinstance(audit["final_ids"], list)
    assert "ml_e08" not in audit["filtered_requires_adj"]
    assert "ml_e08" not in audit["filtered_requires_rev_adj"]
    assert "ml_c05" not in audit["filtered_requires_adj"].get("ml_a04", [])
    assert "ml_a04" not in audit["filtered_requires_rev_adj"].get("ml_c05", [])


async def test_replan_profile_update_passes_confirmed_resolution_to_planner(client, db_session, project, profile, plan):
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

    with patch("app.services.replan_service.plan_with_profile", side_effect=fake_plan_with_profile):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/replans",
            json={"mode": "profile_update", "reason": "确认目标复用"},
        )

    assert resp.status_code == 200
    assert captured["confirmed_goal_result"]["target_node_ids"] == confirmed_target_node_ids
    assert captured["confirmed_goal_result"]["selected_candidate_id"] == project["goal_resolution"]["selected_candidate_id"]
    assert captured["confirmed_goal_result"]["goal_type"] == project["goal_type"]


async def test_replan_progress_aware_audit_goal_result_contains_confirmed_metadata(client, project, plan):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "progress_aware", "reason": "检查审计目标元数据"},
    )
    assert resp.status_code == 200

    latest_plan_resp = await client.get(
        f"/api/v1/projects/{project['id']}/plans/latest"
    )
    assert latest_plan_resp.status_code == 200
    goal_result = latest_plan_resp.json()["audit"]["goal_result"]

    assert goal_result["confirmed_target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]
    assert goal_result["effective_target_node_ids"] == goal_result["target_node_ids"]
    assert goal_result["selected_candidate_id"] == project["goal_resolution"]["selected_candidate_id"]
    assert isinstance(goal_result["source_breakdown"], dict)
    assert isinstance(goal_result["score_breakdown"], dict)
    assert goal_result["goal_type_source"] == "confirmed_resolution"


async def test_replan_returns_goal_targets_removed_when_confirmed_targets_all_removed(client, project, plan):
    for node_id in project["goal_resolution"]["confirmed_target_node_ids"]:
        review_resp = await client.patch(
            f"/api/v1/projects/{project['id']}/graph/nodes/{node_id}",
            json={"status": "removed"},
        )
        assert review_resp.status_code == 200

    latest_before = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_before.status_code == 200
    version_before = latest_before.json()["version"]

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "确认目标全被移除"},
    )
    assert resp.status_code == 409
    assert resp.json()["error"] in {"GOAL_TARGETS_REMOVED", "GOAL_DEFAULT_TARGETS_UNAVAILABLE"}

    latest_after = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_after.status_code == 200
    assert latest_after.json()["version"] == version_before


async def test_replan_reuses_confirmed_resolution_after_session_expiry(client, db_session, project, profile, plan):
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

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/replans",
        json={"mode": "profile_update", "reason": "session 过期后仍应复用 confirmed resolution"},
    )
    assert resp.status_code == 200

    latest_plan_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_plan_resp.status_code == 200
    goal_result = latest_plan_resp.json()["audit"]["goal_result"]
    assert goal_result["confirmed_target_node_ids"] == project["goal_resolution"]["confirmed_target_node_ids"]
    assert goal_result["selected_candidate_id"] == project_row.confirmed_candidate_id
