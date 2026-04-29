from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import event, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import create_project_overlay_indexes, create_query_indexes, upgrade_project_overlay_schema
from app.models.sqlite_models import (
    Base,
    LearningProject,
    PersistedSearchResult,
    ProjectOverlayEdge,
    ProjectOverlayExtractionSession,
    ProjectOverlayNode,
    ProjectOverlayPromotionBatch,
    ProjectOverlayPromotionItem,
    ProjectOverlayResource,
    ProjectOverlayResourceBinding,
    ProjectOverlaySource,
)
from app.repositories.project_repository import delete_project
from app.services.project_overlay_ids import (
    assert_overlay_id_available,
    build_overlay_id,
    overlay_payload_hash,
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


OVERLAY_TABLES = {
    "project_overlay_sources",
    "project_overlay_extraction_sessions",
    "project_overlay_nodes",
    "project_overlay_edges",
    "project_overlay_resources",
    "project_overlay_resource_bindings",
    "project_overlay_promotion_batches",
    "project_overlay_promotion_items",
    "persisted_search_results",
}

EXPECTED_INDEXES = {
    "idx_project_overlay_sources_project_id",
    "idx_project_overlay_extraction_sessions_project_id",
    "idx_project_overlay_nodes_project_id",
    "idx_project_overlay_nodes_session_id",
    "idx_project_overlay_edges_project_id",
    "idx_project_overlay_edges_session_id",
    "idx_project_overlay_resources_project_id",
    "idx_project_overlay_resources_session_id",
    "idx_project_overlay_resource_bindings_project_id",
    "idx_project_overlay_resource_bindings_resource_id",
    "idx_project_overlay_promotion_batches_project_id",
    "idx_project_overlay_promotion_items_project_id",
    "idx_project_overlay_promotion_items_batch_id",
    "idx_persisted_search_results_project_id",
    "idx_persisted_search_results_source_id",
}

EXPECTED_QUERY_INDEXES = {
    "idx_graph_review_project_type_status",
    "idx_graph_review_project_type_element",
    "idx_learning_paths_project_latest",
    "idx_learner_profiles_project_created",
    "idx_overlay_sessions_project_status",
    "idx_overlay_nodes_project_promotion_created",
    "idx_overlay_edges_project_promotion_created",
    "idx_overlay_nodes_planner_visible",
    "idx_overlay_edges_planner_visible",
}


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


async def test_overlay_tables_and_indexes_are_created_idempotently():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await create_project_overlay_indexes(conn)
        await create_project_overlay_indexes(conn)

    async with _engine.connect() as conn:
        tables = await conn.run_sync(lambda sync_conn: set(inspect(sync_conn).get_table_names()))
        indexes = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'index'")
        )

    assert OVERLAY_TABLES <= tables
    assert EXPECTED_INDEXES <= {row[0] for row in indexes}


async def test_query_indexes_are_created_idempotently():
    async with _engine.begin() as conn:
        await create_query_indexes(conn)
        await create_query_indexes(conn)

    async with _engine.connect() as conn:
        indexes = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type = 'index'")
        )

    assert EXPECTED_QUERY_INDEXES <= {row[0] for row in indexes}


async def test_overlay_upgrade_adds_persisted_search_result_source_id_to_legacy_table():
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("DROP TABLE persisted_search_results"))
        await conn.execute(
            text(
                "CREATE TABLE persisted_search_results ("
                "result_id VARCHAR(36) PRIMARY KEY, "
                "project_id VARCHAR(36) NOT NULL, "
                "query TEXT NOT NULL, "
                "provider VARCHAR(50) NOT NULL, "
                "url TEXT NOT NULL, "
                "title TEXT NOT NULL, "
                "created_at DATETIME NOT NULL"
                ")"
            )
        )
        await upgrade_project_overlay_schema(conn)
        await upgrade_project_overlay_schema(conn)

    async with _engine.connect() as conn:
        columns = await conn.execute(text("PRAGMA table_info(persisted_search_results)"))

    assert "source_id" in {row[1] for row in columns}


