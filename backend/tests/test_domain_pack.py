"""Domain Pack 数据校验测试"""
import re

import networkx as nx

from app.planner.closure import get_prerequisite_closure
from app.services.domain_pack_service import get_domain_pack_service


def test_pack_loads_successfully():
    pack = get_domain_pack_service(force_reload=True)
    assert len(pack.nodes) == 47
    assert len(pack.nodes_by_id) == 47
    assert [stage["name"] for stage in pack.stages] == ["基础准备", "核心掌握", "应用突破"]
    assert len(pack.stages_by_id) == 3
    assert len(pack.resources) == 5
    assert len(pack.resources_by_id) == 5


def test_pack_dag_is_acyclic():
    pack = get_domain_pack_service()
    assert pack.validate_dag() is True


def test_pack_node_fields_complete():
    pack = get_domain_pack_service()
    errors = pack.validate_fields()
    assert errors == [], f"字段缺失: {errors}"


def test_pack_requires_edges_reference_valid_nodes():
    pack = get_domain_pack_service()
    for edge in pack.requires_edges:
        assert edge["source"] in pack.nodes_by_id, f"边 source {edge['source']} 不存在"
        assert edge["target"] in pack.nodes_by_id, f"边 target {edge['target']} 不存在"


def test_pack_adjacency_lists_consistent():
    pack = get_domain_pack_service()
    for src, targets in pack.requires_adj.items():
        for tgt in targets:
            assert src in pack.requires_rev_adj[tgt]


def test_pack_goal_templates_have_valid_targets():
    pack = get_domain_pack_service()
    for tmpl in pack.goal_templates:
        for nid in tmpl["target_node_ids"]:
            assert nid in pack.nodes_by_id, f"模板 {tmpl['id']} 引用不存在的节点 {nid}"


def test_pack_stages_and_resources_reference_valid_entities():
    pack = get_domain_pack_service()
    for stage in pack.stages:
        for nid in stage["node_ids"]:
            assert nid in pack.nodes_by_id, f"阶段 {stage['id']} 引用不存在的节点 {nid}"
    for resource in pack.resources:
        for nid in resource["node_ids"]:
            assert nid in pack.nodes_by_id, f"资源 {resource['id']} 引用不存在的节点 {nid}"
        for sid in resource["stage_ids"]:
            assert sid in pack.stages_by_id, f"资源 {resource['id']} 引用不存在的阶段 {sid}"


def test_pack_node_value_ranges():
    pack = get_domain_pack_service()
    for node in pack.nodes:
        assert 1 <= node["difficulty_final"] <= 5, f"{node['id']} difficulty out of range"
        assert 1 <= node["importance_final"] <= 5, f"{node['id']} importance out of range"
        assert node["estimated_hours"] > 0, f"{node['id']} estimated_hours <= 0"
        assert 1 <= node["req_math"] <= 5
        assert 1 <= node["req_coding"] <= 5
        assert 1 <= node["req_ml"] <= 5


def test_edge_count_66():
    pack = get_domain_pack_service(force_reload=True)
    assert len(pack.requires_edges) == 66, f"期望 66 条边，实际 {len(pack.requires_edges)}"


def test_graph_has_no_orphans_after_removing_ml_b03():
    pack = get_domain_pack_service(force_reload=True)
    in_degree = {n["id"]: 0 for n in pack.nodes}
    out_degree = {n["id"]: 0 for n in pack.nodes}

    for edge in pack.requires_edges:
        out_degree[edge["source"]] += 1
        in_degree[edge["target"]] += 1

    orphans = [
        nid for nid in in_degree
        if in_degree[nid] == 0 and out_degree[nid] == 0
    ]
    assert orphans == [], f"检测到孤点节点: {orphans}"


