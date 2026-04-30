from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import select

from app.core.config import replace_runtime_settings
from app.models.sqlite_models import ProjectOverlayExtractionSession
from app.repositories.project_overlay_repository import (
    create_source,
    list_planner_visible_nodes,
    update_planning_enabled,
    update_review_status,
)
from app.services.domain_pack_service import get_domain_pack_service
from app.services.graph_service import build_path_graph_elements_from_snapshot
from app.services import project_graph_snapshot_service as snapshot_module
from app.services.project_graph_snapshot_service import (
    build_project_graph_snapshot,
    clear_project_graph_snapshot_cache,
    get_project_graph_snapshot_cache_stats,
)
from app.services.project_overlay_extraction_service import create_extraction_session_from_sources


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
        "confidence": 0.8,
        "legality_rationale": f"{name} 是合法的知识节点候选",
        "evidence_spans": [{"source_id": "evidence-1", "text": name}],
    }


async def _create_overlay_source(db_session, project_id: str):
    source = await create_source(
        db_session,
        project_id=project_id,
        source_type="pasted_text",
        content_hash="phase4-source-hash",
        raw_text_excerpt="机器学习补充资料",
        commit=False,
    )
    await db_session.commit()
    return source


async def _create_overlay_source_via_api(client, project_id: str) -> dict:
    resp = await client.post(
        f"/api/v1/projects/{project_id}/graph/overlay/sources",
        json={
            "source_type": "pasted_text",
            "raw_text": "机器学习中的逻辑回归和梯度下降。",
        },
    )
    assert resp.status_code == 200
    return resp.json()


class _MockLLMResponse:
    def __init__(self, content: str):
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self.content}}]}


class _MockAsyncLLMClient:
    def __init__(self, content: str, captured: dict | None = None):
        self.content = content
        self.captured = captured

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, *, headers=None, json=None):
        if self.captured is not None:
            self.captured.update({"url": url, "headers": headers, "json": json})
        return _MockLLMResponse(self.content)


class _FailingAsyncLLMClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, *, headers=None, json=None):
        raise httpx.TransportError("temporary network failure")


def _llm_payload(source_id: str) -> str:
    return json.dumps({
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
                "evidence_source_id": source_id,
            }
        ],
        "warnings": ["llm_generated"],
    }, ensure_ascii=False)


def _planned_node_ids(plan_payload: dict) -> list[str]:
    return [
        task["node_id"]
        for stage in plan_payload["stages"]
        for task in stage["tasks"]
    ]


async def test_project_graph_snapshot_cache_reuses_unchanged_revision(
    project,
    db_session,
    monkeypatch,
):
    clear_project_graph_snapshot_cache()
    before_stats = get_project_graph_snapshot_cache_stats()
    first = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    list_nodes = AsyncMock(side_effect=AssertionError("snapshot cache should avoid node reload"))
    list_edges = AsyncMock(side_effect=AssertionError("snapshot cache should avoid edge reload"))
    monkeypatch.setattr(snapshot_module, "list_planner_visible_nodes", list_nodes)
    monkeypatch.setattr(snapshot_module, "list_planner_visible_edges", list_edges)

    second = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    after_stats = get_project_graph_snapshot_cache_stats()

    assert second is first
    assert after_stats["misses"] == before_stats["misses"] + 1
    assert after_stats["hits"] == before_stats["hits"] + 1
    assert after_stats["stores"] == before_stats["stores"] + 1
    assert after_stats["size"] >= 1
    assert after_stats["max_size"] == 64
    assert 0 < after_stats["hit_rate"] <= 1
    list_nodes.assert_not_awaited()
    list_edges.assert_not_awaited()


async def test_project_graph_snapshot_cache_refreshes_after_review_revision_changes(
    client,
    project,
    db_session,
):
    clear_project_graph_snapshot_cache()
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert "ml_c01" in before.nodes_by_id

    resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/nodes/ml_c01",
        json={"status": "removed"},
    )
    assert resp.status_code == 200

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    assert after is not before
    assert "ml_c01" not in after.nodes_by_id


