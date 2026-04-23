from __future__ import annotations

from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

import json

import httpx
import pytest

from scripts.generate_thesis_validation_evidence import (
    DEFAULT_BASE_URL,
    RequestJsonError,
    build_paper_metrics,
    build_run_metadata,
    build_summary,
    build_search_error_metadata,
    build_tracking_checks,
    build_tracking_summary_expected,
    build_validation_contract,
    choose_safe_removed_node_id,
    choose_safe_skipped_node_id,
    compute_dependency_metrics,
    compute_stage_metrics,
    describe_readiness_payload,
    generate_evidence,
    get_actual_online_dependency_usage,
    normalize_readiness,
    run_scenario,
)


def build_scenario_inputs(goal_text: str | None = "我想系统学习机器学习基础"):
    scenario = {
        "id": "scenario-1",
        "title": "scenario title",
        "goal_id": "goal-1",
        "profile_id": "profile-1",
    }
    goals_by_id = {
        "goal-1": {
            "project": {
                "title": "机器学习入门",
                "goal_text": goal_text,
                "goal_type": "domain",
                "domain": "machine_learning",
            }
        }
    }
    profiles_by_id = {
        "profile-1": {
            "profile": {
                "math_level": 2,
                "coding_level": 2,
                "ml_level": 1,
                "theory_weight": 0.6,
                "practice_weight": 0.4,
                "weekly_hours": 10,
                "deadline_weeks": 12,
            }
        }
    }
    return scenario, goals_by_id, profiles_by_id


def test_default_base_url_points_to_current_validation_backend():
    assert DEFAULT_BASE_URL == "http://127.0.0.1:8010/api/v1"


def test_build_run_metadata_distinguishes_configured_and_used_online_dependencies():
    actual_usage = {"llm": False, "search": True}
    metadata = build_run_metadata(
        requested_runtime_mode="online",
        started_at=datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc),
        finished_at=datetime(2026, 4, 14, 12, 0, 5, tzinfo=timezone.utc),
        health={
            "environment": {
                "llm_api_key_set": True,
                "llm_provider": "openai_compatible",
                "search_api_key_set": True,
                "search_provider": "tavily",
            }
        },
        readiness={
            "status": "ready",
            "ready": True,
            "core_ready": True,
            "demo_ready": True,
            "enhanced_ready": True,
            "services": {
                "sqlite": {"status": "ok", "ready": True},
                "neo4j": {"status": "ok", "ready": True},
                "graph_sync": {
                    "status": "ok",
                    "ready": True,
                    "in_sync": True,
                    "domain": "machine_learning",
                },
                "llm": {
                    "status": "ok",
                    "ready": True,
                    "base_url": "https://api.openai.com/v1",
                    "model": "demo-model",
                },
                "search": {
                    "status": "ok",
                    "ready": True,
                    "provider": "tavily",
                },
            },
        },
        actual_usage=actual_usage,
    )

    assert metadata["requested_runtime_mode"] == "online"
    assert metadata["resolved_runtime_mode"] == "search"
    assert metadata["uses_online_dependencies"] is True
    assert metadata["readiness_status"] == "ready"
    assert metadata["core_ready"] is True
    assert metadata["demo_ready"] is True
    assert metadata["enhanced_ready"] is True
    assert metadata["dependency_metadata"]["llm"]["configured"] is True
    assert metadata["dependency_metadata"]["llm"]["used_in_run"] is False
    assert metadata["dependency_metadata"]["search"]["configured"] is True
    assert metadata["dependency_metadata"]["search"]["used_in_run"] is True
    assert metadata["dependency_metadata"]["graph_sync"]["status"] == "ok"


def test_get_actual_online_dependency_usage_distinguishes_configured_and_used_sources():
    usage = get_actual_online_dependency_usage(
        [
            {
                "status": "ok",
                "collector_questions_response": {"source": "llm"},
                "latest_plan_response": {
                    "audit": {"goal_result": {"resolve_source": "template"}}
                },
                "search_attempted": False,
            },
            {
                "status": "ok",
                "collector_questions_response": {"source": "static"},
                "latest_plan_response": {
                    "audit": {"goal_result": {"resolve_source": "llm"}}
                },
                "search_attempted": True,
                "search_results": [],
            },
        ]
    )

    assert usage == {"llm": True, "search": True}


def test_get_actual_online_dependency_usage_counts_failed_search_attempts():
    usage = get_actual_online_dependency_usage(
        [
            {
                "status": "error",
                "search_attempted": True,
            },
        ]
    )

    assert usage == {"llm": False, "search": True}


def test_get_actual_online_dependency_usage_reads_llm_from_source_breakdown():
    usage = get_actual_online_dependency_usage(
        [
            {
                "status": "ok",
                "collector_questions_response": {"source": "static"},
                "latest_plan_response": {
                    "audit": {
                        "goal_result": {
                            "resolve_source": "template",
                            "source_breakdown": {"template": 1.0, "llm": 0.2},
                        }
                    }
                },
                "search_attempted": False,
            }
        ]
    )

    assert usage == {"llm": True, "search": False}


