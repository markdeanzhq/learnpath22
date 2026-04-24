"""
Task 1.1 + 1.4: GoalResolutionSession model — schema creation, TTL contract,
and expired-session cleanup.

TDD: these tests are written BEFORE the implementation and must fail first,
then pass after the model and cleanup logic are added.
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import cleanup_expired_sessions
from app.models.sqlite_models import Base, GoalResolutionSession

# ---------------------------------------------------------------------------
# Isolated in-memory engine for this test module
# (independent from conftest so we control schema lifecycle precisely)
# ---------------------------------------------------------------------------
_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_Session = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(autouse=True)
async def _fresh_schema():
    """Create all tables before each test; drop them after."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ---------------------------------------------------------------------------
# 1.1 — table and column existence
# ---------------------------------------------------------------------------


async def test_table_exists_in_schema():
    """goal_resolution_sessions table must exist after create_all."""
    async with _engine.connect() as conn:
        table_names = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_table_names()
        )
    assert "goal_resolution_sessions" in table_names


async def test_required_columns_present():
    """All spec-mandated columns must be present."""
    required_columns = {
        "session_id",
        "project_id",
        "goal_text_hash",
        "domain",
        "requested_goal_type",
        "auto_detected_goal_type",
        "effective_goal_type",
        "pack_version",
        "pack_hash",
        "graph_hash",
        "candidates_json",
        "recommended_candidate_id",
        "status",
        "expires_at",
        # implementation columns
        "created_at",
    }
    async with _engine.connect() as conn:
        columns = await conn.run_sync(
            lambda sync_conn: {
                c["name"]
                for c in inspect(sync_conn).get_columns("goal_resolution_sessions")
            }
        )
    missing = required_columns - columns
    assert not missing, f"Missing columns: {missing}"


async def test_session_id_is_primary_key():
    """session_id must be the primary key."""
    async with _engine.connect() as conn:
        pk_info = await conn.run_sync(
            lambda sync_conn: inspect(sync_conn).get_pk_constraint(
                "goal_resolution_sessions"
            )
        )
    assert "session_id" in pk_info["constrained_columns"]


# ---------------------------------------------------------------------------
# 1.1 — model can be instantiated and persisted
# ---------------------------------------------------------------------------


async def test_can_insert_minimal_session():
    """Insert a session with only required fields; nullable fields omitted."""
    now = datetime.now(timezone.utc)
    session_obj = GoalResolutionSession(
        project_id=None,  # project_id is nullable (pre-project flow)
        goal_text_hash="abc123",
        domain="machine_learning",
        requested_goal_type="domain",
        effective_goal_type="domain",
        pack_version="1.3.0",
        pack_hash="pack-123",
        graph_hash="deadbeef",
        candidates_json='["linear_regression"]',
        status="pending",
        expires_at=now + timedelta(hours=24),
    )
    async with _Session() as db:
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)

    assert session_obj.session_id is not None
    assert session_obj.status == "pending"


async def test_nullable_fields_accept_none():
    """Optional columns must accept NULL without error."""
    now = datetime.now(timezone.utc)
    session_obj = GoalResolutionSession(
        project_id=None,
        goal_text_hash="hash_nullable_test",
        domain=None,
        requested_goal_type=None,
        auto_detected_goal_type=None,
        effective_goal_type="concept",
        pack_version="1.3.0",
        pack_hash=None,
        graph_hash=None,
        candidates_json=None,
        recommended_candidate_id=None,
        status="pending",
        expires_at=now + timedelta(hours=24),
    )
    async with _Session() as db:
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)

    assert session_obj.session_id is not None


# ---------------------------------------------------------------------------
# 1.4 — 24-hour TTL contract
# ---------------------------------------------------------------------------

SESSION_TTL_HOURS = 24


async def test_default_expires_at_is_24h_from_created_at():
    """When expires_at is not explicitly set, the model default must be
    created_at + 24 hours (within a 5-second tolerance)."""
    before = datetime.now(timezone.utc)
    session_obj = GoalResolutionSession(
        goal_text_hash="ttl_default_test",
        domain="machine_learning",
        effective_goal_type="domain",
        pack_version="1.3.0",
        pack_hash="pack-ttl",
        status="pending",
    )
    async with _Session() as db:
        db.add(session_obj)
        await db.commit()
        await db.refresh(session_obj)

    after = datetime.now(timezone.utc)

    # Normalise to UTC if naive
    expires = session_obj.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    created = session_obj.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)

    expected_low = before + timedelta(hours=SESSION_TTL_HOURS) - timedelta(seconds=5)
    expected_high = after + timedelta(hours=SESSION_TTL_HOURS) + timedelta(seconds=5)

    assert expected_low <= expires <= expected_high, (
        f"expires_at={expires} not within 24 h ± 5 s of now"
    )


# ---------------------------------------------------------------------------
# 1.4 — expired-session cleanup
# ---------------------------------------------------------------------------


async def _insert_session(db: AsyncSession, *, expired: bool) -> str:
    """Helper: insert a session whose expires_at is in the past or future."""
    now = datetime.now(timezone.utc)
    delta = timedelta(hours=-1) if expired else timedelta(hours=24)
    session_obj = GoalResolutionSession(
        goal_text_hash=f"h_{'exp' if expired else 'active'}_{id(delta)}",
        domain="machine_learning",
        effective_goal_type="domain",
        pack_version="1.3.0",
        pack_hash="pack-cleanup",
        status="pending",
        expires_at=now + delta,
    )
    db.add(session_obj)
    await db.flush()
    return session_obj.session_id


async def test_cleanup_removes_expired_sessions():
    """cleanup_expired_sessions() must delete rows where expires_at < now."""
    async with _Session() as db:
        expired_id = await _insert_session(db, expired=True)
        active_id = await _insert_session(db, expired=False)
        await db.commit()

    async with _Session() as db:
        deleted_count = await cleanup_expired_sessions(db)
        await db.commit()

    assert deleted_count == 1

    async with _Session() as db:
        expired_row = await db.get(GoalResolutionSession, expired_id)
        active_row = await db.get(GoalResolutionSession, active_id)

    assert expired_row is None, "Expired session must be removed"
    assert active_row is not None, "Active session must be kept"


async def test_cleanup_returns_zero_when_nothing_expired():
    """cleanup_expired_sessions() returns 0 when no sessions have expired."""
    async with _Session() as db:
        await _insert_session(db, expired=False)
        await db.commit()

    async with _Session() as db:
        deleted_count = await cleanup_expired_sessions(db)
        await db.commit()

    assert deleted_count == 0


async def test_cleanup_idempotent():
    """Running cleanup twice must not raise and must return 0 on second run."""
    async with _Session() as db:
        await _insert_session(db, expired=True)
        await db.commit()

    async with _Session() as db:
        first = await cleanup_expired_sessions(db)
        await db.commit()

    async with _Session() as db:
        second = await cleanup_expired_sessions(db)
        await db.commit()

    assert first == 1
    assert second == 0
