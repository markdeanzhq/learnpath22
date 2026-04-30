from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.init_db import create_project_overlay_indexes, upgrade_project_overlay_schema
from app.models.sqlite_models import (
    Base,
    LearningProject,
    PersistedSearchResult,
    ProjectOverlayExtractionSession,
    ProjectOverlayResource,
    ProjectOverlaySource,
)
from app.repositories.project_overlay_repository import create_extraction_session, update_source
from app.services.project_graph_snapshot_service import build_project_graph_snapshot

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
        await upgrade_project_overlay_schema(conn)
        await create_project_overlay_indexes(conn)
    yield
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture(autouse=True)
def _disable_url_body_fetch(monkeypatch):
    from app.services.url_content_fetch_service import UrlContentFetchResult

    async def fake_fetch_url_text_excerpt(url: str) -> UrlContentFetchResult:
        return UrlContentFetchResult(
            raw_text_excerpt=None,
            summary=None,
            quality_status="url_body_unavailable",
            metadata={"url_fetch": {"status": "disabled_in_test", "url": url}},
        )

    monkeypatch.setattr("app.api.v1.graph.fetch_url_text_excerpt", fake_fetch_url_text_excerpt)
    monkeypatch.setattr("app.services.saved_search_overlay_bridge_service.fetch_url_text_excerpt", fake_fetch_url_text_excerpt)


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


async def test_referenced_overlay_source_cannot_be_updated_in_place():
    async with _Session() as db:
        await _create_project(db, "immutable-source-project")
        from app.repositories.project_overlay_repository import create_source

        source = await create_source(
            db,
            project_id="immutable-source-project",
            source_type="pasted_text",
            content_hash="hash-1",
            raw_text_excerpt="原始文本摘要",
        )
        await create_extraction_session(
            db,
            project_id="immutable-source-project",
            source_ids_json=f'["{source.source_id}"]',
        )

        with pytest.raises(ValueError, match="OVERLAY_SOURCE_IMMUTABLE"):
            await update_source(
                db,
                project_id="immutable-source-project",
                source_id=source.source_id,
                raw_text_excerpt="修改后的摘要",
            )


async def test_persisted_search_results_restore_quality_and_binding_state(client, project, db_session):
    persist_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "逻辑回归 学习资料",
            "provider": "tavily",
            "url": "https://example.com/logistic-regression",
            "title": "逻辑回归教程",
            "snippet": "覆盖逻辑回归与分类评估。",
            "result_rank": 1,
            "summary": "适合入门复习。",
            "quality_status": "good",
            "is_selected": True,
        },
    )
    assert persist_resp.status_code == 200
    persisted = persist_resp.json()
    assert persisted["summary"] == "适合入门复习。"
    assert persisted["quality_status"] == "good"
    assert persisted["binding_count"] == 0

    source_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/sources",
        json={
            "source_type": "search_url",
            "url": persisted["url"],
            "title": persisted["title"],
            "snippet": persisted["snippet"],
            "provider": persisted["provider"],
            "query": persisted["query"],
            "result_rank": persisted["result_rank"],
            "summary": persisted["summary"],
            "quality_status": persisted["quality_status"],
        },
    )
    assert source_resp.status_code == 200
    source = source_resp.json()
    assert source["source_type"] == "search_url"
    assert source["summary"] == "适合入门复习。"
    assert source["quality_status"] == "good"

    session = ProjectOverlayExtractionSession(
        session_id="phase3-session",
        project_id=project["id"],
        source_ids_json=f'["{source["source_id"]}"]',
    )
    resource = ProjectOverlayResource(
        resource_id="po:phase3:r:aaaaaaaaaaaaaaaaaaaaaaaa",
        project_id=project["id"],
        session_id="phase3-session",
        title=persisted["title"],
        url=persisted["url"],
        resource_type="web",
        summary=persisted["summary"],
        canonical_payload_hash="resource-hash",
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(resource)
    await db_session.commit()

    binding_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource.resource_id,
            "target_type": "project_node",
            "target_id": "ml_c01",
            "source_result_id": persisted["result_id"],
        },
    )
    assert binding_resp.status_code == 200
    binding = binding_resp.json()
    assert binding["target_type"] == "project_node"
    assert binding["target_id"] == "ml_c01"
    assert binding["source_result_id"] == persisted["result_id"]

    list_resp = await client.get(f"/api/v1/projects/{project['id']}/search-results")
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["result_id"] == persisted["result_id"]
    assert listed[0]["summary"] == "适合入门复习。"
    assert listed[0]["quality_status"] == "good"
    assert listed[0]["is_selected"] is True
    assert listed[0]["binding_count"] == 1