def test_compute_dependency_metrics_counts_missing_prerequisites_as_unsatisfied():
    metrics = compute_dependency_metrics(
        [
            {
                "scenario_id": "scenario-1",
                "status": "ok",
                "plan_response": {
                    "stages": [
                        {
                            "tasks": [
                                {"node_id": "ml_a01"},
                                {"node_id": "ml_b01"},
                            ]
                        }
                    ]
                },
            }
        ],
        {
            "ml_b01": {"ml_a00", "ml_a01"},
        },
    )

    assert metrics["satisfied_required_edges"] == 1
    assert metrics["total_required_edges"] == 2
    assert metrics["dependency_satisfaction_ratio"] == 0.5
    assert metrics["scenario_breakdown"] == [
        {
            "scenario_id": "scenario-1",
            "status": "ok",
            "satisfied_required_edges": 1,
            "total_required_edges": 2,
            "dependency_satisfaction_ratio": 0.5,
        }
    ]


def test_build_paper_metrics_marks_failed_runs_as_not_citation_ready():
    metrics = build_paper_metrics(
        matrix={
            "matrix_id": "matrix-1",
            "change": "phase-1",
            "goal_templates": [{}],
            "profile_templates": [{}],
        },
        health={},
        readiness={},
        run_metadata={},
        results=[{"scenario_id": "scenario-1", "status": "error"}],
        summary={
            "scenario_count": 1,
            "successful_scenarios": 0,
            "failed_scenarios": 1,
            "all_scenarios_passed": False,
        },
        requires_lookup={},
    )

    assert metrics["citation_ready"] is False


def test_build_summary_includes_dependency_metrics():
    summary = build_summary(
        [
            {
                "scenario_id": "scenario-1",
                "status": "ok",
                "plan_response": {
                    "stages": [
                        {
                            "tasks": [
                                {"node_id": "ml_a01"},
                                {"node_id": "ml_b01"},
                            ]
                        }
                    ]
                },
            }
        ],
        [],
        {
            "ml_b01": {"ml_a01"},
        },
    )

    assert summary == {
        "scenario_count": 1,
        "successful_scenarios": 1,
        "failed_scenarios": 0,
        "context_errors": [],
        "all_scenarios_passed": True,
        "satisfied_required_edges": 1,
        "total_required_edges": 1,
        "dependency_satisfaction_ratio": 1.0,
    }


def test_metrics_keep_partial_plan_evidence_when_checks_fail():
    results = [
        {
            "scenario_id": "scenario-1",
            "status": "ok",
            "scenario_passed": False,
            "plan_response": {
                "stages": [
                    {
                        "tasks": [
                            {"node_id": "ml_a01"},
                            {"node_id": "ml_b01"},
                        ],
                        "stage_name": "基础",
                        "estimated_hours": 4,
                    }
                ]
            },
            "stage_summary": [
                {
                    "stage_name": "基础",
                    "task_count": 2,
                    "estimated_hours": 4,
                }
            ],
        }
    ]

    dependency_metrics = compute_dependency_metrics(
        results,
        {"ml_b01": {"ml_a01"}},
    )
    stage_metrics = compute_stage_metrics(results)

    assert dependency_metrics["scenario_breakdown"] == [
        {
            "scenario_id": "scenario-1",
            "status": "failed",
            "satisfied_required_edges": 1,
            "total_required_edges": 1,
            "dependency_satisfaction_ratio": 1.0,
        }
    ]
    assert stage_metrics["scenario_breakdown"] == [
        {
            "scenario_id": "scenario-1",
            "status": "failed",
            "stage_count": 1,
            "total_stage_hours": 4,
            "stages": [
                {
                    "stage_name": "基础",
                    "task_count": 2,
                    "estimated_hours": 4,
                }
            ],
        }
    ]


def test_build_search_error_metadata_sanitizes_request_json_error():
    metadata = build_search_error_metadata(
        RequestJsonError("POST", "/projects/demo/search", 502)
    )

    assert metadata == {
        "kind": "http_error",
        "method": "POST",
        "path": "/projects/demo/search",
        "status_code": 502,
    }


def test_normalize_readiness_backfills_demo_fields_and_graph_sync():
    readiness = normalize_readiness(
        {
            "status": "ready",
            "ready": True,
            "services": {
                "sqlite": {"status": "ok", "ready": True},
                "neo4j": {"status": "ok", "ready": True},
                "llm": {"status": "ok", "ready": True},
                "search": {"status": "ok", "ready": True, "provider": "tavily"},
            },
        }
    )

    assert readiness["status"] == "ready"
    assert readiness["core_ready"] is True
    assert readiness["demo_ready"] is True
    assert readiness["enhanced_ready"] is True
    assert readiness["services"]["graph_sync"] == {
        "status": "unknown",
        "ready": True,
        "domain": "machine_learning",
        "reason": "联调接口未单独返回图谱同步状态，当前按论文主链依赖兼容估算",
    }