async def test_create_and_get_overlay_extraction_session_endpoints(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])

    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [_valid_node("逻辑回归补充")],
                "edges": [
                    {
                        "source_name_or_id": "逻辑回归补充",
                        "target_name_or_id": "ml_c01",
                        "relation_type": "RELATED_TO",
                        "confidence": 0.7,
                        "legality_rationale": "补充概念关联到现有基础节点",
                    }
                ],
                "resources": [
                    {
                        "title": "逻辑回归补充资料",
                        "url": "https://example.com/logistic-overlay",
                        "resource_type": "article",
                        "summary": "补充逻辑回归基础概念。",
                        "quality_score": 0.9,
                        "confidence": 0.85,
                        "evidence_source_id": source["source_id"],
                    }
                ],
                "warnings": ["normalized"],
            },
        },
    )

    assert create_resp.status_code == 200
    payload = create_resp.json()
    assert payload["session"]["session_status"] == "validated"
    assert payload["warnings"] == ["normalized"]
    assert [item["source_id"] for item in payload["sources"]] == [source["source_id"]]
    assert payload["nodes"][0]["validation_status"] == "valid"
    assert payload["edges"][0]["validation_status"] == "valid"
    assert payload["resources"][0]["validation_status"] == "valid"

    session_id = payload["session"]["session_id"]
    get_resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions/{session_id}"
    )

    assert get_resp.status_code == 200
    loaded = get_resp.json()
    assert loaded["session"]["session_id"] == session_id
    assert loaded["warnings"] == ["normalized"]
    assert loaded["nodes"][0]["name"] == "逻辑回归补充"
    assert loaded["edges"][0]["relation_type"] == "RELATED_TO"
    resource = loaded["resources"][0]
    assert resource["url"] == "https://example.com/logistic-overlay"
    assert resource["evidence_source_id"] == source["source_id"]
    assert resource["source_evidence"]["source_id"] == source["source_id"]
    assert resource["review_status"] == "pending"
    assert resource["planning_enabled"] is True
    assert resource["promotion_status"] == "not_promoted"
    assert resource["binding_summary"] == {"count": 0, "project_node_ids": [], "path_stage_ids": []}


async def test_validate_overlay_extraction_payload_reports_invalid_candidates_without_writes(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])
    invalid_node = _valid_node("预校验非法节点")
    invalid_node["req_coding"] = 9

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-payload/validate",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [invalid_node],
                "edges": [
                    {
                        "source_name_or_id": "预校验非法节点",
                        "target_name_or_id": "ml_c01",
                        "relation_type": "RELATED_TO",
                        "confidence": 0.8,
                        "legality_rationale": "非法节点不会进入可引用节点集合，关系应提示来源悬空。",
                    }
                ],
                "resources": [],
                "warnings": [],
            },
        },
    )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["summary"]["has_blocking_errors"] is True
    assert payload["counts"]["nodes"]["invalid"] == 1
    assert payload["counts"]["edges"]["invalid"] == 1
    assert payload["nodes"][0]["validation_errors"] == ["invalid_req_coding"]
    assert "dangling_source" in payload["edges"][0]["validation_errors"]
    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_patch_overlay_node_candidate_repairs_validation_and_dependent_edges(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])
    invalid_node = _valid_node("可修复扩展节点")
    invalid_node["req_coding"] = 9
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [invalid_node],
                "edges": [
                    {
                        "source_name_or_id": "可修复扩展节点",
                        "target_name_or_id": "ml_c01",
                        "relation_type": "RELATED_TO",
                        "confidence": 0.8,
                        "legality_rationale": "修复节点画像后，这条关系应自动重新校验通过。",
                    }
                ],
                "resources": [],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    node_id = created["nodes"][0]["node_id"]
    assert created["nodes"][0]["validation_status"] == "invalid"
    assert created["edges"][0]["validation_status"] == "invalid"
    assert "dangling_source" in created["edges"][0]["validation_errors"]

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200

    patch_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/candidate",
        json={"req_coding": 2},
    )

    assert patch_resp.status_code == 200
    payload = patch_resp.json()
    node = payload["nodes"][0]
    edge = payload["edges"][0]
    assert node["validation_status"] == "valid"
    assert node["validation_errors"] == []
    assert node["review_status"] == "pending"
    assert edge["validation_status"] == "valid"
    assert edge["validation_errors"] == []
    assert edge["source_node_id"] == node_id


