from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import app.services.goal_resolution_service as goal_resolution_service

from sqlalchemy import select

def goal_understanding(
    domain_decision="in_domain",
    primary_domain="machine_learning",
    ml_relevance="core",
    goal_type="domain",
    target_concepts=None,
    confidence=0.9,
    clarification_question=None,
):
    return {
        "schema_version": "v1",
        "raw_text": "",
        "domain_decision": domain_decision,
        "primary_domain": primary_domain,
        "ml_relevance": ml_relevance,
        "goal_type": goal_type,
        "target_concepts": target_concepts or [],
        "constraints": {},
        "preferences": {},
        "uncertainties": [],
        "clarification_question": clarification_question,
        "confidence": confidence,
        "evidence": [{"span": primary_domain, "label": "primary_domain", "reason": "mocked understanding"}],
        "prompt_version": "goal-understanding-v1",
        "model": "mock-llm",
        "warnings": [],
    }


from app.models.sqlite_models import (
    ClarificationSession,
    GoalResolutionSession,
    LearnerProfile,
    LearningPath,
    LearningProject,
    PathStage,
    PathTask,
    ProjectOverlayExtractionSession,
    ProjectOverlayNode,
    ProjectOverlaySource,
    TrackingEvent,
)


async def test_goal_resolution_preview_returns_session_and_candidates(client, db_session):
    resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_detected_goal_type"] == "domain"
    assert data["effective_goal_type"] == "domain"
    assert data["goal_understanding"]["domain_decision"] == "in_domain"
    assert data["recommended_candidate_id"] == data["candidates"][0]["candidate_id"]
    assert 1 <= len(data["candidates"]) <= 5
    for candidate in data["candidates"]:
        assert len(candidate["target_node_names"]) == len(candidate["target_node_ids"])
        assert len(candidate["target_nodes"]) == len(candidate["target_node_ids"])
        assert [node["node_id"] for node in candidate["target_nodes"]] == candidate["target_node_ids"]
        assert [node["node_name"] for node in candidate["target_nodes"]] == candidate["target_node_names"]

    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    ttl_seconds = (expires_at - now).total_seconds()
    assert 23 * 3600 <= ttl_seconds <= 25 * 3600

    session = await db_session.get(GoalResolutionSession, data["session_id"])
    assert session is not None
    assert session.recommended_candidate_id == data["recommended_candidate_id"]
    assert session.status == "previewed"
    assert session.domain == "machine_learning"
    assert session.pack_hash
    assert session.graph_hash is None

    dependency_models = [
        LearningProject,
        LearningPath,
        PathStage,
        PathTask,
        LearnerProfile,
        TrackingEvent,
    ]
    for model in dependency_models:
        rows = await db_session.execute(select(model))
        assert rows.scalars().first() is None


async def test_goal_resolution_preview_respects_goal_type_override(client):
    resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "requested_goal_type": "concept",
            "domain": "machine_learning",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_detected_goal_type"] == "domain"
    assert data["effective_goal_type"] == "concept"
    assert all(candidate["goal_type"] == "concept" for candidate in data["candidates"])


async def test_goal_resolution_preview_rejects_invalid_goal_type(client):
    resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={
            "goal_text": "理解梯度下降",
            "requested_goal_type": "invalid",
        },
    )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_GOAL_TYPE", "code": 422}


async def test_goal_resolution_preview_rejects_requested_goal_type_not_supported_by_pack(client):
    fake_pack = SimpleNamespace(
        goal_templates=[],
        nodes_by_id={},
        manifest={"version": "test"},
        contract=SimpleNamespace(supported_goal_types=("domain", "problem")),
    )

    with patch("app.services.goal_resolution_service.get_domain_pack_service", return_value=fake_pack):
        resp = await client.post(
            "/api/v1/goal-resolution/preview",
            json={
                "goal_text": "理解梯度下降",
                "requested_goal_type": "concept",
            },
        )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_GOAL_TYPE", "code": 422}


async def test_goal_resolution_preview_rejects_invalid_domain(client):
    resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={
            "goal_text": "理解梯度下降",
            "domain": "other_domain",
        },
    )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_DOMAIN", "code": 422}


