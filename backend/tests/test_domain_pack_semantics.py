from __future__ import annotations

import json
from pathlib import Path

import pytest

import app.services.domain_pack_service as domain_pack_module
from app.services.domain_pack_service import (
    DomainPackService,
    get_domain_pack_registry,
    get_domain_pack_service,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _build_minimal_pack(
    base_dir: Path,
    domain: str,
    *,
    nodes: list[dict],
    goal_templates: list[dict],
    manifest_overrides: dict | None = None,
) -> None:
    pack_dir = base_dir / domain
    pack_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "domain": domain,
        "version": "0.0.1",
        "node_count": len(nodes),
        "stages": ["基础准备"],
        "supported_goal_types": ["domain", "concept", "problem"],
        "default_goal_policy": {
            "by_goal_type": {
                "domain": {
                    "target_node_ids": ["n2"],
                    "mode": "steady",
                    "description": "默认领域目标",
                    "resolve_source": "domain_default",
                }
            }
        },
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)

    _write_json(pack_dir / "manifest.json", manifest)
    _write_json(pack_dir / "nodes.json", nodes)
    _write_json(
        pack_dir / "requires_edges.json",
        [{"source": "n1", "target": "n2", "reason": "基础前置"}],
    )
    _write_json(pack_dir / "related_edges.json", [])
    _write_json(
        pack_dir / "stage_rules.json",
        {
            "stages": ["基础准备"],
            "category_to_stage": {"foundation": "基础准备"},
        },
    )
    _write_json(
        pack_dir / "stages.json",
        [
            {
                "id": "stage_foundation",
                "name": "基础准备",
                "order": 1,
                "description": "基础阶段",
                "category_keys": ["foundation"],
                "node_ids": ["n1", "n2"],
            }
        ],
    )
    _write_json(
        pack_dir / "resources.json",
        [
            {
                "id": "res1",
                "title": "示例资源",
                "resource_type": "article",
                "description": "示例资源描述",
                "node_ids": ["n1"],
                "stage_ids": ["stage_foundation"],
            }
        ],
    )
    _write_json(pack_dir / "goal_templates.json", goal_templates)
    _write_json(pack_dir / "scoring_config.json", {})
    _write_json(pack_dir / "calibration_overrides.json", {"anchors": []})


def _make_node(node_id: str, name: str) -> dict:
    return {
        "id": node_id,
        "name": name,
        "group": "T",
        "category": "foundation",
        "description": f"{name} 描述",
        "difficulty_final": 1,
        "importance_final": 5,
        "estimated_hours": 1,
        "is_main_path": True,
        "is_foundation": True,
        "is_practice": False,
        "req_math": 1,
        "req_coding": 1,
        "req_ml": 1,
        "theory_weight": 0.5,
        "practice_weight": 0.5,
    }


def test_load_normalizes_missing_semantic_fields(tmp_path, monkeypatch):
    domain = "test_semantic_defaults"
    _build_minimal_pack(
        tmp_path,
        domain,
        nodes=[_make_node("n1", "线性代数"), _make_node("n2", "梯度下降")],
        goal_templates=[
            {
                "id": "tmpl1",
                "goal_type": "concept",
                "pattern": ["梯度下降"],
                "target_node_ids": ["n2"],
                "mode": "efficient",
                "description": "理解梯度下降",
            }
        ],
    )

    monkeypatch.setattr(domain_pack_module, "PACK_DIR", tmp_path)

    pack = DomainPackService(domain)
    pack.load()

    assert pack.nodes_by_id["n1"]["aliases"] == []
    assert pack.nodes_by_id["n1"]["keywords"] == []
    assert pack.nodes_by_id["n2"]["aliases"] == []
    assert pack.nodes_by_id["n2"]["keywords"] == []
    assert pack.goal_templates[0]["negative_patterns"] == []
    assert pack.goal_templates[0]["priority"] == 50


@pytest.mark.parametrize(
    ("node_overrides", "template_overrides", "expected_error"),
    [
        ({"aliases": "线代"}, {}, "节点 n1 的 aliases 必须为字符串数组"),
        ({"keywords": 123}, {}, "节点 n1 的 keywords 必须为字符串数组"),
        ({}, {"negative_patterns": "不要这个"}, "模板 tmpl1 的 negative_patterns 必须为字符串数组"),
        ({}, {"priority": 101}, "模板 tmpl1 的 priority 必须在 0 到 100 之间"),
        ({}, {"priority": True}, "模板 tmpl1 的 priority 必须在 0 到 100 之间"),
        ({}, {"priority": False}, "模板 tmpl1 的 priority 必须在 0 到 100 之间"),
    ],
)
def test_load_rejects_invalid_semantic_field_types(
    tmp_path,
    monkeypatch,
    node_overrides,
    template_overrides,
    expected_error,
):
    domain = "test_semantic_invalid"
    node = _make_node("n1", "线性代数")
    node.update(node_overrides)
    second_node = _make_node("n2", "梯度下降")
    template = {
        "id": "tmpl1",
        "goal_type": "concept",
        "pattern": ["梯度下降"],
        "target_node_ids": ["n2"],
        "mode": "efficient",
        "description": "理解梯度下降",
    }
    template.update(template_overrides)
    _build_minimal_pack(
        tmp_path,
        domain,
        nodes=[node, second_node],
        goal_templates=[template],
    )

    monkeypatch.setattr(domain_pack_module, "PACK_DIR", tmp_path)

    pack = DomainPackService(domain)
    with pytest.raises(ValueError, match=expected_error):
        pack.load()