async def test_overlay_candidate_end_to_end_review_planning_preflight_flow(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])
    invalid_node = _valid_node("端到端扩展节点")
    invalid_node["req_coding"] = 9
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [invalid_node],
                "edges": [
                    {
                        "source_name_or_id": "端到端扩展节点",
                        "target_name_or_id": "未知目标",
                        "relation_type": "BAD_RELATION",
                        "confidence": 0.8,
                        "legality_rationale": "端到端流程里先产生非法关系，再由候选编辑修复。",
                    }
                ],
                "resources": [
                    {
                        "title": "端到端扩展资料",
                        "url": "https://example.com/e2e-overlay",
                        "resource_type": "article",
                        "summary": "用于端到端验证的扩展资料。",
                        "quality_score": 2,
                        "confidence": 0.8,
                        "evidence_source_id": source["source_id"],
                    }
                ],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    created = create_resp.json()
    node_id = created["nodes"][0]["node_id"]
    edge_id = created["edges"][0]["edge_id"]
    resource_id = created["resources"][0]["resource_id"]
    assert created["nodes"][0]["validation_status"] == "invalid"
    assert created["edges"][0]["validation_status"] == "invalid"
    assert created["resources"][0]["validation_status"] == "invalid"

    node_patch_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/candidate",
        json={"req_coding": 2},
    )
    assert node_patch_resp.status_code == 200
    assert node_patch_resp.json()["nodes"][0]["validation_status"] == "valid"

    edge_patch_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/edges/{edge_id}/candidate",
        json={
            "source_node_id": node_id,
            "target_node_id": "ml_c01",
            "relation_type": "RELATED_TO",
        },
    )
    assert edge_patch_resp.status_code == 200
    patched_edge = edge_patch_resp.json()["edges"][0]
    assert patched_edge["validation_status"] == "valid"
    assert patched_edge["source_node_id"] == node_id
    assert patched_edge["target_node_id"] == "ml_c01"

    resource_patch_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/resources/{resource_id}/candidate",
        json={"quality_score": 0.85},
    )
    assert resource_patch_resp.status_code == 200
    assert resource_patch_resp.json()["resources"][0]["validation_status"] == "valid"

    pending_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert pending_resp.status_code == 200
    pending = pending_resp.json()
    assert pending["status"] == "warning"
    assert pending["counts"]["nodes"]["pending_review"] == 1
    assert pending["counts"]["edges"]["pending_review"] == 1
    assert node_id not in pending["visible_overlay_node_ids"]
    assert edge_id not in pending["visible_overlay_edge_ids"]

    for group, element_id in (("nodes", node_id), ("edges", edge_id), ("resources", resource_id)):
        review_resp = await client.patch(
            f"/api/v1/projects/{project['id']}/graph/overlay/{group}/{element_id}/review",
            json={"review_status": "confirmed"},
        )
        assert review_resp.status_code == 200
        assert review_resp.json()["review_status"] == "confirmed"

    ready_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert ready_resp.status_code == 200
    ready = ready_resp.json()
    assert ready["status"] == "ok"
    assert node_id in ready["visible_overlay_node_ids"]
    assert edge_id in ready["visible_overlay_edge_ids"]

    planning_off_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/planning",
        json={"planning_enabled": False},
    )
    assert planning_off_resp.status_code == 200
    disabled_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert disabled_resp.status_code == 200
    disabled = disabled_resp.json()
    assert disabled["status"] == "warning"
    assert disabled["counts"]["nodes"]["planning_disabled"] == 1
    assert node_id not in disabled["visible_overlay_node_ids"]
    assert edge_id not in disabled["visible_overlay_edge_ids"]

    planning_on_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/planning",
        json={"planning_enabled": True},
    )
    assert planning_on_resp.status_code == 200
    restored_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert restored_resp.status_code == 200
    restored = restored_resp.json()
    assert restored["status"] == "ok"
    assert node_id in restored["visible_overlay_node_ids"]
    assert edge_id in restored["visible_overlay_edge_ids"]