def test_describe_readiness_payload_marks_legacy_payload_as_normalized():
    description = describe_readiness_payload(
        {
            "status": "ready",
            "ready": True,
            "services": {
                "sqlite": {"status": "ok", "ready": True},
                "neo4j": {"status": "ok", "ready": True},
                "llm": {"status": "ok", "ready": True},
                "search": {"status": "ok", "ready": True, "provider": "tavily"},
            },
        }
    )

    assert description == {
        "mode": "legacy_normalized",
        "normalized": True,
        "has_dual_layer_fields": False,
        "has_graph_sync": False,
        "target_schema": "dual_layer_readiness_v1",
        "target_fields": [
            "status",
            "ready",
            "core_ready",
            "demo_ready",
            "enhanced_ready",
            "services.graph_sync",
        ],
        "reason": "health/readiness 仍是旧结构，已通过 normalize_readiness 补齐 graph_sync/core_ready/demo_ready/enhanced_ready",
    }


def test_describe_readiness_payload_marks_dual_layer_payload_as_native():
    description = describe_readiness_payload(
        {
            "status": "degraded",
            "ready": False,
            "core_ready": True,
            "demo_ready": True,
            "enhanced_ready": False,
            "services": {
                "sqlite": {"status": "ok", "ready": True},
                "neo4j": {"status": "ok", "ready": True},
                "graph_sync": {"status": "ok", "ready": True, "domain": "machine_learning"},
                "llm": {"status": "skipped", "ready": False},
                "search": {"status": "skipped", "ready": False, "provider": "tavily"},
            },
        }
    )

    assert description == {
        "mode": "native_dual_layer",
        "normalized": False,
        "has_dual_layer_fields": True,
        "has_graph_sync": True,
        "target_schema": "dual_layer_readiness_v1",
        "target_fields": [
            "status",
            "ready",
            "core_ready",
            "demo_ready",
            "enhanced_ready",
            "services.graph_sync",
        ],
        "reason": "health/readiness 已直接返回双层预检字段与 graph_sync",
    }


def test_build_validation_contract_records_latest_plan_tracking_scope():
    contract = build_validation_contract(
        {
            "mode": "native_dual_layer",
            "normalized": False,
            "has_dual_layer_fields": True,
            "has_graph_sync": True,
            "target_schema": "dual_layer_readiness_v1",
            "target_fields": [
                "status",
                "ready",
                "core_ready",
                "demo_ready",
                "enhanced_ready",
                "services.graph_sync",
            ],
            "reason": "health/readiness 已直接返回双层预检字段与 graph_sync",
        }
    )

    assert contract == {
        "readiness_contract": {
            "mode": "native_dual_layer",
            "normalized": False,
            "has_dual_layer_fields": True,
            "has_graph_sync": True,
            "target_schema": "dual_layer_readiness_v1",
            "target_fields": [
                "status",
                "ready",
                "core_ready",
                "demo_ready",
                "enhanced_ready",
                "services.graph_sync",
            ],
            "reason": "health/readiness 已直接返回双层预检字段与 graph_sync",
        },
        "tracking_contract": {
            "summary_scope": "latest_plan",
            "verified_checks": [
                "tracking_summary_matches_initial_plan",
                "tracking_summary_matches_progress_latest_plan",
                "tracking_summary_matches_profile_latest_plan",
            ],
        },
    }


def test_build_tracking_summary_expected_matches_latest_plan_semantics():
    summary = build_tracking_summary_expected(
        {
            "stages": [
                {"tasks": [{"node_id": "ml_a01"}, {"node_id": "ml_a02"}]},
                {"tasks": [{"node_id": "ml_b01"}]},
            ]
        },
        completed_ids=("ml_a01",),
        in_progress_ids=("ml_a02",),
        skipped_ids=("legacy_removed",),
    )

    assert summary == {
        "total_nodes": 3,
        "completed": 1,
        "in_progress": 1,
        "skipped": 0,
        "pending": 1,
        "completion_rate": round(1 / 3, 3),
    }


def test_build_tracking_checks_treats_skipped_profile_update_as_passed():
    checks = build_tracking_checks(
        {
            "initial_summary": {"matches_plan": True},
            "progress_aware": {"matches_latest_plan": True},
            "profile_update": {"skipped": True, "matches_latest_plan": False},
        }
    )

    assert checks == {
        "tracking_summary_matches_initial_plan": True,
        "tracking_summary_matches_progress_latest_plan": True,
        "tracking_summary_matches_profile_latest_plan": True,
    }


def test_build_tracking_checks_fails_when_removed_node_is_still_retained():
    checks = build_tracking_checks(
        {
            "initial_summary": {"matches_plan": True},
            "progress_aware": {"matches_latest_plan": True},
            "profile_update": {
                "skipped": False,
                "matches_latest_plan": True,
                "removed_node_retained": True,
            },
        }
    )

    assert checks == {
        "tracking_summary_matches_initial_plan": True,
        "tracking_summary_matches_progress_latest_plan": True,
        "tracking_summary_matches_profile_latest_plan": False,
    }


