"""目标解析服务测试"""
import sys

import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.services.goal_service import (
    UnsupportedGoalTypeError,
    _get_default_goal_policy_entry,
    _jieba_match_nodes,
    _llm_match_nodes,
    build_empty_candidate_reason,
    identify_goal_type,
    match_strong_goal_template,
    resolve_goal,
    resolve_goal_candidates,
)
from app.services.domain_pack_service import get_domain_pack_service


def test_identify_domain_goal():
    assert identify_goal_type("我想系统学习机器学习基础") == "domain"
    assert identify_goal_type("全面入门机器学习") == "domain"


def test_identify_problem_goal():
    assert identify_goal_type("我想搞懂逻辑回归为什么能做分类") == "problem"
    assert identify_goal_type("如何推导梯度下降") == "problem"


def test_identify_concept_goal():
    assert identify_goal_type("理解梯度下降") == "concept"
    assert identify_goal_type("什么是过拟合") == "concept"


def test_resolve_domain_goal():
    pack = get_domain_pack_service()
    result = resolve_goal(
        goal_text="我想系统学习机器学习基础",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
    )
    assert result["goal_type"] == "domain"
    assert result["template_id"] == "domain_ml_full"
    assert result["resolve_source"] == "template"
    assert result["target_node_ids"] == ["ml_c09", "ml_d08", "ml_e03", "ml_e07", "ml_e08"]
    assert result["mode"] == "steady"
    assert all(nid in pack.nodes_by_id for nid in result["target_node_ids"])


def test_match_strong_goal_template_hits_domain_ml_full():
    pack = get_domain_pack_service()
    matched = match_strong_goal_template(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        templates=pack.goal_templates,
    )
    assert matched is not None
    assert matched["id"] == "domain_ml_full"


def test_resolve_problem_goal():
    pack = get_domain_pack_service()
    result = resolve_goal(
        goal_text="我想搞懂逻辑回归为什么能做分类",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
    )
    assert result["goal_type"] == "problem"
    assert len(result["target_node_ids"]) > 0


def test_resolve_concept_goal():
    pack = get_domain_pack_service()
    result = resolve_goal(
        goal_text="理解梯度下降",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
    )
    assert result["goal_type"] == "concept"
    assert len(result["target_node_ids"]) > 0


def test_resolve_with_type_override():
    pack = get_domain_pack_service()
    result = resolve_goal(
        goal_text="机器学习",
        goal_type_override="domain",
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
    )
    assert result["goal_type"] == "domain"


def test_resolve_goal_candidates_rejects_unsupported_goal_type_override():
    pack = get_domain_pack_service()
    with pytest.raises(UnsupportedGoalTypeError):
        resolve_goal_candidates(
            goal_text="机器学习",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types={"domain", "problem"},
            allow_llm=False,
        )


def test_build_empty_candidate_reason_prefers_negative_patterns_excluded_all():
    reason_code, reason_text = build_empty_candidate_reason(
        {
            "requested_goal_type": None,
            "effective_goal_type": "domain",
            "template_match_count": 2,
            "negative_excluded_count": 2,
            "lexical_match_count": 0,
            "llm_status": "llm_unavailable",
        }
    )
    assert reason_code == "negative_patterns_excluded_all"
    assert "排除" in reason_text


def test_negative_patterns_exclude_template_candidates_from_pool():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="我想系统学习机器学习基础，同时理解梯度下降",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )

    candidate_ids = [candidate["candidate_id"] for candidate in result["candidates"]]
    assert "template:domain_ml_full" not in candidate_ids
    assert "template:concept_gradient_descent" in candidate_ids
    assert result["recommended_candidate_id"] == "template:concept_gradient_descent"


def test_build_empty_candidate_reason_prefers_llm_unavailable_after_rule_miss():
    reason_code, reason_text = build_empty_candidate_reason(
        {
            "requested_goal_type": "concept",
            "effective_goal_type": "concept",
            "template_match_count": 0,
            "negative_excluded_count": 0,
            "lexical_match_count": 0,
            "llm_status": "llm_timeout",
        }
    )
    assert reason_code == "llm_unavailable_after_rule_miss"
    assert "LLM" in reason_text