async def test_overlay_candidate_defaults_and_resource_duplicate_schema():
    async with _Session() as db:
        await _create_project(db, "defaults-project")
        session = ProjectOverlayExtractionSession(
            session_id="session-defaults",
            project_id="defaults-project",
        )
        node = ProjectOverlayNode(
            node_id="po:defaults-project:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            project_id="defaults-project",
            session_id="session-defaults",
            canonical_payload_hash="node-hash",
        )
        edge = ProjectOverlayEdge(
            edge_id="po:defaults-project:e:bbbbbbbbbbbbbbbbbbbbbbbb",
            project_id="defaults-project",
            session_id="session-defaults",
            source_node_id=node.node_id,
            target_node_id="ml_c01",
            relation_type="RELATED_TO",
            canonical_payload_hash="edge-hash",
        )
        resource = ProjectOverlayResource(
            resource_id="po:defaults-project:r:cccccccccccccccccccccccc",
            project_id="defaults-project",
            session_id="session-defaults",
            duplicate_candidates_json='[{"resource_id":"existing"}]',
            canonical_payload_hash="resource-hash",
        )
        db.add(session)
        await db.flush()
        db.add_all([node, edge, resource])
        await db.commit()

    async with _Session() as db:
        loaded_session = await db.get(ProjectOverlayExtractionSession, "session-defaults")
        loaded_node = await db.get(ProjectOverlayNode, node.node_id)
        loaded_edge = await db.get(ProjectOverlayEdge, edge.edge_id)
        loaded_resource = await db.get(ProjectOverlayResource, resource.resource_id)

    assert loaded_session is not None
    assert loaded_session.session_status == "drafted"
    for candidate in [loaded_node, loaded_edge, loaded_resource]:
        assert candidate is not None
        assert candidate.validation_status == "unchecked"
        assert candidate.review_status == "pending"
        assert candidate.planning_enabled is True
        assert candidate.promotion_status == "not_promoted"
        assert candidate.canonical_payload_hash is not None
    assert loaded_resource.duplicate_candidates_json == '[{"resource_id":"existing"}]'


async def test_overlay_id_generation_is_bounded_and_round_trips_long_project_id():
    project_id = "p" * 120
    payload = {"name": "梯度下降补充", "source": "pasted text"}
    payload_hash = overlay_payload_hash(payload)
    node_id = build_overlay_id(project_id, "n", payload)

    assert node_id.startswith(f"po:{project_id}:n:")
    assert len(node_id) <= 160

    async with _Session() as db:
        await _create_project(db, project_id)
        node = ProjectOverlayNode(
            node_id=node_id,
            project_id=project_id,
            name="梯度下降补充",
            canonical_payload_hash=payload_hash,
        )
        db.add(node)
        await db.commit()

    async with _Session() as db:
        loaded = await db.get(ProjectOverlayNode, node_id)

    assert loaded is not None
    assert loaded.node_id == node_id
    assert loaded.canonical_payload_hash == payload_hash


async def test_overlay_id_collision_check_allows_exact_replay_and_rejects_collision():
    project_id = "project-collision"
    payload = {"name": "线性代数复习"}
    overlay_id = build_overlay_id(project_id, "n", payload)
    payload_hash = overlay_payload_hash(payload)

    async with _Session() as db:
        await _create_project(db, project_id)
        db.add(
            ProjectOverlayNode(
                node_id=overlay_id,
                project_id=project_id,
                name="线性代数复习",
                canonical_payload_hash=payload_hash,
            )
        )
        await db.commit()

    async with _Session() as db:
        await assert_overlay_id_available(
            db,
            kind="n",
            overlay_id=overlay_id,
            canonical_payload_hash=payload_hash,
        )
        with pytest.raises(ValueError, match="OVERLAY_ID_COLLISION"):
            await assert_overlay_id_available(
                db,
                kind="n",
                overlay_id=overlay_id,
                canonical_payload_hash=overlay_payload_hash({"name": "不同概念"}),
            )