def test_choose_safe_skipped_node_id_avoids_confirmed_targets_and_closure_nodes():
    node_ids = ["ml_b01", "ml_b02", "ml_b10", "ml_b06", "ml_a01"]
    goal_result = {
        "confirmed_target_node_ids": ["ml_c09", "ml_e03"],
    }
    audit = {
        "closure_ids": ["ml_b01", "ml_b02", "ml_b10"],
    }

    chosen = choose_safe_skipped_node_id(
        node_ids=node_ids,
        goal_result=goal_result,
        audit=audit,
    )

    assert chosen == "ml_b06"


def test_choose_safe_removed_node_id_prefers_non_confirmed_pending_nodes():
    pending_node_ids = ["ml_c09", "ml_b06", "ml_e03"]
    goal_result = {
        "confirmed_target_node_ids": ["ml_c09", "ml_e03"],
    }

    chosen = choose_safe_removed_node_id(
        pending_node_ids=pending_node_ids,
        goal_result=goal_result,
    )

    assert chosen == "ml_b06"


@pytest.mark.asyncio
async def test_run_scenario_surfaces_failed_search_attempts_as_error():
    scenario, goals_by_id, profiles_by_id = build_scenario_inputs()

    with patch(
        "scripts.generate_thesis_validation_evidence.request_json",
        AsyncMock(
            side_effect=[
                {
                    "session_id": "session-1",
                    "expires_at": "2026-04-22T10:00:00Z",
                    "auto_detected_goal_type": "domain",
                    "effective_goal_type": "domain",
                    "recommended_candidate_id": "cand-1",
                    "candidates": [{"candidate_id": "cand-1", "goal_type": "domain", "target_node_ids": ["ml_c09"]}],
                },
                {"id": "project-1"},
                {"source": "static"},
                RuntimeError("search boom"),
            ]
        ),
    ):
        result = await run_scenario(
            object(),
            scenario,
            goals_by_id,
            profiles_by_id,
        )

    assert result["status"] == "error"
    assert result["error"] == "search failed"
    assert result["search_attempted"] is True
    assert result["search_results"] == []
    assert result["search_error"] == {
        "kind": "RuntimeError",
        "message": "search request failed",
    }


@pytest.mark.asyncio
async def test_run_scenario_returns_structured_error_when_preview_lacks_recommended_candidate():
    scenario, goals_by_id, profiles_by_id = build_scenario_inputs()

    with patch(
        "scripts.generate_thesis_validation_evidence.request_json",
        AsyncMock(
            side_effect=[
                {
                    "session_id": "session-1",
                    "expires_at": "2026-04-22T10:00:00Z",
                    "auto_detected_goal_type": "domain",
                    "effective_goal_type": "domain",
                    "candidates": [],
                }
            ]
        ),
    ):
        result = await run_scenario(
            object(),
            scenario,
            goals_by_id,
            profiles_by_id,
        )

    assert result["status"] == "error"
    assert result["error"] == "invalid preview response"
    assert result["preview_error"] == {
        "kind": "invalid_preview_response",
        "missing_fields": ["recommended_candidate_id"],
        "candidate_count": 0,
        "recommended_candidate_missing": False,
    }


@pytest.mark.asyncio
async def test_run_scenario_returns_structured_error_when_recommended_candidate_not_in_candidates():
    scenario, goals_by_id, profiles_by_id = build_scenario_inputs()

    with patch(
        "scripts.generate_thesis_validation_evidence.request_json",
        AsyncMock(
            side_effect=[
                {
                    "session_id": "session-1",
                    "expires_at": "2026-04-22T10:00:00Z",
                    "auto_detected_goal_type": "domain",
                    "effective_goal_type": "domain",
                    "recommended_candidate_id": "cand-missing",
                    "candidates": [{"candidate_id": "cand-1", "goal_type": "domain", "target_node_ids": ["ml_c09"]}],
                }
            ]
        ),
    ):
        result = await run_scenario(
            object(),
            scenario,
            goals_by_id,
            profiles_by_id,
        )

    assert result["status"] == "error"
    assert result["error"] == "invalid preview response"
    assert result["preview_error"] == {
        "kind": "invalid_preview_response",
        "missing_fields": [],
        "candidate_count": 1,
        "recommended_candidate_missing": True,
    }