async def test_overlay_preflight_reports_review_and_planning_readiness(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [_valid_node("预检扩展节点")],
                "edges": [],
                "resources": [],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    node_id = create_resp.json()["nodes"][0]["node_id"]

    pending_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert pending_resp.status_code == 200
    pending = pending_resp.json()
    assert pending["status"] == "warning"
    assert pending["counts"]["nodes"]["pending_review"] == 1
    assert node_id not in pending["visible_overlay_node_ids"]

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200
    ready_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert ready_resp.status_code == 200
    ready = ready_resp.json()
    assert ready["status"] == "ok"
    assert node_id in ready["visible_overlay_node_ids"]

    planning_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/nodes/{node_id}/planning",
        json={"planning_enabled": False},
    )
    assert planning_resp.status_code == 200
    disabled_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert disabled_resp.status_code == 200
    disabled = disabled_resp.json()
    assert disabled["status"] == "warning"
    assert disabled["counts"]["nodes"]["planning_disabled"] == 1
    assert node_id not in disabled["visible_overlay_node_ids"]


async def test_overlay_preflight_reports_shadowed_overlay_edges(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])
    baseline_edge = get_domain_pack_service(project["domain"]).requires_edges[0]
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [],
                "edges": [
                    {
                        "source_node_id": baseline_edge["source"],
                        "target_node_id": baseline_edge["target"],
                        "relation_type": "REQUIRES",
                        "confidence": 0.9,
                        "legality_rationale": "这条关系已存在于基线图谱，用于验证预检提示。",
                    }
                ],
                "resources": [],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    edge_id = create_resp.json()["edges"][0]["edge_id"]
    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/edges/{edge_id}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200

    preflight_resp = await client.get(f"/api/v1/projects/{project['id']}/graph/overlay/preflight")
    assert preflight_resp.status_code == 200
    preflight = preflight_resp.json()
    assert preflight["status"] == "warning"
    assert edge_id in preflight["ignored_overlay_edge_ids"]
    assert edge_id in preflight["shadowed_edge_ids"]
    assert edge_id not in preflight["visible_overlay_edge_ids"]
    assert any(item["kind"] == "shadowed_edges" for item in preflight["warning_items"])


async def test_preview_overlay_extraction_payload_uses_llm_without_creating_session(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])
    replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://llm.example.com/v1",
        "llm_model": "test-model",
    })
    captured: dict = {}

    with patch(
        "app.services.project_overlay_llm_extraction_service.httpx.AsyncClient",
        return_value=_MockAsyncLLMClient(_llm_payload(source["source_id"]), captured),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/graph/overlay/extraction-payload/preview",
            json={
                "source_ids": [source["source_id"]],
                "expansion_topic": "随机森林",
                "constraint_note": "只抽取基础前置知识",
            },
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["counts"] == {"nodes": 1, "edges": 1, "resources": 1}
    assert payload["warnings"] == ["llm_generated"]
    assert payload["provenance"]["draft_origin"] == "llm_overlay_extraction"
    assert payload["provenance"]["writes_formal_graph"] is False
    assert payload["provenance"]["expansion_context"]["constraint_note"] == "只抽取基础前置知识"
    assert payload["extraction_payload"]["nodes"][0]["name"] == "随机森林扩展"
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["json"]["model"] == "test-model"
    llm_request = json.loads(captured["json"]["messages"][1]["content"])
    assert llm_request["expansion_context"]["expansion_topic"] == "随机森林"
    assert llm_request["expansion_context"]["constraint_note"] == "只抽取基础前置知识"

    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_preview_overlay_extraction_payload_retries_transient_llm_failure(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])
    replace_runtime_settings({"llm_api_key": "sk-test"})

    with patch(
        "app.services.project_overlay_llm_extraction_service.httpx.AsyncClient",
        side_effect=[_FailingAsyncLLMClient(), _MockAsyncLLMClient(_llm_payload(source["source_id"]))],
    ) as client_factory:
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/graph/overlay/extraction-payload/preview",
            json={"source_ids": [source["source_id"]]},
        )

    assert resp.status_code == 200
    assert client_factory.call_count == 2
    assert resp.json()["counts"] == {"nodes": 1, "edges": 1, "resources": 1}