async def test_goal_resolution_preview_rejects_non_default_enabled_domain(client):
    original_registry = goal_resolution_service.get_domain_pack_registry

    def fake_registry():
        registry = original_registry()
        return SimpleNamespace(
            default_domain=registry.default_domain,
            enabled_domains=frozenset({registry.default_domain, "alt_domain"}),
            resolve_domain=lambda domain=None: registry.default_domain if domain is None else domain,
        )

    fake_pack = SimpleNamespace(
        goal_templates=[],
        nodes_by_id={},
        manifest={"version": "test"},
        contract=SimpleNamespace(supported_goal_types=("domain", "concept", "problem")),
    )

    with patch("app.services.goal_resolution_service.get_domain_pack_registry", side_effect=fake_registry), patch(
        "app.services.goal_resolution_service.get_domain_pack_service",
        return_value=fake_pack,
    ):
        resp = await client.post(
            "/api/v1/goal-resolution/preview",
            json={
                "goal_text": "理解梯度下降",
                "domain": "alt_domain",
            },
        )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_DOMAIN", "code": 422}


async def test_goal_resolution_preview_maps_auto_detected_unsupported_goal_type_to_422(client):
    fake_pack = SimpleNamespace(
        goal_templates=[],
        nodes_by_id={},
        manifest={"version": "test"},
        contract=SimpleNamespace(supported_goal_types=("domain", "problem")),
    )

    with patch("app.services.goal_resolution_service.get_domain_pack_service", return_value=fake_pack):
        resp = await client.post(
            "/api/v1/goal-resolution/preview",
            json={
                "goal_text": "理解梯度下降",
            },
        )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_GOAL_TYPE", "code": 422}


async def test_goal_resolution_preview_returns_boundary_state_when_no_safe_candidates(client):
    with patch(
        "app.services.goal_resolution_service.resolve_goal_candidates",
        return_value={
            "auto_detected_goal_type": "domain",
            "effective_goal_type": "domain",
            "goal_type_source": "auto",
            "recommended_candidate_id": None,
            "candidates": [],
            "warnings": [],
            "reason_code": "no_supported_candidates",
            "reason_text": "当前目标未能匹配到可确认的学习目标候选，请尝试改写目标描述或切换目标类型。",
        },
    ):
        resp = await client.post(
            "/api/v1/goal-resolution/preview",
            json={
                "goal_text": "量子力学和相对论",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "boundary_reject"
    assert data["coverage_status"] == "out_of_domain"
    assert data["reason_code"] == "OUT_OF_DOMAIN_GOAL"
    assert data["goal_frame"]["planner_parameters"]["path_mode"] == "standard"


async def test_goal_resolution_preview_returns_goal_frame_and_covered_union(client, db_session):
    resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={"goal_text": "我四周后要面试，想搞懂逻辑回归为什么能做分类"},
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "select_candidate"
    assert data["coverage_status"] == "covered"
    assert data["goal_frame"]["schema_version"] == "v1"
    assert data["goal_frame"]["planner_parameters"]["path_mode"] == "theory_first"
    assert data["goal_frame"]["planner_parameters"]["deadline_weeks"] == 4
    assert data["recommended_candidate_id"] == data["candidates"][0]["candidate_id"]

    session = await db_session.get(GoalResolutionSession, data["session_id"])
    assert session is not None
    assert session.goal_frame_json
    assert session.coverage_response_json


async def test_goal_frame_parameter_bounds_are_normalized_across_inputs(client):
    cases = [
        ("我想快速学习机器学习基础，99周完成，每周99小时", "compressed", 52, 40.0),
        ("我想多练项目，每周0.1小时，一周完成机器学习基础", "practice_first", 1, 0.5),
        ("我想推导理论，十周完成，每周12.5h", "theory_first", 10, 12.5),
    ]

    for goal_text, expected_mode, expected_weeks, expected_hours in cases:
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": goal_text})
        assert resp.status_code == 200
        params = resp.json()["goal_frame"]["planner_parameters"]
        assert params["path_mode"] == expected_mode
        assert params["deadline_weeks"] == expected_weeks
        assert params["weekly_hours"] == expected_hours
        if expected_mode in {"practice_first", "theory_first"}:
            assert round(params["practice_weight"] + params["theory_weight"], 3) == 1.0
            assert 0 <= params["practice_weight"] <= 1
            assert 0 <= params["theory_weight"] <= 1


async def test_coverage_router_returns_closed_discriminated_union_matrix(client):
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
        ambiguous_resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "AI"})

    cases = [
        ("我想系统学习机器学习基础", "select_candidate", "covered"),
        ("我想学习随机森林和监督学习", "confirm_partial", "partial"),
        ("我想补一下线性代数", "select_candidate", "adjacent_domain"),
        ("我想学习 Vue3 前端开发", "boundary_reject", "out_of_domain"),
    ]
    observed = {ambiguous_resp.json()["coverage_status"]: ambiguous_resp.json()["result_type"]}
    for goal_text, result_type, coverage_status in cases:
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": goal_text})
        assert resp.status_code == 200
        data = resp.json()
        assert data["result_type"] == result_type
        assert data["coverage_status"] == coverage_status
        observed[coverage_status] = result_type

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
        uncovered_resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "我想学习深度学习"})
    assert uncovered_resp.status_code == 200
    uncovered = uncovered_resp.json()
    assert uncovered["result_type"] == "review_extension_draft"
    assert uncovered["coverage_status"] == "in_domain_uncovered"
    observed["in_domain_uncovered"] = "review_extension_draft"

    assert observed == {
        "covered": "select_candidate",
        "partial": "confirm_partial",
        "in_domain_uncovered": "review_extension_draft",
        "adjacent_domain": "select_candidate",
        "out_of_domain": "boundary_reject",
        "ambiguous": "answer_clarification",
    }


