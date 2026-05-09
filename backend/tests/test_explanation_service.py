"""ExplanationService 单元测试"""
import pytest

from app.services.domain_pack_service import get_domain_pack_service
from app.services import explanation_service
from app.schemas.explanation import ExplanationAskRequest
from app.services.explanation_service import answer_explanation_question, build_explanation


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


def test_build_explanation_mentions_persona_summary_when_available():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0},
                "reasons": [],
            }
        },
        budget_summary={
            "total_hours": 8,
            "weekly_hours": 10,
            "estimated_weeks": 0.8,
            "status": "feasible",
            "suggestion": "",
        },
        profile_snapshot={
            **_DEFAULT_PROFILE,
            "persona_summary": "均衡推进型学习者：每周约 10 小时。",
        },
    )

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert result.budget_explanation is not None
    assert "学习者画像：均衡推进型学习者" in result.budget_explanation.suggestion


def test_build_explanation_ignores_missing_persona_summary_for_legacy_audit():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0},
                "reasons": [],
            }
        },
        budget_summary={
            "total_hours": 8,
            "weekly_hours": 10,
            "estimated_weeks": 0.8,
            "status": "feasible",
            "suggestion": "",
        },
        profile_snapshot=_DEFAULT_PROFILE,
    )

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert result.budget_explanation is not None
    assert "学习者画像" not in result.budget_explanation.suggestion


def test_build_explanation_mentions_compressed_exclusions():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0},
                "reasons": [],
            }
        },
        budget_summary={
            "total_hours": 8,
            "weekly_hours": 10,
            "estimated_weeks": 0.8,
            "status": "feasible",
            "suggestion": "",
        },
    )
    audit["path_mode"] = "compressed"
    audit["excluded_nodes"] = [
        {"node_id": "ml_a01", "exclusion_reason": "compressed_optional_reinforcement"}
    ]

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert result.budget_explanation is not None
    assert "压缩模式已裁剪" in result.budget_explanation.suggestion


def test_build_explanation_mentions_over_budget_required_closure():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0},
                "reasons": [],
            }
        },
        budget_summary={
            "total_hours": 80,
            "weekly_hours": 1,
            "estimated_weeks": 80,
            "status": "over_budget_required_closure",
            "suggestion": "目标及硬前置依赖已超出预算，不能裁剪硬依赖链",
        },
    )
    audit["path_mode"] = "compressed"
    audit["budget_status"] = "over_budget_required_closure"

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert result.budget_explanation is not None
    assert "硬前置闭包已超过预算" in result.budget_explanation.suggestion


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


def test_reinforcement_zero_gap_explains_foundation_bridge():
    pack = get_domain_pack_service()
    audit = _make_audit(
        target_ids=["ml_c09"],
        profile_snapshot=_DEFAULT_PROFILE,
        ordering_logs={
            "ml_a01": {
                "priority_score": 0.7,
                "goal_relevance": 0.3,
                "gap": {"gap_total": 0, "gap_math": 0, "gap_code": 0, "gap_ml": 0},
                "reasons": [],
            },
        },
        reinforcement_logs={
            "ml_a01": {
                "gap": {"gap_total": 0, "gap_math": 0, "gap_code": 0, "gap_ml": 0},
            },
        },
    )

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    node_expl = next(item for item in result.node_explanations if item.node_id == "ml_a01")

    assert node_expl.decision_type == "reinforced"
    assert node_expl.reinforcement_type == "foundation_bridge"
    assert node_expl.reinforce_score is not None and node_expl.reinforce_score > 0
    assert node_expl.score_breakdown["foundation"] > 0
    assert "基础桥接补强" in node_expl.reason
    assert "能力差距分 0.000" in node_expl.reason
    assert "补强选择分" in node_expl.reason
    assert "差距最明显" not in node_expl.reason
    assert "总分" not in node_expl.reason

    answer = answer_explanation_question(
        result,
        ExplanationAskRequest(question_id="why_include_node", node_id="ml_a01"),
    )
    assert "基础桥接补强" in answer.answer