@pytest.mark.asyncio
async def test_run_scenario_uses_preview_select_create_flow():
    scenario, goals_by_id, profiles_by_id = build_scenario_inputs()
    request_json_mock = AsyncMock(
        side_effect=[
            {
                "session_id": "session-1",
                "expires_at": "2026-04-22T10:00:00Z",
                "auto_detected_goal_type": "domain",
                "effective_goal_type": "domain",
                "recommended_candidate_id": "cand-1",
                "candidates": [
                    {
                        "candidate_id": "cand-1",
                        "goal_type": "domain",
                        "target_node_ids": ["ml_c09"],
                        "mode": "steady",
                        "description": "系统学习机器学习基础",
                        "template_id": "domain_ml_full",
                        "resolve_source": "template",
                        "source_breakdown": {"template": 1.0},
                        "score": 0.9,
                        "score_breakdown": {"final_score": 0.9},
                        "explanation": "命中推荐候选",
                        "warnings": [],
                    }
                ],
            },
            {"id": "project-1"},
            {"source": "static"},
            {"id": "profile-1"},
            {
                "node_count": 1,
                "stages": [
                    {
                        "stage_index": 1,
                        "stage_name": "基础",
                        "estimated_hours": 4,
                        "tasks": [{"node_id": "ml_a01", "name": "线性代数"}],
                    }
                ],
            },
            {
                "stages": [{"tasks": [{"node_id": "ml_a01", "name": "线性代数"}]}],
                "audit": {"goal_result": {"resolve_source": "template", "source_breakdown": {"template": 1.0}}},
            },
            {"node_explanations": [{}]},
            {"node_id": "ml_a01", "event_type": "complete"},
            {"total_nodes": 1, "completed": 1, "in_progress": 0, "skipped": 0, "pending": 0, "completion_rate": 1.0},
            {"diff": {"completed": ["ml_a01"], "pending": []}},
            {"version": 2, "stages": []},
            {"total_nodes": 0, "completed": 0, "in_progress": 0, "skipped": 0, "pending": 0, "completion_rate": 0.0},
        ]
    )

    with patch(
        "scripts.generate_thesis_validation_evidence.request_json",
        request_json_mock,
    ):
        result = await run_scenario(
            object(),
            scenario,
            goals_by_id,
            profiles_by_id,
            runtime_mode="offline",
        )

    assert result["status"] == "ok"
    preview_call = request_json_mock.await_args_list[0]
    create_call = request_json_mock.await_args_list[1]
    assert preview_call.args[1:] == ("POST", "/goal-resolution/preview")
    assert preview_call.kwargs["payload"] == {
        "goal_text": "我想系统学习机器学习基础",
        "requested_goal_type": "domain",
        "domain": "machine_learning",
    }
    assert create_call.args[1:] == ("POST", "/projects")
    assert create_call.kwargs["payload"] == {
        "title": "机器学习入门",
        "goal_text": "我想系统学习机器学习基础",
        "domain": "machine_learning",
        "resolution_session_id": "session-1",
        "selected_candidate_id": "cand-1",
    }


@pytest.mark.asyncio
async def test_run_scenario_skips_search_in_offline_runtime_mode():
    scenario, goals_by_id, profiles_by_id = build_scenario_inputs()
    request_json_mock = AsyncMock(
        side_effect=[
            {
                "session_id": "session-1",
                "expires_at": "2026-04-22T10:00:00Z",
                "auto_detected_goal_type": "domain",
                "effective_goal_type": "domain",
                "recommended_candidate_id": "cand-1",
                "candidates": [{"candidate_id": "cand-1", "goal_type": "domain", "target_node_ids": ["ml_c09"]}],
            },
            {"id": "project-1"},
            {"source": "static"},
            {"id": "profile-1"},
            {
                "node_count": 3,
                "stages": [
                    {
                        "stage_index": 1,
                        "stage_name": "基础",
                        "estimated_hours": 4,
                        "tasks": [
                            {"node_id": "ml_a01", "name": "线性代数"},
                            {"node_id": "ml_a02", "name": "概率论"},
                            {"node_id": "ml_b01", "name": "梯度下降"},
                        ],
                    }
                ],
            },
            {
                "stages": [
                    {
                        "tasks": [
                            {"node_id": "ml_a01", "name": "线性代数"},
                            {"node_id": "ml_a02", "name": "概率论"},
                            {"node_id": "ml_b01", "name": "梯度下降"},
                        ]
                    }
                ],
                "audit": {"goal_result": {"resolve_source": "template"}},
            },
            {"node_explanations": [{}]},
            {"node_id": "ml_a01", "event_type": "complete"},
            {"node_id": "ml_a02", "event_type": "start"},
            {"node_id": "ml_b01", "event_type": "skip"},
            {
                "total_nodes": 3,
                "completed": 1,
                "in_progress": 1,
                "skipped": 1,
                "pending": 0,
                "completion_rate": 0.333,
            },
            {"diff": {"completed": ["ml_a01"], "pending": ["ml_b01"]}},
            {
                "version": 2,
                "stages": [
                    {
                        "tasks": [
                            {"node_id": "ml_a02", "name": "概率论"},
                            {"node_id": "ml_b01", "name": "梯度下降"},
                        ]
                    }
                ],
            },
            {
                "total_nodes": 2,
                "completed": 0,
                "in_progress": 1,
                "skipped": 1,
                "pending": 0,
                "completion_rate": 0.0,
            },
            {"status": "removed"},
            {"diff": {"removed": ["ml_b01"], "unchanged": ["ml_a02"]}},
            {"version": 3, "stages": [{"tasks": [{"node_id": "ml_a02", "name": "概率论"}]}]},
            {
                "total_nodes": 1,
                "completed": 0,
                "in_progress": 1,
                "skipped": 0,
                "pending": 0,
                "completion_rate": 0.0,
            },
        ]
    )

    with patch(
        "scripts.generate_thesis_validation_evidence.request_json",
        request_json_mock,
    ):
        result = await run_scenario(
            object(),
            scenario,
            goals_by_id,
            profiles_by_id,
            runtime_mode="offline",
        )

    assert result["status"] == "ok"
    assert result["scenario_passed"] is True
    assert result["search_attempted"] is False
    assert result["search_results"] == []
    assert result["search_skipped_reason"] == "search disabled by runtime_mode=offline"
    assert result["tracking_evidence"]["initial_summary"]["matches_plan"] is True
    assert result["tracking_evidence"]["progress_aware"]["matches_latest_plan"] is True
    assert result["tracking_evidence"]["profile_update"]["matches_latest_plan"] is True
    assert result["tracking_evidence"]["profile_update"]["removed_node_retained"] is False
    assert "/projects/project-1/search" not in [
        call.args[2] for call in request_json_mock.await_args_list
    ]