async def test_goal_resolution_preview_returns_out_of_domain_boundary_without_writes(client, db_session):
    with patch(
        "app.services.goal_resolution_service.interpret_goal_with_llm",
        return_value=goal_understanding(
            domain_decision="out_of_domain",
            primary_domain="frontend",
            ml_relevance="none",
            target_concepts=["Vue3 前端开发"],
        ),
    ):
        resp = await client.post(
            "/api/v1/goal-resolution/preview",
            json={"goal_text": "我想学习 Vue3 前端开发"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "boundary_reject"
    assert data["coverage_status"] == "out_of_domain"
    assert data["goal_understanding"]["domain_decision"] == "out_of_domain"
    assert data["goal_understanding"]["primary_domain"] == "frontend"
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


async def test_goal_resolution_preview_returns_ambiguous_clarification(client, db_session):
    with patch(
        "app.services.goal_resolution_service.interpret_goal_with_llm",
        return_value=goal_understanding(
            domain_decision="ambiguous",
            primary_domain="unknown",
            ml_relevance="unclear",
            confidence=0.62,
            clarification_question="你想学习的是机器学习基础，还是其他方向？",
        ),
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "AI"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "answer_clarification"
    assert data["coverage_status"] == "ambiguous"
    assert data["goal_understanding"]["domain_decision"] == "ambiguous"
    assert data["clarification_session_id"]


async def test_goal_resolution_preview_returns_cross_domain_clarification(client, db_session):
    with patch(
        "app.services.goal_resolution_service.interpret_goal_with_llm",
        return_value=goal_understanding(
            domain_decision="cross_domain",
            primary_domain="new_energy",
            ml_relevance="application",
            target_concepts=["新能源预测", "机器学习"],
            clarification_question="是否只按机器学习基础部分创建路径？",
        ),
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "学习新能源预测中的机器学习"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "answer_clarification"
    assert data["coverage_status"] == "cross_domain"
    assert data["goal_understanding"]["domain_decision"] == "cross_domain"
    assert data["goal_understanding"]["ml_relevance"] == "application"
    assert data["questions"][0]["question_id"] == "confirm_ml_scope"
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


async def test_goal_resolution_preview_clarifies_low_confidence_in_domain(client, db_session):
    with patch(
        "app.services.goal_resolution_service.interpret_goal_with_llm",
        return_value=goal_understanding(
            domain_decision="in_domain",
            primary_domain="machine_learning",
            ml_relevance="core",
            confidence=0.42,
            clarification_question="你想学习机器学习基础还是其他方向？",
        ),
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "我想学习基础"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "answer_clarification"
    assert data["coverage_status"] == "ambiguous"
    assert data["goal_understanding"]["confidence"] == 0.42
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


@pytest.mark.parametrize("ml_relevance", ["application", "none", "unclear"])
async def test_goal_resolution_preview_clarifies_unsafe_ml_relevance(client, db_session, ml_relevance):
    with patch(
        "app.services.goal_resolution_service.interpret_goal_with_llm",
        return_value=goal_understanding(
            domain_decision="in_domain",
            primary_domain="machine_learning",
            ml_relevance=ml_relevance,
            confidence=0.9,
            clarification_question="请确认是否按机器学习基础创建路径。",
        ),
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "学习新能源预测"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "answer_clarification"
    assert data["coverage_status"] == "ambiguous"
    assert data["goal_understanding"]["ml_relevance"] == ml_relevance
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


async def test_goal_resolution_preview_clarifies_llm_warning_without_candidate_session(client, db_session):
    understanding = goal_understanding(
        domain_decision="in_domain",
        primary_domain="machine_learning",
        ml_relevance="core",
        confidence=0.9,
        clarification_question="目标理解服务暂不可用，请稍后重试或确认目标范围。",
    )
    understanding["warnings"] = ["llm_goal_understanding_failed"]
    understanding["model"] = None
    with patch("app.services.goal_resolution_service.interpret_goal_with_llm", return_value=understanding):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "我想系统学习机器学习基础"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "answer_clarification"
    assert data["coverage_status"] == "ambiguous"
    assert data["goal_frame"]["sources"][-1]["source"] == "fallback"
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


async def test_goal_resolution_llm_unavailable_fails_closed(client, db_session, monkeypatch):
    monkeypatch.undo()
    from app.core.config import replace_runtime_settings

    replace_runtime_settings({"llm_api_key": ""})
    resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "我想系统学习机器学习基础"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "answer_clarification"
    assert data["coverage_status"] == "ambiguous"
    assert data["goal_understanding"]["domain_decision"] == "ambiguous"
    assert data["goal_understanding"]["ml_relevance"] == "unclear"
    assert data["goal_understanding"]["warnings"] == ["llm_goal_understanding_missing_api_key"]
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


async def test_clarification_controlled_answer_resolves_to_fresh_goal_preview(client, db_session):
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
        json={
            "answers": [
                {
                    "question_id": "goal_direction",
                    "selected_option_id": "machine_learning_foundation",
                }
            ]
        },
    )

    assert answer_resp.status_code == 200
    data = answer_resp.json()
    assert data["status"] == "resolved"
    assert data["turn_count"] == 1
    assert data["coverage_response"]["result_type"] == "select_candidate"
    assert data["coverage_response"]["coverage_status"] == "covered"

    clarification = await db_session.get(ClarificationSession, preview["clarification_session_id"])
    assert clarification is not None
    assert clarification.status == "resolved"
    assert clarification.goal_resolution_session_id == data["coverage_response"]["session_id"]
    assert clarification.controlled_answers_json
    assert clarification.coverage_response_json


async def test_clarification_answer_rejects_invalid_option_without_resolving(client, db_session):
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

    session_id = preview_resp.json()["clarification_session_id"]
    answer_resp = await client.post(
        f"/api/v1/goal-resolution/clarifications/{session_id}/answers",
        json={"answers": [{"question_id": "goal_direction", "selected_option_id": "unknown"}]},
    )

    assert answer_resp.status_code == 422
    assert answer_resp.json() == {"error": "INVALID_CLARIFICATION_ANSWER", "code": 422}
    clarification = await db_session.get(ClarificationSession, session_id)
    assert clarification is not None
    assert clarification.status == "active"
    assert clarification.turn_count == 0


async def test_unresolved_clarification_session_cannot_create_project(client):
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

    session_id = preview_resp.json()["clarification_session_id"]
    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "未澄清",
            "goal_text": "AI",
            "resolution_session_id": session_id,
            "selected_candidate_id": "anything",
        },
    )

    assert create_resp.status_code == 409
    assert create_resp.json() == {"error": "STALE_RESOLUTION_SESSION", "code": 409}


async def test_clarification_answer_rejects_repeat_submission(client):
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

    session_id = preview_resp.json()["clarification_session_id"]
    payload = {
        "answers": [
            {
                "question_id": "goal_direction",
                "selected_option_id": "machine_learning_foundation",
            }
        ]
    }
    first_resp = await client.post(f"/api/v1/goal-resolution/clarifications/{session_id}/answers", json=payload)
    assert first_resp.status_code == 200

    second_resp = await client.post(f"/api/v1/goal-resolution/clarifications/{session_id}/answers", json=payload)
    assert second_resp.status_code == 409
    assert second_resp.json() == {"error": "STALE_CLARIFICATION_SESSION", "code": 409}


async def test_clarification_free_text_answer_is_parsed_before_resolution(client):
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

    preview = preview_resp.json()
    answer_resp = await client.post(
        f"/api/v1/goal-resolution/clarifications/{preview['clarification_session_id']}/answers",
        json={"answers": [{"question_id": "goal_direction", "free_text": "理解梯度下降"}]},
    )

    assert answer_resp.status_code == 200
    data = answer_resp.json()
    assert data["status"] == "resolved"
    assert data["coverage_response"]["result_type"] == "select_candidate"
    assert "梯度下降" in data["coverage_response"]["goal_frame"]["raw_text"]


async def test_clarification_answer_rejects_max_turns_session(client, db_session):
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

    session_id = preview_resp.json()["clarification_session_id"]
    clarification = await db_session.get(ClarificationSession, session_id)
    assert clarification is not None
    clarification.turn_count = clarification.max_turns
    await db_session.commit()

    answer_resp = await client.post(
        f"/api/v1/goal-resolution/clarifications/{session_id}/answers",
        json={"answers": [{"question_id": "goal_direction", "selected_option_id": "machine_learning_foundation"}]},
    )

    assert answer_resp.status_code == 409
    assert answer_resp.json() == {"error": "STALE_CLARIFICATION_SESSION", "code": 409}
    refreshed = await db_session.get(ClarificationSession, session_id)
    assert refreshed.status == "active"
    assert refreshed.controlled_answers_json is None


async def test_clarification_answer_rejects_expired_session(client, db_session):
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

    session_id = preview_resp.json()["clarification_session_id"]
    clarification = await db_session.get(ClarificationSession, session_id)
    assert clarification is not None
    clarification.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
    await db_session.commit()

    answer_resp = await client.post(
        f"/api/v1/goal-resolution/clarifications/{session_id}/answers",
        json={
            "answers": [
                {
                    "question_id": "goal_direction",
                    "selected_option_id": "machine_learning_foundation",
                }
            ]
        },
    )

    assert answer_resp.status_code == 409
    assert answer_resp.json() == {"error": "STALE_CLARIFICATION_SESSION", "code": 409}


async def test_project_clarification_answer_rejects_graph_drift(client, db_session, project):
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
        preview_resp = await client.post(
            f"/api/v1/projects/{project['id']}/goal-resolution/preview",
            json={"goal_text": "AI"},
        )

    assert preview_resp.status_code == 200
    session_id = preview_resp.json()["clarification_session_id"]
    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_e08",
        json={"status": "removed"},
    )
    assert review_resp.status_code == 200

    answer_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/clarifications/{session_id}/answers",
        json={"answers": [{"question_id": "goal_direction", "selected_option_id": "machine_learning_foundation"}]},
    )

    assert answer_resp.status_code == 409
    assert answer_resp.json() == {
        "error": "STALE_CLARIFICATION_SESSION",
        "code": 409,
        "reason_code": "PROJECT_GRAPH_DRIFT",
    }
    clarification = await db_session.get(ClarificationSession, session_id)
    assert clarification is not None
    assert clarification.status == "active"
    assert clarification.controlled_answers_json is None


async def test_project_clarification_answer_rejects_cross_project_session(client, db_session):
    first_preview = await client.post(
        "/api/v1/goal-resolution/preview",
        json={"goal_text": "我想系统学习机器学习基础"},
    )
    first = first_preview.json()
    project_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "项目一",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": first["session_id"],
            "selected_candidate_id": first["recommended_candidate_id"],
        },
    )
    assert project_resp.status_code == 200
    project_id = project_resp.json()["id"]

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

    session_id = preview_resp.json()["clarification_session_id"]
    answer_resp = await client.post(
        f"/api/v1/projects/{project_id}/goal-resolution/clarifications/{session_id}/answers",
        json={
            "answers": [
                {
                    "question_id": "goal_direction",
                    "selected_option_id": "machine_learning_foundation",
                }
            ]
        },
    )

    assert answer_resp.status_code == 409
    assert answer_resp.json() == {"error": "STALE_CLARIFICATION_SESSION", "code": 409}