def test_reinforcement_positive_gap_explains_ability_gap():
    pack = get_domain_pack_service()
    profile = {**_DEFAULT_PROFILE, "coding_level": 1}
    audit = _make_audit(
        target_ids=["ml_c09"],
        profile_snapshot=profile,
        ordering_logs={
            "ml_b08": {
                "priority_score": 0.7,
                "goal_relevance": 0.3,
                "gap": {"gap_total": 0.062, "gap_math": 0, "gap_code": 0.25, "gap_ml": 0},
                "reasons": [],
            },
        },
        reinforcement_logs={
            "ml_b08": {
                "gap": {"gap_total": 0.062, "gap_math": 0, "gap_code": 0.25, "gap_ml": 0},
            },
        },
    )

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    node_expl = next(item for item in result.node_explanations if item.node_id == "ml_b08")

    assert node_expl.reinforcement_type == "ability_gap"
    assert node_expl.score_breakdown["ability_gap"] > 0
    assert "能力短板补强" in node_expl.reason
    assert "编程实现差距较明显" in node_expl.reason
    assert "能力差距分 0.062" in node_expl.reason
    assert "总分" not in node_expl.reason


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
    assert result.meta is not None
    assert result.meta.provenance.fallback_used is False


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
    assert result.meta is not None
    assert result.meta.provenance.fallback_used is True
    assert "filtered_requires_rev_adj_null" in result.meta.provenance.fallback_reasons
    assert "requires_rev_adj" in result.meta.provenance.live_pack_fields


def test_build_explanation_distinguishes_empty_snapshot_from_fallback():
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
        filtered_requires_rev_adj={},
    )
    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)
    assert result.meta is not None
    assert result.meta.provenance.fallback_used is False
    assert result.dependency_chain_explanations[0].chain_node_ids == ["ml_c05"]


@pytest.mark.parametrize(
    "snapshot_marker,expected_reason,expected_fallback,expected_chain",
    [
        ("missing", "filtered_requires_rev_adj_missing", True, ["ml_a04", "ml_c05"]),
        (None, "filtered_requires_rev_adj_null", True, ["ml_a04", "ml_c05"]),
        ({}, None, False, ["ml_c05"]),
        ({"ml_c05": []}, None, False, ["ml_c05"]),
    ],
)
def test_build_explanation_distinguishes_requires_snapshot_states(
    snapshot_marker,
    expected_reason,
    expected_fallback,
    expected_chain,
):
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
        filtered_requires_rev_adj=snapshot_marker,
    )
    if snapshot_marker == "missing":
        audit.pop("filtered_requires_rev_adj")

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert result.meta is not None
    assert result.meta.provenance.fallback_used is expected_fallback
    assert result.dependency_chain_explanations[0].chain_node_ids == expected_chain
    if expected_reason is None:
        assert result.meta.provenance.fallback_reasons == []
        assert result.meta.provenance.live_pack_fields == []
    else:
        assert expected_reason in result.meta.provenance.fallback_reasons
        assert "requires_rev_adj" in result.meta.provenance.live_pack_fields


def test_build_explanation_populates_phase1_meta_context():
    pack = get_domain_pack_service(force_reload=True)
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.5},
                "reasons": [],
            },
        },
        filtered_requires_rev_adj={"ml_c09": []},
    )

    result = build_explanation(
        audit,
        pack.nodes_by_id,
        pack.requires_rev_adj,
        pack.scoring_config,
        context={
            "plan_version": 3,
            "pack_version": "1.3.0",
            "pack_version_source": "live_pack",
            "project_graph_hash": "graph-hash-1",
        },
    )

    assert result.meta is not None
    assert result.meta.plan_version == 3
    assert result.meta.pack_version == "1.3.0"
    assert result.meta.project_graph_hash == "graph-hash-1"
    assert result.meta.polish.requested is False
    assert "pack_version" in result.meta.provenance.live_pack_fields


