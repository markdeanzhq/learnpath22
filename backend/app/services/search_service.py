"""搜索服务：封装 Tavily API，最小可用版"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.exceptions import AppError
from app.core.config import get_search_api_key

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


class SearchResult:
    def __init__(self, title: str, url: str, snippet: str, score: float):
        self.title = title
        self.url = url
        self.snippet = snippet
        self.score = score

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "score": self.score,
        }


async def search(
    query: str,
    max_results: int = 5,
    search_depth: str = "basic",
) -> list[dict[str, Any]]:
    """调用 Tavily API 搜索学习资料。"""
    api_key = get_search_api_key()

    if not api_key:
        logger.warning("未配置 SEARCH_API_KEY")
        raise AppError(code=503, message="搜索服务未配置")

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                TAVILY_API_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": search_depth,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except httpx.TimeoutException as e:
        logger.error("搜索超时: %s", e)
        raise AppError(code=503, message="搜索服务超时") from e
    except httpx.HTTPStatusError as e:
        logger.error("搜索上游错误: %s", e)
        status_code = e.response.status_code
        if status_code in (401, 403):
            raise AppError(code=502, message="搜索服务鉴权失败") from e
        raise AppError(code=503, message="搜索服务暂时不可用") from e
    except httpx.HTTPError as e:
        logger.error("搜索网络错误: %s", e)
        raise AppError(code=503, message="搜索服务连接失败") from e

    results = []
    for item in data.get("results", []):
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("content", "")[:300],
            "score": item.get("score", 0),
        })
    return results