async def test_goal_resolution_preview_returns_in_domain_uncovered_draft_entry(client):
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
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "我想学习随机森林"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "review_extension_draft"
    assert data["coverage_status"] == "in_domain_uncovered"
    assert "随机森林" in data["missing_concepts"]
    assert "session_id" not in data or data["session_id"] is None


async def test_project_goal_extension_draft_requires_explicit_creation(client, db_session, project):
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
    assert preview["session_id"]
    assert preview["audit_trace"]["trace_id"] == preview["session_id"]

    sources_before = (await db_session.execute(select(ProjectOverlaySource))).scalars().all()
    overlay_sessions_before = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sources_before == []
    assert overlay_sessions_before == []

    draft_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/extension-drafts",
        json={"resolution_session_id": preview["session_id"]},
    )

    assert draft_resp.status_code == 200
    draft = draft_resp.json()
    assert draft["goal_trace"]["trace_id"] == preview["session_id"]
    assert "随机森林" in draft["missing_concepts"]
    assert draft["session"]["session_status"] == "validated"
    assert draft["session"]["provenance"]["origin"] == "goal_extension_draft"
    assert draft["session"]["provenance"]["goal_trace"]["trace_id"] == preview["session_id"]
    assert draft["warnings"] == ["goal_extension_draft_requires_review"]
    assert len(draft["sources"]) == 1
    assert draft["sources"][0]["quality_status"] == "goal_extension_draft"
    source_metadata = json.loads(draft["sources"][0]["metadata_json"])
    assert source_metadata["goal_trace"]["trace_id"] == preview["session_id"]

    duplicate_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/extension-drafts",
        json={"resolution_session_id": preview["session_id"]},
    )
    assert duplicate_resp.status_code == 200
    duplicate = duplicate_resp.json()
    assert duplicate["session"]["session_id"] == draft["session"]["session_id"]
    assert [source["source_id"] for source in duplicate["sources"]] == [draft["sources"][0]["source_id"]]
    assert len((await db_session.execute(select(ProjectOverlaySource))).scalars().all()) == 1
    assert len((await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()) == 1
    assert len((await db_session.execute(select(ProjectOverlayNode))).scalars().all()) == 1

    get_resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions/{draft['session']['session_id']}"
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["session"]["provenance"]["goal_trace"]["trace_id"] == preview["session_id"]

    node = draft["nodes"][0]
    assert node["validation_status"] == "valid"
    assert node["review_status"] == "pending"
    assert node["planning_enabled"] is True
    assert node["provenance"]["origin"] == "goal_extension_draft"
    assert node["provenance"]["goal_trace"]["trace_id"] == preview["session_id"]
    assert "随机森林" in node["name"]


async def test_project_goal_extension_draft_rejects_global_preview_session(client, project):
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
        preview_resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "我想学习随机森林"})

    assert preview_resp.status_code == 200
    preview = preview_resp.json()
    assert preview.get("session_id") is None

    draft_resp = await client.post(
        f"/api/v1/projects/{project['id']}/goal-resolution/extension-drafts",
        json={"resolution_session_id": "not-a-project-session"},
    )

    assert draft_resp.status_code == 409
    assert draft_resp.json()["error"] == "STALE_RESOLUTION_SESSION"


