#!/usr/bin/env python3
"""Apply edge patch to Domain Pack requires_edges.json"""
import json
from pathlib import Path
from typing import Any

EDGE_PATCH_SPEC = {
    "remove": [
        {"source": "ml_c09", "target": "ml_c10"}
    ],
    "add": [
        {"source": "ml_c10", "target": "ml_c09", "reason": "Sigmoid 是逻辑回归的核心激活函数"},
        {"source": "ml_b10", "target": "ml_c01", "reason": "先理解机器学习基本流程，再学习具体算法"},
        {"source": "ml_c01", "target": "ml_c07", "reason": "先见线性回归实例，再讨论过拟合现象"},
        {"source": "ml_c01", "target": "ml_c09", "reason": "逻辑回归建立在线性回归基础之上"},
        {"source": "ml_a06", "target": "ml_a08", "reason": "概率基础是理解随机变量的前提"},
        {"source": "ml_a08", "target": "ml_a09", "reason": "先理解随机变量分布，再学习均值方差"},
        {"source": "ml_a10", "target": "ml_b08", "reason": "数据可视化是数据预处理的前置技能"},
        {"source": "ml_b01", "target": "ml_b02", "reason": "先理解机器学习概念，再区分监督学习"},
        {"source": "ml_b01", "target": "ml_b03", "reason": "先理解机器学习概念，再区分无监督学习"},
        {"source": "ml_b01", "target": "ml_b10", "reason": "先理解机器学习概念，再学习基本流程"},
        {"source": "ml_b05", "target": "ml_b04", "reason": "先理解数据集与样本，再学习特征与标签"},
        {"source": "ml_b08", "target": "ml_b07", "reason": "先掌握数据预处理基础，再系统学习特征工程"},
        {"source": "ml_b09", "target": "ml_c05", "reason": "理解模型参数是学习梯度下降的前提"},
        {"source": "ml_b09", "target": "ml_d05", "reason": "理解超参数是学习交叉验证的前提"},
        {"source": "ml_b07", "target": "ml_e04", "reason": "特征工程基础是标准化实战的前置知识"},
        {"source": "ml_c09", "target": "ml_c12", "reason": "逻辑回归是理解决策边界与阈值的基础"}
    ]
}


def apply_patch(base_edges: list[dict[str, Any]], patch_spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply edge patch: remove, then add, then sort and deduplicate"""
    edges = base_edges.copy()

    # Remove edges
    for remove_edge in patch_spec["remove"]:
        edges = [e for e in edges if not (e["source"] == remove_edge["source"] and e["target"] == remove_edge["target"])]

    # Add edges
    for add_edge in patch_spec["add"]:
        edges.append(add_edge)

    # Deduplicate by (source, target)
    seen = set()
    unique_edges = []
    for edge in edges:
        key = (edge["source"], edge["target"])
        if key not in seen:
            seen.add(key)
            unique_edges.append(edge)

    # Sort by (source, target)
    unique_edges.sort(key=lambda e: (e["source"], e["target"]))

    return unique_edges


def main():
    base_dir = Path(__file__).parent.parent
    edges_file = base_dir / "app" / "domain_packs" / "machine_learning" / "requires_edges.json"

    print(f"Reading {edges_file}")
    with open(edges_file, "r", encoding="utf-8") as f:
        base_edges = json.load(f)

    print(f"Base edge count: {len(base_edges)}")

    print("Applying patch...")
    patched_edges = apply_patch(base_edges, EDGE_PATCH_SPEC)

    print(f"Patched edge count: {len(patched_edges)}")

    # Verify (40 base - 1 remove + 16 add = 55)
    assert len(patched_edges) == 55, f"Expected 55 edges, got {len(patched_edges)}"

    has_ml_c10_to_ml_c09 = any(e["source"] == "ml_c10" and e["target"] == "ml_c09" for e in patched_edges)
    has_ml_c09_to_ml_c12 = any(e["source"] == "ml_c09" and e["target"] == "ml_c12" for e in patched_edges)
    has_ml_c09_to_ml_c10 = any(e["source"] == "ml_c09" and e["target"] == "ml_c10" for e in patched_edges)

    assert has_ml_c10_to_ml_c09, "Missing ml_c10 → ml_c09"
    assert has_ml_c09_to_ml_c12, "Missing ml_c09 → ml_c12"
    assert not has_ml_c09_to_ml_c10, "ml_c09 → ml_c10 should be removed"

    print("✓ Verification passed")

    print(f"Writing {edges_file}")
    with open(edges_file, "w", encoding="utf-8") as f:
        json.dump(patched_edges, f, ensure_ascii=False, indent=2)

    print("✓ Edge patch applied successfully")


if __name__ == "__main__":
    main()
