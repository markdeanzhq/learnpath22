"""LLM 解释润色层测试"""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import get_settings
from app.schemas.explanation import (
    ExplanationAskRequest,
    ExplanationResponse,
    NodeExplanation,
    OrderExplanation,
    StageExplanation,
)
from app.services.explanation_service import (
    POLISH_MAX_LENGTH,
    answer_explanation_question,
    polish_explanation,
    _build_llm_client,
    _request_llm_polish,
)


def _make_response() -> ExplanationResponse:
    return ExplanationResponse(
        node_explanations=[
            NodeExplanation(
                node_id="ml_c05",
                node_name="梯度下降",
                reason="目标节点：直接匹配学习目标",
                decision_type="target",
            ),
            NodeExplanation(
                node_id="ml_a04",
                node_name="导数与偏导",
                reason="前置依赖：目标节点的必要前置知识",
                decision_type="prerequisite",
            ),
        ],
        ordering_explanations=[
            OrderExplanation(
                node_id="ml_c05", node_name="梯度下降",
                priority_score=0.7, goal_relevance=1.0, factors=["高目标相关度"],
            ),
        ],
        stage_explanations=[
            StageExplanation(
                node_id="ml_c05", node_name="梯度下降",
                assigned_stage="核心掌握",
                reasons=["category=algorithm", "goal_type=concept", "default_stage_rule"],
            ),
        ],
        budget_explanation=None,
        reinforcement_explanations=[],
        dependency_chain_explanations=[],
    )


def _replace_runtime_settings(overrides: dict[str, str]) -> None:
    from app.core.config import replace_runtime_settings
    replace_runtime_settings(overrides)


def _mock_factory(polished_text_by_key: dict[str, str]):
    def factory(_llm_cfg):
        items_payload = json.dumps(
            [{"key": k, "text": v} for k, v in polished_text_by_key.items()],
            ensure_ascii=False,
        )
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content=items_payload),
                )
            ]
        )
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kw: response
                )
            )
        )
        return client
    return factory


def _mock_ask_factory(answer: str, captured: dict[str, Any] | None = None):
    def factory(_llm_cfg):
        def create(**kwargs):
            if captured is not None:
                captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=answer),
                    )
                ]
            )
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        )
    return factory


class FakeAPITimeoutError(Exception):
    pass


FakeAPITimeoutError.__name__ = "APITimeoutError"


class FakeBlockedError(Exception):
    pass


FakeBlockedError.__name__ = "BadRequestError"


def _mock_factory_raises(exc: Exception | None = None):
    def factory(_llm_cfg):
        def raise_fn(**kw):
            raise exc or TimeoutError("LLM timeout")
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=raise_fn)
            )
        )
    return factory


def _mock_factory_rejects_temperature(answer: str, captured_calls: list[dict[str, Any]]):
    def factory(_llm_cfg):
        def create(**kwargs):
            captured_calls.append(dict(kwargs))
            if "temperature" in kwargs:
                raise ValueError("temperature is unsupported by this model")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=answer),
                    )
                ]
            )
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        )
    return factory


def _mock_factory_blocks_system_then_succeeds(answer: str, captured_calls: list[dict[str, Any]]):
    def factory(_llm_cfg):
        def create(**kwargs):
            captured_calls.append(dict(kwargs))
            if any(message.get("role") == "system" for message in kwargs.get("messages", [])):
                raise FakeBlockedError("Your request was blocked.")
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content=answer),
                    )
                ]
            )
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=create)
            )
        )
    return factory