async def test_goal_resolution_preview_partial_cannot_be_confirmed_as_full_project(client):
    resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "随机森林和监督学习"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "confirm_partial"
    assert data["coverage_status"] == "partial"
    assert data["covered_target_node_ids"]
    assert "随机森林" in data["missing_concepts"]

    confirm_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "部分覆盖",
            "goal_text": "随机森林和监督学习",
            "resolution_session_id": data["session_id"],
            "selected_candidate_id": data["candidates"][0]["candidate_id"],
        },
    )
    assert confirm_resp.status_code == 409
    assert confirm_resp.json()["error"] == "STALE_RESOLUTION_SESSION"


async def test_goal_resolution_preview_partial_can_be_explicitly_accepted(client):
    resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "随机森林和监督学习"})
    assert resp.status_code == 200
    preview = resp.json()
    selected = preview["candidates"][0]

    confirm_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "显式接受部分覆盖",
            "goal_text": "随机森林和监督学习",
            "resolution_session_id": preview["session_id"],
            "selected_candidate_id": selected["candidate_id"],
            "accept_partial": True,
        },
    )

    assert confirm_resp.status_code == 200
    project = confirm_resp.json()
    assert project["goal_resolution"]["partial_accepted"] is True
    assert "随机森林" in project["goal_resolution"]["missing_concepts"]
    assert project["goal_resolution"]["confirmed_target_node_ids"] == selected["target_node_ids"]