def test_readability_overlay_lineage_uses_audit_snapshot_not_live_pack():
    pack = get_domain_pack_service(force_reload=True)
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.1},
                "reasons": [],
            },
        },
        stage_logs={
            "ml_c09": {"assigned_stage": "核心掌握", "reasons": ["category=algorithm"]},
        },
        filtered_requires_rev_adj={"ml_c09": []},
    )
    audit["overlay_lineage"] = {
        "nodes": {
            "ml_c09": {
                "node_snapshot": {"id": "ml_c09", "name": "审计快照节点名"},
                "source_ids": ["snapshot-source"],
            }
        },
        "edges": {},
    }

    live_nodes = {
        node_id: dict(node)
        for node_id, node in pack.nodes_by_id.items()
    }
    live_nodes["ml_c09"]["name"] = "live pack 漂移节点名"
    snapshot_nodes = dict(live_nodes)
    snapshot_nodes["ml_c09"] = {
        **snapshot_nodes["ml_c09"],
        "name": "审计快照节点名",
    }

    result = build_explanation(audit, snapshot_nodes, pack.requires_rev_adj, pack.scoring_config)

    assert result.readability is not None
    assert result.node_explanations[0].node_name == "审计快照节点名"
    assert result.readability.overview_summary.goal_names == ["审计快照节点名"]
    assert result.readability.trace_summary.overlay_lineage_items == [
        {
            "kind": "node",
            "id": "ml_c09",
            "name": "审计快照节点名",
            "source_ids": ["snapshot-source"],
            "validation_status": None,
            "review_status": None,
            "promotion_status": None,
            "confidence": None,
        }
    ]


