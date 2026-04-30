from __future__ import annotations

from unittest.mock import AsyncMock, patch

from app.models.sqlite_models import PersistedSearchResult, ProjectOverlaySource


def _valid_node(name: str) -> dict:
    return {
        "name": name,
        "group": "concept",
        "category": "core",
        "summary": f"{name} 的候选摘要",
        "difficulty_final": 2,
        "importance_final": 4,
        "estimated_hours": 3,
        "req_math": 2,
        "req_coding": 2,
        "req_ml": 1,
        "theory_weight": 0.6,
        "practice_weight": 0.4,
        "confidence": 0.82,
        "legality_rationale": f"{name} 是合法的机器学习扩展候选",
        "evidence_spans": [{"source_id": "auto-source", "text": name}],
    }


async def test_auto_overlay_draft_endpoint_searches_persists_and_creates_session(client, project, db_session):
    async def fake_preview(db, *, project_id, source_ids, mode="default", domain=None):
        payload = {
            "nodes": [_valid_node("随机森林扩展")],
            "edges": [
                {
                    "source_name_or_id": "随机森林扩展",
                    "target_name_or_id": "ml_c01",
                    "relation_type": "RELATED_TO",
                    "confidence": 0.74,
                    "legality_rationale": "资料把随机森林作为机器学习基础扩展概念。",
                }
            ],
            "resources": [
                {
                    "title": "随机森林扩展资料",
                    "url": "https://example.com/random-forest",
                    "resource_type": "article",
                    "summary": "介绍随机森林基础概念。",
                    "quality_score": 0.82,
                    "confidence": 0.8,
                    "evidence_source_id": source_ids[0],
                }
            ],
            "warnings": ["llm_generated"],
        }
        return {
            "source_ids": source_ids,
            "mode": mode,
            "extraction_payload": payload,
            "warnings": payload["warnings"],
            "counts": {"nodes": 1, "edges": 1, "resources": 1},
            "provenance": {
                "schema_version": "v1",
                "draft_origin": "llm_overlay_extraction",
                "draft_engine": "llm",
                "model": "mock-llm",
                "writes_formal_graph": False,
                "writes_formal_path": False,
            },
        }

    search_mock = AsyncMock(return_value=[
        {
            "title": "随机森林入门",
            "url": "https://example.com/random-forest",
            "snippet": "随机森林是基于决策树的集成学习方法。",
            "score": 0.91,
        }
    ])
    from app.services.url_content_fetch_service import UrlContentFetchResult

    with (
        patch("app.services.project_overlay_auto_draft_service.search", search_mock),
        patch("app.services.saved_search_overlay_bridge_service.fetch_url_text_excerpt", AsyncMock(return_value=UrlContentFetchResult(
            raw_text_excerpt="随机森林网页正文",
            summary="随机森林网页正文",
            quality_status="url_body_fetched",
            metadata={"url_fetch": {"status": "fetched"}},
        ))),
        patch("app.services.project_overlay_auto_draft_service.preview_overlay_extraction_payload_from_sources", side_effect=fake_preview),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/graph/overlay/auto-drafts",
            json={"query": "随机森林", "max_results": 2},
        )

    assert resp.status_code == 200
    data = resp.json()
    search_mock.assert_awaited_once_with("随机森林", max_results=2)
    assert data["session"]["session_status"] == "validated"
    assert data["session"]["provenance"]["draft_origin"] == "auto_overlay_draft"
    assert data["session"]["provenance"]["draft_engine"] == "search_llm"
    assert data["nodes"][0]["name"] == "随机森林扩展"
    assert data["nodes"][0]["validation_status"] == "valid"
    assert data["resources"][0]["source_evidence"]["source_id"] == data["sources"][0]["source_id"]
    assert data["auto_draft"] == {
        "query": "随机森林",
        "search_result_count": 1,
        "selected_result_count": 1,
        "selected_result_ids": data["auto_draft"]["selected_result_ids"],
        "source_ids": [data["sources"][0]["source_id"]],
        "reused_source_count": 0,
        "preview_counts": {"nodes": 1, "edges": 1, "resources": 1},
        "validation_summary": {"has_blocking_errors": False, "needs_review": False, "invalid_count": 0, "needs_review_count": 0},
    }

    result_id = data["auto_draft"]["selected_result_ids"][0]
    stored_result = await db_session.get(PersistedSearchResult, result_id)
    stored_source = await db_session.get(ProjectOverlaySource, data["sources"][0]["source_id"])
    assert stored_result is not None
    assert stored_result.source_id == stored_source.source_id
    assert stored_result.query == "随机森林"
    assert stored_source.source_type == "search_url"
    assert stored_source.url == "https://example.com/random-forest"


async def test_auto_overlay_draft_endpoint_reports_empty_search(client, project):
    with patch("app.services.project_overlay_auto_draft_service.search", AsyncMock(return_value=[])):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/graph/overlay/auto-drafts",
            json={"query": "没有结果的概念"},
        )

    assert resp.status_code == 422
    assert resp.json()["error"] == "AUTO_DRAFT_NO_SEARCH_RESULTS"
