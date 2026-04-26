"""Plans API 集成测试"""

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models.sqlite_models import GoalResolutionSession, LearningProject
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
    assert latest["audit"]["path_mode"] == "compressed"
    assert latest["audit"]["included_nodes"]


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
            "path_mode_preference": "practice_first",
        },
    )
    assert profile_resp.status_code == 200

    plan_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_resp.status_code == 200

    latest_resp = await client.get(f"/api/v1/projects/{project['id']}/plans/latest")
    assert latest_resp.status_code == 200
    snapshot = latest_resp.json()["audit"]["profile_snapshot"]
    assert snapshot["path_mode_preference"] == "practice_first"
    assert snapshot["persona_label"] == "实践驱动型学习者"
    assert "实践驱动型学习者" in snapshot["persona_summary"]


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

    assert data["meta"]["plan_version"] == plan["version"]
    assert data["meta"]["provenance"]["truth_source"] == "plan_audit_snapshot"
    assert data["meta"]["polish"]["requested"] is False
    assert data["meta"]["polish"]["applied"] is False


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