def test_polish_disabled_by_default(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    get_settings.cache_clear()
    _replace_runtime_settings({})

    original = _make_response()
    result = polish_explanation(original)

    assert result.node_explanations == original.node_explanations
    assert result.stage_explanations == original.stage_explanations
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.scope == []
    assert result.meta.polish.fallback_reason == "disabled"


def test_polish_no_llm_key(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": ""})

    original = _make_response()
    result = polish_explanation(original)

    assert result.node_explanations[0].raw_reason is None
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "missing_api_key"


def test_polish_success(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    factory = _mock_factory({
        "node:ml_c05": "这是你的学习目标，路径从这里展开。",
        "node:ml_a04": "理解梯度下降需要先掌握导数。",
        "stage:ml_c05": "归入核心掌握阶段，属于算法类。",
    })

    result = polish_explanation(_make_response(), llm_client_factory=factory)

    target_node = result.node_explanations[0]
    assert target_node.reason == "这是你的学习目标，路径从这里展开。"
    assert target_node.raw_reason == "目标节点：直接匹配学习目标"

    stage = result.stage_explanations[0]
    assert stage.rationale == "归入核心掌握阶段，属于算法类。"
    assert stage.raw_rationale is not None
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is True
    assert result.meta.polish.scope == ["node_reason", "stage_rationale"]
    assert result.meta.polish.fallback_reason is None


@pytest.mark.parametrize("exc", [TimeoutError("LLM timeout"), FakeAPITimeoutError("SDK timeout")])
def test_polish_failure_falls_back(monkeypatch, exc):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    original = _make_response()
    result = polish_explanation(original, llm_client_factory=_mock_factory_raises(exc))

    assert result.node_explanations[0].reason == original.node_explanations[0].reason
    assert result.node_explanations[0].raw_reason is None
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "timeout"


def test_polish_blocked_request_records_blocked_fallback(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    original = _make_response()
    result = polish_explanation(
        original,
        llm_client_factory=_mock_factory_raises(FakeBlockedError("Your request was blocked.")),
    )

    assert result.node_explanations == original.node_explanations
    assert result.stage_explanations == original.stage_explanations
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "blocked"


def test_polish_retries_with_user_only_prompt_when_system_prompt_is_blocked(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    calls: list[dict[str, Any]] = []
    result = polish_explanation(
        _make_response(),
        llm_client_factory=_mock_factory_blocks_system_then_succeeds(
            "[{\"key\":\"node:ml_c05\",\"text\":\"系统提示被拦截后仍成功润色。\"}]",
            calls,
        ),
    )

    assert len(calls) == 2
    assert any(message["role"] == "system" for message in calls[0]["messages"])
    assert all(message["role"] == "user" for message in calls[1]["messages"])
    assert result.node_explanations[0].reason == "系统提示被拦截后仍成功润色。"
    assert result.meta is not None
    assert result.meta.polish.applied is True
    assert result.meta.polish.fallback_reason is None


def test_default_llm_client_uses_http_chat_completions(monkeypatch):
    captured: dict[str, Any] = {}

    def fake_post(self, url, *, headers=None, json=None):
        captured.update({"url": url, "headers": headers, "json": json})
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "choices": [
                    {"message": {"content": "[{\"key\":\"node:ml_c05\",\"text\":\"HTTP 直连润色成功。\"}]"}}
                ],
            },
        )

    monkeypatch.setattr("httpx.Client.post", fake_post)
    client = _build_llm_client({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://proxy.example/v1/",
        "llm_model": "gpt-5.2",
    }, None, timeout=5.0)

    response = _request_llm_polish(
        client,
        {"llm_model": "gpt-5.2"},
        [{"role": "user", "content": "ping"}],
    )

    assert captured["url"] == "https://proxy.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["json"]["model"] == "gpt-5.2"
    assert captured["json"]["messages"] == [{"role": "user", "content": "ping"}]
    assert response.choices[0].message.content == "[{\"key\":\"node:ml_c05\",\"text\":\"HTTP 直连润色成功。\"}]"


def test_polish_rejects_overlong_text(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    too_long = "啊" * (POLISH_MAX_LENGTH + 10)
    factory = _mock_factory({"node:ml_c05": too_long})
    result = polish_explanation(_make_response(), llm_client_factory=factory)

    assert result.node_explanations[0].reason == "目标节点：直接匹配学习目标"
    assert result.node_explanations[0].raw_reason is None
    assert result.meta is not None
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "length_exceeded"


def test_polish_invalid_json_returns_metadata_fallback(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    original = _make_response()
    result = polish_explanation(
        original,
        llm_client_factory=_mock_ask_factory("not json"),
    )

    assert result.node_explanations == original.node_explanations
    assert result.stage_explanations == original.stage_explanations
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "invalid_response"


@pytest.mark.parametrize(
    "payload",
    [
        "{}",
        "[{\"key\":\"node:ml_c05\"}]",
        "[{\"text\":\"缺少 key 的文本\"}]",
    ],
)
def test_polish_schema_violation_returns_metadata_fallback(monkeypatch, payload):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    original = _make_response()
    result = polish_explanation(original, llm_client_factory=_mock_ask_factory(payload))

    assert result.node_explanations == original.node_explanations
    assert result.stage_explanations == original.stage_explanations
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "invalid_response"


def test_polish_accepts_json_code_fence_response(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    result = polish_explanation(
        _make_response(),
        llm_client_factory=_mock_ask_factory(
            "```json\n"
            "[{\"key\":\"node:ml_c05\",\"text\":\"用更自然的语言说明目标节点。\"}]\n"
            "```"
        ),
    )

    assert result.node_explanations[0].reason == "用更自然的语言说明目标节点。"
    assert result.node_explanations[0].raw_reason == "目标节点：直接匹配学习目标"
    assert result.meta is not None
    assert result.meta.polish.applied is True
    assert result.meta.polish.fallback_reason is None


def test_polish_retries_without_temperature_for_strict_models(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-5.2",
    })

    calls: list[dict[str, Any]] = []
    result = polish_explanation(
        _make_response(),
        llm_client_factory=_mock_factory_rejects_temperature(
            "[{\"key\":\"node:ml_c05\",\"text\":\"兼容严格模型后的润色文本。\"}]",
            calls,
        ),
    )

    assert len(calls) == 2
    assert calls[0]["model"] == "gpt-5.2"
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]
    assert result.node_explanations[0].reason == "兼容严格模型后的润色文本。"
    assert result.meta is not None
    assert result.meta.polish.applied is True


def test_polish_runtime_override_disables(monkeypatch):
    """T6: runtime override {llm_explanation_polish: false} 必须短路润色，即使 .env=true 且 api_key 已配置。"""
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "false",
    })

    original = _make_response()
    factory = _mock_factory({"node:ml_c05": "不应被调用"})
    result = polish_explanation(original, llm_client_factory=factory)

    assert result.node_explanations == original.node_explanations
    assert result.node_explanations[0].raw_reason is None
    assert result.meta is not None
    assert result.meta.polish.requested is True
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason == "disabled"


def test_polish_runtime_override_enables(monkeypatch):
    """T7: runtime override {llm_explanation_polish: true} 即使 .env=false 也能进入 LLM 调用分支。"""
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "true",
    })

    factory = _mock_factory({
        "node:ml_c05": "经润色的目标说明。",
        "node:ml_a04": "经润色的前置说明。",
        "stage:ml_c05": "经润色的阶段说明。",
    })
    result = polish_explanation(_make_response(), llm_client_factory=factory)

    assert result.node_explanations[0].reason == "经润色的目标说明。"
    assert result.node_explanations[0].raw_reason == "目标节点：直接匹配学习目标"
    assert result.meta is not None
    assert result.meta.polish.applied is True


