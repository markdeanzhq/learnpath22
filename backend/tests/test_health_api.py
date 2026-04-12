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