def test_get_default_goal_policy_entry_reads_manifest_mapping():
    policy = _get_default_goal_policy_entry(
        "domain",
        {
            "by_goal_type": {
                "domain": {
                    "target_node_ids": ["ml_c09"],
                    "mode": "steady",
                    "description": "默认目标",
                    "resolve_source": "domain_default",
                }
            }
        },
    )
    assert policy == {
        "target_node_ids": ["ml_c09"],
        "mode": "steady",
        "description": "默认目标",
        "resolve_source": "domain_default",
    }


# --- 新增：jieba 分词匹配测试 ---

def test_jieba_match_finds_gradient_descent():
    pack = get_domain_pack_service()
    matched = _jieba_match_nodes("理解梯度下降的原理", pack.nodes_by_id)
    assert len(matched) > 0
    # 应该命中梯度下降相关节点
    node_names = [pack.nodes_by_id[nid]["name"] for nid in matched]
    assert any("梯度" in n for n in node_names)


def test_jieba_match_finds_logistic_regression():
    pack = get_domain_pack_service()
    matched = _jieba_match_nodes("逻辑回归做分类", pack.nodes_by_id)
    assert len(matched) > 0
    node_names = [pack.nodes_by_id[nid]["name"] for nid in matched]
    assert any("逻辑回归" in n or "回归" in n for n in node_names)


def test_jieba_match_returns_empty_for_unrelated():
    pack = get_domain_pack_service()
    matched = _jieba_match_nodes("量子力学和相对论", pack.nodes_by_id)
    # 无关主题可能匹配到0个或少量噪音
    assert len(matched) <= 2


# --- 新增：LLM fallback 测试 ---

def test_llm_match_returns_none_without_api_key():
    """无 API key 时应 graceful 返回 None。"""
    pack = get_domain_pack_service()
    with patch("app.services.goal_service.get_llm_config", return_value={
        "llm_api_key": "",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-3.5-turbo",
    }):
        result = _llm_match_nodes("理解梯度下降", pack.nodes_by_id)
    assert result is None


def test_llm_invalid_json_degrades_to_rule_candidates_with_warning():
    pack = get_domain_pack_service(force_reload=True)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(*args, **kwargs):
                    return SimpleNamespace(
                        choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))]
                    )

    with patch("app.services.goal_service.get_llm_config", return_value={
        "llm_api_key": "test-key",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-3.5-turbo",
    }), patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeClient)}):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_invalid_json" in candidate["warnings"] for candidate in result["candidates"])


def test_llm_timeout_degrades_to_rule_candidates_with_warning():
    pack = get_domain_pack_service(force_reload=True)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(*args, **kwargs):
                    raise TimeoutError("timeout")

    with patch("app.services.goal_service.get_llm_config", return_value={
        "llm_api_key": "test-key",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-3.5-turbo",
    }), patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeClient)}):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_timeout" in candidate["warnings"] for candidate in result["candidates"])


def test_llm_auth_failure_degrades_to_rule_candidates_with_warning():
    pack = get_domain_pack_service(force_reload=True)

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        class chat:
            class completions:
                @staticmethod
                def create(*args, **kwargs):
                    raise PermissionError("401 unauthorized")

    with patch("app.services.goal_service.get_llm_config", return_value={
        "llm_api_key": "test-key",
        "llm_base_url": "https://api.openai.com/v1",
        "llm_model": "gpt-3.5-turbo",
    }), patch.dict(sys.modules, {"openai": SimpleNamespace(OpenAI=FakeClient)}):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_auth_failed" in candidate["warnings"] for candidate in result["candidates"])


def test_resolve_source_field_present():
    """resolve_goal 应返回 resolve_source 字段。"""
    pack = get_domain_pack_service()
    result = resolve_goal(
        goal_text="我想系统学习机器学习基础",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
    )
    assert "resolve_source" in result


def test_resolve_concept_uses_jieba_when_no_llm():
    """concept 目标无 LLM 时应 fallback 到 jieba。"""
    pack = get_domain_pack_service()
    with patch("app.services.goal_service.get_llm_config", return_value={
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
    }):
        result = resolve_goal(
            goal_text="理解过拟合和欠拟合",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
        )
    assert result["goal_type"] == "concept"
    assert len(result["target_node_ids"]) > 0
    assert result["resolve_source"] in ("jieba", "fallback", "template")