def test_polish_only_changes_text_fields(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    original = _make_response()
    factory = _mock_factory({
        "node:ml_c05": "润色后的目标文本。",
        "node:ml_a04": "润色后的前置文本。",
        "stage:ml_c05": "润色后的阶段文本。",
    })
    result = polish_explanation(original, llm_client_factory=factory)

    assert result.node_explanations[0].node_id == original.node_explanations[0].node_id
    assert result.node_explanations[0].decision_type == original.node_explanations[0].decision_type
    assert result.ordering_explanations == original.ordering_explanations
    assert result.dependency_chain_explanations == original.dependency_chain_explanations
    assert result.stage_explanations[0].assigned_stage == original.stage_explanations[0].assigned_stage
    assert result.stage_explanations[0].reasons == original.stage_explanations[0].reasons


def test_polish_not_requested_records_metadata():
    original = _make_response()
    result = polish_explanation(original, requested=False)

    assert result.node_explanations == original.node_explanations
    assert result.meta is not None
    assert result.meta.polish.requested is False
    assert result.meta.polish.applied is False
    assert result.meta.polish.fallback_reason is None


def test_answer_question_uses_minimal_llm_payload(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "true",
    })

    captured: dict[str, Any] = {}
    original = _make_response()
    before = original.model_dump()
    result = answer_explanation_question(
        original,
        ExplanationAskRequest(question_id="why_include_node", node_id="ml_c05"),
        llm_client_factory=_mock_ask_factory(
            "{\"answer\":\"因为它直接匹配当前学习目标。\",\"limitations\":[\"ai_auxiliary\"]}",
            captured,
        ),
    )

    assert result.ai_used is True
    assert result.fallback_reason is None
    assert result.answer == "因为它直接匹配当前学习目标。"
    assert result.limitations == ["ai_auxiliary"]
    assert original.model_dump() == before

    payload = json.loads(captured["messages"][1]["content"])
    assert set(payload) == {
        "question",
        "rule_answer",
        "evidence_refs",
        "limitations",
        "readability",
        "rule_explanation",
        "audit_summary",
    }
    assert payload["question"]["question_id"] == "why_include_node"
    assert payload["question"]["node_id"] == "ml_c05"
    assert payload["rule_explanation"]["node_explanation"]["node_id"] == "ml_c05"
    assert "audit" not in payload
    assert "raw_audit" not in payload
    assert "node_groups" not in payload