async def test_preview_overlay_extraction_payload_accepts_text_wrapped_llm_json(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])
    replace_runtime_settings({"llm_api_key": "sk-test"})
    wrapped_payload = f"抽取完成，JSON 如下：\n{_llm_payload(source['source_id'])}\n请进入人工审核。"

    with patch(
        "app.services.project_overlay_llm_extraction_service.httpx.AsyncClient",
        return_value=_MockAsyncLLMClient(wrapped_payload),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/graph/overlay/extraction-payload/preview",
            json={"source_ids": [source["source_id"]]},
        )

    assert resp.status_code == 200
    payload = resp.json()
    assert payload["counts"] == {"nodes": 1, "edges": 1, "resources": 1}
    assert payload["extraction_payload"]["nodes"][0]["name"] == "随机森林扩展"
    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_preview_overlay_extraction_payload_rejects_invalid_llm_json(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])
    replace_runtime_settings({"llm_api_key": "sk-test"})

    with patch(
        "app.services.project_overlay_llm_extraction_service.httpx.AsyncClient",
        return_value=_MockAsyncLLMClient("not json"),
    ):
        resp = await client.post(
            f"/api/v1/projects/{project['id']}/graph/overlay/extraction-payload/preview",
            json={"source_ids": [source["source_id"]]},
        )

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_LLM_EXTRACTION_JSON"
    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_preview_overlay_extraction_payload_requires_llm(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-payload/preview",
        json={"source_ids": [source["source_id"]]},
    )

    assert resp.status_code == 503
    assert resp.json()["error"] == "LLM_NOT_READY"


async def test_resource_binding_detail_and_target_validation(client, project):
    source = await _create_overlay_source_via_api(client, project["id"])
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [],
                "edges": [],
                "resources": [
                    {
                        "title": "资源绑定资料",
                        "url": "https://example.com/resource-binding",
                        "resource_type": "article",
                        "summary": "用于测试资源绑定。",
                        "quality_score": 0.9,
                        "confidence": 0.85,
                        "evidence_source_id": source["source_id"],
                    }
                ],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    payload = create_resp.json()
    session_id = payload["session"]["session_id"]
    resource_id = payload["resources"][0]["resource_id"]

    invalid_type_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "latest_path_stage",
            "target_id": "stage_foundation",
        },
    )
    assert invalid_type_resp.status_code == 422
    assert invalid_type_resp.json()["error"] == "INVALID_RESOURCE_BINDING_TARGET_TYPE"

    missing_node_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "project_node",
            "target_id": "missing-node",
        },
    )
    assert missing_node_resp.status_code == 422
    assert missing_node_resp.json()["error"] == "RESOURCE_BINDING_TARGET_NOT_FOUND"

    bad_stage_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "path_stage",
            "target_id": "latest:0",
        },
    )
    assert bad_stage_resp.status_code == 422
    assert bad_stage_resp.json()["error"] == "UNRESOLVABLE_PATH_STAGE_BINDING"

    node_binding_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "project_node",
            "target_id": "ml_c01",
        },
    )
    assert node_binding_resp.status_code == 200
    stage_binding_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "path_stage",
            "target_id": "stage_foundation",
        },
    )
    assert stage_binding_resp.status_code == 200

    get_resp = await client.get(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions/{session_id}"
    )
    assert get_resp.status_code == 200
    resource = get_resp.json()["resources"][0]
    assert {binding["target_id"] for binding in resource["bindings"]} == {"ml_c01", "stage_foundation"}
    assert resource["binding_summary"] == {
        "count": 2,
        "project_node_ids": ["ml_c01"],
        "path_stage_ids": ["stage_foundation"],
    }