def test_flipped_edge_exists():
    """任务 5.3: 断言 ml_c10→ml_c09 存在，ml_c09→ml_c10 不存在"""
    pack = get_domain_pack_service()
    edges_set = {(e["source"], e["target"]) for e in pack.requires_edges}

    assert ("ml_c10", "ml_c09") in edges_set, "缺少 ml_c10→ml_c09"
    assert ("ml_c09", "ml_c10") not in edges_set, "不应存在 ml_c09→ml_c10"


def test_ml_c12_connected():
    """任务 5.4: 断言 ml_c12 有至少 1 条入边或出边"""
    pack = get_domain_pack_service()
    in_degree = 0
    out_degree = 0

    for edge in pack.requires_edges:
        if edge["source"] == "ml_c12":
            out_degree += 1
        if edge["target"] == "ml_c12":
            in_degree += 1

    assert in_degree + out_degree > 0, "ml_c12 是孤点节点"


def test_manifest_version_semver():
    pack = get_domain_pack_service(force_reload=True)
    assert pack.manifest["version"] == "1.3.0", f"期望版本 1.3.0，实际 {pack.manifest['version']}"
    assert pack.manifest["node_count"] == 47


def test_all_edges_have_chinese_reason():
    """任务 5.6: 断言所有边的 reason 字段非空且包含中文"""
    pack = get_domain_pack_service()
    chinese_pattern = re.compile(r"[\u4e00-\u9fff]")

    for edge in pack.requires_edges:
        assert "reason" in edge, f"边 {edge['source']}→{edge['target']} 缺少 reason 字段"
        assert edge["reason"], f"边 {edge['source']}→{edge['target']} 的 reason 为空"
        assert chinese_pattern.search(edge["reason"]), \
            f"边 {edge['source']}→{edge['target']} 的 reason 不包含中文: {edge['reason']}"


def test_fixed_bridge_edges_exist():
    pack = get_domain_pack_service(force_reload=True)
    edges_set = {(e["source"], e["target"]) for e in pack.requires_edges}
    expected_new_edges = {
        ("ml_b08", "ml_e03"),
        ("ml_e04", "ml_e07"),
        ("ml_a09", "ml_d07"),
        ("ml_d07", "ml_d08"),
        ("ml_c06", "ml_e05"),
        ("ml_c08", "ml_d07"),
        ("ml_c11", "ml_d04"),
        ("ml_c12", "ml_d08"),
        ("ml_d04", "ml_d08"),
        ("ml_e02", "ml_e03"),
        ("ml_e05", "ml_e07"),
        ("ml_e06", "ml_e05"),
    }
    for edge in expected_new_edges:
        assert edge in edges_set, f"缺少固定桥接边: {edge[0]}→{edge[1]}"


def test_ml_b03_removed_from_domain_pack():
    pack = get_domain_pack_service(force_reload=True)
    assert "ml_b03" not in pack.nodes_by_id
    assert all(edge["source"] != "ml_b03" and edge["target"] != "ml_b03" for edge in pack.requires_edges)


def test_static_graph_integrity_covers_dag_duplicates_self_loops_and_refs():
    pack = get_domain_pack_service(force_reload=True)
    result = pack.validate_graph_integrity(strict=True)
    assert result["valid"] is True
    assert result["errors"] == []
    assert result["weak_connected_components"] == 1


def test_static_graph_has_single_weakly_connected_component():
    pack = get_domain_pack_service(force_reload=True)
    graph = nx.DiGraph()
    graph.add_nodes_from(pack.nodes_by_id)
    graph.add_edges_from((edge["source"], edge["target"]) for edge in pack.requires_edges)
    assert nx.number_weakly_connected_components(graph) == 1


def test_domain_ml_full_reverse_closure_covers_all_active_nodes():
    pack = get_domain_pack_service(force_reload=True)
    template = next(t for t in pack.goal_templates if t["id"] == "domain_ml_full")
    closure = set(get_prerequisite_closure(template["target_node_ids"], pack.requires_rev_adj))
    closure.update(template["target_node_ids"])
    assert closure == set(pack.nodes_by_id)
