"""Profiles API 集成测试"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from sqlalchemy import select

from app.models.sqlite_models import LearnerProfile
from app.services.profile_collector_service import (
    generate_llm_questions,
    get_collector_questions,
    get_static_questions,
    map_answers_to_profile,
)


def _mock_async_client(*, response=None, side_effect=None):
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    if side_effect is not None:
        mock_client.post = AsyncMock(side_effect=side_effect)
    else:
        mock_client.post = AsyncMock(return_value=response)
    return mock_client


async def _get_latest_profile_row(db_session, project_id: str) -> LearnerProfile:
    result = await db_session.execute(
        select(LearnerProfile)
        .where(LearnerProfile.project_id == project_id)
        .order_by(LearnerProfile.created_at.desc())
        .limit(1)
    )
    return result.scalar_one()


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


async def test_collector_questions_returns_llm_source(client, project, monkeypatch):
    llm_questions = [
        {
            "id": "llm_q1",
            "field": "math_level",
            "question": "你对线性代数熟悉吗？",
            "options": [{"label": "一般", "value": 3}],
        }
    ]
    collector_query = AsyncMock(return_value=(llm_questions, "llm"))
    monkeypatch.setattr("app.api.v1.profiles.get_collector_questions", collector_query)

    resp = await client.post(f"/api/v1/projects/{project['id']}/collector/questions")

    assert resp.status_code == 200
    assert resp.json() == {"questions": llm_questions, "source": "llm"}
    collector_query.assert_awaited_once_with(project["goal_text"])


async def test_collector_questions_returns_static_source(client, project, monkeypatch):
    collector_query = AsyncMock(return_value=(get_static_questions(), "static"))
    monkeypatch.setattr("app.api.v1.profiles.get_collector_questions", collector_query)

    resp = await client.post(f"/api/v1/projects/{project['id']}/collector/questions")

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "static"
    assert data["questions"] == get_static_questions()
    collector_query.assert_awaited_once_with(project["goal_text"])


@pytest.mark.parametrize(
    ("mock_content", "expected_source"),
    [
        (
            json.dumps(
                [
                    {
                        "id": "llm_q1",
                        "field": "coding_level",
                        "question": "你能独立写 Python 脚本吗？",
                        "options": [{"label": "可以", "value": 4}],
                    }
                ],
                ensure_ascii=False,
            ),
            "llm",
        ),
        ("not-json", "static"),
        (
            json.dumps(
                [
                    {
                        "id": "llm_q1",
                        "field": "unknown_field",
                        "question": "非法字段",
                        "options": [{"label": "x", "value": 1}],
                    }
                ],
                ensure_ascii=False,
            ),
            "static",
        ),
        (json.dumps([], ensure_ascii=False), "static"),
    ],
)
async def test_get_collector_questions_uses_llm_or_static_by_payload_validity(
    mock_content,
    expected_source,
):
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "choices": [{"message": {"content": mock_content}}]
    }

    with (
        patch(
            "app.services.profile_collector_service.get_llm_config",
            return_value={
                "llm_api_key": "test-key",
                "llm_base_url": "https://llm.example.com/v1",
                "llm_model": "test-model",
            },
        ),
        patch("httpx.AsyncClient", return_value=_mock_async_client(response=mock_response)),
    ):
        questions, source = await get_collector_questions("我想系统学习机器学习基础")

    assert source == expected_source
    if expected_source == "llm":
        assert questions[0]["id"] == "llm_q1"
        assert questions[0]["field"] == "coding_level"
    else:
        assert questions == get_static_questions()


@pytest.mark.parametrize(
    "side_effect",
    [
        httpx.TimeoutException("timeout"),
        httpx.HTTPStatusError(
            "unauthorized",
            request=httpx.Request("POST", "https://llm.example.com/v1/chat/completions"),
            response=httpx.Response(
                401,
                request=httpx.Request("POST", "https://llm.example.com/v1/chat/completions"),
            ),
        ),
    ],
)
async def test_generate_llm_questions_returns_none_on_transport_failures(side_effect):
    with (
        patch(
            "app.services.profile_collector_service.get_llm_config",
            return_value={
                "llm_api_key": "test-key",
                "llm_base_url": "https://llm.example.com/v1",
                "llm_model": "test-model",
            },
        ),
        patch("httpx.AsyncClient", return_value=_mock_async_client(side_effect=side_effect)),
    ):
        questions = await generate_llm_questions("我想系统学习机器学习基础")

    assert questions is None


@pytest.mark.parametrize("source", ["llm", "static"])
async def test_collector_submit_persists_source_marker_and_mapped_answers(
    client,
    project,
    db_session,
    source,
):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/collector/submit",
        json={
            "source": source,
            "answers": [
                {"question_id": "q_math", "field": "math_level", "value": 4},
                {"question_id": "q_preference", "field": "theory_weight", "value": 0.6},
                {"question_id": "q_hours", "field": "weekly_hours", "value": 12},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["math_level"] == 4
    assert data["theory_weight"] == 0.6
    assert data["practice_weight"] == 0.4
    assert data["weekly_hours"] == 12

    profile = await _get_latest_profile_row(db_session, project["id"])
    assert json.loads(profile.raw_answers_json) == [
        {"question_id": "q_math", "field": "math_level", "value": 4},
        {"question_id": "q_preference", "field": "theory_weight", "value": 0.6},
        {"question_id": "q_hours", "field": "weekly_hours", "value": 12},
    ]
    trace = json.loads(profile.collector_trace_json)
    assert trace["source"] == source
    assert trace["mapped"]["math_level"] == 4
    assert trace["mapped"]["theory_weight"] == 0.6
    assert trace["mapped"]["practice_weight"] == 0.4
    assert trace["mapped"]["weekly_hours"] == 12.0
    assert trace["mapped"]["path_mode_preference"] == "standard"
    assert trace["mapped"]["persona_label"]
    assert trace["mapped"]["persona_summary"]


async def test_submit_profile_generates_persona_fields(client, project):
    resp = await client.post(
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

    assert resp.status_code == 200
    data = resp.json()
    assert data["path_mode_preference"] == "practice_first"
    assert data["persona_label"] == "实践驱动型学习者"
    assert "实践驱动型学习者" in data["persona_summary"]
    evidence = json.loads(data["persona_evidence"])
    assert evidence["path_mode_preference"] == "practice_first"
    assert evidence["deadline_weeks"] == 6


async def test_collector_static_questions_include_budget_and_mode_fields(client, project):
    resp = await client.post(f"/api/v1/projects/{project['id']}/collector/questions")

    assert resp.status_code == 200
    fields = {question["field"] for question in resp.json()["questions"]}
    assert {"weekly_hours", "deadline_weeks", "path_mode_preference"} <= fields


async def test_collector_submit_maps_deadline_path_mode_and_persona(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/collector/submit",
        json={
            "source": "static",
            "answers": [
                {"question_id": "q_math", "value": 2},
                {"question_id": "q_coding", "value": 4},
                {"question_id": "q_ml", "value": 3},
                {"question_id": "q_hours", "value": 4},
                {"question_id": "q_deadline", "value": 4},
                {"question_id": "q_path_mode", "value": "compressed"},
            ],
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["deadline_weeks"] == 4
    assert data["path_mode_preference"] == "compressed"
    assert data["persona_label"] == "时间压缩型学习者"
    assert data["persona_summary"]


def test_map_answers_ignores_invalid_path_mode_and_uses_fallback():
    mapped = map_answers_to_profile([
        {"question_id": "q_path_mode", "value": "invalid"},
    ])

    assert mapped["path_mode_preference"] == "standard"
    assert mapped["persona_label"] == "基础补齐型学习者"