@pytest.mark.asyncio
async def test_generate_evidence_auto_mode_uses_search_runtime_when_only_search_is_ready(tmp_path):
    matrix = {
        "matrix_id": "matrix-1",
        "change": "phase-1",
        "description": "test matrix",
        "goal_templates": [
            {
                "id": "goal-1",
                "project": {
                    "title": "机器学习入门",
                    "goal_text": "我想系统学习机器学习基础",
                    "goal_type": "domain",
                    "domain": "machine_learning",
                },
            }
        ],
        "profile_templates": [
            {
                "id": "profile-1",
                "profile": {
                    "math_level": 2,
                    "coding_level": 2,
                    "ml_level": 1,
                    "theory_weight": 0.6,
                    "practice_weight": 0.4,
                    "weekly_hours": 10,
                    "deadline_weeks": 12,
                },
            }
        ],
        "scenarios": [
            {"id": "scenario-1", "title": "scenario title", "goal_id": "goal-1", "profile_id": "profile-1"}
        ],
    }
    matrix_file = tmp_path / "matrix.json"
    matrix_file.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
    requires_file = tmp_path / "requires.json"
    requires_file.write_text("[]", encoding="utf-8")
    output_file = tmp_path / "latest.json"
    summary_file = tmp_path / "paper_metrics.json"

    with patch(
        "scripts.generate_thesis_validation_evidence.capture_context",
        AsyncMock(
            return_value=(
                {"environment": {"search_api_key_set": True, "search_provider": "tavily"}},
                {
                    "status": "degraded",
                    "ready": False,
                    "core_ready": True,
                    "demo_ready": True,
                    "enhanced_ready": False,
                    "services": {
                        "sqlite": {"status": "ok", "ready": True},
                        "neo4j": {"status": "ok", "ready": True},
                        "graph_sync": {"status": "ok", "ready": True, "domain": "machine_learning"},
                        "llm": {"status": "skipped", "ready": False},
                        "search": {"status": "ok", "ready": True, "provider": "tavily"},
                    },
                },
                {
                    "status": "degraded",
                    "ready": False,
                    "core_ready": True,
                    "demo_ready": True,
                    "enhanced_ready": False,
                    "services": {
                        "sqlite": {"status": "ok", "ready": True},
                        "neo4j": {"status": "ok", "ready": True},
                        "graph_sync": {"status": "ok", "ready": True, "domain": "machine_learning"},
                        "llm": {"status": "skipped", "ready": False},
                        "search": {"status": "ok", "ready": True, "provider": "tavily"},
                    },
                },
                [],
            )
        ),
    ), patch(
        "scripts.generate_thesis_validation_evidence.run_scenario",
        AsyncMock(
            return_value={
                "scenario_id": "scenario-1",
                "status": "ok",
                "scenario_passed": True,
                "project_id": "project-1",
                "search_attempted": True,
                "search_results": [{"title": "result-1"}],
                "search_skipped_reason": None,
                "collector_questions_response": {"source": "static"},
                "latest_plan_response": {"audit": {"goal_result": {"resolve_source": "template"}}},
                "plan_response": {"stages": []},
                "stage_summary": [],
            }
        ),
    ) as run_scenario_mock:
        exit_code = await generate_evidence(
            base_url="http://localhost:8011/api/v1",
            matrix_file=matrix_file,
            output_file=output_file,
            summary_file=summary_file,
            runtime_mode="auto",
            requires_file=requires_file,
        )

    assert exit_code == 0
    assert run_scenario_mock.await_args.kwargs["runtime_mode"] == "search"
    evidence = json.loads(output_file.read_text(encoding="utf-8"))
    assert evidence["run_metadata"]["resolved_runtime_mode"] == "search"


