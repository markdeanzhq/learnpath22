from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import create_project_overlay_indexes
from app.models.sqlite_models import Base, LearningProject
from app.repositories.project_overlay_repository import (
    create_edge,
    create_extraction_session,
    create_node,
    create_promotion_batch,
    create_promotion_item,
    create_resource,
    list_planner_visible_edges,
    list_planner_visible_nodes,
    update_extraction_session_status,
    update_planning_enabled,
    update_promotion_status,
    update_review_status,
    update_validation_status,
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


async def _create_project(db: AsyncSession, project_id: str) -> LearningProject:
    project = LearningProject(
        id=project_id,
        title=f"Project {project_id}",
        goal_text="系统学习机器学习基础",
        goal_type="domain",
        domain="machine_learning",
    )
    db.add(project)
    await db.flush()
    return project


async def _create_session(db: AsyncSession, project_id: str, session_id: str = "session-1"):
    await _create_project(db, project_id)
    return await create_extraction_session(
        db,
        project_id=project_id,
        session_id=session_id,
        commit=False,
    )


async def test_planner_visible_filters_require_valid_confirmed_and_enabled():
    async with _Session() as db:
        await _create_session(db, "planner-project")
        await create_node(
            db,
            project_id="planner-project",
            node_id="po:planner-project:n:pendingaaaaaaaaaaaaaaaaaa",
            session_id="session-1",
            canonical_payload_hash="pending-hash",
            commit=False,
        )
        disabled = await create_node(
            db,
            project_id="planner-project",
            node_id="po:planner-project:n:disabledbbbbbbbbbbbbbbbb",
            session_id="session-1",
            canonical_payload_hash="disabled-hash",
            commit=False,
        )
        visible = await create_node(
            db,
            project_id="planner-project",
            node_id="po:planner-project:n:visibleccccccccccccccccc",
            session_id="session-1",
            canonical_payload_hash="visible-hash",
            commit=False,
        )
        visible_edge = await create_edge(
            db,
            project_id="planner-project",
            edge_id="po:planner-project:e:visibleddddddddddddddddd",
            session_id="session-1",
            source_node_id=visible.node_id,
            target_node_id="ml_c01",
            relation_type="RELATED_TO",
            canonical_payload_hash="visible-edge-hash",
            commit=False,
        )
        await db.commit()

        await update_validation_status(
            db,
            project_id="planner-project",
            element_type="node",
            element_id=disabled.node_id,
            validation_status="valid",
        )
        await update_review_status(
            db,
            project_id="planner-project",
            element_type="node",
            element_id=disabled.node_id,
            review_status="confirmed",
        )
        await update_planning_enabled(
            db,
            project_id="planner-project",
            element_type="node",
            element_id=disabled.node_id,
            planning_enabled=False,
        )
        for element_type, element_id in [("node", visible.node_id), ("edge", visible_edge.edge_id)]:
            await update_validation_status(
                db,
                project_id="planner-project",
                element_type=element_type,
                element_id=element_id,
                validation_status="valid",
            )
            await update_review_status(
                db,
                project_id="planner-project",
                element_type=element_type,
                element_id=element_id,
                review_status="confirmed",
            )

        nodes = await list_planner_visible_nodes(db, "planner-project")
        edges = await list_planner_visible_edges(db, "planner-project")

    assert [node.node_id for node in nodes] == [visible.node_id]
    assert [edge.edge_id for edge in edges] == [visible_edge.edge_id]


async def test_create_candidates_are_idempotent_for_exact_replay_and_reject_collisions():
    async with _Session() as db:
        await _create_session(db, "replay-project")
        node = await create_node(
            db,
            project_id="replay-project",
            node_id="po:replay-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id="session-1",
            canonical_payload_hash="same-hash",
            commit=False,
        )
        replayed = await create_node(
            db,
            project_id="replay-project",
            node_id=node.node_id,
            session_id="session-1",
            canonical_payload_hash="same-hash",
            commit=False,
        )
        assert replayed is node

        with pytest.raises(ValueError, match="OVERLAY_ID_COLLISION"):
            await create_node(
                db,
                project_id="replay-project",
                node_id=node.node_id,
                session_id="session-1",
                canonical_payload_hash="different-hash",
                commit=False,
            )

        await create_extraction_session(
            db,
            project_id="replay-project",
            session_id="session-2",
            commit=False,
        )
        with pytest.raises(ValueError, match="OVERLAY_ID_REPLAY_SESSION_MISMATCH"):
            await create_node(
                db,
                project_id="replay-project",
                node_id=node.node_id,
                session_id="session-2",
                canonical_payload_hash="same-hash",
                commit=False,
            )


async def test_review_and_planning_updates_are_independent():
    async with _Session() as db:
        await _create_session(db, "independent-project")
        node = await create_node(
            db,
            project_id="independent-project",
            node_id="po:independent-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id="session-1",
            canonical_payload_hash="node-hash",
        )
        await db.commit()

        await update_planning_enabled(
            db,
            project_id="independent-project",
            element_type="node",
            element_id=node.node_id,
            planning_enabled=False,
        )
        after_planning = await update_review_status(
            db,
            project_id="independent-project",
            element_type="node",
            element_id=node.node_id,
            review_status="confirmed",
        )

        assert after_planning.review_status == "confirmed"
        assert after_planning.planning_enabled is False
        assert after_planning.validation_status == "unchecked"
        assert after_planning.promotion_status == "not_promoted"

        after_review = await update_planning_enabled(
            db,
            project_id="independent-project",
            element_type="node",
            element_id=node.node_id,
            planning_enabled=True,
        )

        assert after_review.review_status == "confirmed"
        assert after_review.planning_enabled is True
        assert after_review.validation_status == "unchecked"
        assert after_review.promotion_status == "not_promoted"


async def test_status_updates_only_change_their_own_lifecycle_field():
    async with _Session() as db:
        await _create_session(db, "status-project")
        edge = await create_edge(
            db,
            project_id="status-project",
            edge_id="po:status-project:e:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id="session-1",
            source_node_id="ml_c01",
            target_node_id="ml_c02",
            relation_type="RELATED_TO",
            canonical_payload_hash="edge-hash",
        )
        await db.commit()

        after_validation = await update_validation_status(
            db,
            project_id="status-project",
            element_type="edge",
            element_id=edge.edge_id,
            validation_status="valid",
        )
        assert after_validation.validation_status == "valid"
        assert after_validation.review_status == "pending"
        assert after_validation.planning_enabled is True
        assert after_validation.promotion_status == "not_promoted"

        invalid = await update_validation_status(
            db,
            project_id="status-project",
            element_type="edge",
            element_id=edge.edge_id,
            validation_status="invalid",
            validation_errors_json='["missing field"]',
        )
        assert invalid.validation_errors_json == '["missing field"]'

        valid_again = await update_validation_status(
            db,
            project_id="status-project",
            element_type="edge",
            element_id=edge.edge_id,
            validation_status="valid",
        )
        assert valid_again.validation_errors_json is None

        after_promotion = await update_promotion_status(
            db,
            project_id="status-project",
            element_type="edge",
            element_id=edge.edge_id,
            promotion_status="promotion_ready",
        )
        assert after_promotion.validation_status == "valid"
        assert after_promotion.review_status == "pending"
        assert after_promotion.planning_enabled is True
        assert after_promotion.promotion_status == "promotion_ready"


async def test_create_methods_reject_lifecycle_overrides():
    async with _Session() as db:
        await _create_project(db, "create-guard-project")
        await db.commit()

        with pytest.raises(ValueError, match="LIFECYCLE_FIELDS_NOT_ALLOWED"):
            await create_extraction_session(
                db,
                project_id="create-guard-project",
                session_status="promoted",
            )
        await db.rollback()

        await create_extraction_session(
            db,
            project_id="create-guard-project",
            session_id="session-1",
        )

        with pytest.raises(ValueError, match="LIFECYCLE_FIELDS_NOT_ALLOWED"):
            await create_node(
                db,
                project_id="create-guard-project",
                node_id="po:create-guard-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
                session_id="session-1",
                canonical_payload_hash="node-hash",
                review_status="confirmed",
            )
        await db.rollback()

        with pytest.raises(ValueError, match="LIFECYCLE_FIELDS_NOT_ALLOWED"):
            await create_edge(
                db,
                project_id="create-guard-project",
                edge_id="po:create-guard-project:e:bbbbbbbbbbbbbbbbbbbbbbbb",
                session_id="session-1",
                source_node_id="ml_c01",
                target_node_id="ml_c02",
                relation_type="RELATED_TO",
                canonical_payload_hash="edge-hash",
                promotion_status="promotion_ready",
            )

        with pytest.raises(ValueError, match="LIFECYCLE_FIELDS_NOT_ALLOWED"):
            await create_resource(
                db,
                project_id="create-guard-project",
                resource_id="po:create-guard-project:r:cccccccccccccccccccccccc",
                session_id="session-1",
                canonical_payload_hash="resource-hash",
                planning_enabled=False,
            )

        with pytest.raises(ValueError, match="LIFECYCLE_FIELDS_NOT_ALLOWED"):
            await create_promotion_batch(
                db,
                project_id="create-guard-project",
                status="promoted",
            )

        batch = await create_promotion_batch(db, project_id="create-guard-project")
        assert batch.status == "previewed"

        with pytest.raises(ValueError, match="LIFECYCLE_FIELDS_NOT_ALLOWED"):
            await create_promotion_item(
                db,
                project_id="create-guard-project",
                batch_id=batch.batch_id,
                element_type="node",
                element_id="po:create-guard-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
                status="promoted",
            )


async def test_closed_sessions_do_not_expose_planner_visible_candidates():
    async with _Session() as db:
        session = await _create_session(db, "archived-project")
        session_id = session.session_id
        node = await create_node(
            db,
            project_id="archived-project",
            node_id="po:archived-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id=session_id,
            canonical_payload_hash="node-hash",
            commit=False,
        )
        await db.commit()
        await update_validation_status(
            db,
            project_id="archived-project",
            element_type="node",
            element_id=node.node_id,
            validation_status="valid",
        )
        await update_review_status(
            db,
            project_id="archived-project",
            element_type="node",
            element_id=node.node_id,
            review_status="confirmed",
        )

        assert [item.node_id for item in await list_planner_visible_nodes(db, "archived-project")] == [node.node_id]

        archived = await update_extraction_session_status(
            db,
            project_id="archived-project",
            session_id=session_id,
            session_status="archived",
        )

        assert archived.session_status == "archived"
        assert await list_planner_visible_nodes(db, "archived-project") == []

    async with _Session() as db:
        session = await _create_session(db, "failed-project", session_id="session-failed")
        session_id = session.session_id
        node = await create_node(
            db,
            project_id="failed-project",
            node_id="po:failed-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id=session_id,
            canonical_payload_hash="node-hash",
            commit=False,
        )
        await db.commit()
        await update_validation_status(
            db,
            project_id="failed-project",
            element_type="node",
            element_id=node.node_id,
            validation_status="valid",
        )
        await update_review_status(
            db,
            project_id="failed-project",
            element_type="node",
            element_id=node.node_id,
            review_status="confirmed",
        )
        failed = await update_extraction_session_status(
            db,
            project_id="failed-project",
            session_id=session_id,
            session_status="failed",
        )

        assert failed.session_status == "failed"
        assert await list_planner_visible_nodes(db, "failed-project") == []

    async with _Session() as db:
        session = await _create_session(db, "promoted-project", session_id="session-promoted")
        session_id = session.session_id
        node = await create_node(
            db,
            project_id="promoted-project",
            node_id="po:promoted-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id=session_id,
            canonical_payload_hash="node-hash",
            commit=False,
        )
        edge = await create_edge(
            db,
            project_id="promoted-project",
            edge_id="po:promoted-project:e:bbbbbbbbbbbbbbbbbbbbbbbb",
            session_id=session_id,
            source_node_id=node.node_id,
            target_node_id="ml_c01",
            relation_type="RELATED_TO",
            canonical_payload_hash="edge-hash",
            commit=False,
        )
        node_id = node.node_id
        edge_id = edge.edge_id
        await db.commit()
        for element_type, element_id in [("node", node_id), ("edge", edge_id)]:
            await update_validation_status(
                db,
                project_id="promoted-project",
                element_type=element_type,
                element_id=element_id,
                validation_status="valid",
            )
            await update_review_status(
                db,
                project_id="promoted-project",
                element_type=element_type,
                element_id=element_id,
                review_status="confirmed",
            )

        assert [item.node_id for item in await list_planner_visible_nodes(db, "promoted-project")] == [node_id]
        assert [item.edge_id for item in await list_planner_visible_edges(db, "promoted-project")] == [edge_id]

        reviewed = await update_extraction_session_status(
            db,
            project_id="promoted-project",
            session_id=session_id,
            session_status="validated",
        )
        reviewed = await update_extraction_session_status(
            db,
            project_id="promoted-project",
            session_id=reviewed.session_id,
            session_status="reviewed",
        )
        promoted = await update_extraction_session_status(
            db,
            project_id="promoted-project",
            session_id=reviewed.session_id,
            session_status="promoted",
        )

        assert promoted.session_status == "promoted"
        assert await list_planner_visible_nodes(db, "promoted-project") == []
        assert await list_planner_visible_edges(db, "promoted-project") == []


async def test_edges_require_visible_overlay_endpoints():
    async with _Session() as db:
        await _create_session(db, "edge-endpoint-project")
        source = await create_node(
            db,
            project_id="edge-endpoint-project",
            node_id="po:edge-endpoint-project:n:sourceaaaaaaaaaaaaaaaaaa",
            session_id="session-1",
            canonical_payload_hash="source-hash",
            commit=False,
        )
        target = await create_node(
            db,
            project_id="edge-endpoint-project",
            node_id="po:edge-endpoint-project:n:targetbbbbbbbbbbbbbbbbb",
            session_id="session-1",
            canonical_payload_hash="target-hash",
            commit=False,
        )
        edge = await create_edge(
            db,
            project_id="edge-endpoint-project",
            edge_id="po:edge-endpoint-project:e:edgecccccccccccccccccc",
            session_id="session-1",
            source_node_id=source.node_id,
            target_node_id=target.node_id,
            relation_type="RELATED_TO",
            canonical_payload_hash="edge-hash",
            commit=False,
        )
        source_id = source.node_id
        target_id = target.node_id
        edge_id = edge.edge_id
        await db.commit()
        for element_type, element_id in [("node", source_id), ("node", target_id), ("edge", edge_id)]:
            await update_validation_status(
                db,
                project_id="edge-endpoint-project",
                element_type=element_type,
                element_id=element_id,
                validation_status="valid",
            )
            await update_review_status(
                db,
                project_id="edge-endpoint-project",
                element_type=element_type,
                element_id=element_id,
                review_status="confirmed",
            )

        assert [item.edge_id for item in await list_planner_visible_edges(db, "edge-endpoint-project")] == [edge_id]

        await update_planning_enabled(
            db,
            project_id="edge-endpoint-project",
            element_type="node",
            element_id=target_id,
            planning_enabled=False,
        )

        assert await list_planner_visible_edges(db, "edge-endpoint-project") == []


async def test_closed_session_candidates_cannot_be_mutated():
    async with _Session() as db:
        session = await _create_session(db, "closed-mutation-project")
        session_id = session.session_id
        node = await create_node(
            db,
            project_id="closed-mutation-project",
            node_id="po:closed-mutation-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id=session_id,
            canonical_payload_hash="node-hash",
        )
        node_id = node.node_id
        await db.commit()
        archived = await update_extraction_session_status(
            db,
            project_id="closed-mutation-project",
            session_id=session_id,
            session_status="archived",
        )
        assert archived.session_status == "archived"

        update_calls = [
            lambda: update_validation_status(
                db,
                project_id="closed-mutation-project",
                element_type="node",
                element_id=node_id,
                validation_status="valid",
            ),
            lambda: update_review_status(
                db,
                project_id="closed-mutation-project",
                element_type="node",
                element_id=node_id,
                review_status="confirmed",
            ),
            lambda: update_planning_enabled(
                db,
                project_id="closed-mutation-project",
                element_type="node",
                element_id=node_id,
                planning_enabled=False,
            ),
            lambda: update_promotion_status(
                db,
                project_id="closed-mutation-project",
                element_type="node",
                element_id=node_id,
                promotion_status="promotion_ready",
            ),
        ]
        for update_call in update_calls:
            with pytest.raises(ValueError, match="OVERLAY_SESSION_NOT_EDITABLE"):
                await update_call()
            await db.rollback()


async def test_closed_sessions_reject_new_candidates():
    async with _Session() as db:
        session = await _create_session(db, "closed-create-project")
        session_id = session.session_id
        archived = await update_extraction_session_status(
            db,
            project_id="closed-create-project",
            session_id=session_id,
            session_status="archived",
        )
        assert archived.session_status == "archived"

        with pytest.raises(ValueError, match="OVERLAY_SESSION_NOT_EDITABLE"):
            await create_node(
                db,
                project_id="closed-create-project",
                node_id="po:closed-create-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
                session_id=session_id,
                canonical_payload_hash="node-hash",
            )
        await db.rollback()

        with pytest.raises(ValueError, match="OVERLAY_SESSION_NOT_EDITABLE"):
            await create_edge(
                db,
                project_id="closed-create-project",
                edge_id="po:closed-create-project:e:bbbbbbbbbbbbbbbbbbbbbbbb",
                session_id=session_id,
                source_node_id="ml_c01",
                target_node_id="ml_c02",
                relation_type="RELATED_TO",
                canonical_payload_hash="edge-hash",
            )
        await db.rollback()

        with pytest.raises(ValueError, match="OVERLAY_SESSION_NOT_EDITABLE"):
            await create_resource(
                db,
                project_id="closed-create-project",
                resource_id="po:closed-create-project:r:cccccccccccccccccccccccc",
                session_id=session_id,
                canonical_payload_hash="resource-hash",
            )


async def test_extraction_session_state_machine_accepts_only_allowed_transitions():
    async with _Session() as db:
        session = await _create_session(db, "session-project")
        session_id = session.session_id
        node = await create_node(
            db,
            project_id="session-project",
            node_id="po:session-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            session_id=session_id,
            canonical_payload_hash="node-hash",
            commit=False,
        )
        node_id = node.node_id
        await db.commit()

        with pytest.raises(ValueError, match="INVALID_OVERLAY_SESSION_TRANSITION"):
            await update_extraction_session_status(
                db,
                project_id="session-project",
                session_id=session_id,
                session_status="reviewed",
            )
        await db.rollback()

        validated = await update_extraction_session_status(
            db,
            project_id="session-project",
            session_id=session_id,
            session_status="validated",
        )
        with pytest.raises(ValueError, match="OVERLAY_SESSION_REVIEW_REQUIRED"):
            await update_extraction_session_status(
                db,
                project_id="session-project",
                session_id=validated.session_id,
                session_status="reviewed",
            )
        await db.rollback()

        await update_review_status(
            db,
            project_id="session-project",
            element_type="node",
            element_id=node_id,
            review_status="confirmed",
        )
        reviewed = await update_extraction_session_status(
            db,
            project_id="session-project",
            session_id=session_id,
            session_status="reviewed",
        )
        archived = await update_extraction_session_status(
            db,
            project_id="session-project",
            session_id=reviewed.session_id,
            session_status="archived",
        )

        assert archived.session_status == "archived"
        with pytest.raises(ValueError, match="INVALID_OVERLAY_SESSION_TRANSITION"):
            await update_extraction_session_status(
                db,
                project_id="session-project",
                session_id=archived.session_id,
                session_status="failed",
            )