async def test_resource_only_changes_do_not_affect_planning_snapshot_or_path_graph(
    client,
    project,
    profile,
    db_session,
):
    plan_before_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_before_resp.status_code == 200
    plan_before = plan_before_resp.json()
    before = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    before_path = build_path_graph_elements_from_snapshot(
        before,
        node_ids=["ml_c01"],
        path_id="latest",
    )
    source = await _create_overlay_source_via_api(client, project["id"])
    create_resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [],
                "edges": [],
                "resources": [
                    {
                        "title": "只影响资源层资料",
                        "url": "https://example.com/resource-only",
                        "resource_type": "article",
                        "summary": "该资源不应进入 planning graph。",
                        "quality_score": 0.9,
                        "confidence": 0.85,
                        "evidence_source_id": source["source_id"],
                    }
                ],
                "warnings": [],
            },
        },
    )
    assert create_resp.status_code == 200
    resource_id = create_resp.json()["resources"][0]["resource_id"]

    review_resp = await client.patch(
        f"/api/v1/projects/{project['id']}/graph/overlay/resources/{resource_id}/review",
        json={"review_status": "confirmed"},
    )
    assert review_resp.status_code == 200
    await update_planning_enabled(
        db_session,
        project_id=project["id"],
        element_type="resource",
        element_id=resource_id,
        planning_enabled=False,
    )
    binding_resp = await client.post(
        f"/api/v1/projects/{project['id']}/resources/bindings",
        json={
            "resource_id": resource_id,
            "target_type": "project_node",
            "target_id": "ml_c01",
        },
    )
    assert binding_resp.status_code == 200

    after = await build_project_graph_snapshot(db_session, project["id"], domain=project["domain"])
    after_path = build_path_graph_elements_from_snapshot(
        after,
        node_ids=["ml_c01"],
        path_id="latest",
    )
    assert after.project_graph_hash == before.project_graph_hash
    assert after.nodes_by_id == before.nodes_by_id
    assert after.requires_edges == before.requires_edges
    assert after.related_edges == before.related_edges
    assert after.overlay_lineage == before.overlay_lineage
    assert after_path == before_path
    assert await list_planner_visible_nodes(db_session, project["id"]) == []

    plan_after_resp = await client.post(f"/api/v1/projects/{project['id']}/plans")
    assert plan_after_resp.status_code == 200
    plan_after = plan_after_resp.json()
    assert _planned_node_ids(plan_after) == _planned_node_ids(plan_before)
    assert plan_after["node_count"] == plan_before["node_count"]
    assert plan_after["total_hours"] == plan_before["total_hours"]


