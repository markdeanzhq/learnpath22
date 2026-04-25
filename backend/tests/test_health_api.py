from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import socket

import pytest
from fastapi import FastAPI
from sqlalchemy import select

from app.core.config import get_llm_config, replace_runtime_settings
from app.db.sqlite import get_runtime_settings_map
from app.main import create_app, lifespan
from app.models.sqlite_models import (
    ProjectOverlayExtractionSession,
    ProjectOverlayNode,
    ProjectOverlayProjectionState,
    RuntimeSetting,
)


async def test_lifespan_degrades_when_neo4j_startup_fails():
    app = create_app()
    assert isinstance(app, FastAPI)

    with (
        patch("app.main.init_sqlite", AsyncMock()),
        patch("app.main.async_session") as async_session_mock,
        patch("app.main.get_runtime_settings_map", AsyncMock(return_value={})),
        patch("app.main.replace_runtime_settings"),
        patch("app.main.neo4j_driver.connect", AsyncMock(side_effect=RuntimeError("neo4j auth failed"))),
        patch("app.main.initialize_knowledge_node_schema", AsyncMock()),
        patch("app.main.neo4j_driver.close", AsyncMock()),
    ):
        session_cm = AsyncMock()
        session_cm.__aenter__.return_value = object()
        session_cm.__aexit__.return_value = None
        async_session_mock.return_value = session_cm

        async with lifespan(app):
            pass


async def test_health_includes_environment_fingerprint(client):
    await client.put(
        "/api/v1/health/config",
        json={
            "llm_base_url": "https://example.com/v1",
            "llm_model": "demo-model",
            "llm_api_key": "test-llm-key",
            "search_api_key": "test-search-key",
        },
    )

    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200

    data = resp.json()
    environment = data["environment"]

    assert data["status"] == "ok"
    assert data["project"] == "LearnPath-KG"
    assert data["version"] == "0.1.0"
    assert environment["prototype_scope"] == "machine_learning_only"
    assert environment["delivery_stage"] == "graduation_prototype"
    assert environment["python_baseline"] == "3.12"
    assert isinstance(environment["python_version"], str)
    assert environment["runtime_settings_scope"] == "sqlite-persisted"
    assert environment["sqlite_backend"] == "sqlite+aiosqlite"
    assert environment["neo4j_scheme"] == "bolt"
    assert environment["llm_provider"] == "openai_compatible"
    assert environment["llm_api_key_set"] is True
    assert environment["search_provider"] == "tavily"
    assert environment["search_api_key_set"] is True
    assert "llm_api_key" not in environment
    assert "search_api_key" not in environment
    assert "llm_base_url" not in environment
    assert "llm_model" not in environment