async def test_pasted_text_overlay_source_persists_hash_and_excerpt(client, project):
    raw_text = "机器学习中的逻辑回归可以用于二分类任务。" * 20
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/sources",
        json={
            "source_type": "pasted_text",
            "raw_text": raw_text,
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["source_type"] == "pasted_text"
    assert len(data["content_hash"]) == 64
    assert data["raw_text_excerpt"] == raw_text[:500]
    assert data["created_at"] is not None


async def test_search_url_overlay_source_fetches_body_excerpt(client, project, monkeypatch):
    from app.services.url_content_fetch_service import UrlContentFetchResult

    async def fake_fetch_url_text_excerpt(url: str) -> UrlContentFetchResult:
        return UrlContentFetchResult(
            raw_text_excerpt="随机森林正文包含定义、前置知识和实践案例。",
            summary="随机森林正文包含定义、前置知识和实践案例。",
            quality_status="url_body_fetched",
            metadata={"url_fetch": {"status": "fetched", "url": url}},
        )

    monkeypatch.setattr("app.api.v1.graph.fetch_url_text_excerpt", fake_fetch_url_text_excerpt)

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/sources",
        json={
            "source_type": "search_url",
            "url": "https://example.com/random-forest-body",
            "title": "随机森林教程",
            "snippet": "搜索摘要",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["raw_text_excerpt"] == "随机森林正文包含定义、前置知识和实践案例。"
    assert data["summary"] == "随机森林正文包含定义、前置知识和实践案例。"
    assert data["quality_status"] == "url_body_fetched"
    assert "url_fetch" in data["metadata_json"]


async def test_saved_search_bridge_fetches_body_excerpt(client, project, db_session, monkeypatch):
    from app.services.url_content_fetch_service import UrlContentFetchResult

    async def fake_fetch_url_text_excerpt(url: str) -> UrlContentFetchResult:
        return UrlContentFetchResult(
            raw_text_excerpt="梯度下降网页正文包含概念、公式和代码练习。",
            summary="梯度下降网页正文包含概念、公式和代码练习。",
            quality_status="url_body_fetched",
            metadata={"url_fetch": {"status": "fetched", "url": url}},
        )

    monkeypatch.setattr("app.services.saved_search_overlay_bridge_service.fetch_url_text_excerpt", fake_fetch_url_text_excerpt)

    persist_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "梯度下降 学习资料",
            "provider": "tavily",
            "url": "https://example.com/gradient-descent-body",
            "title": "梯度下降教程",
            "snippet": "覆盖梯度下降直觉与实践。",
            "result_rank": 1,
        },
    )
    result_id = persist_resp.json()["result_id"]

    bridge_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )

    assert bridge_resp.status_code == 200
    source_id = bridge_resp.json()["source_ids"][0]
    stored_source = await db_session.get(ProjectOverlaySource, source_id)
    assert stored_source.raw_text_excerpt == "梯度下降网页正文包含概念、公式和代码练习。"
    assert stored_source.summary == "梯度下降网页正文包含概念、公式和代码练习。"
    assert stored_source.quality_status == "url_body_fetched"
    assert "url_fetch" in stored_source.metadata_json


