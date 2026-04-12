"""规划引擎核心测试"""
from app.planner.closure import get_prerequisite_closure, extract_subgraph
from app.planner.scoring import calc_gap, calc_reinforce_score
from app.planner.staging import assign_stage, build_stage_plan
from app.planner.budget import calc_budget_summary
from app.planner.topology import topo_sort_with_profile_priority
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