async def test_overlay_rejects_cross_project_links_and_missing_canonical_hash():
    async with _Session() as db:
        await _create_project(db, "project-a")
        await _create_project(db, "project-b")
        db.add_all([
            ProjectOverlaySource(
                source_id="source-a",
                project_id="project-a",
                source_type="pasted_text",
            ),
            ProjectOverlayExtractionSession(
                session_id="session-a",
                project_id="project-a",
            ),
            ProjectOverlayPromotionBatch(
                batch_id="batch-a",
                project_id="project-a",
            ),
        ])
        await db.flush()
        db.add(
            ProjectOverlayResource(
                resource_id="po:project-a:r:aaaaaaaaaaaaaaaaaaaaaaaa",
                project_id="project-a",
                session_id="session-a",
                canonical_payload_hash="resource-hash",
            )
        )
        await db.commit()

        db.add(
            ProjectOverlayNode(
                node_id="po:project-b:n:bbbbbbbbbbbbbbbbbbbbbbbb",
                project_id="project-b",
                session_id="session-a",
                canonical_payload_hash="node-hash",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        db.add(
            ProjectOverlayResourceBinding(
                project_id="project-b",
                resource_id="po:project-a:r:aaaaaaaaaaaaaaaaaaaaaaaa",
                target_type="node",
                target_id="ml_c01",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        db.add(
            ProjectOverlayPromotionItem(
                project_id="project-b",
                batch_id="batch-a",
                element_type="node",
                element_id="ml_c01",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        db.add(
            PersistedSearchResult(
                result_id="result-cross-source",
                project_id="project-b",
                source_id="source-a",
                query="梯度下降",
                provider="tavily",
                url="https://example.com/gradient",
                title="Gradient",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        db.add(
            ProjectOverlayEdge(
                edge_id="po:project-a:e:cccccccccccccccccccccccc",
                project_id="project-a",
                session_id="session-a",
                source_node_id="ml_c01",
                target_node_id="ml_c02",
                relation_type="RELATED_TO",
            )
        )
        with pytest.raises(IntegrityError):
            await db.commit()


async def test_delete_project_removes_overlay_rows_without_touching_other_projects():
    async with _Session() as db:
        await _create_project(db, "delete-me")
        await _create_project(db, "keep-me")

        source = ProjectOverlaySource(
            source_id="source-delete",
            project_id="delete-me",
            source_type="pasted_text",
            content_hash="h1",
        )
        keep_source = ProjectOverlaySource(
            source_id="source-keep",
            project_id="keep-me",
            source_type="pasted_text",
            content_hash="h2",
        )
        session = ProjectOverlayExtractionSession(
            session_id="session-delete",
            project_id="delete-me",
            source_ids_json='["source-delete"]',
        )
        keep_session = ProjectOverlayExtractionSession(
            session_id="session-keep",
            project_id="keep-me",
            source_ids_json='["source-keep"]',
        )
        node = ProjectOverlayNode(
            node_id="po:delete-me:n:aaaaaaaaaaaaaaaaaaaaaaaa",
            project_id="delete-me",
            session_id="session-delete",
            canonical_payload_hash="n-hash",
        )
        edge = ProjectOverlayEdge(
            edge_id="po:delete-me:e:bbbbbbbbbbbbbbbbbbbbbbbb",
            project_id="delete-me",
            session_id="session-delete",
            source_node_id=node.node_id,
            target_node_id="ml_c01",
            relation_type="RELATED_TO",
            canonical_payload_hash="e-hash",
        )
        resource = ProjectOverlayResource(
            resource_id="po:delete-me:r:cccccccccccccccccccccccc",
            project_id="delete-me",
            session_id="session-delete",
            canonical_payload_hash="r-hash",
        )
        keep_resource = ProjectOverlayResource(
            resource_id="po:keep-me:r:dddddddddddddddddddddddd",
            project_id="keep-me",
            session_id="session-keep",
            canonical_payload_hash="keep-r-hash",
        )
        binding = ProjectOverlayResourceBinding(
            project_id="delete-me",
            resource_id=resource.resource_id,
            target_type="node",
            target_id=node.node_id,
        )
        keep_binding = ProjectOverlayResourceBinding(
            id="binding-keep",
            project_id="keep-me",
            resource_id=keep_resource.resource_id,
            target_type="node",
            target_id="ml_c01",
        )
        batch = ProjectOverlayPromotionBatch(
            batch_id="batch-delete",
            project_id="delete-me",
        )
        keep_batch = ProjectOverlayPromotionBatch(
            batch_id="batch-keep",
            project_id="keep-me",
        )
        item = ProjectOverlayPromotionItem(
            project_id="delete-me",
            batch_id="batch-delete",
            element_type="node",
            element_id=node.node_id,
            source_session_id="session-delete",
        )
        keep_item = ProjectOverlayPromotionItem(
            id="item-keep",
            project_id="keep-me",
            batch_id="batch-keep",
            element_type="resource",
            element_id=keep_resource.resource_id,
            source_session_id="session-keep",
        )
        search_result = PersistedSearchResult(
            result_id="result-delete",
            project_id="delete-me",
            source_id="source-delete",
            query="梯度下降",
            provider="tavily",
            url="https://example.com/gradient",
            title="Gradient",
        )
        keep_search_result = PersistedSearchResult(
            result_id="result-keep",
            project_id="keep-me",
            source_id="source-keep",
            query="线性代数",
            provider="tavily",
            url="https://example.com/linear",
            title="Linear Algebra",
        )
        db.add_all([source, keep_source, session, keep_session, batch, keep_batch])
        await db.flush()
        db.add_all([node, edge, resource, keep_resource, search_result, keep_search_result])
        await db.flush()
        db.add_all([binding, keep_binding, item, keep_item])
        await db.commit()

        deleted = await delete_project(db, "delete-me")

    assert deleted is True

    checks = [
        (ProjectOverlaySource, ProjectOverlaySource.project_id == "delete-me"),
        (ProjectOverlayExtractionSession, ProjectOverlayExtractionSession.project_id == "delete-me"),
        (ProjectOverlayNode, ProjectOverlayNode.project_id == "delete-me"),
        (ProjectOverlayEdge, ProjectOverlayEdge.project_id == "delete-me"),
        (ProjectOverlayResource, ProjectOverlayResource.project_id == "delete-me"),
        (ProjectOverlayResourceBinding, ProjectOverlayResourceBinding.project_id == "delete-me"),
        (ProjectOverlayPromotionBatch, ProjectOverlayPromotionBatch.project_id == "delete-me"),
        (ProjectOverlayPromotionItem, ProjectOverlayPromotionItem.project_id == "delete-me"),
        (PersistedSearchResult, PersistedSearchResult.project_id == "delete-me"),
    ]
    async with _Session() as db:
        for model, condition in checks:
            result = await db.execute(select(model).where(condition))
            assert result.scalar_one_or_none() is None
        assert await db.get(ProjectOverlaySource, "source-keep") is not None
        assert await db.get(ProjectOverlayExtractionSession, "session-keep") is not None
        assert await db.get(ProjectOverlayResource, "po:keep-me:r:dddddddddddddddddddddddd") is not None
        assert await db.get(ProjectOverlayResourceBinding, "binding-keep") is not None
        assert await db.get(ProjectOverlayPromotionBatch, "batch-keep") is not None
        assert await db.get(ProjectOverlayPromotionItem, "item-keep") is not None
        assert await db.get(PersistedSearchResult, "result-keep") is not None
        assert await db.get(LearningProject, "keep-me") is not None
