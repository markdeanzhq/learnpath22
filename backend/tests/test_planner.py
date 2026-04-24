"""规划引擎核心测试"""
from copy import deepcopy

import pytest

from app.planner.closure import get_prerequisite_closure, extract_subgraph
from app.planner.scoring import calc_gap, calc_reinforce_score
from app.planner.staging import assign_stage, build_stage_plan
from app.planner.budget import calc_budget_summary
from app.planner.topology import topo_sort_with_profile_priority
import app.services.planner_service as planner_service_module
from app.services.domain_pack_service import get_domain_pack_service
from app.services.planner_service import plan_with_profile


PROFILE_BEGINNER = {
    "math_level": 2,
    "coding_level": 2,
    "ml_level": 1,
    "theory_weight": 0.6,
    "weekly_hours": 10,
    "deadline_weeks": 12,
}


def _get_pack():
    return get_domain_pack_service()


# --- closure ---

def test_prerequisite_closure_returns_list():
    pack = _get_pack()
    closure = get_prerequisite_closure(["ml_c09"], pack.requires_rev_adj)
    assert isinstance(closure, list)
    assert "ml_c09" not in closure


def test_closure_includes_transitive_deps():
    pack = _get_pack()
    closure = get_prerequisite_closure(["ml_c09"], pack.requires_rev_adj)
    assert len(closure) >= 1


def test_extract_subgraph_valid():
    pack = _get_pack()
    closure = get_prerequisite_closure(["ml_c09"], pack.requires_rev_adj)
    all_ids = closure + ["ml_c09"]
    sub_adj, indegree = extract_subgraph(all_ids, dict(pack.requires_adj))
    assert set(indegree.keys()) == set(all_ids)
    assert all(v >= 0 for v in indegree.values())


# --- scoring ---

def test_calc_gap_beginner():
    node = {"req_math": 4, "req_coding": 3, "req_ml": 3}
    gap = calc_gap(node, PROFILE_BEGINNER)
    assert gap["gap_total"] > 0
    assert 0 <= gap["gap_math"] <= 1
    assert 0 <= gap["gap_code"] <= 1
    assert 0 <= gap["gap_ml"] <= 1


def test_calc_gap_expert():
    node = {"req_math": 1, "req_coding": 1, "req_ml": 1}
    profile = {"math_level": 5, "coding_level": 5, "ml_level": 5}
    gap = calc_gap(node, profile)
    assert gap["gap_total"] == 0


# --- staging ---

def test_assign_stage_foundation():
    node = {"category": "foundation"}
    assert assign_stage(node, "domain") == "基础准备"


def test_assign_stage_algorithm():
    node = {"category": "algorithm"}
    assert assign_stage(node, "domain") == "核心掌握"


def test_assign_stage_practice():
    node = {"category": "practice"}
    assert assign_stage(node, "domain") == "应用突破"


# --- budget ---

def test_budget_feasible():
    result = calc_budget_summary(
        {"weekly_hours": 10, "deadline_weeks": 12}, 80.0
    )
    assert result["status"] == "feasible"
    assert result["available_hours"] == 120.0


def test_budget_tight():
    result = calc_budget_summary(
        {"weekly_hours": 8, "deadline_weeks": 10}, 100.0
    )
    assert result["status"] == "tight"


def test_budget_insufficient():
    result = calc_budget_summary(
        {"weekly_hours": 5, "deadline_weeks": 4}, 100.0
    )
    assert result["status"] == "insufficient"


# --- full pipeline ---

def test_plan_domain_goal_full_pipeline():
    """场景A: 领域型目标完整规划"""
    pack = _get_pack()
    result = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )
    assert "stage_plan" in result
    assert "audit" in result
    assert "total_hours" in result
    assert result["node_count"] > 0
    stages = result["stage_plan"]
    assert "基础准备" in stages
    assert "核心掌握" in stages
    assert "应用突破" in stages
    all_tasks = []
    for tasks in stages.values():
        all_tasks.extend(tasks)
    assert len(all_tasks) == result["node_count"]


def test_reinforced_nodes_include_their_prerequisites_in_domain_goal():
    pack = _get_pack()
    result = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )

    ordered_ids = result["ordered_ids"]
    assert "ml_b08" in ordered_ids
    assert "ml_a10" in ordered_ids
    assert ordered_ids.index("ml_a10") < ordered_ids.index("ml_b08")


