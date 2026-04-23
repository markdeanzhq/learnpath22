"""目标解析服务测试"""
import sys
from types import SimpleNamespace
from unittest.mock import patch

from app.services.goal_service import (
    _jieba_match_nodes,
    _llm_match_nodes,
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
    )
    assert result["goal_type"] == "domain"


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
    assert 0 <= candidate["score"] <= 1
    assert all(node_id in pack.nodes_by_id for node_id in candidate["target_node_ids"])


def test_specific_problem_candidate_beats_generic_domain_candidate():
    pack = get_domain_pack_service(force_reload=True)
    result = resolve_goal_candidates(
        goal_text="我想系统学习机器学习基础，但更想搞懂逻辑回归为什么能做分类",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        allow_llm=False,
    )

    candidate_ids = [candidate["candidate_id"] for candidate in result["candidates"]]
    assert "template:problem_logistic_classification" in candidate_ids
    assert "template:domain_ml_full" in candidate_ids
    assert candidate_ids.index("template:problem_logistic_classification") < candidate_ids.index("template:domain_ml_full")
    assert result["recommended_candidate_id"] == "template:problem_logistic_classification"


def test_ranking_is_deterministic_under_same_inputs():
    pack = get_domain_pack_service(force_reload=True)
    first = resolve_goal_candidates(
        goal_text="我想系统学习机器学习基础，但更想搞懂逻辑回归为什么能做分类",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
        allow_llm=False,
    )
    second = resolve_goal_candidates(
        goal_text="我想系统学习机器学习基础，但更想搞懂逻辑回归为什么能做分类",
        goal_type_override=None,
        templates=pack.goal_templates,
        nodes_by_id=pack.nodes_by_id,
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
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_empty_result" in candidate["warnings"] for candidate in result["candidates"])


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
    with patch("app.services.goal_service._collect_template_candidates", return_value=[]), patch(
        "app.services.goal_service._collect_lexical_candidates", return_value=[]
    ), patch(
        "app.services.goal_service._llm_match_nodes",
        return_value=(None, "llm_timeout"),
    ):
        result = resolve_goal(
            goal_text="完全无匹配目标",
            goal_type_override="concept",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
            allow_llm=True,
        )

    assert result["resolve_source"] == "fallback"
    assert result["target_node_ids"] == ["ml_c09", "ml_d08", "ml_e03"]
    assert result["warnings"] == ["empty_candidates", "llm_timeout"]


def test_llm_duplicate_nodes_are_deduplicated_and_retained_via_source_breakdown():
    pack = get_domain_pack_service(force_reload=True)
    with patch("app.services.goal_service._llm_match_nodes", return_value=["ml_c05", "ml_c05", "ml_c06"]):
        result = resolve_goal_candidates(
            goal_text="推导梯度下降更新公式",
            goal_type_override="problem",
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
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
            allow_llm=True,
        )

    assert result["recommended_candidate_id"]
    assert all(candidate["resolve_source"] != "llm" for candidate in result["candidates"])
    assert any("llm_invalid_response" in candidate["warnings"] for candidate in result["candidates"])