async def test_saved_search_bridge_creates_stable_search_url_source(client, project, db_session):
    persist_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "梯度下降 学习资料",
            "provider": "tavily",
            "url": "https://example.com/gradient-descent",
            "title": "梯度下降教程",
            "snippet": "覆盖梯度下降直觉与实践。",
            "result_rank": 1,
            "summary": "适合作为补充材料。",
            "quality_status": "good",
        },
    )
    assert persist_resp.status_code == 200
    result_id = persist_resp.json()["result_id"]

    first_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )
    second_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )

    assert first_resp.status_code == 200
    assert second_resp.status_code == 200
    first = first_resp.json()
    second = second_resp.json()
    assert first["source_ids"] == second["source_ids"]
    assert first["results"][0]["result_id"] == result_id
    assert first["results"][0]["source_type"] == "search_url"
    assert first["results"][0]["reused"] is False
    assert second["results"][0]["reused"] is True

    source_id = first["source_ids"][0]
    stored_result = await db_session.get(PersistedSearchResult, result_id)
    stored_source = await db_session.get(ProjectOverlaySource, source_id)
    assert stored_result.source_id == source_id
    assert stored_source.project_id == project["id"]
    assert stored_source.source_type == "search_url"
    assert stored_source.url == "https://example.com/gradient-descent"
    assert stored_source.summary == "适合作为补充材料。"


async def test_saved_search_bridge_source_id_is_monotonic_across_replays(client, project, db_session):
    result_ids = []
    for index, topic in enumerate(["线性回归", "模型评估", "正则化"], start=1):
        persist_resp = await client.post(
            f"/api/v1/projects/{project['id']}/search-results",
            json={
                "query": f"{topic} 学习资料",
                "provider": "tavily",
                "url": f"https://example.com/{index}",
                "title": f"{topic} 教程",
                "result_rank": index,
            },
        )
        assert persist_resp.status_code == 200
        result_ids.append(persist_resp.json()["result_id"])

    known_source_ids: dict[str, str] = {}
    for replay_ids in [result_ids[:1], result_ids[:2], result_ids[::-1], result_ids]:
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
            json={"result_ids": replay_ids},
        )
        assert resp.status_code == 200
        by_result_id = {item["result_id"]: item["source_id"] for item in resp.json()["results"]}
        for result_id, source_id in by_result_id.items():
            if result_id in known_source_ids:
                assert known_source_ids[result_id] == source_id
            known_source_ids[result_id] = source_id

        db_session.expire_all()
        stored = [await db_session.get(PersistedSearchResult, result_id) for result_id in result_ids]
        for row in stored:
            if row.result_id in known_source_ids:
                assert row.source_id == known_source_ids[row.result_id]

    assert set(known_source_ids) == set(result_ids)
    assert len(set(known_source_ids.values())) == len(result_ids)


async def test_saved_search_bridge_reuses_equivalent_source_and_repairs_missing_source_id(client, project, db_session):
    persist_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "逻辑回归 学习资料",
            "provider": "tavily",
            "url": "https://example.com/logistic-regression-reuse",
            "title": "逻辑回归教程",
            "snippet": "覆盖逻辑回归。",
            "result_rank": 2,
        },
    )
    result_id = persist_resp.json()["result_id"]
    equivalent_source = ProjectOverlaySource(
        project_id=project["id"],
        source_type="search_url",
        url="https://example.com/logistic-regression-reuse",
        title="旧逻辑回归教程",
        snippet="旧摘要",
        provider="tavily",
        query="逻辑回归 学习资料",
        result_rank=2,
    )
    db_session.add(equivalent_source)
    await db_session.commit()

    bridge_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )

    assert bridge_resp.status_code == 200
    bridged = bridge_resp.json()["results"][0]
    assert bridged["source_id"] == equivalent_source.source_id
    assert bridged["reused"] is True
    assert bridged["repaired"] is False
    repaired_result = await db_session.get(PersistedSearchResult, result_id)
    assert repaired_result.source_id == equivalent_source.source_id

    replay_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )
    assert replay_resp.status_code == 200
    assert replay_resp.json()["source_ids"] == [equivalent_source.source_id]