def test_plan_with_confirmed_goal_result_skips_legacy_resolution():
    pack = _get_pack()
    confirmed_goal_result = {
        "goal_text": "已确认目标",
        "goal_type": "concept",
        "target_node_ids": ["ml_c09"],
        "mode": "steady",
        "description": "已确认候选",
        "template_id": "confirmed-template",
        "resolve_source": "confirmed",
        "candidate_id": "cand_confirmed",
        "selected_candidate_id": "cand_confirmed",
        "recommended_candidate_id": "cand_confirmed",
        "auto_detected_goal_type": "domain",
        "effective_goal_type": "concept",
        "goal_type_source": "confirmed_resolution",
        "source_breakdown": {"template": 1.0},
        "score_breakdown": {},
        "warnings": [],
    }

    with pytest.MonkeyPatch.context() as mp:
        def _boom(**kwargs):
            raise AssertionError("resolve_goal should not be called")

        mp.setattr("app.services.planner_service.resolve_goal", _boom)
        result = plan_with_profile(
            goal_text="会误导旧解析器的文本",
            goal_type="domain",
            profile=PROFILE_BEGINNER,
            pack=pack,
            confirmed_goal_result=confirmed_goal_result,
        )

    assert result["goal_result"]["goal_text"] == "已确认目标"
    assert result["goal_result"]["goal_type"] == "concept"
    assert result["goal_result"]["target_node_ids"] == ["ml_c09"]


def test_plan_with_confirmed_goal_result_preserves_confirmed_and_effective_targets():
    pack = _get_pack()
    confirmed_goal_result = {
        "goal_text": "已确认目标",
        "goal_type": "concept",
        "target_node_ids": ["ml_c09", "ml_d08"],
        "confirmed_target_node_ids": ["ml_c09", "ml_d08"],
        "effective_target_node_ids": ["ml_c09", "ml_d08"],
        "mode": "steady",
        "description": "已确认候选",
        "template_id": "confirmed-template",
        "resolve_source": "confirmed",
        "candidate_id": "cand_confirmed",
        "selected_candidate_id": "cand_confirmed",
        "recommended_candidate_id": "cand_confirmed",
        "auto_detected_goal_type": "domain",
        "effective_goal_type": "concept",
        "goal_type_source": "confirmed_resolution",
        "source_breakdown": {"template": 1.0},
        "score_breakdown": {},
        "warnings": [],
    }

    result = plan_with_profile(
        goal_text="会误导旧解析器的文本",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
        removed_node_ids={"ml_d08"},
        confirmed_goal_result=confirmed_goal_result,
    )

    assert result["goal_result"]["confirmed_target_node_ids"] == ["ml_c09", "ml_d08"]
    assert result["goal_result"]["effective_target_node_ids"] == ["ml_c09"]
    assert result["goal_result"]["target_node_ids"] == ["ml_c09"]


def test_plan_with_confirmed_goal_result_does_not_fallback_when_all_targets_removed():
    pack = _get_pack()
    confirmed_goal_result = {
        "goal_text": "已确认目标",
        "goal_type": "concept",
        "target_node_ids": ["ml_b02"],
        "confirmed_target_node_ids": ["ml_b02"],
        "effective_target_node_ids": ["ml_b02"],
        "mode": "steady",
        "description": "已确认候选",
        "template_id": "confirmed-template",
        "resolve_source": "confirmed",
        "candidate_id": "cand_confirmed",
        "selected_candidate_id": "cand_confirmed",
        "recommended_candidate_id": "cand_confirmed",
        "auto_detected_goal_type": "domain",
        "effective_goal_type": "concept",
        "goal_type_source": "confirmed_resolution",
        "source_breakdown": {"template": 1.0},
        "score_breakdown": {},
        "warnings": [],
    }

    result = plan_with_profile(
        goal_text="会误导旧解析器的文本",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
        removed_node_ids={"ml_b02"},
        confirmed_goal_result=confirmed_goal_result,
    )

    assert result["goal_result"]["confirmed_target_node_ids"] == ["ml_b02"]
    assert result["goal_result"]["effective_target_node_ids"] == []
    assert result["goal_result"]["target_node_ids"] == []


def test_plan_with_profile_uses_pack_default_policy_for_legacy_empty_result():
    pack = _get_pack()

    def _fake_resolve_goal(**kwargs):
        return {
            "goal_text": kwargs["goal_text"],
            "goal_type": "domain",
            "target_node_ids": ["ml_e07"],
            "confirmed_target_node_ids": ["ml_e07"],
            "effective_target_node_ids": ["ml_e07"],
            "mode": "steady",
            "description": "默认策略命中",
            "template_id": None,
            "resolve_source": "domain_default",
            "candidate_id": "legacy-default",
            "recommended_candidate_id": None,
            "auto_detected_goal_type": "domain",
            "effective_goal_type": "domain",
            "goal_type_source": "auto_detected",
            "source_breakdown": {},
            "score_breakdown": {},
            "warnings": ["empty_candidates"],
        }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(planner_service_module, "resolve_goal", _fake_resolve_goal)
        result = plan_with_profile(
            goal_text="完全无匹配目标",
            goal_type="domain",
            profile=PROFILE_BEGINNER,
            pack=pack,
        )

    assert result["goal_result"]["resolve_source"] == "domain_default"
    assert result["goal_result"]["target_node_ids"] == ["ml_e07"]
    assert result["goal_result"]["effective_target_node_ids"] == ["ml_e07"]