async def test_goal_resolution_preview_adjacent_maps_only_existing_support_nodes(client, db_session):
    empty_result = {
        "auto_detected_goal_type": "concept",
        "effective_goal_type": "concept",
        "goal_type_source": "auto",
        "recommended_candidate_id": None,
        "candidates": [],
        "warnings": [],
    }
    with patch(
        "app.services.goal_resolution_service.resolve_goal_candidates",
        return_value=empty_result,
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "Python 编程基础"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "select_candidate"
    assert data["coverage_status"] == "adjacent_domain"
    assert data["candidates"][0]["target_node_ids"] == ["ml_a01"]
    assert data["candidates"][0]["warnings"] == ["adjacent_domain_support_only"]
    rows = (await db_session.execute(select(GoalResolutionSession))).scalars().all()
    assert len(rows) == 1


async def test_goal_resolution_preview_adjacent_without_safe_mapping_does_not_create_session(client, db_session):
    empty_result = {
        "auto_detected_goal_type": "concept",
        "effective_goal_type": "concept",
        "goal_type_source": "auto",
        "recommended_candidate_id": None,
        "candidates": [],
        "warnings": [],
    }
    with patch(
        "app.services.goal_resolution_service.resolve_goal_candidates",
        return_value=empty_result,
    ), patch(
        "app.services.goal_resolution_service._coverage_status",
        return_value="adjacent_domain",
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "邻近但无映射目标"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["result_type"] == "boundary_reject"
    assert data["coverage_status"] == "adjacent_domain"
    assert data["reason_code"] == "NO_SAFE_MAPPING"
    rows = await db_session.execute(select(GoalResolutionSession))
    assert rows.scalars().first() is None


async def test_confirmed_candidate_targets_remain_authoritative_over_goal_frame_hints(client, db_session):
    candidate = {
        "candidate_id": "mock:logistic",
        "goal_type": "concept",
        "target_node_ids": ["ml_c09"],
        "mode": "concept",
        "description": "mock candidate",
        "template_id": None,
        "resolve_source": "mock",
        "source_breakdown": {"template": 1.0},
        "score": 0.9,
        "score_breakdown": {"final_score": 0.9},
        "explanation": "mock",
        "warnings": [],
    }
    with patch(
        "app.services.goal_resolution_service.resolve_goal_candidates",
        return_value={
            "auto_detected_goal_type": "concept",
            "effective_goal_type": "concept",
            "goal_type_source": "auto",
            "recommended_candidate_id": "mock:logistic",
            "candidates": [candidate],
            "warnings": [],
        },
    ):
        resp = await client.post("/api/v1/goal-resolution/preview", json={"goal_text": "梯度下降"})

    assert resp.status_code == 200
    data = resp.json()
    selected = data["candidates"][0]
    assert set(data["goal_frame"]["target_node_ids"]) == {"ml_c05"}
    assert set(selected["target_node_ids"]) == {"ml_c09"}

    session = await db_session.get(GoalResolutionSession, data["session_id"])
    coverage_response = json.loads(session.coverage_response_json)
    target_authority = coverage_response["target_authority"]
    assert target_authority["source"] == "confirmed_candidate"
    assert target_authority["mismatch_recorded"] is True
    assert target_authority["goal_frame_target_node_ids"] == sorted(data["goal_frame"]["target_node_ids"])
    assert target_authority["recommended_candidate_target_node_ids"] == sorted(selected["target_node_ids"])

    create_resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "候选权威",
            "goal_text": "梯度下降",
            "resolution_session_id": data["session_id"],
            "selected_candidate_id": selected["candidate_id"],
        },
    )
    assert create_resp.status_code == 200
    project = create_resp.json()
    assert project["goal_resolution"]["confirmed_target_node_ids"] == selected["target_node_ids"]
