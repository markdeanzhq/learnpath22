from app.services.domain_pack_service import get_domain_pack_service
from app.services.planner_service import plan_with_profile


PROFILE = {
    "math_level": 3,
    "coding_level": 3,
    "ml_level": 1,
    "theory_weight": 0.5,
    "weekly_hours": 10,
    "deadline_weeks": 8,
}

def test_plan_filters_removed_nodes():
    pack = get_domain_pack_service("machine_learning", force_reload=True)

    res1 = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE,
        pack=pack,
    )
    node_to_remove = res1["ordered_ids"][0]

    res2 = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE,
        pack=pack,
        removed_node_ids={node_to_remove},
    )

    assert node_to_remove not in res2["ordered_ids"]
    assert len(res2["ordered_ids"]) < len(res1["ordered_ids"])
    assert node_to_remove in res2["audit"]["removed_node_ids"]
    assert node_to_remove not in res2["audit"]["filtered_requires_adj"]
    assert node_to_remove not in res2["audit"]["filtered_requires_rev_adj"]


def test_plan_audit_contains_filtered_snapshot():
    pack = get_domain_pack_service("machine_learning", force_reload=True)
    removed_nodes = {"ml_e08"}
    removed_edges = {"ml_a04->ml_c05::REQUIRES"}

    res = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE,
        pack=pack,
        removed_node_ids=removed_nodes,
        removed_edge_ids=removed_edges,
    )

    audit = res["audit"]
    assert audit["pack_version"] == "1.3.0"
    assert audit["removed_node_ids"] == ["ml_e08"]
    assert audit["removed_edge_ids"] == ["ml_a04->ml_c05::REQUIRES"]
    assert "filtered_requires_adj" in audit
    assert "filtered_requires_rev_adj" in audit
    assert audit["closure_ids"]
    assert isinstance(audit["reinforced_ids"], list)
    assert sorted(audit["final_ids"]) == sorted(res["ordered_ids"])
    assert "ml_e08" not in audit["filtered_requires_adj"]
    assert "ml_e08" not in audit["filtered_requires_rev_adj"]
    assert "ml_c05" not in audit["filtered_requires_adj"].get("ml_a04", [])
    assert "ml_a04" not in audit["filtered_requires_rev_adj"].get("ml_c05", [])
