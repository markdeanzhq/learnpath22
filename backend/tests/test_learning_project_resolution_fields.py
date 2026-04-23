"""
Task 1.2: LearningProject model — confirmed-resolution fields.

TDD: these tests are written BEFORE the implementation and must fail first,
then pass after the ORM fields and schema-upgrade logic are added.

Covers:
  1. All 11 new confirmed-resolution columns are present in the schema
  2. Legacy project creation (without new fields) still works
  3. Existing old-style table (created without new columns) can be upgraded
  4. Fully populated row with all confirmed-resolution fields can be persisted/read
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import upgrade_learning_projects_schema
from app.models.sqlite_models import Base, LearningProject

# ---------------------------------------------------------------------------
# Isolated in-memory engine for this test module
# ---------------------------------------------------------------------------
_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)

# All 11 confirmed-resolution fields required by spec
RESOLUTION_COLUMNS = {
    "requested_goal_type",
    "auto_detected_goal_type",
    "confirmed_target_node_ids_json",
    "confirmed_mode",
    "confirmed_description",
    "confirmed_template_id",
    "confirmed_resolve_source",
    "confirmed_source_breakdown_json",
    "confirmed_candidate_id",
    "resolution_pack_version",
    "resolution_confirmed_at",
}


@pytest.fixture(autouse=True)
async def _fresh_schema():
    """Create all tables before each test; drop them after."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# 1. New columns present in schema
# ---------------------------------------------------------------------------


async def test_all_resolution_columns_present():
    """All 11 confirmed-resolution columns must exist in learning_projects."""
    async with _engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"]
                for c in inspect(sync_conn).get_columns("learning_projects")
            }
        )
    missing = RESOLUTION_COLUMNS - columns
    assert not missing, f"Missing columns: {missing}"


async def test_legacy_columns_still_present():
    """Original columns must still exist alongside the new ones."""
    legacy_columns = {"id", "title", "goal_text", "goal_type", "domain", "status", "created_at", "updated_at"}
    async with _engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"]
                for c in inspect(sync_conn).get_columns("learning_projects")
            }
        )
    missing = legacy_columns - columns
    assert not missing, f"Missing legacy columns: {missing}"


# ---------------------------------------------------------------------------
# 2. Legacy project creation works without new fields
# ---------------------------------------------------------------------------


async def test_legacy_create_without_resolution_fields():
    """LearningProject can be created with only legacy fields; new fields default to None."""
    project = LearningProject(
        title="Test Project",
        goal_text="I want to learn ML",
        goal_type="domain",
        domain="machine_learning",
    )
    async with _Session() as db:
        db.add(project)
        await db.commit()
        await db.refresh(project)

    assert project.id is not None
    assert project.title == "Test Project"
    # All new resolution fields must be None
    for col in RESOLUTION_COLUMNS:
        val = getattr(project, col)
        assert val is None, f"Expected {col} to be None, got {val!r}"


async def test_legacy_project_status_default():
    """Default status must still be 'active' after adding new columns."""
    project = LearningProject(
        title="Status Test",
        goal_text="test goal",
        goal_type="domain",
    )
    async with _Session() as db:
        db.add(project)
        await db.commit()
        await db.refresh(project)

    assert project.status == "active"


# ---------------------------------------------------------------------------
# 3. Schema upgrade of old-style table (migration logic)
# ---------------------------------------------------------------------------


async def test_upgrade_adds_missing_columns():
    """upgrade_learning_projects_schema() must add missing columns to an existing table."""
    # Simulate an old table: drop all then create only the legacy schema by
    # temporarily removing the new columns from metadata (we use raw SQL instead).
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        # Create old-style table without resolution columns
        await conn.execute(text(
            """
            CREATE TABLE learning_projects (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                goal_text TEXT NOT NULL,
                goal_type TEXT NOT NULL,
                domain TEXT DEFAULT 'machine_learning',
                status TEXT DEFAULT 'active',
                created_at DATETIME,
                updated_at DATETIME
            )
            """
        ))

    # Now run the upgrade
    async with _engine.begin() as conn:
        await upgrade_learning_projects_schema(conn)

    # Verify all resolution columns are now present
    async with _engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"]
                for c in inspect(sync_conn).get_columns("learning_projects")
            }
        )
    missing = RESOLUTION_COLUMNS - columns
    assert not missing, f"Missing after upgrade: {missing}"


async def test_upgrade_is_idempotent():
    """Running upgrade_learning_projects_schema() twice must not raise."""
    async with _engine.begin() as conn:
        await upgrade_learning_projects_schema(conn)
    # Second run — must not raise OperationalError or anything else
    async with _engine.begin() as conn:
        await upgrade_learning_projects_schema(conn)


# ---------------------------------------------------------------------------
# 4. Fully populated row with all confirmed-resolution fields
# ---------------------------------------------------------------------------


async def test_full_resolution_fields_persist_and_read():
    """A LearningProject with all confirmed-resolution fields set must round-trip correctly."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    project = LearningProject(
        title="Full Resolution Project",
        goal_text="Understand logistic regression",
        goal_type="problem",
        domain="machine_learning",
        requested_goal_type="problem",
        auto_detected_goal_type="problem",
        confirmed_target_node_ids_json='["logistic_regression"]',
        confirmed_mode="problem",
        confirmed_description="I want to understand why logistic regression works for classification",
        confirmed_template_id="problem_understand_001",
        confirmed_resolve_source="template",
        confirmed_source_breakdown_json='{"template": 1.0}',
        confirmed_candidate_id="cand_abc123",
        resolution_pack_version="1.3.0",
        resolution_confirmed_at=now,
    )
    async with _Session() as db:
        db.add(project)
        await db.commit()
        project_id = project.id

    # Read back from DB
    async with _Session() as db:
        loaded = await db.get(LearningProject, project_id)

    assert loaded is not None
    assert loaded.requested_goal_type == "problem"
    assert loaded.auto_detected_goal_type == "problem"
    assert loaded.confirmed_target_node_ids_json == '["logistic_regression"]'
    assert loaded.confirmed_mode == "problem"
    assert loaded.confirmed_description == "I want to understand why logistic regression works for classification"
    assert loaded.confirmed_template_id == "problem_understand_001"
    assert loaded.confirmed_resolve_source == "template"
    assert loaded.confirmed_source_breakdown_json == '{"template": 1.0}'
    assert loaded.confirmed_candidate_id == "cand_abc123"
    assert loaded.resolution_pack_version == "1.3.0"
    assert loaded.resolution_confirmed_at is not None


async def test_partial_resolution_fields_allowed():
    """Only some of the new fields may be set; others remain None."""
    project = LearningProject(
        title="Partial Resolution",
        goal_text="Learn gradient descent",
        goal_type="concept",
        confirmed_candidate_id="cand_xyz",
        resolution_pack_version="1.3.0",
    )
    async with _Session() as db:
        db.add(project)
        await db.commit()
        await db.refresh(project)

    assert project.confirmed_candidate_id == "cand_xyz"
    assert project.resolution_pack_version == "1.3.0"
    assert project.requested_goal_type is None
    assert project.confirmed_mode is None
    assert project.resolution_confirmed_at is None
