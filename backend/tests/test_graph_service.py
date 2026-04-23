"""Graph service read-only entity metadata tests."""

from unittest.mock import AsyncMock

import pytest

from app.services.graph_service import get_graph_entity_metadata


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