def test_build_explanation_populates_phase2_readability():
    pack = get_domain_pack_service(force_reload=True)
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_a04": {
                "priority_score": 0.4,
                "goal_relevance": 0.2,
                "gap": {"gap_total": 0.1},
                "reasons": ["依赖优先"],
            },
            "ml_c01": {
                "priority_score": 0.7,
                "goal_relevance": 0.4,
                "gap": {"gap_total": 0.3, "gap_math": 0.1, "gap_code": 0.1, "gap_ml": 0.1},
                "reasons": ["画像补强优先"],
            },
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.2, "gap_math": 0.1, "gap_code": 0.0, "gap_ml": 0.1},
                "reasons": ["目标优先"],
            },
        },
        stage_logs={
            "ml_a04": {"assigned_stage": "基础准备", "reasons": ["category=foundation"]},
            "ml_c01": {"assigned_stage": "基础准备", "reasons": ["category=ml_core"]},
            "ml_c09": {"assigned_stage": "核心掌握", "reasons": ["category=algorithm"]},
        },
        budget_summary={
            "total_hours": 24,
            "weekly_hours": 8,
            "estimated_weeks": 3,
            "status": "tight",
            "suggestion": "时间较紧，建议后续提供压缩版路径",
            "path_mode": "compressed",
        },
        reinforcement_logs={
            "ml_c01": {
                "gap": {"gap_total": 0.3, "gap_math": 0.1, "gap_code": 0.1, "gap_ml": 0.1},
                "reinforce_score": 0.6,
                "reasons": ["补齐基础薄弱项"],
            }
        },
        filtered_requires_rev_adj={
            "ml_c09": ["ml_c01"],
            "ml_c01": ["ml_a04"],
            "ml_a04": [],
        },
    )
    audit["goal_result"].update(
        {
            "goal_text": "理解梯度下降",
            "goal_type": "concept",
            "description": "理解梯度下降核心机制",
            "resolve_source": "template",
            "source_breakdown": {"template": 1.0, "lexical": 0.0, "llm": 0.0},
            "warnings": ["llm_unavailable"],
            "candidate_id": "template:ml-gradient",
            "recommended_candidate_id": "llm:other-candidate",
        }
    )
    audit["path_mode"] = "compressed"
    audit["budget_status"] = "tight"
    audit["closure_ids"] = ["ml_a04", "ml_c01"]
    audit["reinforced_ids"] = ["ml_c01"]
    audit["final_ids"] = ["ml_a04", "ml_c01", "ml_c09"]
    audit["excluded_nodes"] = [
        {"node_id": "ml_d08", "exclusion_reason": "compressed_optional_reinforcement"}
    ]
    audit["pack_version"] = "2026.04"
    audit["project_graph_hash"] = "graph-hash-phase2"
    audit["overlay_lineage"] = {
        "nodes": {
            "ml_c09": {"node_snapshot": {"id": "ml_c09", "name": pack.nodes_by_id["ml_c09"]["name"]}},
            "ml_c01": {"node_snapshot": {"id": "ml_c01", "name": pack.nodes_by_id["ml_c01"]["name"]}},
        },
        "edges": {
            "ml_c01->ml_c09::REQUIRES": {"source": "snapshot"},
        },
    }

    result = build_explanation(
        audit,
        pack.nodes_by_id,
        pack.requires_rev_adj,
        pack.scoring_config,
        context={
            "plan_version": 7,
            "stages": [
                {
                    "stage_index": 0,
                    "stage_name": "基础准备",
                    "tasks": [
                        {"node_id": "ml_a04", "name": pack.nodes_by_id["ml_a04"]["name"], "estimated_hours": 8},
                        {"node_id": "ml_c01", "name": pack.nodes_by_id["ml_c01"]["name"], "estimated_hours": 8},
                    ],
                    "estimated_hours": 16,
                },
                {
                    "stage_index": 1,
                    "stage_name": "核心掌握",
                    "tasks": [
                        {"node_id": "ml_c09", "name": pack.nodes_by_id["ml_c09"]["name"], "estimated_hours": 8},
                    ],
                    "estimated_hours": 8,
                },
            ],
            "total_hours": 24,
            "budget_status": "tight",
            "path_mode": "compressed",
        },
    )

    assert result.readability is not None
    readability = result.readability

    assert readability.overview_summary.node_count == 3
    assert readability.overview_summary.path_mode == "compressed"
    assert readability.overview_summary.goal_names == [pack.nodes_by_id["ml_c09"]["name"]]
    assert any("不会裁剪硬前置依赖" in note for note in readability.overview_summary.notes)

    assert readability.goal_resolution_summary.final_goal_text == "理解梯度下降核心机制"
    assert readability.goal_resolution_summary.resolve_source == "template"
    assert readability.goal_resolution_summary.target_node_ids == ["ml_c09"]
    assert readability.goal_resolution_summary.target_node_names == [pack.nodes_by_id["ml_c09"]["name"]]
    assert readability.goal_resolution_summary.source_breakdown == {
        "template": 1.0,
        "lexical": 0.0,
        "llm": 0.0,
    }

    assert [step.step_id for step in readability.generation_steps] == [
        "goal_resolution",
        "prerequisite_closure",
        "profile_reinforcement",
        "topological_ordering",
        "stage_assignment",
        "time_budget",
    ]

    assert [group.group_id for group in readability.node_groups] == [
        "target",
        "reinforced",
        "prerequisite",
    ]
    groups = {group.group_id: group for group in readability.node_groups}
    assert groups["target"].node_ids == ["ml_c09"]
    assert groups["reinforced"].node_ids == ["ml_c01"]
    assert groups["prerequisite"].node_ids == ["ml_a04"]

    assert readability.ordering_summary.ordered_node_ids == ["ml_a04", "ml_c01", "ml_c09"]
    assert readability.stage_summary.stage_count == 2
    assert readability.budget_summary is not None
    assert "不会裁剪硬前置依赖" in readability.budget_summary.compressed_dependency_note
    assert readability.trace_summary.pack_version == "2026.04"
    assert readability.trace_summary.project_graph_hash == "graph-hash-phase2"
    assert readability.trace_summary.overlay_node_count == 2
    assert readability.trace_summary.overlay_edge_count == 1
    assert {item["kind"] for item in readability.trace_summary.overlay_lineage_items} == {"node", "edge"}

    highlights = {item.key: item for item in readability.audit_highlights}
    assert highlights["dependency_closure"].source == "audit.closure_ids"
    assert highlights["dependency_closure"].value["closure_ids"] == ["ml_a04", "ml_c01"]
    assert highlights["overlay_lineage"].value["lineage_items"] == readability.trace_summary.overlay_lineage_items
    assert "authority_labels" in highlights
    assert "decision_chain" in highlights

    highlight_keys = [item.key for item in readability.audit_highlights]
    assert highlight_keys == [
        "goal_resolution",
        "dependency_closure",
        "profile_reinforcement",
        "ordering",
        "stage_assignment",
        "budget",
        "overlay_lineage",
        "fallback_status",
        "authority_labels",
        "decision_chain",
    ]


