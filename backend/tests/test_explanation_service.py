"""ExplanationService 单元测试"""
from app.services.domain_pack_service import get_domain_pack_service
from app.services.explanation_service import build_explanation


def _make_audit(
    target_ids=None,
    ordering_logs=None,
    stage_logs=None,
    budget_summary=None,
    reinforcement_logs=None,
    profile_snapshot=None,
    mode="steady",
    filtered_requires_rev_adj=None,
):
    return {
        "goal_result": {"target_node_ids": target_ids or [], "mode": mode},
        "ordering_logs": ordering_logs or {},
        "stage_logs": stage_logs or {},
        "budget_summary": budget_summary,
        "reinforcement_logs": reinforcement_logs or {},
        "profile_snapshot": profile_snapshot,
        "filtered_requires_rev_adj": filtered_requires_rev_adj,
    }


_DEFAULT_PROFILE = {
    "math_level": 2,
    "coding_level": 2,
    "ml_level": 1,
    "theory_weight": 0.6,
    "practice_weight": 0.4,
}


def test_build_explanation_basic():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c01": {
                "priority_score": 0.8,
                "goal_relevance": 0.5,
                "gap": {"gap_total": 0.2, "gap_math": 0.1, "gap_code": 0.1, "gap_ml": 0},
                "reasons": [],
            },
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.5, "gap_math": 0.2, "gap_code": 0.1, "gap_ml": 0.2},
                "reasons": [],
            },
        },
        stage_logs={
            "ml_c01": {"assigned_stage": "基础准备", "reasons": ["基础类别"]},
            "ml_c09": {"assigned_stage": "核心掌握", "reasons": ["算法类别"]},
        },
        budget_summary={
            "total_hours": 80,
            "weekly_hours": 10,
            "estimated_weeks": 8,
            "status": "feasible",
            "suggestion": "",
        },
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert len(result.node_explanations) == 2
    assert len(result.ordering_explanations) == 2
    assert len(result.stage_explanations) == 2
    assert len(result.dependency_chain_explanations) == 1
    assert result.budget_explanation is not None
    assert result.budget_explanation.status == "feasible"


def test_build_explanation_empty_audit():
    pack = get_domain_pack_service()
    audit = _make_audit()
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert len(result.node_explanations) == 0
    assert len(result.ordering_explanations) == 0
    assert len(result.dependency_chain_explanations) == 0
    assert result.budget_explanation is None


def test_build_explanation_with_reinforcement():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c01": {
                "priority_score": 0.7,
                "goal_relevance": 0.3,
                "gap": {"gap_total": 0.4},
                "reasons": [],
            },
        },
        reinforcement_logs={
            "ml_c01": {
                "gap": {"gap_total": 0.4, "gap_math": 0.2, "gap_code": 0.1, "gap_ml": 0.1},
                "reinforce_score": 0.6,
                "reasons": ["基础薄弱"],
            },
        },
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert len(result.reinforcement_explanations) == 1
    assert result.reinforcement_explanations[0].node_id == "ml_c01"
    node_expl = [n for n in result.node_explanations if n.node_id == "ml_c01"]
    assert len(node_expl) == 1
    assert node_expl[0].decision_type == "reinforced"


def test_node_explanation_decision_types():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0},
                "reasons": [],
            },
            "ml_c01": {
                "priority_score": 0.5,
                "goal_relevance": 0.2,
                "gap": {"gap_total": 0.1},
                "reasons": [],
            },
        },
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    types = {n.node_id: n.decision_type for n in result.node_explanations}
    assert types["ml_c09"] == "target"
    assert types["ml_c01"] == "prerequisite"


def test_ordering_explanation_factors():
    pack = get_domain_pack_service()
    audit = _make_audit(
        profile_snapshot=_DEFAULT_PROFILE,
        ordering_logs={
            "ml_c01": {
                "priority_score": 0.9,
                "goal_relevance": 0.8,
                "gap": {"gap_total": 0.5},
                "reasons": ["自定义因子"],
            },
        },
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert len(result.ordering_explanations) == 1
    factors = result.ordering_explanations[0].factors
    assert len(factors) >= 3
    assert "自定义因子" in factors
    # top-3 分量使用中文 label + 带 sign 的 3 位小数
    top3 = factors[:3]
    assert all("(" in f and ")" in f for f in top3)


def test_build_explanation_prefers_filtered_snapshot_over_legacy_graph():
    pack = get_domain_pack_service(force_reload=True)
    audit = _make_audit(
        target_ids=["ml_c05"],
        ordering_logs={
            "ml_c05": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.1},
                "reasons": [],
            },
        },
        filtered_requires_rev_adj={"ml_c05": []},
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert len(result.dependency_chain_explanations) == 1
    chain = result.dependency_chain_explanations[0].chain_node_ids
    assert chain == ["ml_c05"]


def test_build_explanation_uses_legacy_graph_when_snapshot_missing():
    pack = get_domain_pack_service(force_reload=True)
    audit = _make_audit(
        target_ids=["ml_c05"],
        ordering_logs={
            "ml_a04": {
                "priority_score": 0.4,
                "goal_relevance": 0.3,
                "gap": {"gap_total": 0.2},
                "reasons": [],
            },
            "ml_c05": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.1},
                "reasons": [],
            },
        },
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert len(result.dependency_chain_explanations) == 1
    chain = result.dependency_chain_explanations[0].chain_node_ids
    assert "ml_a04" in chain
    assert chain[-1] == "ml_c05"