@pytest.mark.asyncio
async def test_generate_evidence_auto_mode_skips_search_when_readiness_search_unavailable(tmp_path):
    matrix = {
        "matrix_id": "matrix-1",
        "change": "phase-1",
        "description": "test matrix",
        "goal_templates": [
            {
                "id": "goal-1",
                "project": {
                    "title": "机器学习入门",
                    "goal_text": "我想系统学习机器学习基础",
                    "goal_type": "domain",
                    "domain": "machine_learning",
                },
            }
        ],
        "profile_templates": [
            {
                "id": "profile-1",
                "profile": {
                    "math_level": 2,
                    "coding_level": 2,
                    "ml_level": 1,
                    "theory_weight": 0.6,
                    "practice_weight": 0.4,
                    "weekly_hours": 10,
                    "deadline_weeks": 12,
                },
            }
        ],
        "scenarios": [
            {"id": "scenario-1", "title": "scenario title", "goal_id": "goal-1", "profile_id": "profile-1"}
        ],
    }
    matrix_file = tmp_path / "matrix.json"
    matrix_file.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
    requires_file = tmp_path / "requires.json"
    requires_file.write_text("[]", encoding="utf-8")
    output_file = tmp_path / "latest.json"
    summary_file = tmp_path / "paper_metrics.json"

    with patch(
        "scripts.generate_thesis_validation_evidence.capture_context",
        AsyncMock(
            return_value=(
                {"environment": {"search_api_key_set": False, "search_provider": "tavily"}},
                {
                    "status": "degraded",
                    "ready": False,
                    "core_ready": True,
                    "demo_ready": True,
                    "enhanced_ready": False,
                    "services": {
                        "sqlite": {"status": "ok", "ready": True},
                        "neo4j": {"status": "ok", "ready": True},
                        "graph_sync": {"status": "ok", "ready": True, "domain": "machine_learning"},
                        "llm": {"status": "skipped", "ready": False},
                        "search": {"status": "skipped", "ready": False, "provider": "tavily", "reason": "搜索服务未配置"},
                    },
                },
                {
                    "status": "degraded",
                    "ready": False,
                    "core_ready": True,
                    "demo_ready": True,
                    "enhanced_ready": False,
                    "services": {
                        "sqlite": {"status": "ok", "ready": True},
                        "neo4j": {"status": "ok", "ready": True},
                        "graph_sync": {"status": "ok", "ready": True, "domain": "machine_learning"},
                        "llm": {"status": "skipped", "ready": False},
                        "search": {"status": "skipped", "ready": False, "provider": "tavily", "reason": "搜索服务未配置"},
                    },
                },
                [],
            )
        ),
    ), patch(
        "scripts.generate_thesis_validation_evidence.run_scenario",
        AsyncMock(
            return_value={
                "scenario_id": "scenario-1",
                "status": "ok",
                "scenario_passed": True,
                "project_id": "project-1",
                "search_attempted": False,
                "search_results": [],
                "search_skipped_reason": "search disabled by runtime_mode=offline",
                "collector_questions_response": {"source": "static"},
                "latest_plan_response": {"audit": {"goal_result": {"resolve_source": "template"}}},
                "plan_response": {"stages": []},
                "stage_summary": [],
            }
        ),
    ) as run_scenario_mock:
        exit_code = await generate_evidence(
            base_url="http://localhost:8011/api/v1",
            matrix_file=matrix_file,
            output_file=output_file,
            summary_file=summary_file,
            runtime_mode="auto",
            requires_file=requires_file,
        )

    assert exit_code == 0
    assert run_scenario_mock.await_args.kwargs["runtime_mode"] == "offline"


@pytest.mark.asyncio
async def test_generate_evidence_preserves_legacy_readiness_contract_metadata(tmp_path):
    matrix = {
        "matrix_id": "matrix-1",
        "change": "phase-1",
        "description": "test matrix",
        "goal_templates": [
            {
                "id": "goal-1",
                "project": {
                    "title": "机器学习入门",
                    "goal_text": "我想系统学习机器学习基础",
                    "goal_type": "domain",
                    "domain": "machine_learning",
                },
            }
        ],
        "profile_templates": [
            {
                "id": "profile-1",
                "profile": {
                    "math_level": 2,
                    "coding_level": 2,
                    "ml_level": 1,
                    "theory_weight": 0.6,
                    "practice_weight": 0.4,
                    "weekly_hours": 10,
                    "deadline_weeks": 12,
                },
            }
        ],
        "scenarios": [
            {"id": "scenario-1", "title": "scenario title", "goal_id": "goal-1", "profile_id": "profile-1"}
        ],
    }
    matrix_file = tmp_path / "matrix.json"
    matrix_file.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
    requires_file = tmp_path / "requires.json"
    requires_file.write_text("[]", encoding="utf-8")
    output_file = tmp_path / "latest.json"
    summary_file = tmp_path / "paper_metrics.json"
    legacy_readiness = {
        "status": "ok",
        "ready": True,
        "services": {
            "sqlite": {"status": "ok", "ready": True},
            "neo4j": {"status": "ok", "ready": True},
            "llm": {"status": "skipped", "ready": False},
            "search": {"status": "ok", "ready": True, "provider": "tavily"},
        },
    }

    with patch(
        "scripts.generate_thesis_validation_evidence.capture_context",
        AsyncMock(
            return_value=(
                {"environment": {"search_api_key_set": True, "search_provider": "tavily"}},
                legacy_readiness,
                legacy_readiness,
                [],
            )
        ),
    ), patch(
        "scripts.generate_thesis_validation_evidence.run_scenario",
        AsyncMock(
            return_value={
                "scenario_id": "scenario-1",
                "status": "ok",
                "scenario_passed": True,
                "project_id": "project-1",
                "search_attempted": True,
                "search_results": [{"title": "result-1"}],
                "search_skipped_reason": None,
                "collector_questions_response": {"source": "static"},
                "latest_plan_response": {"audit": {"goal_result": {"resolve_source": "template"}}},
                "plan_response": {"stages": []},
                "stage_summary": [],
            }
        ),
    ):
        exit_code = await generate_evidence(
            base_url="http://localhost:8011/api/v1",
            matrix_file=matrix_file,
            output_file=output_file,
            summary_file=summary_file,
            runtime_mode="auto",
            requires_file=requires_file,
        )

    assert exit_code == 0
    evidence = json.loads(output_file.read_text(encoding="utf-8"))
    assert evidence["run_metadata"]["readiness_contract"]["mode"] == "legacy_normalized"
    assert evidence["run_metadata"]["readiness_contract"]["normalized"] is True


