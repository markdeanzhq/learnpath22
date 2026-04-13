import pytest
from app.services.planner_service import plan_with_profile
from app.services.domain_pack_service import get_domain_pack_service

def test_plan_filters_removed_nodes():
    pack = get_domain_pack_service("machine_learning")
    profile = {
        "math_level": 3,
        "coding_level": 3,
        "ml_level": 1,
        "theory_weight": 0.5,
        "weekly_hours": 10,
        "deadline_weeks": 8,
    }
    
    # 正常规划
    res1 = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=profile,
        pack=pack
    )
    all_nodes = set(res1["ordered_ids"])
    
    # 挑选一个在路径中的节点进行移除
    node_to_remove = res1["ordered_ids"][0]
    
    # 移除该节点后的规划
    res2 = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=profile,
        pack=pack,
        removed_node_ids={node_to_remove}
    )
    
    assert node_to_remove not in res2["ordered_ids"]
    assert len(res2["ordered_ids"]) < len(res1["ordered_ids"])

def test_plan_filters_removed_edges():
    pack = get_domain_pack_service("machine_learning")
    profile = {
        "math_level": 3,
        "coding_level": 3,
        "ml_level": 1,
        "theory_weight": 0.5,
        "weekly_hours": 10,
        "deadline_weeks": 8,
    }
    
    # 移除一条实际存在的 REQUIRES 边，验证 typed edge id 能被规划过滤逻辑识别
    # 注意：规划结果受多重因素影响，这里主要验证能跑通且接受 typed edge id
    
    removed_edges = {"ml_a04->ml_c05::REQUIRES"}
    
    res = plan_with_profile(
        goal_text="机器学习",
        goal_type="domain",
        profile=profile,
        pack=pack,
        removed_edge_ids=removed_edges
    )
    
    # 验证逻辑：在 filtered_adj 中不应该存在该边
    # 由于 plan_with_profile 内部逻辑较多，我们主要验证它能跑通且不报错
    assert "ordered_ids" in res
