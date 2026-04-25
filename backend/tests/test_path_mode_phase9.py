from __future__ import annotations

import pytest

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


def _pack():
    return get_domain_pack_service(force_reload=True)


def _assert_topological_order(result, pack) -> None:
    position = {node_id: idx for idx, node_id in enumerate(result["ordered_ids"])}
    for source, targets in pack.requires_adj.items():
        for target in targets:
            if source in position and target in position:
                assert position[source] < position[target]


def test_invalid_path_mode_is_rejected_by_planner():
    with pytest.raises(ValueError, match="INVALID_PATH_MODE"):
        plan_with_profile(
            goal_text="我想系统学习机器学习基础",
            goal_type="domain",
            profile=PROFILE_BEGINNER,
            pack=_pack(),
            path_mode="unknown",
        )


def test_persona_fields_are_audit_only_and_do_not_change_plan_order():
    pack = _pack()
    base_profile = {**PROFILE_BEGINNER, "path_mode_preference": "standard"}
    persona_profile = {
        **base_profile,
        "path_mode_preference": "compressed",
        "persona_label": "时间压缩型学习者",
        "persona_summary": "时间压缩型学习者：用于展示。",
        "persona_evidence": "{}",
    }

    base = plan_with_profile(
        goal_text="理解梯度下降",
        goal_type="concept",
        profile=base_profile,
        pack=pack,
        path_mode="standard",
    )
    with_persona = plan_with_profile(
        goal_text="理解梯度下降",
        goal_type="concept",
        profile=persona_profile,
        pack=pack,
        path_mode="standard",
    )

    assert with_persona["ordered_ids"] == base["ordered_ids"]
    assert with_persona["reinforced_ids"] == base["reinforced_ids"]
    snapshot = with_persona["audit"]["profile_snapshot"]
    assert snapshot["persona_label"] == "时间压缩型学习者"
    assert snapshot["persona_summary"] == "时间压缩型学习者：用于展示。"


def test_compressed_mode_keeps_required_closure_and_prunes_optional_reinforcement():
    pack = _pack()
    standard = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
        path_mode="standard",
    )
    compressed = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=PROFILE_BEGINNER,
        pack=pack,
        path_mode="compressed",
    )

    required_ids = set(compressed["audit"]["closure_ids"]) | set(
        compressed["goal_result"]["target_node_ids"]
    )
    assert required_ids <= set(compressed["ordered_ids"])
    assert set(compressed["ordered_ids"]) <= set(standard["ordered_ids"])
    assert len(compressed["ordered_ids"]) <= len(standard["ordered_ids"])
    assert compressed["path_mode"] == "compressed"
    assert compressed["audit"]["path_mode"] == "compressed"
    assert compressed["audit"]["included_nodes"]
    assert all("exclusion_reason" in item for item in compressed["audit"]["excluded_nodes"])
    _assert_topological_order(compressed, pack)


def test_compressed_mode_reports_over_budget_required_closure_without_pruning_required_nodes():
    pack = _pack()
    profile = {**PROFILE_BEGINNER, "weekly_hours": 1, "deadline_weeks": 1}
    result = plan_with_profile(
        goal_text="我想系统学习机器学习基础",
        goal_type="domain",
        profile=profile,
        pack=pack,
        path_mode="compressed",
    )

    required_ids = set(result["audit"]["closure_ids"]) | set(result["goal_result"]["target_node_ids"])
    assert result["budget_summary"]["status"] == "over_budget_required_closure"
    assert result["audit"]["budget_status"] == "over_budget_required_closure"
    assert required_ids <= set(result["ordered_ids"])
    assert result["budget_summary"]["required_hours"] > result["budget_summary"]["available_hours"]
    _assert_topological_order(result, pack)


@pytest.mark.parametrize("path_mode", ["theory_first", "practice_first"])
def test_theory_and_practice_modes_preserve_existing_plan_shape(path_mode):
    result = plan_with_profile(
        goal_text="理解梯度下降",
        goal_type="concept",
        profile=PROFILE_BEGINNER,
        pack=_pack(),
        path_mode=path_mode,
    )

    assert result["path_mode"] == path_mode
    assert result["goal_result"]["path_mode"] == path_mode
    assert result["audit"]["path_mode"] == path_mode
    assert result["audit"]["ordering_mode"] in {"steady", "practice"}
    assert "stage_plan" in result
    assert "budget_summary" in result
    assert result["node_count"] == len(result["ordered_ids"])