async def test_custom_extension_requires_search_readiness_before_writes(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "mode": "custom_extension",
            "extraction_payload": {"nodes": [], "edges": [], "resources": [], "warnings": []},
        },
    )

    assert resp.status_code == 503
    assert resp.json()["error"] == "SEARCH_NOT_READY"

    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_unknown_extraction_mode_is_rejected_before_writes(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "mode": "custom_extension ",
            "extraction_payload": {"nodes": [], "edges": [], "resources": [], "warnings": []},
        },
    )

    assert resp.status_code == 422
    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_pasted_text_source_rejects_oversized_client_excerpt(client, project):
    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/sources",
        json={
            "source_type": "pasted_text",
            "raw_text": "短文本",
            "raw_text_excerpt": "x" * 12001,
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "TEXT_LIMIT_EXCEEDED"


async def test_invalid_llm_json_returns_422_without_creating_session(client, project, db_session):
    source = await _create_overlay_source_via_api(client, project["id"])

    resp = await client.post(
        f"/api/v1/projects/{project['id']}/graph/overlay/extraction-sessions",
        json={
            "source_ids": [source["source_id"]],
            "extraction_payload": {
                "nodes": [],
                "edges": [],
                "resources": [],
                "warnings": [],
                "bogus": [],
            },
        },
    )

    assert resp.status_code == 422
    assert resp.json()["error"] == "INVALID_LLM_EXTRACTION_JSON"

    sessions = (await db_session.execute(select(ProjectOverlayExtractionSession))).scalars().all()
    assert sessions == []


async def test_duplicate_candidates_are_marked_needs_review(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [_valid_node("重复节点"), _valid_node("  重复节点  ")],
            "edges": [],
            "resources": [
                {
                    "title": "重复资源一",
                    "url": "https://example.com/dup",
                    "resource_type": "article",
                    "summary": "资源一",
                    "quality_score": 0.8,
                    "confidence": 0.6,
                    "evidence_source_id": source.source_id,
                },
                {
                    "title": "重复资源二",
                    "url": " https://example.com/dup ",
                    "resource_type": "article",
                    "summary": "资源二",
                    "quality_score": 0.7,
                    "confidence": 0.6,
                    "evidence_source_id": source.source_id,
                },
            ],
            "warnings": [],
        },
    )

    node_duplicates = [json.loads(node.duplicate_candidates_json) for node in result["nodes"]]
    resource_duplicates = [json.loads(resource.duplicate_candidates_json) for resource in result["resources"]]

    assert [node.validation_status for node in result["nodes"]] == ["needs_review", "needs_review"]
    assert [item["indexes"] for item in node_duplicates] == [[0, 1], [0, 1]]
    assert [resource.validation_status for resource in result["resources"]] == ["needs_review", "needs_review"]
    assert [item["indexes"] for item in resource_duplicates] == [[0, 1], [0, 1]]


async def test_missing_fields_node_is_invalid_and_not_planner_visible(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    invalid_node = _valid_node("缺字段节点")
    invalid_node.pop("group")

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [invalid_node],
            "edges": [],
            "resources": [],
            "warnings": [],
        },
    )

    node = result["nodes"][0]
    errors = json.loads(node.validation_errors_json)
    assert node.validation_status == "invalid"
    assert any(error.startswith("missing_fields:") and "group" in error for error in errors)

    await update_review_status(
        db_session,
        project_id=project["id"],
        element_type="node",
        element_id=node.node_id,
        review_status="confirmed",
    )
    planner_visible = await list_planner_visible_nodes(db_session, project["id"])
    assert planner_visible == []


async def test_invalid_weights_make_node_invalid_and_hidden(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])
    invalid_node = _valid_node("权重非法节点")
    invalid_node["theory_weight"] = 0.8
    invalid_node["practice_weight"] = 0.8

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={"nodes": [invalid_node], "edges": [], "resources": [], "warnings": []},
    )

    node = result["nodes"][0]
    assert node.validation_status == "invalid"
    assert "invalid_weight_sum" in json.loads(node.validation_errors_json)

    await update_review_status(
        db_session,
        project_id=project["id"],
        element_type="node",
        element_id=node.node_id,
        review_status="confirmed",
    )
    assert await list_planner_visible_nodes(db_session, project["id"]) == []


async def test_self_loop_and_invalid_relation_edges_are_invalid(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [_valid_node("自环节点")],
            "edges": [
                {
                    "source_name_or_id": "自环节点",
                    "target_name_or_id": "自环节点",
                    "relation_type": "DEPENDS_ON",
                    "confidence": 0.8,
                    "legality_rationale": "非法关系和自环都必须被拒绝",
                }
            ],
            "resources": [],
            "warnings": [],
        },
    )

    edge = result["edges"][0]
    errors = json.loads(edge.validation_errors_json)
    assert edge.validation_status == "invalid"
    assert "self_loop" in errors
    assert "invalid_relation_type" in errors


async def test_requires_cycle_marks_edges_invalid(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [_valid_node("环节点A"), _valid_node("环节点B")],
            "edges": [
                {
                    "source_name_or_id": "环节点A",
                    "target_name_or_id": "环节点B",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                    "legality_rationale": "A 依赖 B",
                },
                {
                    "source_name_or_id": "环节点B",
                    "target_name_or_id": "环节点A",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                    "legality_rationale": "B 依赖 A",
                },
            ],
            "resources": [],
            "warnings": [],
        },
    )

    assert [edge.validation_status for edge in result["edges"]] == ["invalid", "invalid"]
    for edge in result["edges"]:
        assert "requires_cycle" in json.loads(edge.validation_errors_json)


