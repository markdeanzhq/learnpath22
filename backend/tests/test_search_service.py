"""SearchService 测试：mock Tavily API"""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from app.core.exceptions import AppError
from app.services.search_service import search


async def test_search_no_api_key():
    """无 API key 时返回明确错误"""
    with patch("app.services.search_service.get_search_api_key", return_value=""):
        with pytest.raises(AppError) as exc:
            await search("机器学习入门")
    assert exc.value.code == 503
    assert exc.value.message == "搜索服务未配置"


async def test_search_with_mock_tavily():
    """Mock Tavily API 正常返回"""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "results": [
            {
                "title": "ML 入门教程",
                "url": "https://example.com/ml",
                "content": "机器学习基础教程内容",
                "score": 0.9,
            },
            {
                "title": "深度学习概述",
                "url": "https://example.com/dl",
                "content": "深度学习入门" * 50,
                "score": 0.8,
            },
        ]
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.search_service.get_search_api_key", return_value="test-key"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        results = await search("机器学习", max_results=5)

    assert len(results) == 2
    assert results[0]["title"] == "ML 入门教程"
    assert results[0]["url"] == "https://example.com/ml"
    assert "snippet" in results[0]
    # snippet 应被截断到 300 字符以内
    assert len(results[1]["snippet"]) <= 300


async def test_search_handles_timeout_error():
    """Tavily 超时时返回明确错误"""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("connection timeout"))

    with (
        patch("app.services.search_service.get_search_api_key", return_value="test-key"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        with pytest.raises(AppError) as exc:
            await search("机器学习")

    assert exc.value.code == 503
    assert exc.value.message == "搜索服务超时"


async def test_search_handles_auth_error():
    """Tavily 鉴权失败时返回明确错误"""
    mock_response = MagicMock()
    mock_response.status_code = 401
    request = httpx.Request("POST", "https://api.tavily.com/search")
    response = httpx.Response(401, request=request)
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "unauthorized",
        request=request,
        response=response,
    )

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.search_service.get_search_api_key", return_value="test-key"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        with pytest.raises(AppError) as exc:
            await search("机器学习")

    assert exc.value.code == 502
    assert exc.value.message == "搜索服务鉴权失败"


async def test_search_empty_results():
    """Tavily 返回空结果"""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"results": []}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = False
    mock_client.post = AsyncMock(return_value=mock_response)

    with (
        patch("app.services.search_service.get_search_api_key", return_value="test-key"),
        patch("httpx.AsyncClient", return_value=mock_client),
    ):
        results = await search("不存在的内容")

    assert results == []
