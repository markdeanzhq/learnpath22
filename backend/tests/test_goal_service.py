"""目标解析服务测试"""
from unittest.mock import patch

from app.services.goal_service import (
    _jieba_match_nodes,
    _llm_match_nodes,
    identify_goal_type,
    resolve_goal,
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
    assert len(result["target_node_ids"]) > 0
    assert result["mode"] in ("steady", "efficient")
    assert all(nid in pack.nodes_by_id for nid in result["target_node_ids"])


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


def test_resolve_prefers_llm_over_template_and_jieba():
    pack = get_domain_pack_service()
    with patch("app.services.goal_service._llm_match_nodes", return_value=["ml_c09"]), patch(
        "app.services.goal_service._jieba_match_nodes", return_value=["ml_c01"]
    ):
        result = resolve_goal(
            goal_text="我想系统学习机器学习基础",
            goal_type_override=None,
            templates=pack.goal_templates,
            nodes_by_id=pack.nodes_by_id,
        )
    assert result["target_node_ids"] == ["ml_c09"]
    assert result["resolve_source"] == "llm"
