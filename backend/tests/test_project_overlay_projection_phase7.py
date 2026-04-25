from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import create_project_overlay_indexes
from app.db.seed_graph import seed_graph
from app.models.sqlite_models import Base, LearningProject, ProjectOverlayNode, ProjectOverlayProjectionState
from app.repositories.project_overlay_repository import (
    create_edge,
    create_extraction_session,
    create_node,
    create_resource,
    create_resource_binding,
    get_projection_state,
)
from app.services.project_overlay_projection_service import (
    PROJECT_NODE_LABEL,
    PROJECT_OVERLAY_OWNER,
    PROJECT_RELATED_RELATIONSHIP,
    PROJECT_RESOURCE_LABEL,
    PROJECTION_STATUS_DRIFTED,
    PROJECTION_STATUS_EMPTY,
    PROJECTION_STATUS_ERROR,
    PROJECTION_STATUS_MISSING,
    PROJECTION_STATUS_OK,
    build_project_overlay_projection_payload,
    get_project_overlay_projection_status,
    sync_project_overlay_projection,
)

_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(_engine.sync_engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@pytest.fixture(autouse=True)
async def _fresh_schema():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_project_overlay_indexes(conn)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class FakeTx:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    async def run(self, query: str, **params):
        self.calls.append((query, params))


class FakeDriver:
    def __init__(self, *, fail: Exception | None = None):
        self.fail = fail
        self.tx = FakeTx()
        self.write_count = 0

    async def execute_write(self, operation):
        self.write_count += 1
        if self.fail is not None:
            raise self.fail
        return await operation(self.tx)


async def _create_project(db: AsyncSession, project_id: str = "project-1") -> LearningProject:
    project = LearningProject(
        id=project_id,
        title="Project",
        goal_text="系统学习机器学习基础",
        goal_type="domain",
        domain="machine_learning",
    )
    db.add(project)
    await db.flush()
    return project


async def _create_overlay_fixture(db: AsyncSession, project_id: str = "project-1") -> None:
    await _create_project(db, project_id)
    await create_extraction_session(
        db,
        project_id=project_id,
        session_id="session-1",
        commit=False,
    )
    await create_node(
        db,
        project_id=project_id,
        session_id="session-1",
        node_id=f"po:{project_id}:n:test",
        canonical_payload_hash="node-hash",
        name="Overlay Node",
        group="concept",
        category="foundation",
        difficulty_final=1,
        importance_final=5,
        estimated_hours=2,
        req_math=1,
        req_coding=1,
        req_ml=1,
        theory_weight=0.5,
        practice_weight=0.5,
        source_ids_json='["source-1"]',
        provenance_json='{"summary":"overlay"}',
        commit=False,
    )
    await create_edge(
        db,
        project_id=project_id,
        session_id="session-1",
        edge_id=f"po:{project_id}:e:test",
        source_node_id="ml_c01",
        target_node_id=f"po:{project_id}:n:test",
        relation_type="RELATED_TO",
        canonical_payload_hash="edge-hash",
        commit=False,
    )
    await create_resource(
        db,
        project_id=project_id,
        session_id="session-1",
        resource_id=f"po:{project_id}:r:test",
        canonical_payload_hash="resource-hash",
        title="Overlay Resource",
        url="https://example.test/resource",
        resource_type="article",
        summary="resource summary",
        commit=False,
    )
    await create_resource_binding(
        db,
        project_id=project_id,
        resource_id=f"po:{project_id}:r:test",
        target_type="project_node",
        target_id=f"po:{project_id}:n:test",
        commit=False,
    )
    await db.commit()


async def test_overlay_projection_payload_uses_isolated_labels_and_owner_metadata():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        payload = await build_project_overlay_projection_payload(db, "project-1")

    assert payload["nodes"][0]["owner"] == PROJECT_OVERLAY_OWNER
    assert payload["nodes"][0]["origin"] == "overlay"
    assert payload["nodes"][0]["overlay_id"] == "po:project-1:n:test"
    assert payload["resources"][0]["owner"] == PROJECT_OVERLAY_OWNER
    assert payload["edges"][0]["owner"] == PROJECT_OVERLAY_OWNER
    assert payload["overlay_hash"]


async def test_projection_status_reports_empty_when_no_overlay_payload():
    async with _Session() as db:
        await _create_project(db)
        await db.commit()
        status = await get_project_overlay_projection_status(db, "project-1")
        driver = FakeDriver()
        sync_result = await sync_project_overlay_projection(db, driver, "project-1")
        second = await sync_project_overlay_projection(db, driver, "project-1")

    assert status["status"] == PROJECTION_STATUS_EMPTY
    assert status["in_sync"] is True
    assert status["reason"] == "no_overlay"
    assert sync_result["status"] == PROJECTION_STATUS_EMPTY
    assert sync_result["reason"] == "no_overlay"
    assert second["status"] == PROJECTION_STATUS_EMPTY
    assert second["reason"] == "unchanged"
    assert driver.write_count == 1


async def test_projection_status_reports_missing_when_overlay_payload_has_no_state():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        status = await get_project_overlay_projection_status(db, "project-1")

    assert status["status"] == PROJECTION_STATUS_MISSING
    assert status["in_sync"] is False
    assert status["reason"] == "projection_missing"
    assert status["overlay_hash"]
    assert status["projected_hash"] is None


async def test_sync_project_overlay_projection_is_idempotent_and_records_state():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        driver = FakeDriver()

        first = await sync_project_overlay_projection(db, driver, "project-1")
        second = await sync_project_overlay_projection(db, driver, "project-1")
        state = await get_projection_state(db, "project-1")

    assert first["synced"] is True
    assert first["status"] == PROJECTION_STATUS_OK
    assert first["projected_hash"] == first["overlay_hash"]
    assert second["synced"] is False
    assert second["reason"] == "unchanged"
    assert driver.write_count == 1
    assert state is not None
    assert state.status == PROJECTION_STATUS_OK
    assert state.overlay_hash == first["overlay_hash"]


async def test_projection_status_reports_drifted_when_payload_hash_changes_after_sync():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        driver = FakeDriver()
        await sync_project_overlay_projection(db, driver, "project-1")
        result = await db.execute(select(ProjectOverlayNode).where(ProjectOverlayNode.project_id == "project-1"))
        node = result.scalar_one()
        node.name = "Changed Overlay Node"
        await db.commit()
        status = await get_project_overlay_projection_status(db, "project-1")

    assert status["status"] == PROJECTION_STATUS_DRIFTED
    assert status["in_sync"] is False
    assert status["overlay_hash"] != status["projected_hash"]
    assert status["reason"] == "overlay_projection_drifted"


async def test_projection_status_reports_drifted_when_empty_state_becomes_non_empty_payload():
    async with _Session() as db:
        await _create_project(db)
        driver = FakeDriver()
        await sync_project_overlay_projection(db, driver, "project-1")
        await create_extraction_session(
            db,
            project_id="project-1",
            session_id="session-after-empty",
            commit=False,
        )
        await create_node(
            db,
            project_id="project-1",
            session_id="session-after-empty",
            node_id="po:project-1:n:after-empty",
            canonical_payload_hash="after-empty-hash",
            name="After Empty",
            commit=False,
        )
        await db.commit()
        status = await get_project_overlay_projection_status(db, "project-1")

    assert status["status"] == PROJECTION_STATUS_DRIFTED
    assert status["reason"] == "overlay_projection_drifted"


async def test_projection_sync_can_defer_state_commit_to_outer_transaction():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        driver = FakeDriver()
        result = await sync_project_overlay_projection(db, driver, "project-1", commit=False)
        state = await get_projection_state(db, "project-1")
        await db.rollback()
        rolled_back_state = await get_projection_state(db, "project-1")

    assert result["status"] == PROJECTION_STATUS_OK
    assert state is not None
    assert rolled_back_state is None


async def test_projection_failure_can_defer_error_state_to_outer_transaction():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        driver = FakeDriver(fail=RuntimeError("projection failed"))
        result = await sync_project_overlay_projection(db, driver, "project-1", commit=False)
        state = await get_projection_state(db, "project-1")
        await db.rollback()
        rolled_back_state = await get_projection_state(db, "project-1")

    assert result["status"] == PROJECTION_STATUS_ERROR
    assert state is not None
    assert rolled_back_state is None


async def test_projection_failure_records_error_without_rolling_back_sqlite_truth():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        driver = FakeDriver(fail=RuntimeError("projection failed"))

        result = await sync_project_overlay_projection(db, driver, "project-1")
        state = await get_projection_state(db, "project-1")
        nodes = (await db.execute(select(ProjectOverlayNode))).scalars().all()

    assert result["status"] == PROJECTION_STATUS_ERROR
    assert result["reason"] == "projection failed"
    assert result["projected_hash"] is None
    assert state is not None
    assert state.status == PROJECTION_STATUS_ERROR
    assert len(nodes) == 1


async def test_projection_status_reports_error_for_unknown_project():
    async with _Session() as db:
        status = await get_project_overlay_projection_status(db, "missing-project")

    assert status["status"] == PROJECTION_STATUS_ERROR
    assert status["ready"] is False
    assert status["reason"] == "PROJECT_NOT_FOUND"


async def test_projection_status_endpoint_returns_canonical_status(client, project):
    resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/overlay/projection/status"
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == PROJECTION_STATUS_EMPTY
    assert body["ready"] is True
    assert body["in_sync"] is True
    assert body["reason"] == "no_overlay"


async def test_projection_queries_use_project_labels_and_owned_relationships():
    async with _Session() as db:
        await _create_overlay_fixture(db)
        driver = FakeDriver()

        await sync_project_overlay_projection(db, driver, "project-1")

    queries = "\n".join(query for query, _ in driver.tx.calls)
    assert f":{PROJECT_NODE_LABEL}" in queries
    assert f":{PROJECT_RESOURCE_LABEL}" in queries
    assert f":{PROJECT_RELATED_RELATIONSHIP}" in queries
    assert "owner = $owner" in queries
    assert "KnowledgeNode {id: edge.source" in queries


async def test_baseline_seed_queries_do_not_target_project_overlay_labels():
    driver = FakeDriver()

    await seed_graph(
        driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash="pack-hash",
        nodes=[
            {
                "id": "ml_c01",
                "name": "Baseline Node",
                "group": "C",
                "category": "foundation",
                "difficulty_final": 1,
                "importance_final": 5,
                "estimated_hours": 2,
            }
        ],
        requires_edges=[],
        related_edges=[],
        stages=[],
        resources=[],
    )

    queries = "\n".join(query for query, _ in driver.tx.calls)
    assert PROJECT_NODE_LABEL not in queries
    assert PROJECT_RESOURCE_LABEL not in queries
    assert "coalesce(n.owner, $baseline_owner) = $baseline_owner" in queries