def test_answer_question_ignores_polish_toggle(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "false",
    })

    result = answer_explanation_question(
        _make_response(),
        ExplanationAskRequest(question_id="why_include_node", node_id="ml_c05"),
        llm_client_factory=_mock_ask_factory(
            "{\"answer\":\"因为它直接匹配当前学习目标。\",\"limitations\":[]}"
        ),
    )

    assert result.ai_used is True
    assert result.fallback_reason is None
    assert result.answer == "因为它直接匹配当前学习目标。"


def test_answer_question_retries_without_temperature_for_strict_models(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-5.2",
    })

    calls: list[dict[str, Any]] = []
    result = answer_explanation_question(
        _make_response(),
        ExplanationAskRequest(question_id="why_path_order"),
        llm_client_factory=_mock_factory_rejects_temperature(
            "{\"answer\":\"严格模型兼容后仍可回答排序原因。\",\"limitations\":[]}",
            calls,
        ),
    )

    assert len(calls) == 2
    assert calls[0]["model"] == "gpt-5.2"
    assert "temperature" in calls[0]
    assert "temperature" not in calls[1]
    assert result.ai_used is True
    assert result.answer == "严格模型兼容后仍可回答排序原因。"


@pytest.mark.parametrize("exc", [TimeoutError("LLM timeout"), FakeAPITimeoutError("SDK timeout")])
def test_answer_question_timeout_returns_rule_fallback(monkeypatch, exc):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "true",
    })

    result = answer_explanation_question(
        _make_response(),
        ExplanationAskRequest(question_id="why_path_order"),
        llm_client_factory=_mock_factory_raises(exc),
    )

    assert result.ai_used is False
    assert result.fallback_reason == "timeout"
    assert result.evidence_refs[0].source == "readability.ordering_summary"


def test_answer_question_blocked_request_returns_rule_fallback(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "true",
    })

    result = answer_explanation_question(
        _make_response(),
        ExplanationAskRequest(question_id="why_path_order"),
        llm_client_factory=_mock_factory_raises(FakeBlockedError("Your request was blocked.")),
    )

    assert result.ai_used is False
    assert result.fallback_reason == "blocked"
    assert result.evidence_refs[0].source == "readability.ordering_summary"


def test_answer_question_invalid_response_returns_rule_fallback(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    _replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "true",
    })

    result = answer_explanation_question(
        _make_response(),
        ExplanationAskRequest(question_id="why_stage_assignment", node_id="ml_c05"),
        llm_client_factory=_mock_ask_factory("{\"oops\":\"bad\"}"),
    )

    assert result.ai_used is False
    assert result.fallback_reason == "invalid_response"
    assert result.answer == "category=algorithm、goal_type=concept、default_stage_rule"


def test_answer_question_invalid_node_id_returns_limitation():
    result = answer_explanation_question(
        _make_response(),
        ExplanationAskRequest(question_id="why_include_node", node_id="missing_node"),
    )

    assert result.ai_used is False
    assert result.fallback_reason == "invalid_node_id"
    assert result.limitations == ["node_not_in_latest_plan"]


@pytest.mark.parametrize(
    "value,expected",
    [
        ("true", True), ("TRUE", True), ("True", True), ("1", True),
        ("yes", True), ("on", True), ("t", True), (True, True),
        ("false", False), ("FALSE", False), ("False", False), ("0", False),
        ("no", False), ("off", False), ("f", False), (False, False),
    ],
)
def test_parse_runtime_bool_accepts(value, expected):
    from app.core.config import parse_runtime_bool
    assert parse_runtime_bool(value) is expected


@pytest.mark.parametrize("value", ["", "maybe", "2", "null", None, 0.5, [], {}])
def test_parse_runtime_bool_rejects(value):
    from app.core.config import parse_runtime_bool
    with pytest.raises(ValueError):
        parse_runtime_bool(value)