@pytest.mark.asyncio
async def test_generate_evidence_uses_proxy_safe_client_for_loopback_base_url(tmp_path):
    matrix = {
        "matrix_id": "matrix-1",
        "change": "phase-1",
        "description": "test matrix",
        "goal_templates": [],
        "profile_templates": [],
        "scenarios": [],
    }
    matrix_file = tmp_path / "matrix.json"
    matrix_file.write_text(json.dumps(matrix, ensure_ascii=False), encoding="utf-8")
    requires_file = tmp_path / "requires.json"
    requires_file.write_text("[]", encoding="utf-8")
    output_file = tmp_path / "latest.json"
    summary_file = tmp_path / "paper_metrics.json"

    async def fake_capture_context(client):
        assert client.base_url == httpx.URL("http://localhost:8011/api/v1/")
        assert client._trust_env is False
        readiness = {"status": "ready", "ready": True, "services": {}}
        return ({}, readiness, readiness, [])

    with patch(
        "scripts.generate_thesis_validation_evidence.capture_context",
        AsyncMock(side_effect=fake_capture_context),
    ):
        exit_code = await generate_evidence(
            base_url="http://localhost:8011/api/v1",
            matrix_file=matrix_file,
            output_file=output_file,
            summary_file=summary_file,
            runtime_mode="offline",
            requires_file=requires_file,
        )

    assert exit_code == 0


@pytest.mark.asyncio
async def test_run_scenario_marks_failed_checks_as_not_ok():
    scenario, goals_by_id, profiles_by_id = build_scenario_inputs(goal_text=None)
    request_json_mock = AsyncMock(
        side_effect=[
            {
                "session_id": "session-1",
                "expires_at": "2026-04-22T10:00:00Z",
                "auto_detected_goal_type": "domain",
                "effective_goal_type": "domain",
                "recommended_candidate_id": "cand-1",
                "candidates": [{"candidate_id": "cand-1", "goal_type": "domain", "target_node_ids": ["ml_c09"]}],
            },
            {"id": "project-1"},
            {"source": "static"},
            {"id": "profile-1"},
            {
                "node_count": 1,
                "stages": [
                    {
                        "stage_index": 1,
                        "stage_name": "基础",
                        "estimated_hours": 4,
                        "tasks": [{"node_id": "ml_a01", "name": "线性代数"}],
                    }
                ],
            },
            {
                "stages": [
                    {
                        "tasks": [{"node_id": "ml_a01", "name": "线性代数"}],
                    }
                ],
                "audit": {"goal_result": {"resolve_source": "template"}},
            },
            {"node_explanations": []},
            {"node_id": "ml_a01", "event_type": "complete"},
            {
                "total_nodes": 1,
                "completed": 1,
                "in_progress": 0,
                "skipped": 0,
                "pending": 0,
                "completion_rate": 1.0,
            },
            {"diff": {"completed": ["ml_a01"], "pending": []}},
            {"version": 2, "stages": []},
            {
                "total_nodes": 0,
                "completed": 0,
                "in_progress": 0,
                "skipped": 0,
                "pending": 0,
                "completion_rate": 0.0,
            },
        ]
    )

    with patch(
        "scripts.generate_thesis_validation_evidence.request_json",
        request_json_mock,
    ):
        result = await run_scenario(
            object(),
            scenario,
            goals_by_id,
            profiles_by_id,
        )

    assert result["status"] == "ok"
    assert result["scenario_passed"] is False
    assert result["failed_checks"] == ["explanations_available"]
    assert result["error"] == "critical checks failed: explanations_available"
    assert result["plan_response"]["node_count"] == 1
    assert result["tracking_evidence"]["profile_update"]["skipped"] is True
    assert result["stage_summary"] == [
        {
            "stage_index": 1,
            "stage_name": "基础",
            "task_count": 1,
            "estimated_hours": 4,
            "task_node_ids": ["ml_a01"],
            "task_names": ["线性代数"],
        }
    ]