def test_plan_with_profile_raises_when_legacy_default_targets_removed():
    pack = _get_pack()

    def _fake_resolve_goal(**kwargs):
        return {
            "goal_text": kwargs["goal_text"],
            "goal_type": "domain",
            "target_node_ids": ["ml_e07"],
            "confirmed_target_node_ids": ["ml_e07"],
            "effective_target_node_ids": ["ml_e07"],
            "mode": "steady",
            "description": "默认策略命中",
            "template_id": None,
            "resolve_source": "domain_default",
            "candidate_id": "legacy-default",
            "recommended_candidate_id": None,
            "auto_detected_goal_type": "domain",
            "effective_goal_type": "domain",
            "goal_type_source": "auto_detected",
            "source_breakdown": {},
            "score_breakdown": {},
            "warnings": ["empty_candidates"],
        }

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(planner_service_module, "resolve_goal", _fake_resolve_goal)
        with pytest.raises(planner_service_module.UnsupportedGoalTypeError, match="No effective target nodes available"):
            plan_with_profile(
                goal_text="完全无匹配目标",
                goal_type="domain",
                profile=PROFILE_BEGINNER,
                pack=pack,
                removed_node_ids={"ml_e07"},
            )


def test_plan_problem_goal():
    """场景B: 问题型目标"""
    pack = _get_pack()
    result = plan_with_profile(
        goal_text="我想搞懂逻辑回归为什么能做分类",
        goal_type="problem",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )
    assert result["node_count"] >= 1
    assert result["budget_summary"]["status"] in ("feasible", "tight", "insufficient")


def test_plan_concept_goal():
    """场景C: 概念型目标"""
    pack = _get_pack()
    result = plan_with_profile(
        goal_text="理解梯度下降",
        goal_type="concept",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )
    assert result["node_count"] >= 1


def test_plan_produces_valid_task_fields():
    """验证任务字段完整性"""
    pack = _get_pack()
    result = plan_with_profile(
        goal_text="系统学习机器学习",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )
    for stage_name, tasks in result["stage_plan"].items():
        for task in tasks:
            assert "node_id" in task
            assert "name" in task
            assert "difficulty" in task
            assert "importance" in task
            assert "estimated_hours" in task
            assert "order_in_stage" in task


def test_stage_and_resource_entities_do_not_change_domain_plan_semantics():
    pack = _get_pack()
    baseline = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )

    mutated_pack = deepcopy(pack)
    mutated_pack.stages.append(
        {
            "id": "stage_extra",
            "name": "额外阶段",
            "order": 99,
            "description": "should not affect planner",
            "category_keys": ["foundation"],
            "node_ids": ["ml_a01"],
        }
    )
    mutated_pack.stages_by_id["stage_extra"] = mutated_pack.stages[-1]
    mutated_pack.resources.append(
        {
            "id": "resource_extra",
            "title": "额外资源",
            "resource_type": "article",
            "description": "should not affect planner",
            "node_ids": ["ml_a01"],
            "stage_ids": ["stage_extra"],
        }
    )
    mutated_pack.resources_by_id["resource_extra"] = mutated_pack.resources[-1]

    candidate = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=mutated_pack,
    )

    assert candidate["ordered_ids"] == baseline["ordered_ids"]
    assert candidate["reinforced_ids"] == baseline["reinforced_ids"]
    assert candidate["stage_plan"] == baseline["stage_plan"]
    assert candidate["budget_summary"] == baseline["budget_summary"]
    assert candidate["total_hours"] == baseline["total_hours"]
    assert candidate["node_count"] == baseline["node_count"]
    assert candidate["audit"]["goal_result"] == baseline["audit"]["goal_result"]
    assert candidate["audit"]["ordering_logs"] == baseline["audit"]["ordering_logs"]
    assert candidate["audit"]["stage_logs"] == baseline["audit"]["stage_logs"]