async def test_dangling_edge_is_invalid(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [_valid_node("边起点")],
            "edges": [
                {
                    "source_name_or_id": "边起点",
                    "target_name_or_id": "不存在的节点",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                    "legality_rationale": "非法悬空边",
                }
            ],
            "resources": [],
            "warnings": [],
        },
    )

    edge = result["edges"][0]
    assert edge.validation_status == "invalid"
    assert "dangling_target" in json.loads(edge.validation_errors_json)


async def test_missing_endpoint_edge_is_persisted_as_invalid(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [],
            "edges": [
                {
                    "target_name_or_id": "ml_c01",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                    "legality_rationale": "缺少 source 端点",
                }
            ],
            "resources": [],
            "warnings": [],
        },
    )

    edge = result["edges"][0]
    assert edge.source_node_id == ""
    assert edge.validation_status == "invalid"
    assert "missing_endpoint" in json.loads(edge.validation_errors_json)


async def test_baseline_node_name_reference_is_resolved(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [_valid_node("名称解析补充")],
            "edges": [
                {
                    "source_name_or_id": "名称解析补充",
                    "target_name_or_id": "线性回归",
                    "relation_type": "RELATED_TO",
                    "confidence": 0.8,
                    "legality_rationale": "使用 baseline 节点名称作为端点",
                }
            ],
            "resources": [],
            "warnings": [],
        },
    )

    edge = result["edges"][0]
    assert edge.target_node_id == "ml_c01"
    assert edge.validation_status == "valid"


async def test_resource_evidence_source_must_belong_to_session(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [],
            "edges": [],
            "resources": [
                {
                    "title": "证据来源非法资源",
                    "url": "https://example.com/bad-evidence",
                    "resource_type": "article",
                    "summary": "证据来源不属于当前 session。",
                    "quality_score": 0.8,
                    "confidence": 0.7,
                    "evidence_source_id": "other-source",
                }
            ],
            "warnings": [],
        },
    )

    resource = result["resources"][0]
    assert resource.validation_status == "invalid"
    assert "invalid_evidence_source_id" in json.loads(resource.validation_errors_json)


async def test_related_to_cycle_does_not_trigger_requires_cycle_validation(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [_valid_node("关联节点A"), _valid_node("关联节点B")],
            "edges": [
                {
                    "source_name_or_id": "关联节点A",
                    "target_name_or_id": "关联节点B",
                    "relation_type": "RELATED_TO",
                    "confidence": 0.8,
                    "legality_rationale": "A 关联 B",
                },
                {
                    "source_name_or_id": "关联节点B",
                    "target_name_or_id": "关联节点A",
                    "relation_type": "RELATED_TO",
                    "confidence": 0.8,
                    "legality_rationale": "B 关联 A",
                },
            ],
            "resources": [],
            "warnings": [],
        },
    )

    assert [edge.validation_status for edge in result["edges"]] == ["valid", "valid"]
    assert all(edge.validation_errors_json is None for edge in result["edges"])


async def test_requires_cycle_checks_baseline_edges(project, db_session):
    source = await _create_overlay_source(db_session, project["id"])

    result = await create_extraction_session_from_sources(
        db_session,
        project_id=project["id"],
        source_ids=[source.source_id],
        extraction_payload={
            "nodes": [],
            "edges": [
                {
                    "source_name_or_id": "ml_c01",
                    "target_name_or_id": "ml_a02",
                    "relation_type": "REQUIRES",
                    "confidence": 0.8,
                    "legality_rationale": "反向连接用于测试 baseline 依赖环检测",
                }
            ],
            "resources": [],
            "warnings": [],
        },
    )

    edge = result["edges"][0]
    assert edge.validation_status == "invalid"
    assert "requires_cycle" in json.loads(edge.validation_errors_json)
