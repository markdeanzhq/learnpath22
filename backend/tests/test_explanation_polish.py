"""LLM 解释润色层测试"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.core.config import get_settings
from app.schemas.explanation import (
    ExplanationResponse,
    NodeExplanation,
    OrderExplanation,
    StageExplanation,
)
from app.services.explanation_service import (
    POLISH_MAX_LENGTH,
    polish_explanation,
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


def _mock_factory_raises():
    def factory(_llm_cfg):
        def raise_fn(**kw):
            raise TimeoutError("LLM timeout")
        return SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=raise_fn)
            )
        )
    return factory


def test_polish_disabled_by_default(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    get_settings.cache_clear()
    original = _make_response()
    result = polish_explanation(original)
    assert result is original


def test_polish_no_llm_key(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({"llm_api_key": None})

    original = _make_response()
    result = polish_explanation(original)
    assert result.node_explanations[0].raw_reason is None


def test_polish_success(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

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


def test_polish_failure_falls_back(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    original = _make_response()
    result = polish_explanation(original, llm_client_factory=_mock_factory_raises())

    assert result.node_explanations[0].reason == original.node_explanations[0].reason
    assert result.node_explanations[0].raw_reason is None


def test_polish_rejects_overlong_text(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

    too_long = "啊" * (POLISH_MAX_LENGTH + 10)
    factory = _mock_factory({"node:ml_c05": too_long})
    result = polish_explanation(_make_response(), llm_client_factory=factory)

    assert result.node_explanations[0].reason == "目标节点：直接匹配学习目标"
    assert result.node_explanations[0].raw_reason is None


def test_polish_runtime_override_disables(monkeypatch):
    """T6: runtime override {llm_explanation_polish: false} 必须短路润色，即使 .env=true 且 api_key 已配置。"""
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({
        "llm_api_key": "sk-test",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_explanation_polish": "false",
    })

    original = _make_response()
    factory = _mock_factory({"node:ml_c05": "不应被调用"})
    result = polish_explanation(original, llm_client_factory=factory)

    assert result is original
    assert result.node_explanations[0].raw_reason is None


def test_polish_runtime_override_enables(monkeypatch):
    """T7: runtime override {llm_explanation_polish: true} 即使 .env=false 也能进入 LLM 调用分支。"""
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "false")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({
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


def test_polish_only_changes_text_fields(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("LLM_EXPLANATION_POLISH", "true")
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    get_settings.cache_clear()
    from app.core.config import replace_runtime_settings
    replace_runtime_settings({"llm_api_key": "sk-test", "llm_base_url": "https://api.openai.com/v1"})

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