async def test_saved_search_bridge_rejects_cross_project_and_duplicates(client, project, db_session):
    other_project = LearningProject(
        id="bridge-other-project",
        title="另一个项目",
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        domain="machine_learning",
    )
    db_session.add(other_project)
    await db_session.commit()

    cross_project_result = PersistedSearchResult(
        project_id=other_project.id,
        query="跨项目资料",
        provider="tavily",
        url="https://example.com/cross-project",
        title="跨项目资料",
    )
    db_session.add(cross_project_result)
    await db_session.commit()

    persist_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "SVM 学习资料",
            "provider": "tavily",
            "url": "https://example.com/svm",
            "title": "SVM 教程",
        },
    )
    result_id = persist_resp.json()["result_id"]

    duplicate_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id, result_id]},
    )
    missing_resp = await client.post(
        f"/api/v1/projects/not-found/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )
    unknown_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": ["not-a-result"]},
    )
    cross_project_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [cross_project_result.result_id]},
    )

    assert duplicate_resp.status_code == 422
    assert duplicate_resp.json()["error"] == "DUPLICATE_PERSISTED_SEARCH_RESULT_ID"
    assert missing_resp.status_code == 404
    assert unknown_resp.status_code == 422
    assert unknown_resp.json()["error"] == "PERSISTED_SEARCH_RESULT_NOT_FOUND"
    assert cross_project_resp.status_code == 422
    assert cross_project_resp.json()["error"] == "PERSISTED_SEARCH_RESULT_NOT_FOUND"


async def test_extraction_session_rejects_result_ids_and_accepts_bridged_source_ids(client, project):
    persist_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results",
        json={
            "query": "决策树 学习资料",
            "provider": "tavily",
            "url": "https://example.com/decision-tree",
            "title": "决策树教程",
        },
    )
    result_id = persist_resp.json()["result_id"]

    direct_result_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [result_id],
            "extraction_payload": {"nodes": [], "edges": [], "resources": [], "warnings": []},
        },
    )
    mixed_field_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [],
            "result_ids": [result_id],
            "extraction_payload": {"nodes": [], "edges": [], "resources": [], "warnings": []},
        },
    )
    bridge_resp = await client.post(
        f"/api/v1/projects/{project['id']}/search-results/bridge-overlay-sources",
        json={"result_ids": [result_id]},
    )
    source_id = bridge_resp.json()["source_ids"][0]
    source_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source_id],
            "extraction_payload": {"nodes": [], "edges": [], "resources": [], "warnings": []},
        },
    )

    assert direct_result_resp.status_code == 404
    assert direct_result_resp.json()["error"] == "overlay source 不存在"
    assert mixed_field_resp.status_code == 422
    assert source_resp.status_code == 200
    assert source_resp.json()["session"]["source_ids"] == [source_id]


async def test_resource_only_overlay_changes_do_not_change_project_graph_snapshot(client, project, db_session):
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    session = ProjectOverlayExtractionSession(
        session_id="resource-only-session",
        project_id=project["id"],
        source_ids_json="[]",
    )
    resource = ProjectOverlayResource(
        resource_id="po:resource-only:r:aaaaaaaaaaaaaaaa",
        project_id=project["id"],
        session_id=session.session_id,
        title="Resource-only material",
        url="https://example.com/resource-only",
        resource_type="article",
        summary="Only resource state changes",
        validation_status="valid",
        review_status="confirmed",
        planning_enabled=True,
        promotion_status="promotion_ready",
        canonical_payload_hash="resource-only-hash",
    )
    db_session.add(session)
    await db_session.flush()
    db_session.add(resource)
    await db_session.commit()

    binding_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource.resource_id,
            "target_type": "project_node",
            "target_id": "ml_c01",
            "binding_source": "overlay",
        },
    )
    planning_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/resources/{resource.resource_id}/planning",
        json={"planning_enabled": False},
    )
    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])

    assert binding_resp.status_code == 200
    assert planning_resp.status_code == 200
    assert after.project_graph_hash == before.project_graph_hash
    assert after.nodes_by_id == before.nodes_by_id
    assert after.requires_edges == before.requires_edges
    assert after.related_edges == before.related_edges