async def test_health_config_updates_runtime_settings(client):
    resp = await client.put(
        "/api/v1/health/config",
        json={
            "llm_base_url": "https://example.com/v1",
            "llm_model": "demo-model",
            "llm_api_key": "test-llm-key",
            "search_api_key": "test-search-key",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "运行时配置已保存"
    assert data["llm_base_url"] == "https://example.com/v1"
    assert data["llm_model"] == "demo-model"
    assert data["llm_api_key_set"] is True
    assert data["search_api_key_set"] is True


async def test_health_config_rejects_unknown_fields(client):
    resp = await client.put(
        "/api/v1/health/config",
        json={
            "unexpected": "bad-field",
        },
    )
    assert resp.status_code == 422


async def test_health_config_returns_noop_when_payload_empty(client):
    resp = await client.put(
        "/api/v1/health/config",
        json={},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["message"] == "未提供可更新的运行时配置"
    assert "llm_api_key_set" in data
    assert "search_api_key_set" in data


async def test_health_config_persists_and_reads_back_from_sqlite(client):
    save_resp = await client.put(
        "/api/v1/health/config",
        json={
            "llm_base_url": "https://persisted.example/v1",
            "llm_model": "persisted-model",
            "llm_api_key": "persisted-llm-key",
            "search_api_key": "persisted-search-key",
        },
    )
    assert save_resp.status_code == 200

    read_resp = await client.get("/api/v1/health/config")
    assert read_resp.status_code == 200
    assert read_resp.json() == {
        "llm_base_url": "https://persisted.example/v1",
        "llm_model": "persisted-model",
        "llm_api_key_set": True,
        "search_api_key_set": True,
        "llm_explanation_polish": False,
    }


async def test_health_config_encrypts_secret_values_before_persisting_to_sqlite(client, db_session):
    save_resp = await client.put(
        "/api/v1/health/config",
        json={
            "llm_base_url": "https://persisted.example/v1",
            "llm_model": "persisted-model",
            "llm_api_key": "persisted-llm-key",
            "search_api_key": "persisted-search-key",
        },
    )
    assert save_resp.status_code == 200

    result = await db_session.execute(select(RuntimeSetting))
    persisted_rows = {
        row.setting_key: row.setting_value
        for row in result.scalars().all()
    }

    assert persisted_rows["llm_base_url"] == "https://persisted.example/v1"
    assert persisted_rows["llm_model"] == "persisted-model"
    assert persisted_rows["llm_api_key"] != "persisted-llm-key"
    assert persisted_rows["search_api_key"] != "persisted-search-key"
    assert persisted_rows["llm_api_key"].startswith("enc:v1:")
    assert persisted_rows["search_api_key"].startswith("enc:v1:")


async def test_runtime_settings_map_migrates_legacy_plaintext_secret_values(client, db_session):
    db_session.add_all(
        [
            RuntimeSetting(setting_key="llm_api_key", setting_value="legacy-llm-key"),
            RuntimeSetting(setting_key="search_api_key", setting_value="legacy-search-key"),
        ]
    )
    await db_session.commit()

    runtime_settings = await get_runtime_settings_map(db_session)

    assert runtime_settings["llm_api_key"] == "legacy-llm-key"
    assert runtime_settings["search_api_key"] == "legacy-search-key"

    result = await db_session.execute(select(RuntimeSetting))
    persisted_rows = {
        row.setting_key: row.setting_value
        for row in result.scalars().all()
    }
    assert persisted_rows["llm_api_key"] != "legacy-llm-key"
    assert persisted_rows["search_api_key"] != "legacy-search-key"
    assert persisted_rows["llm_api_key"].startswith("enc:v1:")
    assert persisted_rows["search_api_key"].startswith("enc:v1:")


@pytest.mark.parametrize(
    "base_url",
    [
        "https://api.openai.com/v1",
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://[::1]:11434/v1",
    ],
)
async def test_health_config_accepts_safe_llm_base_urls(client, base_url):
    resp = await client.put(
        "/api/v1/health/config",
        json={
            "llm_base_url": base_url,
        },
    )

    assert resp.status_code == 200
    assert resp.json()["llm_base_url"] == base_url


@pytest.mark.parametrize(
    "base_url",
    [
        "http://example.com/v1",
        "https://10.0.0.5/v1",
        "https://169.254.169.254/latest",
        "https://user:pass@example.com/v1",
        "https://metadata.google.internal/latest",
        "https://ollama.local/v1",
    ],
)
async def test_health_config_rejects_unsafe_llm_base_urls(client, base_url):
    with patch(
        "app.core.config.socket.getaddrinfo",
        return_value=[(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.5", 443))],
    ):
        resp = await client.put(
            "/api/v1/health/config",
            json={
                "llm_base_url": base_url,
            },
        )

    assert resp.status_code == 422


async def test_replace_runtime_settings_ignores_unsafe_llm_base_url_override(client):
    replace_runtime_settings(
        {
            "llm_base_url": "http://10.0.0.9/v1",
            "llm_model": "unsafe-model",
        }
    )

    cfg = get_llm_config()

    assert cfg["llm_base_url"] == "https://api.openai.com/v1"
    assert cfg["llm_model"] == "unsafe-model"


async def test_health_config_partial_update_preserves_existing_values(client):
    await client.put(
        "/api/v1/health/config",
        json={
            "llm_base_url": "https://persisted.example/v1",
            "llm_model": "persisted-model",
            "llm_api_key": "persisted-llm-key",
            "search_api_key": "persisted-search-key",
        },
    )

    resp = await client.put(
        "/api/v1/health/config",
        json={
            "llm_model": "updated-model",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["llm_model"] == "updated-model"

    read_resp = await client.get("/api/v1/health/config")
    assert read_resp.status_code == 200
    assert read_resp.json() == {
        "llm_base_url": "https://persisted.example/v1",
        "llm_model": "updated-model",
        "llm_api_key_set": True,
        "search_api_key_set": True,
        "llm_explanation_polish": False,
    }


async def test_health_search_reports_skipped_when_unconfigured(client):
    resp = await client.get("/api/v1/health/search")
    assert resp.status_code == 200
    assert resp.json() == {
        "status": "skipped",
        "ready": False,
        "provider": "tavily",
        "reason": "搜索服务未配置",
    }


async def test_health_readiness_uses_registry_default_domain_for_graph_sync(client, monkeypatch):
    sync_service = SimpleNamespace(
        get_sync_status=AsyncMock(
            return_value={
                "status": "ok",
                "ready": True,
                "in_sync": True,
                "reason": "synced",
                "domain": "demo_domain",
                "version": "1.0.0",
                "pack_hash": "pack-hash",
                "main_graph_synced": True,
                "entity_graph_synced": True,
                "nodes": 1,
                "edges": 0,
            }
        )
    )
    monkeypatch.setattr(
        "app.api.v1.health.get_domain_pack_registry",
        lambda: SimpleNamespace(resolve_domain=lambda: "demo_domain"),
    )
    monkeypatch.setattr("app.api.v1.health.get_graph_sync_service", lambda neo4j: sync_service)

    with (
        patch("app.api.v1.health.llm_health_check", AsyncMock(return_value={"status": "skipped"})),
        patch("app.api.v1.health._check_neo4j", AsyncMock(return_value={"status": "ok", "ready": True})),
        patch("app.api.v1.health._check_search", AsyncMock(return_value={"status": "skipped", "ready": False})),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    assert resp.json()["services"]["graph_sync"]["domain"] == "demo_domain"
    sync_service.get_sync_status.assert_awaited_once_with("demo_domain")


async def test_health_readiness_exposes_overlay_projection_error_without_blocking_sqlite_truth(client, db_session, monkeypatch):
    from app.models.sqlite_models import LearningProject

    db_session.add(
        LearningProject(
            id="project-drifted",
            title="Project Drifted",
            goal_text="系统学习机器学习基础",
            goal_type="domain",
            domain="machine_learning",
        )
    )
    await db_session.flush()
    session = ProjectOverlayExtractionSession(
        project_id="project-drifted",
        session_id="session-drifted",
        session_status="validated",
    )
    db_session.add(session)
    db_session.add(
        ProjectOverlayNode(
            project_id="project-drifted",
            session_id="session-drifted",
            node_id="po:project-drifted:n:test",
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
        )
    )
    db_session.add(
        ProjectOverlayProjectionState(
            project_id="project-drifted",
            status="error",
            overlay_hash="overlay-hash",
            error_message="projection failed",
        )
    )
    await db_session.commit()
    sync_service = SimpleNamespace(
        get_sync_status=AsyncMock(
            return_value={
                "status": "ok",
                "ready": True,
                "in_sync": True,
                "reason": "synced",
                "domain": "demo_domain",
                "version": "1.0.0",
                "pack_hash": "pack-hash",
                "main_graph_synced": True,
                "entity_graph_synced": True,
                "nodes": 1,
                "edges": 0,
            }
        )
    )
    monkeypatch.setattr(
        "app.api.v1.health.get_domain_pack_registry",
        lambda: SimpleNamespace(resolve_domain=lambda: "demo_domain"),
    )
    monkeypatch.setattr("app.api.v1.health.get_graph_sync_service", lambda neo4j: sync_service)

    with (
        patch("app.api.v1.health.llm_health_check", AsyncMock(return_value={"status": "skipped"})),
        patch("app.api.v1.health._check_neo4j", AsyncMock(return_value={"status": "ok", "ready": True})),
        patch("app.api.v1.health._check_search", AsyncMock(return_value={"status": "skipped", "ready": False})),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    body = resp.json()
    assert body["core_ready"] is False
    assert body["services"]["graph_sync"]["ready"] is True
    overlay_projection = body["services"]["graph_sync"]["overlay_projection"]
    assert overlay_projection["status"] == "error"
    assert overlay_projection["ready"] is False
    assert overlay_projection["in_sync"] is False
    assert overlay_projection["problem_projects"] == 1
    assert overlay_projection["latest_project_id"] == "project-drifted"
    assert overlay_projection["overlay_hash"]
    assert overlay_projection["overlay_hash"] != "overlay-hash"
    assert overlay_projection["projected_hash"] == "overlay-hash"
    assert overlay_projection["reason"] == "projection failed"


async def test_health_readiness_reports_blocked_graph_sync_with_registry_default_domain(client):
    with (
        patch(
            "app.api.v1.health.get_domain_pack_registry",
            return_value=SimpleNamespace(resolve_domain=lambda: "demo_domain"),
        ),
        patch(
            "app.api.v1.health.llm_health_check",
            AsyncMock(return_value={"status": "skipped", "reason": "LLM_API_KEY not configured"}),
        ),
        patch(
            "app.api.v1.health._check_neo4j",
            AsyncMock(return_value={"status": "error", "ready": False, "reason": "offline"}),
        ),
        patch(
            "app.api.v1.health._check_search",
            AsyncMock(return_value={"status": "skipped", "ready": False}),
        ),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    assert resp.json()["services"]["graph_sync"] == {
        "status": "blocked",
        "ready": False,
        "in_sync": False,
        "reason": "neo4j_unavailable",
        "domain": "demo_domain",
    }


async def test_health_readiness_reports_demo_ready_when_core_services_are_ready(client):
    with (
        patch(
            "app.api.v1.health.llm_health_check",
            AsyncMock(return_value={"status": "skipped", "reason": "LLM_API_KEY not configured"}),
        ),
        patch(
            "app.api.v1.health._check_neo4j",
            AsyncMock(return_value={"status": "ok", "ready": True}),
        ),
        patch(
            "app.api.v1.health._check_graph_sync",
            AsyncMock(
                return_value={
                    "status": "ok",
                    "ready": True,
                    "in_sync": True,
                    "reason": "synced",
                    "domain": "machine_learning",
                    "version": "1.0.0",
                    "pack_hash": "pack-hash",
                    "main_graph_synced": True,
                    "entity_graph_synced": True,
                    "nodes": 5,
                    "edges": 8,
                }
            ),
        ),
        patch(
            "app.api.v1.health._check_search",
            AsyncMock(
                return_value={
                    "status": "skipped",
                    "ready": False,
                    "provider": "tavily",
                    "reason": "搜索服务未配置",
                }
            ),
        ),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "degraded",
        "ready": False,
        "core_ready": True,
        "demo_ready": True,
        "enhanced_ready": False,
        "services": {
            "sqlite": {"status": "ok", "ready": True},
            "neo4j": {"status": "ok", "ready": True},
            "graph_sync": {
                "status": "ok",
                "ready": True,
                "in_sync": True,
                "reason": "synced",
                "domain": "machine_learning",
                "version": "1.0.0",
                "pack_hash": "pack-hash",
                "main_graph_synced": True,
                "entity_graph_synced": True,
                "nodes": 5,
                "edges": 8,
            },
            "llm": {"status": "skipped", "reason": "LLM_API_KEY not configured", "ready": False},
            "search": {"status": "skipped", "ready": False, "provider": "tavily", "reason": "搜索服务未配置"},
        },
    }


async def test_health_readiness_reports_not_demo_ready_when_graph_is_not_synced(client):
    with (
        patch(
            "app.api.v1.health.search",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.v1.health.llm_health_check",
            AsyncMock(return_value={"status": "ok", "base_url": "https://example.com/v1", "model": "demo-model"}),
        ),
        patch(
            "app.api.v1.health._check_neo4j",
            AsyncMock(return_value={"status": "ok", "ready": True}),
        ),
        patch(
            "app.api.v1.health._check_graph_sync",
            AsyncMock(
                return_value={
                    "status": "missing",
                    "ready": False,
                    "in_sync": False,
                    "reason": "domain_pack_not_seeded",
                    "domain": "machine_learning",
                    "version": "1.0.0",
                    "pack_hash": "pack-hash",
                    "nodes": 5,
                    "edges": 8,
                }
            ),
        ),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["ready"] is False
    assert data["core_ready"] is False
    assert data["demo_ready"] is False
    assert data["enhanced_ready"] is True
    assert data["services"]["graph_sync"] == {
        "status": "missing",
        "ready": False,
        "in_sync": False,
        "reason": "domain_pack_not_seeded",
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": "pack-hash",
        "nodes": 5,
        "edges": 8,
    }


async def test_health_readiness_reports_search_auth_failure(client):
    with (
        patch(
            "app.api.v1.health.llm_health_check",
            AsyncMock(return_value={"status": "ok", "base_url": "https://example.com/v1", "model": "demo-model"}),
        ),
        patch(
            "app.api.v1.health._check_neo4j",
            AsyncMock(return_value={"status": "ok", "ready": True}),
        ),
        patch(
            "app.api.v1.health._check_graph_sync",
            AsyncMock(
                return_value={
                    "status": "ok",
                    "ready": True,
                    "in_sync": True,
                    "reason": "synced",
                    "domain": "machine_learning",
                    "version": "1.0.0",
                    "pack_hash": "pack-hash",
                    "main_graph_synced": True,
                    "entity_graph_synced": True,
                    "nodes": 5,
                    "edges": 8,
                }
            ),
        ),
        patch(
            "app.api.v1.health.search",
            AsyncMock(side_effect=Exception("should not be called")),
        ),
        patch(
            "app.api.v1.health._check_search",
            AsyncMock(
                return_value={
                    "status": "error",
                    "ready": False,
                    "provider": "tavily",
                    "reason": "搜索服务鉴权失败",
                }
            ),
        ),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "degraded"
    assert data["ready"] is False
    assert data["core_ready"] is True
    assert data["demo_ready"] is True
    assert data["enhanced_ready"] is False
    assert data["services"]["search"] == {
        "status": "error",
        "ready": False,
        "provider": "tavily",
        "reason": "搜索服务鉴权失败",
    }


async def test_health_readiness_reports_ready_when_all_services_are_ready(client):
    with (
        patch(
            "app.api.v1.health.search",
            AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.v1.health.llm_health_check",
            AsyncMock(return_value={"status": "ok", "base_url": "https://example.com/v1", "model": "demo-model"}),
        ),
        patch(
            "app.api.v1.health._check_neo4j",
            AsyncMock(return_value={"status": "ok", "ready": True}),
        ),
        patch(
            "app.api.v1.health._check_graph_sync",
            AsyncMock(
                return_value={
                    "status": "ok",
                    "ready": True,
                    "in_sync": True,
                    "reason": "synced",
                    "domain": "machine_learning",
                    "version": "1.0.0",
                    "pack_hash": "pack-hash",
                    "main_graph_synced": True,
                    "entity_graph_synced": True,
                    "nodes": 5,
                    "edges": 8,
                }
            ),
        ),
    ):
        resp = await client.get("/api/v1/health/readiness")

    assert resp.status_code == 200
    assert resp.json() == {
        "status": "ready",
        "ready": True,
        "core_ready": True,
        "demo_ready": True,
        "enhanced_ready": True,
        "services": {
            "sqlite": {"status": "ok", "ready": True},
            "neo4j": {"status": "ok", "ready": True},
            "graph_sync": {
                "status": "ok",
                "ready": True,
                "in_sync": True,
                "reason": "synced",
                "domain": "machine_learning",
                "version": "1.0.0",
                "pack_hash": "pack-hash",
                "main_graph_synced": True,
                "entity_graph_synced": True,
                "nodes": 5,
                "edges": 8,
            },
            "llm": {"status": "ok", "base_url": "https://example.com/v1", "model": "demo-model", "ready": True},
            "search": {"status": "ok", "ready": True, "provider": "tavily"},
        },
    }


async def test_health_llm_test_is_disabled(client):
    resp = await client.post(
        "/api/v1/health/llm-test",
        json={
            "base_url": "https://evil.example",
            "model": "bad-model",
            "api_key": "__use_saved__",
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"


async def test_polish_config_put_true_then_get_returns_true(client):
    resp = await client.put(
        "/api/v1/health/config",
        json={"llm_explanation_polish": True},
    )
    assert resp.status_code == 200
    assert resp.json()["llm_explanation_polish"] is True

    read_resp = await client.get("/api/v1/health/config")
    assert read_resp.status_code == 200
    assert read_resp.json()["llm_explanation_polish"] is True


async def test_polish_config_put_false_overrides_existing_true(client):
    put_true = await client.put(
        "/api/v1/health/config",
        json={"llm_explanation_polish": True},
    )
    assert put_true.status_code == 200
    assert put_true.json()["llm_explanation_polish"] is True

    put_false = await client.put(
        "/api/v1/health/config",
        json={"llm_explanation_polish": False},
    )
    assert put_false.status_code == 200
    assert put_false.json()["llm_explanation_polish"] is False

    read_resp = await client.get("/api/v1/health/config")
    assert read_resp.json()["llm_explanation_polish"] is False


async def test_polish_config_empty_body_remains_noop(client, db_session):
    before = (await db_session.execute(select(RuntimeSetting))).scalars().all()
    before_count = len(before)

    resp = await client.put("/api/v1/health/config", json={})
    assert resp.status_code == 200
    assert resp.json()["message"] == "未提供可更新的运行时配置"
    assert "llm_explanation_polish" in resp.json()

    after = (await db_session.execute(select(RuntimeSetting))).scalars().all()
    assert len(after) == before_count


async def test_polish_config_restart_restores_from_sqlite(client, db_session):
    put_resp = await client.put(
        "/api/v1/health/config",
        json={"llm_explanation_polish": True},
    )
    assert put_resp.status_code == 200

    replace_runtime_settings({})
    restored = await get_runtime_settings_map(db_session)
    replace_runtime_settings(restored)

    read_resp = await client.get("/api/v1/health/config")
    assert read_resp.json()["llm_explanation_polish"] is True