def test_resolve_prefers_jieba_over_llm_when_no_template_hit():
    pack = get_domain_pack_service()
    with patch("app.services.goal_service._jieba_match_nodes", return_value=["ml_c01"]), patch(
        "app.services.goal_service._llm_match_nodes", return_value=["ml_c09"]
    ):
        result = resolve_goal(
            goal_text="请帮我看一下数据预处理怎么做",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
        )
    assert result["target_node_ids"] == ["ml_c01"]
    assert result["resolve_source"] == "jieba"


def test_resolve_template_hit_blocks_llm_override():
    pack = get_domain_pack_service()
    with patch("app.services.goal_service._jieba_match_nodes", return_value=["ml_c01"]), patch(
        "app.services.goal_service._llm_match_nodes", return_value=["ml_c09"]
    ):
        result = resolve_goal(
            goal_text="我想系统学习机器学习基础",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
        )
    assert result["template_id"] == "domain_ml_full"
    assert result["resolve_source"] == "template"
    assert result["target_node_ids"] == ["ml_c09", "ml_d08", "ml_e03", "ml_e07", "ml_e08"]


def test_resolve_goal_candidates_returns_stable_schema():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="理解梯度下降",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )

    assert result["auto_detected_goal_type"] == "concept"
    assert result["effective_goal_type"] == "concept"
    assert result["recommended_candidate_id"]
    assert len(result["candidates"]) >= 1

    candidate = result["candidates"][0]
    assert candidate["candidate_id"]
    assert candidate["goal_type"] in {"domain", "concept", "problem"}
    assert candidate["target_node_ids"]
    assert candidate["mode"] in {"steady", "efficient"}
    assert isinstance(candidate["description"], str)
    assert "resolve_source" in candidate
    assert isinstance(candidate["source_breakdown"], dict)
    assert isinstance(candidate["score_breakdown"], dict)
    assert isinstance(candidate["warnings"], list)
    assert candidate["confidence_level"] in {"high", "medium", "low"}
    assert candidate["recommended_action"] in {"confirm", "review", "clarify", "rewrite", "extension_draft"}
    assert isinstance(candidate["confidence_reason"], str) and candidate["confidence_reason"]
    assert isinstance(candidate["user_explanation"], str) and candidate["user_explanation"]
    assert isinstance(candidate["debug_explanation"], str) and candidate["debug_explanation"]
    assert isinstance(candidate["match_signals"], list)
    assert isinstance(candidate["is_recommended"], bool)
    assert 0 <= candidate["score"] <= 1
    assert all(node_id in pack.nodes_by_id for node_id in candidate["target_node_ids"])


def test_lexical_only_low_score_candidate_is_not_marked_recommended():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="学习机器学习的数学基础",
        goal_type_override="domain",
        templates=[],
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )

    candidate = result["candidates"][0]
    assert candidate["resolve_source"] == "jieba"
    assert candidate["score"] < 0.30
    assert candidate["confidence_level"] == "low"
    assert candidate["recommended_action"] == "clarify"
    assert candidate["is_recommended"] is False
    assert "关键词匹配" in candidate["confidence_reason"]



def test_template_candidate_exposes_user_friendly_confidence_metadata():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="理解梯度下降",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )

    candidate = result["candidates"][0]
    assert candidate["candidate_id"] == "template:concept_gradient_descent"
    assert candidate["confidence_level"] == "high"
    assert candidate["recommended_action"] == "confirm"
    assert candidate["is_recommended"] is True
    assert "template=" in candidate["debug_explanation"]
    assert "系统较可靠" in candidate["user_explanation"]
    assert any(signal["type"] == "template" for signal in candidate["match_signals"])



def test_specific_problem_candidate_beats_generic_domain_candidate():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="机器学习基础里的逻辑回归分类",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )

    candidate_ids = [candidate["candidate_id"] for candidate in result["candidates"]]
    assert "template:problem_logistic_classification" in candidate_ids
    assert "template:domain_ml_full" in candidate_ids
    assert candidate_ids.index("template:problem_logistic_classification") < candidate_ids.index("template:domain_ml_full")
    assert result["recommended_candidate_id"] == "template:problem_logistic_classification"


