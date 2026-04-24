from fastapi import APIRouter, Depends

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import (
    RuntimeSettingsUpdate,
    get_environment_fingerprint,
    get_llm_config,
    get_llm_polish_enabled,
    get_search_api_key,
    get_settings,
    replace_runtime_settings,
)
from app.api.deps import get_neo4j
from app.core.exceptions import AppError
from app.db.neo4j import Neo4jDriver
from app.db.sqlite import get_db, persist_runtime_settings
from app.services.domain_pack_service import get_domain_pack_registry
from app.services.graph_sync_service import get_graph_sync_service
from app.services.search_service import search

router = APIRouter()


@router.get("/health")
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "environment": get_environment_fingerprint(),
    }


@router.get("/health/config")
async def get_config():
    cfg = get_llm_config()
    return {
        "llm_base_url": cfg["llm_base_url"],
        "llm_model": cfg["llm_model"],
        "llm_api_key_set": bool(cfg["llm_api_key"]),
        "search_api_key_set": bool(get_search_api_key()),
        "llm_explanation_polish": get_llm_polish_enabled(),
    }


@router.put("/health/config")
async def put_config(
    payload: RuntimeSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        cfg = get_llm_config()
        return {
            "message": "未提供可更新的运行时配置",
            "llm_base_url": cfg["llm_base_url"],
            "llm_model": cfg["llm_model"],
            "llm_api_key_set": bool(cfg["llm_api_key"]),
            "search_api_key_set": bool(get_search_api_key()),
            "llm_explanation_polish": get_llm_polish_enabled(),
        }

    persisted_settings = await persist_runtime_settings(db, payload)
    replace_runtime_settings(persisted_settings)
    cfg = get_llm_config()
    return {
        "message": "运行时配置已保存",
        "llm_base_url": cfg["llm_base_url"],
        "llm_model": cfg["llm_model"],
        "llm_api_key_set": bool(cfg["llm_api_key"]),
        "search_api_key_set": bool(get_search_api_key()),
        "llm_explanation_polish": get_llm_polish_enabled(),
    }


@router.get("/health/llm")
async def llm_health_check():
    cfg = get_llm_config()
    if not cfg["llm_api_key"]:
        return {"status": "skipped", "reason": "LLM_API_KEY not configured"}
    return await _test_llm(cfg["llm_base_url"], cfg["llm_model"], cfg["llm_api_key"])


@router.post("/health/llm-test")
async def llm_test_custom():
    return {"status": "skipped", "reason": "自定义 LLM 连通性测试已禁用"}


@router.get("/health/search")
async def search_health_check():
    return await _check_search()


@router.get("/health/readiness")
async def readiness_check(
    db: AsyncSession = Depends(get_db),
    neo4j: Neo4jDriver = Depends(get_neo4j),
):
    sqlite_status = await _check_sqlite(db)
    neo4j_status = await _check_neo4j(neo4j)
    graph_sync_status = await _check_graph_sync(neo4j) if neo4j_status["ready"] else {
        "status": "blocked",
        "ready": False,
        "in_sync": False,
        "reason": "neo4j_unavailable",
        "domain": _get_default_domain(),
    }
    llm_status = await _check_llm()
    search_status = await _check_search()

    services = {
        "sqlite": sqlite_status,
        "neo4j": neo4j_status,
        "graph_sync": graph_sync_status,
        "llm": llm_status,
        "search": search_status,
    }
    core_ready = all(service["ready"] for service in (sqlite_status, neo4j_status, graph_sync_status))
    demo_ready = core_ready
    enhanced_ready = all(service["ready"] for service in (llm_status, search_status))

    return {
        "status": "ready" if demo_ready and enhanced_ready else "degraded",
        "ready": demo_ready and enhanced_ready,
        "core_ready": core_ready,
        "demo_ready": demo_ready,
        "enhanced_ready": enhanced_ready,
        "services": services,
    }


async def _check_sqlite(db: AsyncSession) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "ready": True}
    except Exception as e:
        return {"status": "error", "ready": False, "reason": str(e)}


async def _check_neo4j(neo4j: Neo4jDriver) -> dict:
    try:
        await neo4j.execute_query("RETURN 1 AS ok")
        return {"status": "ok", "ready": True}
    except Exception as e:
        return {"status": "error", "ready": False, "reason": str(e)}


async def _check_llm() -> dict:
    result = await llm_health_check()
    return {
        **result,
        "ready": result["status"] == "ok",
    }


def _get_default_domain() -> str:
    return get_domain_pack_registry().resolve_domain()


async def _check_graph_sync(neo4j: Neo4jDriver) -> dict:
    domain = _get_default_domain()
    try:
        return await get_graph_sync_service(neo4j).get_sync_status(domain)
    except (RuntimeError, ValueError) as e:
        return {
            "status": "error",
            "ready": False,
            "in_sync": False,
            "domain": domain,
            "reason": str(e),
        }


async def _check_search() -> dict:
    try:
        await search("机器学习", max_results=1)
        return {"status": "ok", "ready": True, "provider": "tavily"}
    except AppError as e:
        return {
            "status": "skipped" if e.message == "搜索服务未配置" else "error",
            "ready": False,
            "provider": "tavily",
            "reason": e.message,
        }
    except Exception as e:
        return {
            "status": "error",
            "ready": False,
            "provider": "tavily",
            "reason": str(e),
        }


async def _test_llm(base_url: str, model: str, api_key: str) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
            resp.raise_for_status()
            return {"status": "ok", "base_url": base_url, "model": model}
    except httpx.TimeoutException:
        return {"status": "error", "reason": "timeout", "base_url": base_url}
    except httpx.HTTPStatusError as e:
        return {"status": "error", "reason": f"HTTP {e.response.status_code}", "base_url": base_url}
    except Exception as e:
        return {"status": "error", "reason": str(e), "base_url": base_url}