def test_load_rejects_missing_template_required_fields(tmp_path, monkeypatch):
    domain = "test_semantic_template_required"
    _build_minimal_pack(
        tmp_path,
        domain,
        nodes=[_make_node("n1", "线性代数"), _make_node("n2", "梯度下降")],
        goal_templates=[
            {
                "goal_type": "concept",
                "pattern": ["梯度下降"],
                "target_node_ids": ["n2"],
                "mode": "efficient",
                "description": "理解梯度下降",
            }
        ],
    )

    monkeypatch.setattr(domain_pack_module, "PACK_DIR", tmp_path)

    pack = DomainPackService(domain)
    with pytest.raises(ValueError, match=r"模板 \? 缺少字段 id"):
        pack.load()


def test_machine_learning_pack_has_seed_semantic_metadata():
    pack = get_domain_pack_service(force_reload=True)

    logistic = pack.nodes_by_id["ml_c09"]
    gradient = pack.nodes_by_id["ml_c05"]
    domain_full = next(t for t in pack.goal_templates if t["id"] == "domain_ml_full")
    logistic_problem = next(
        t for t in pack.goal_templates if t["id"] == "problem_logistic_classification"
    )

    assert "logistic regression" in logistic["aliases"]
    assert "分类" in logistic["keywords"]
    assert "gradient descent" in gradient["aliases"]
    assert "优化" in gradient["keywords"]
    assert domain_full["priority"] == 40
    assert "逻辑回归为什么能做分类" in domain_full["negative_patterns"]
    assert logistic_problem["priority"] == 90


def test_registry_uses_manifest_driven_domains_and_default_domain():
    registry = get_domain_pack_registry(force_reload=True)

    assert registry.default_domain == "machine_learning"
    assert registry.enabled_domains == {"machine_learning"}


def test_service_cache_invalidates_when_pack_dir_changes(tmp_path, monkeypatch):
    original_pack = get_domain_pack_service(force_reload=True)
    assert original_pack.manifest["version"] == "1.3.0"

    _build_minimal_pack(
        tmp_path,
        "machine_learning",
        nodes=[_make_node("n1", "线性代数"), _make_node("n2", "梯度下降")],
        goal_templates=[
            {
                "id": "tmpl1",
                "goal_type": "concept",
                "pattern": ["梯度下降"],
                "target_node_ids": ["n2"],
                "mode": "efficient",
                "description": "理解梯度下降",
            }
        ],
        manifest_overrides={"version": "9.9.9"},
    )

    monkeypatch.setattr(domain_pack_module, "PACK_DIR", tmp_path)

    reloaded_pack = get_domain_pack_service()

    assert reloaded_pack.manifest["version"] == "9.9.9"
    assert reloaded_pack.domain == "machine_learning"


def test_machine_learning_manifest_declares_supported_goal_types_and_default_goal_policy():
    pack = get_domain_pack_service(force_reload=True)

    assert pack.manifest["supported_goal_types"] == ["domain", "concept", "problem"]
    assert pack.manifest["default_goal_policy"]["by_goal_type"]["domain"] == {
        "target_node_ids": ["ml_c09", "ml_d08", "ml_e03", "ml_e07", "ml_e08"],
        "mode": "steady",
        "description": "系统学习机器学习基础 — 完整三阶段路径",
        "resolve_source": "domain_default",
    }


@pytest.mark.parametrize(
    ("manifest_overrides", "expected_error"),
    [
        ({"supported_goal_types": ["domain", "invalid"]}, "manifest.supported_goal_types 包含不支持的 goal_type: invalid"),
        ({"default_goal_policy": {}}, "manifest.default_goal_policy.by_goal_type 必须为对象"),
        (
            {
                "default_goal_policy": {
                    "by_goal_type": {
                        "domain": {
                            "target_node_ids": ["missing"],
                            "mode": "steady",
                            "description": "默认领域目标",
                            "resolve_source": "domain_default",
                        }
                    }
                }
            },
            "default_goal_policy.domain.target_node_ids 引用不存在的节点 missing",
        ),
        (
            {
                "default_goal_policy": {
                    "by_goal_type": {
                        "domain": {
                            "target_node_ids": ["n2"],
                            "mode": "steady",
                            "description": "默认领域目标",
                        }
                    }
                }
            },
            "default_goal_policy.domain 缺少字段 resolve_source",
        ),
    ],
)
def test_load_rejects_invalid_manifest_contract_fields(
    tmp_path,
    monkeypatch,
    manifest_overrides,
    expected_error,
):
    domain = "test_manifest_contract"
    _build_minimal_pack(
        tmp_path,
        domain,
        nodes=[_make_node("n1", "线性代数"), _make_node("n2", "梯度下降")],
        goal_templates=[
            {
                "id": "tmpl1",
                "goal_type": "concept",
                "pattern": ["梯度下降"],
                "target_node_ids": ["n2"],
                "mode": "efficient",
                "description": "理解梯度下降",
            }
        ],
        manifest_overrides=manifest_overrides,
    )

    monkeypatch.setattr(domain_pack_module, "PACK_DIR", tmp_path)

    pack = DomainPackService(domain)
    with pytest.raises(ValueError, match=expected_error):
        pack.load()