@pytest.mark.parametrize(
    "goal_text",
    [
        "机器学习基础里的逻辑回归分类",
        "理解梯度下降",
        "我想系统学习机器学习基础",
    ],
)
def test_ranking_is_deterministic_under_same_inputs(goal_text):
    pack = get_domain_pack_service(force_reload=True)
    first = resolve_goal_candidates(
        goal_text=goal_text,
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )
    second = resolve_goal_candidates(
        goal_text=goal_text,
        goal_type_override=None,
        templates=list(reversed(pack.goal_templates)),
        nodes_by_id=dict(reversed(list(pack.nodes_by_id.items()))),
        supported_goal_types=tuple(reversed(pack.contract.supported_goal_types)),
        allow_llm=False,
    )

    assert first["recommended_candidate_id"] == second["recommended_candidate_id"]
    assert first["candidates"] == second["candidates"]


def test_generic_penalty_is_exposed_for_generic_domain_candidate():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="我想系统学习机器学习基础",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types,
        allow_llm=False,
    )

    domain_candidate = next(
        candidate for candidate in result["candidates"] if candidate["candidate_id"] == "template:domain_ml_full"
    )
    assert domain_candidate["score_breakdown"]["generic_penalty"] > 0


def test_llm_empty_array_degrades_to_rule_candidates_with_warning():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._llm_match_nodes", return_value=[]):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_empty_result" in candidate["warnings"] for candidate in result["candidates"])


def test_resolve_goal_candidates_returns_reason_fields_when_empty():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._collect_template_candidates", return_value=([], {"template_match_count": 0, "negative_excluded_count": 0})), patch(
        "app.services.goal_service._collect_lexical_candidates",
        return_value=([], 0),
    ), patch(
        "app.services.goal_service._collect_llm_candidates",
        return_value=([], ["llm_unavailable"], "llm_unavailable"),
    ):
        result = resolve_goal_candidates(
            goal_text="完全无匹配目标",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["candidates"] == []
    assert result["reason_code"] == "llm_unavailable_after_rule_miss"
    assert isinstance(result["reason_text"], str) and result["reason_text"]
    assert result["empty_evidence"] == {
        "requested_goal_type": "concept",
        "effective_goal_type": "concept",
        "template_match_count": 0,
        "negative_excluded_count": 0,
        "lexical_match_count": 0,
        "llm_status": "llm_unavailable",
    }


def test_llm_structured_candidates_are_retained_as_separate_ranked_candidates():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._jieba_match_nodes", return_value=[]), patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=[["ml_c05"], ["ml_c06", "ml_c07"], ["ml_d08"]],
    ):
        result = resolve_goal_candidates(
            goal_text="我想补一下优化和模型选择",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    llm_candidates = [
        candidate for candidate in result["candidates"]
        if candidate["resolve_source"] == "llm"
    ]
    assert len(llm_candidates) == 3
    assert {tuple(candidate["target_node_ids"]) for candidate in llm_candidates} == {
        ("ml_c05",),
        ("ml_c06", "ml_c07"),
        ("ml_d08",),
    }
    assert all(candidate["score_breakdown"]["llm_score"] == 1.0 for candidate in llm_candidates)


def test_llm_unknown_nodes_degrade_to_rule_candidates_with_warning():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._llm_match_nodes", return_value=["not_exists"]):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_invalid_nodes" in candidate["warnings"] for candidate in result["candidates"])


def test_llm_structured_invalid_groups_are_dropped_with_warnings():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._jieba_match_nodes", return_value=[]), patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=[
            [],
            ["not_exists"],
            ["ml_a01", "ml_a02", "ml_a03", "ml_a04", "ml_a05", "ml_a06"],
            ["ml_c05", "ml_c05", "ml_c06"],
        ],
    ):
        result = resolve_goal_candidates(
            goal_text="推导梯度下降更新公式",
            goal_type_override="problem",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    merged_candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["target_node_ids"] == ["ml_c05", "ml_c06"]
    )
    assert merged_candidate["source_breakdown"]["llm"] == 1.0
    assert set(merged_candidate["warnings"]) == {
        "llm_candidate_too_large",
        "llm_empty_result",
        "llm_invalid_nodes",
        "llm_too_many_candidates",
    }