@pytest.mark.parametrize(
    ("goal_text", "goal_type"),
    [
        ("我想系统学习机器学习基础", "domain"),
        ("我想搞懂逻辑回归为什么能做分类", "problem"),
        ("理解梯度下降", "concept"),
    ],
)
def test_stage_and_resource_entities_do_not_change_goal_resolution(goal_text, goal_type):
    pack = _get_pack()
    baseline = plan_with_profile(
        goal_text=goal_text,
        goal_type=goal_type,
        profile=PROFILE_BEGINNER,
        pack=pack,
    )

    mutated_pack = deepcopy(pack)
    mutated_pack.stages[0]["node_ids"] = list(reversed(mutated_pack.stages[0]["node_ids"]))
    mutated_pack.resources = mutated_pack.resources + [
        {
            "id": "resource_reference_only",
            "title": "仅验证资源",
            "resource_type": "book",
            "description": "planner should ignore resources",
            "node_ids": [baseline["ordered_ids"][0]],
            "stage_ids": [mutated_pack.stages[0]["id"]],
        }
    ]
    mutated_pack.resources_by_id["resource_reference_only"] = mutated_pack.resources[-1]

    candidate = plan_with_profile(
        goal_text=goal_text,
        goal_type=goal_type,
        profile=PROFILE_BEGINNER,
        pack=mutated_pack,
    )

    assert candidate["goal_result"] == baseline["goal_result"]
    assert candidate["ordered_ids"] == baseline["ordered_ids"]
    assert candidate["stage_plan"] == baseline["stage_plan"]


def test_topology_tie_breaks_ready_nodes_by_node_id():
    nodes_by_id = {
        "ml_b": {
            "importance_final": 3,
            "difficulty_final": 3,
            "estimated_hours": 2,
            "theory_weight": 0.5,
            "practice_weight": 0.5,
            "req_math": 1,
            "req_coding": 1,
            "req_ml": 1,
        },
        "ml_a": {
            "importance_final": 3,
            "difficulty_final": 3,
            "estimated_hours": 2,
            "theory_weight": 0.5,
            "practice_weight": 0.5,
            "req_math": 1,
            "req_coding": 1,
            "req_ml": 1,
        },
        "ml_c": {
            "importance_final": 3,
            "difficulty_final": 3,
            "estimated_hours": 2,
            "theory_weight": 0.5,
            "practice_weight": 0.5,
            "req_math": 1,
            "req_coding": 1,
            "req_ml": 1,
        },
    }
    ordered_ids, _ = topo_sort_with_profile_priority(
        sub_adj={"ml_b": ["ml_c"], "ml_a": ["ml_c"]},
        indegree={"ml_b": 0, "ml_a": 0, "ml_c": 2},
        nodes_by_id=nodes_by_id,
        profile=PROFILE_BEGINNER,
        goal_relevance_map={"ml_b": 0.5, "ml_a": 0.5, "ml_c": 1.0},
        mode="steady",
    )

    assert ordered_ids == ["ml_a", "ml_b", "ml_c"]


@pytest.mark.parametrize(
    ("goal_text", "goal_type"),
    [
        ("我想系统学习机器学习基础", "domain"),
        ("我想搞懂逻辑回归为什么能做分类", "problem"),
        ("理解梯度下降", "concept"),
    ],
)
def test_plan_order_is_stable_across_repeated_runs(goal_text, goal_type):
    pack = _get_pack()
    first = plan_with_profile(
        goal_text=goal_text,
        goal_type=goal_type,
        profile=PROFILE_BEGINNER,
        pack=pack,
    )
    second = plan_with_profile(
        goal_text=goal_text,
        goal_type=goal_type,
        profile=PROFILE_BEGINNER,
        pack=pack,
    )

    assert first["ordered_ids"] == second["ordered_ids"]
    assert first["stage_plan"] == second["stage_plan"]
    assert first["audit"]["ordering_logs"] == second["audit"]["ordering_logs"]


def test_plan_order_is_stable_when_pack_inputs_are_reordered():
    pack = _get_pack()
    baseline = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
    )

    mutated_pack = deepcopy(pack)
    mutated_pack.requires_adj = {
        src: list(reversed(tgts))
        for src, tgts in reversed(list(mutated_pack.requires_adj.items()))
    }
    mutated_pack.requires_rev_adj = {
        tgt: list(reversed(srcs))
        for tgt, srcs in reversed(list(mutated_pack.requires_rev_adj.items()))
    }
    mutated_pack.nodes_by_id = dict(reversed(list(mutated_pack.nodes_by_id.items())))

    candidate = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=mutated_pack,
    )

    assert candidate["ordered_ids"] == baseline["ordered_ids"]
    assert candidate["reinforced_ids"] == baseline["reinforced_ids"]
    assert candidate["stage_plan"] == baseline["stage_plan"]
    assert candidate["audit"]["ordering_logs"] == baseline["audit"]["ordering_logs"]
