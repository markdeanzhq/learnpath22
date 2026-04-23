from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

from sqlalchemy import select

from app.models.sqlite_models import (
    GoalResolutionSession,
    LearnerProfile,
    LearningPath,
    LearningProject,
    PathStage,
    PathTask,
    TrackingEvent,
)


async def test_goal_resolution_preview_returns_session_and_candidates(client, db_session):
    resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
            "domain": "machine_learning",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["auto_detected_goal_type"] == "domain"
    assert data["effective_goal_type"] == "domain"
    assert data["recommended_candidate_id"] == data["candidates"][0]["candidate_id"]
    assert 1 <= len(data["candidates"]) <= 5

    expires_at = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    ttl_seconds = (expires_at - now).total_seconds()
    assert 23 * 3600 <= ttl_seconds <= 25 * 3600

    session = await db_session.get(GoalResolutionSession, data["session_id"])
    assert session is not None
    assert session.recommended_candidate_id == data["recommended_candidate_id"]
    assert session.status == "previewed"

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
            "domain": "machine_learning",
        },
    )

    assert resp.status_code == 422
    assert resp.json() == {"error": "INVALID_GOAL_TYPE", "code": 422}


async def test_goal_resolution_preview_returns_empty_candidates_error(client):
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
        resp = await client.post(
            "/api/v1/goal-resolution/preview",
            json={
                "goal_text": "量子力学和相对论",
                "domain": "machine_learning",
            },
        )

    assert resp.status_code == 422
    assert resp.json() == {"error": "EMPTY_CANDIDATES", "code": 422}
