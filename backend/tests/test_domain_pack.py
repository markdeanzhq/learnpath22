"""Domain Pack 数据校验测试"""
from app.services.domain_pack_service import get_domain_pack_service


def test_pack_loads_successfully():
    pack = get_domain_pack_service()
    assert len(pack.nodes) == 48
    assert len(pack.nodes_by_id) == 48


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


def test_pack_node_value_ranges():
    pack = get_domain_pack_service()
    for node in pack.nodes:
        assert 1 <= node["difficulty_final"] <= 5, f"{node['id']} difficulty out of range"
        assert 1 <= node["importance_final"] <= 5, f"{node['id']} importance out of range"
        assert node["estimated_hours"] > 0, f"{node['id']} estimated_hours <= 0"
        assert 1 <= node["req_math"] <= 5
        assert 1 <= node["req_coding"] <= 5
        assert 1 <= node["req_ml"] <= 5
