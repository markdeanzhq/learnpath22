import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import get_settings, replace_runtime_settings
from app.models.sqlite_models import (
    Base,
    GraphReviewStatus,
    KnowledgeSource,
    LearnerProfile,
    LearningPath,
    PathStage,
    PathTask,
    ResourceBinding,
    TrackingEvent,
)

# ---------------------------------------------------------------------------
# In-memory SQLite for testing (StaticPool ensures single shared connection)
# ---------------------------------------------------------------------------
_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


@event.listens_for(_test_engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


async def _override_get_db():
    async with _TestSession() as session:
        yield session


async def _override_get_neo4j():
    return None


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_runtime_config_state():
    get_settings.cache_clear()
    replace_runtime_settings({})
    yield
    get_settings.cache_clear()
    replace_runtime_settings({})


@pytest.fixture
async def client():
    """Provide an httpx async client backed by an in-memory test database."""
    replace_runtime_settings({})
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    from app.api.router import api_router
    from app.core.exceptions import register_exception_handlers
    from app.db.neo4j import get_neo4j
    from app.db.sqlite import get_db
    from fastapi import FastAPI

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_neo4j] = _override_get_neo4j

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac

    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    replace_runtime_settings({})


@pytest.fixture
async def db_session():
    async with _TestSession() as session:
        yield session


@pytest.fixture
async def goal_resolution_preview(client):
    """Create a reusable goal resolution preview session and return its JSON."""
    preview_resp = await client.post(
        "/api/v1/goal-resolution/preview",
        json={
            "goal_text": "我想系统学习机器学习基础",
        }
    )
    assert preview_resp.status_code == 200
    return preview_resp.json()


@pytest.fixture
async def confirmed_project(client, goal_resolution_preview):
    """Create a confirmed project from a resolution session and return its JSON."""
    resp = await client.post(
        "/api/v1/projects",
        json={
            "title": "测试项目",
            "goal_text": "我想系统学习机器学习基础",
            "resolution_session_id": goal_resolution_preview["session_id"],
            "selected_candidate_id": goal_resolution_preview["recommended_candidate_id"],
        }
    )
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
async def project(confirmed_project):
    """Backwards-compatible alias for the confirmed project fixture."""
    return confirmed_project


@pytest.fixture
async def project_with_dependents(project, db_session):
    profile = LearnerProfile(project_id=project["id"])
    source = KnowledgeSource(
        project_id=project["id"],
        url="https://example.com/ml",
        title="ML Source",
        source_type="web",
    )
    path = LearningPath(project_id=project["id"], plan_json='{"stages": []}')
    tracking_event = TrackingEvent(
        project_id=project["id"],
        node_id="gradient_descent",
        event_type="start",
    )
    review_status = GraphReviewStatus(
        project_id=project["id"],
        element_type="node",
        element_id="gradient_descent",
    )

    db_session.add_all([profile, source, path, tracking_event, review_status])
    await db_session.flush()

    stage = PathStage(
        path_id=path.id,
        stage_index=1,
        stage_name="阶段一",
        node_count=1,
    )
    db_session.add(stage)
    await db_session.flush()

    task = PathTask(
        stage_id=stage.id,
        node_id="gradient_descent",
        node_name="梯度下降",
        order_in_stage=1,
        difficulty=2,
        importance=3,
    )
    db_session.add(task)
    await db_session.commit()

    return {
        "project": project,
        "path_id": path.id,
        "stage_id": stage.id,
    }


@pytest.fixture
async def profile(client, project):
    """Create a test learner profile and return its JSON."""
    resp = await client.post(
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
    assert resp.status_code == 200
    return resp.json()


@pytest.fixture
async def plan(client, project, profile):
    """Generate a learning path and return its JSON."""
    resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert resp.status_code == 200
    return resp.json()