def test_readability_dependency_highlight_uses_chain_when_closure_ids_missing():
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
            "ml_c01": {
                "priority_score": 0.6,
                "goal_relevance": 0.4,
                "gap": {"gap_total": 0.5, "gap_math": 0.2, "gap_code": 0.1, "gap_ml": 0.2},
                "reasons": [],
            },
            "ml_c05": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.1},
                "reasons": [],
            },
        },
        reinforcement_logs={
            "ml_c01": {
                "gap": {"gap_total": 0.5, "gap_math": 0.2, "gap_code": 0.1, "gap_ml": 0.2},
                "reinforce_score": 0.7,
                "reasons": ["补齐基础薄弱项"],
            }
        },
        filtered_requires_rev_adj={"ml_c05": ["ml_a04"], "ml_a04": [], "ml_c01": []},
    )
    audit["goal_result"].update({"goal_type": "concept", "resolve_source": "template"})
    audit["closure_ids"] = []
    audit["reinforced_ids"] = ["ml_c01"]

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert result.readability is not None
    highlights = {item.key: item for item in result.readability.audit_highlights}
    assert highlights["dependency_closure"].source == "dependency_chain_explanations"
    assert highlights["dependency_closure"].value["closure_ids"] == ["ml_a04"]


def test_build_explanation_readability_failure_falls_back_to_legacy_blocks(monkeypatch: pytest.MonkeyPatch):
    pack = get_domain_pack_service(force_reload=True)
    audit = _make_audit(
        target_ids=["ml_c09"],
        ordering_logs={
            "ml_c01": {
                "priority_score": 0.7,
                "goal_relevance": 0.4,
                "gap": {"gap_total": 0.3, "gap_math": 0.1, "gap_code": 0.1, "gap_ml": 0.1},
                "reasons": [],
            },
            "ml_c09": {
                "priority_score": 0.9,
                "goal_relevance": 1.0,
                "gap": {"gap_total": 0.1},
                "reasons": [],
            },
        },
        stage_logs={
            "ml_c01": {"assigned_stage": "基础准备", "reasons": ["category=ml_core"]},
            "ml_c09": {"assigned_stage": "核心掌握", "reasons": ["category=algorithm"]},
        },
        budget_summary={
            "total_hours": 8,
            "weekly_hours": 8,
            "estimated_weeks": 1,
            "status": "feasible",
            "suggestion": "当前时间预算可支持完整路径",
        },
        reinforcement_logs={
            "ml_c01": {
                "gap": {"gap_total": 0.3, "gap_math": 0.1, "gap_code": 0.1, "gap_ml": 0.1},
                "reinforce_score": 0.6,
                "reasons": ["补齐基础薄弱项"],
            }
        },
        filtered_requires_rev_adj={"ml_c09": ["ml_c01"], "ml_c01": []},
    )
    audit["goal_result"].update(
        {
            "goal_text": "理解梯度下降",
            "goal_type": "concept",
            "description": "理解梯度下降",
            "resolve_source": "template",
            "source_breakdown": {"template": 1.0},
            "warnings": [],
        }
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("readability exploded")

    monkeypatch.setattr(explanation_service, "_build_explanation_readability", _boom)

    result = build_explanation(audit, pack.nodes_by_id, pack.requires_rev_adj, pack.scoring_config)

    assert len(result.node_explanations) == 2
    assert len(result.ordering_explanations) == 2
    assert len(result.stage_explanations) == 2
    assert result.budget_explanation is not None
    assert len(result.reinforcement_explanations) == 1
    assert len(result.dependency_chain_explanations) == 1
    assert result.readability is None
    assert result.meta is not None
    assert result.meta.provenance.fallback_used is True
    assert "readability_build_failed" in result.meta.provenance.fallback_reasons