def test_llm_duplicate_heavy_candidate_is_deduped_before_size_limit():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._jieba_match_nodes", return_value=[]), patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=[["ml_c05", "ml_c05", "ml_c05", "ml_c06", "ml_c06", "ml_c07"]],
    ):
        result = resolve_goal_candidates(
            goal_text="理解优化路径",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    llm_candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["resolve_source"] == "llm"
        and candidate["target_node_ids"] == ["ml_c05", "ml_c06", "ml_c07"]
    )
    assert llm_candidate["warnings"] == []


def test_resolve_goal_preserves_llm_warning_when_candidates_empty():
    pack = get_domain_pack_service(force_reload=True)
    with patch(
        "app.services.goal_service._collect_template_candidates",
        return_value=([], {"template_match_count": 0, "negative_excluded_count": 0}),
    ), patch(
        "app.services.goal_service._collect_lexical_candidates",
        return_value=([], 0),
    ), patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=(None, "llm_timeout"),
    ):
        result = resolve_goal(
            goal_text="完全无匹配目标",
            goal_type_override="domain",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
            default_goal_policy=pack.contract.default_goal_policy,
        )

    assert result["resolve_source"] == "domain_default"
    assert result["target_node_ids"] == ["ml_c09", "ml_d08", "ml_e03", "ml_e07", "ml_e08"]
    assert result["description"] == "系统学习机器学习基础 — 完整三阶段路径"
    assert result["warnings"] == ["empty_candidates", "llm_timeout"]



def test_resolve_goal_raises_when_default_policy_fallback_disabled():
    pack = get_domain_pack_service(force_reload=True)
    with patch(
        "app.services.goal_service._collect_template_candidates",
        return_value=([], {"template_match_count": 0, "negative_excluded_count": 0}),
    ), patch(
        "app.services.goal_service._collect_lexical_candidates",
        return_value=([], 0),
    ), patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=(None, "llm_timeout"),
    ):
        with pytest.raises(UnsupportedGoalTypeError, match="fallback is disabled"):
            resolve_goal(
                goal_text="完全无匹配目标",
                goal_type_override="concept",
                templates=pack.goal_templates,
                nodes_by_id=pack.nodes_by_id,
                supported_goal_types=pack.contract.supported_goal_types,
                allow_llm=True,
                allow_default_policy_fallback=False,
                default_goal_policy=pack.contract.default_goal_policy,
            )



def test_build_empty_candidate_reason_skips_llm_when_disabled():
    class _FailFactory:
        def __call__(self, *_args, **_kwargs):
            raise AssertionError("LLM reason generation should be disabled")

    reason_code, reason_text = build_empty_candidate_reason(
        {
            "requested_goal_type": "concept",
            "effective_goal_type": "concept",
            "template_match_count": 0,
            "negative_excluded_count": 0,
            "lexical_match_count": 0,
            "llm_status": "llm_timeout",
        },
        allow_llm=False,
        llm_client_factory=_FailFactory(),
    )

    assert reason_code == "llm_unavailable_after_rule_miss"
    assert reason_text == "当前目标未命中规则候选，且 LLM 解析暂时不可用，请稍后重试或改写目标描述。"



def test_llm_duplicate_nodes_are_deduplicated_and_retained_via_source_breakdown():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._llm_match_nodes", return_value=["ml_c05", "ml_c05", "ml_c06"]):
        result = resolve_goal_candidates(
            goal_text="推导梯度下降更新公式",
            goal_type_override="problem",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    merged_candidate = next(
        candidate
        for candidate in result["candidates"]
        if candidate["candidate_id"] == "template:problem_gradient_derivation"
    )
    assert merged_candidate["target_node_ids"] == ["ml_c05", "ml_c06"]
    assert merged_candidate["source_breakdown"]["llm"] == 1.0
    assert merged_candidate["warnings"] == []


def test_llm_candidates_over_five_nodes_are_dropped_with_warning():
    pack = get_domain_pack_service(force_reload=True)
    with patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=["ml_a01", "ml_a02", "ml_a03", "ml_a04", "ml_a05", "ml_a06"],
    ):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_candidate_too_large" in candidate["warnings"] for candidate in result["candidates"])


def test_llm_invalid_structured_shape_degrades_with_warning():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._llm_match_nodes", return_value={"candidates": ["ml_c05", 1]}):
        result = resolve_goal_candidates(
            goal_text="理解梯度下降",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            supported_goal_types=pack.contract.supported_goal_types,
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_invalid_response" in candidate["warnings"] for candidate in result["candidates"])
