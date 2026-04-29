"""Graph service read-only entity metadata tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.graph_service import (
    GRAPH_SCOPE_DOMAIN,
    build_graph_entity_metadata_from_pack,
    build_pack_subgraph_elements,
    build_path_graph_elements_from_snapshot,
    build_project_graph_elements,
    clear_pack_graph_elements_cache,
    get_graph_entity_metadata,
)


def test_build_graph_entity_metadata_from_pack_matches_synced_shape():
    pack = SimpleNamespace(
        domain="machine_learning",
        stages=[
            {
                "id": "stage_core",
                "name": "核心掌握",
                "order": 2,
                "description": "core",
                "category_keys": ["algorithm"],
                "node_ids": [],
            },
            {
                "id": "stage_foundation",
                "name": "基础准备",
                "order": 1,
                "description": "foundation",
                "category_keys": ["foundation"],
                "node_ids": ["ml_a02", "ml_a01", "ml_a01"],
            },
        ],
        resources=[
            {
                "id": "resource_foundation_map",
                "title": "机器学习预备知识导图",
                "resource_type": "concept_guide",
                "description": "guide",
                "stage_ids": ["stage_foundation", "stage_foundation"],
                "node_ids": ["ml_a02", "ml_a01"],
            }
        ],
    )

    result = build_graph_entity_metadata_from_pack(pack)

    assert result == {
        "domain": "machine_learning",
        "stages": [
            {
                "id": "stage_foundation",
                "name": "基础准备",
                "order": 1,
                "description": "foundation",
                "category_keys": ["foundation"],
                "node_ids": ["ml_a01", "ml_a02"],
                "resource_ids": ["resource_foundation_map"],
            },
            {
                "id": "stage_core",
                "name": "核心掌握",
                "order": 2,
                "description": "core",
                "category_keys": ["algorithm"],
                "node_ids": [],
                "resource_ids": [],
            },
        ],
        "resources": [
            {
                "id": "resource_foundation_map",
                "title": "机器学习预备知识导图",
                "resource_type": "concept_guide",
                "description": "guide",
                "stage_ids": ["stage_foundation"],
                "node_ids": ["ml_a01", "ml_a02"],
            }
        ],
        "relationships": {
            "stage_sequences": [
                {"source": "stage_foundation", "target": "stage_core", "type": "PRECEDES"}
            ],
            "stage_nodes": [
                {"stage_id": "stage_foundation", "node_id": "ml_a01", "type": "CONTAINS"},
                {"stage_id": "stage_foundation", "node_id": "ml_a02", "type": "CONTAINS"},
            ],
            "stage_resources": [
                {
                    "stage_id": "stage_foundation",
                    "resource_id": "resource_foundation_map",
                    "type": "HAS_RESOURCE",
                }
            ],
            "resource_nodes": [
                {
                    "resource_id": "resource_foundation_map",
                    "node_id": "ml_a01",
                    "type": "COVERS",
                },
                {
                    "resource_id": "resource_foundation_map",
                    "node_id": "ml_a02",
                    "type": "COVERS",
                },
            ],
        },
        "is_empty": False,
    }


def test_build_pack_subgraph_elements_returns_local_induced_graph():
    pack = SimpleNamespace(
        nodes_by_id={
            "ml_a01": {"id": "ml_a01", "name": "线性代数基础", "group": "concept", "category": "foundation"},
            "ml_a02": {"id": "ml_a02", "name": "Python 基础", "group": "concept", "category": "foundation"},
            "ml_a03": {"id": "ml_a03", "name": "概率基础", "group": "concept", "category": "foundation"},
        },
        requires_edges=[
            {"source": "ml_a01", "target": "ml_a02"},
            {"source": "ml_a03", "target": "ml_a02"},
        ],
        related_edges=[{"source": "ml_a02", "target": "ml_a01"}],
    )

    result = build_pack_subgraph_elements(
        pack,
        node_ids=["missing", "ml_a02", "ml_a01", "ml_a02"],
    )

    assert result["scope"] == "path"
    assert result["node_ids"] == ["missing", "ml_a01", "ml_a02"]
    assert result["missing_node_ids"] == ["missing"]
    element_ids = [element["data"]["id"] for element in result["elements"]]
    assert element_ids == ["ml_a01", "ml_a02", "ml_a01->ml_a02::REQUIRES", "ml_a02->ml_a01::RELATED_TO"]


def test_build_project_graph_elements_caches_pack_only_graph_defensively():
    clear_pack_graph_elements_cache()
    pack = SimpleNamespace(
        domain="machine_learning",
        pack_hash="pack-hash-cache-test",
        nodes_by_id={
            "ml_a01": {
                "id": "ml_a01",
                "name": "线性代数基础",
                "group": "concept",
                "category": "foundation",
            }
        },
        requires_edges=[],
        related_edges=[],
    )

    first = build_project_graph_elements(pack, scope=GRAPH_SCOPE_DOMAIN)
    first["elements"][0]["data"]["label"] = "mutated label"
    second = build_project_graph_elements(pack, scope=GRAPH_SCOPE_DOMAIN)

    assert second["elements"][0]["data"]["label"] == "线性代数基础"


@pytest.mark.asyncio
async def test_get_graph_entity_metadata_aggregates_stage_and_resource_relationships():
    driver = AsyncMock()
    driver.execute_query = AsyncMock(
        side_effect=[
            [
                {
                    "s": {
                        "id": "stage_foundation",
                        "name": "基础准备",
                        "order": 1,
                        "description": "foundation",
                        "category_keys": ["foundation"],
                    }
                },
                {
                    "s": {
                        "id": "stage_core",
                        "name": "核心掌握",
                        "order": 2,
                        "description": "core",
                        "category_keys": ["algorithm"],
                    }
                },
            ],
            [
                {
                    "r": {
                        "id": "resource_foundation_map",
                        "title": "机器学习预备知识导图",
                        "resource_type": "concept_guide",
                        "description": "guide",
                    }
                }
            ],
            [{"source": "stage_foundation", "target": "stage_core"}],
            [
                {"stage_id": "stage_foundation", "node_id": "ml_a01"},
                {"stage_id": "stage_foundation", "node_id": "ml_a02"},
            ],
            [{"stage_id": "stage_foundation", "resource_id": "resource_foundation_map"}],
            [
                {"resource_id": "resource_foundation_map", "node_id": "ml_a01"},
                {"resource_id": "resource_foundation_map", "node_id": "ml_a02"},
            ],
        ]
    )

    result = await get_graph_entity_metadata(driver, "machine_learning")

    assert result == {
        "domain": "machine_learning",
        "stages": [
            {
                "id": "stage_foundation",
                "name": "基础准备",
                "order": 1,
                "description": "foundation",
                "category_keys": ["foundation"],
                "node_ids": ["ml_a01", "ml_a02"],
                "resource_ids": ["resource_foundation_map"],
            },
            {
                "id": "stage_core",
                "name": "核心掌握",
                "order": 2,
                "description": "core",
                "category_keys": ["algorithm"],
                "node_ids": [],
                "resource_ids": [],
            },
        ],
        "resources": [
            {
                "id": "resource_foundation_map",
                "title": "机器学习预备知识导图",
                "resource_type": "concept_guide",
                "description": "guide",
                "stage_ids": ["stage_foundation"],
                "node_ids": ["ml_a01", "ml_a02"],
            }
        ],
        "relationships": {
            "stage_sequences": [
                {"source": "stage_foundation", "target": "stage_core", "type": "PRECEDES"}
            ],
            "stage_nodes": [
                {"stage_id": "stage_foundation", "node_id": "ml_a01", "type": "CONTAINS"},
                {"stage_id": "stage_foundation", "node_id": "ml_a02", "type": "CONTAINS"},
            ],
            "stage_resources": [
                {
                    "stage_id": "stage_foundation",
                    "resource_id": "resource_foundation_map",
                    "type": "HAS_RESOURCE",
                }
            ],
            "resource_nodes": [
                {
                    "resource_id": "resource_foundation_map",
                    "node_id": "ml_a01",
                    "type": "COVERS",
                },
                {
                    "resource_id": "resource_foundation_map",
                    "node_id": "ml_a02",
                    "type": "COVERS",
                },
            ],
        },
        "is_empty": False,
    }
    assert driver.execute_query.await_count == 6


def test_build_path_graph_elements_from_snapshot_preserves_overlay_metadata():
    snapshot = SimpleNamespace(
        nodes_by_id={
            "ml_a01": {
                "id": "ml_a01",
                "name": "线性代数基础",
                "group": "concept",
                "category": "foundation",
                "difficulty_final": 1,
                "importance_final": 5,
                "estimated_hours": 3,
            },
            "ml_a02": {
                "id": "ml_a02",
                "name": "Python 基础",
                "group": "concept",
                "category": "foundation",
                "difficulty_final": 1,
                "importance_final": 4,
                "estimated_hours": 4,
            },
            "po:demo:n:1": {
                "id": "po:demo:n:1",
                "name": "补充 Overlay 节点",
                "group": "concept",
                "category": "foundation",
                "difficulty_final": 2,
                "importance_final": 5,
                "estimated_hours": 2,
                "origin": "overlay",
            },
        },
        requires_edges=[
            {"source": "ml_a01", "target": "ml_a02"},
            {
                "source": "ml_a01",
                "target": "po:demo:n:1",
                "type": "REQUIRES",
                "origin": "overlay",
                "overlay_id": "po:demo:e:1",
            },
        ],
        related_edges=[],
        overlay_lineage={
            "nodes": {
                "po:demo:n:1": {
                    "validation_status": "valid",
                    "review_status": "confirmed",
                    "planning_enabled": True,
                    "promotion_status": "not_promoted",
                    "source_ids": ["source-1"],
                    "provenance": {"summary": "overlay summary"},
                    "validation_errors": [],
                    "confidence": 0.93,
                }
            },
            "edges": {
                "po:demo:e:1": {
                    "edge_id": "po:demo:e:1",
                    "validation_status": "valid",
                    "review_status": "confirmed",
                    "planning_enabled": True,
                    "promotion_status": "not_promoted",
                    "source_ids": ["source-1"],
                    "provenance": {"evidence": "source-1"},
                    "validation_errors": [],
                    "confidence": 0.81,
                }
            },
        },
    )

    result = build_path_graph_elements_from_snapshot(
        snapshot,
        node_ids=["po:demo:n:1", "ml_a02", "missing-node", "ml_a01"],
        path_id="path-123",
    )

    assert result["scope"] == "path"
    assert result["path_id"] == "path-123"
    assert result["node_ids"] == ["missing-node", "ml_a01", "ml_a02", "po:demo:n:1"]
    assert result["missing_node_ids"] == ["missing-node"]
    assert result["is_empty"] is False

    overlay_node = next(
        element for element in result["elements"] if element["group"] == "nodes" and element["data"]["id"] == "po:demo:n:1"
    )
    overlay_edge = next(
        element for element in result["elements"] if element["group"] == "edges" and element["data"]["id"] == "po:demo:e:1"
    )

    assert overlay_node["data"]["origin"] == "overlay"
    assert overlay_node["data"]["validation_status"] == "valid"
    assert overlay_node["data"]["review_status"] == "confirmed"
    assert overlay_node["data"]["planning_enabled"] is True
    assert overlay_node["data"]["promotion_status"] == "not_promoted"
    assert overlay_node["data"]["source_ids"] == ["source-1"]
    assert overlay_node["data"]["provenance"] == {"summary": "overlay summary"}
    assert overlay_edge["data"]["origin"] == "overlay"
    assert overlay_edge["data"]["source"] == "ml_a01"
    assert overlay_edge["data"]["target"] == "po:demo:n:1"
    assert overlay_edge["data"]["type"] == "REQUIRES"
    assert overlay_edge["data"]["provenance"] == {"evidence": "source-1"}


def test_build_path_graph_elements_from_snapshot_returns_empty_missing_only_subgraph():
    snapshot = SimpleNamespace(
        nodes_by_id={
            "ml_a01": {
                "id": "ml_a01",
                "name": "线性代数基础",
                "group": "concept",
                "category": "foundation",
            }
        },
        requires_edges=[],
        related_edges=[],
        overlay_lineage={"nodes": {}, "edges": {}},
    )

    result = build_path_graph_elements_from_snapshot(
        snapshot,
        node_ids=["missing-a", "missing-b"],
        path_id="path-404",
    )

    assert result == {
        "scope": "path",
        "path_id": "path-404",
        "elements": [],
        "node_ids": ["missing-a", "missing-b"],
        "missing_node_ids": ["missing-a", "missing-b"],
        "is_empty": True,
        "empty_reason": "path_nodes_missing",
    }
