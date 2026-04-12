from fastapi import APIRouter

import httpx

from app.core.config import RuntimeSettingsUpdate, get_llm_config, get_search_api_key, get_settings, update_runtime_settings

router = APIRouter()


@router.get("/health")
async def health_check():
    settings = get_settings()
    return {
        "status": "ok",
        "project": settings.PROJECT_NAME,
        "version": settings.VERSION,
    }


@router.get("/health/config")
async def get_config():
    cfg = get_llm_config()
    return {
        "llm_base_url": cfg["llm_base_url"],
        "llm_model": cfg["llm_model"],
        "llm_api_key_set": bool(cfg["llm_api_key"]),
        "search_api_key_set": bool(get_search_api_key()),
    }


@router.put("/health/config")
async def put_config(payload: RuntimeSettingsUpdate):
    if not any([
        payload.llm_base_url,
        payload.llm_model,
        payload.llm_api_key,
        payload.search_api_key,
    ]):
        return {
            "message": "未提供可更新的运行时配置",
            "llm_api_key_set": bool(get_llm_config()["llm_api_key"]),
            "search_api_key_set": bool(get_search_api_key()),
        }
    update_runtime_settings(payload)
    cfg = get_llm_config()
    return {
        "message": "运行时配置已保存",
        "llm_base_url": cfg["llm_base_url"],
        "llm_model": cfg["llm_model"],
        "llm_api_key_set": bool(cfg["llm_api_key"]),
        "search_api_key_set": bool(get_search_api_key()),
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
