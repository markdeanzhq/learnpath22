"""Graph sync service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.db.neo4j import Neo4jDriverError
from app.services.graph_sync_service import GraphSyncService


STAGES = [
    {
        "id": "stage_foundation",
        "name": "基础准备",
        "order": 1,
        "description": "foundation",
        "category_keys": ["foundation"],
        "node_ids": ["ml_c01"],
    },
    {
        "id": "stage_core",
        "name": "核心掌握",
        "order": 2,
        "description": "core",
        "category_keys": ["algorithm"],
        "node_ids": ["ml_c02"],
    },
]

RESOURCES = [
    {
        "id": "resource_workflow",
        "title": "监督学习建模流程卡片",
        "resource_type": "workflow_guide",
        "description": "workflow",
        "node_ids": ["ml_c01", "ml_c02"],
        "stage_ids": ["stage_core"],
    }
]


def _pack(*, domain="machine_learning", version="1.0.0", field_errors=None):
    pack = SimpleNamespace(
        domain=domain,
        manifest={"domain": domain, "version": version},
        nodes=[
            {
                "id": "ml_c01",
                "name": "监督学习",
                "group": "C",
                "category": "foundation",
                "description": "foundation node",
                "difficulty_final": 2,
                "importance_final": 5,
                "estimated_hours": 6,
                "is_main_path": True,
                "is_foundation": True,
                "is_practice": False,
                "req_math": 2,
                "req_coding": 2,
                "req_ml": 1,
                "theory_weight": 0.7,
                "practice_weight": 0.3,
                "bridge_value": 0.5,
                "optional_level": None,
            },
            {
                "id": "ml_c02",
                "name": "损失函数",
                "group": "C",
                "category": "algorithm",
                "description": "core node",
                "difficulty_final": 3,
                "importance_final": 4,
                "estimated_hours": 4,
                "is_main_path": True,
                "is_foundation": False,
                "is_practice": False,
                "req_math": 2,
                "req_coding": 2,
                "req_ml": 1,
                "theory_weight": 0.6,
                "practice_weight": 0.4,
                "bridge_value": 0.4,
                "optional_level": None,
            },
        ],
        requires_edges=[{"source": "ml_c01", "target": "ml_c02"}],
        related_edges=[{"source": "ml_c02", "target": "ml_c01"}],
        stages=STAGES,
        resources=RESOURCES,
    )
    pack.validate_fields = lambda: field_errors or []
    pack.validate_dag = lambda: None
    return pack


@pytest.mark.asyncio
async def test_get_sync_status_reports_ok_when_pack_and_graph_are_synced(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    monkeypatch.setattr(service, "_is_main_graph_synced", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_is_entity_graph_synced", AsyncMock(return_value=True))

    result = await service.get_sync_status("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "in_sync": True,
        "ready": True,
        "status": "ok",
        "reason": "synced",
        "main_graph_synced": True,
        "entity_graph_synced": True,
        "nodes": 5,
        "edges": 8,
    }


@pytest.mark.asyncio
async def test_get_sync_status_reports_missing_when_domain_pack_not_seeded(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(service, "_get_sync_state", AsyncMock(return_value=None))

    result = await service.get_sync_status("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "in_sync": False,
        "ready": False,
        "status": "missing",
        "reason": "domain_pack_not_seeded",
        "nodes": 5,
        "edges": 8,
    }


@pytest.mark.asyncio
async def test_get_sync_status_reports_stale_when_seed_metadata_differs(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "0.9.0", "pack_hash": "stale"}),
    )

    result = await service.get_sync_status("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "in_sync": False,
        "ready": False,
        "status": "stale",
        "reason": "seed_metadata_stale",
        "seeded_version": "0.9.0",
        "seeded_pack_hash": "stale",
        "nodes": 5,
        "edges": 8,
    }


@pytest.mark.asyncio
async def test_get_sync_status_reports_drifted_when_graph_data_differs(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    monkeypatch.setattr(service, "_is_main_graph_synced", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_is_entity_graph_synced", AsyncMock(return_value=False))

    result = await service.get_sync_status("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "in_sync": False,
        "ready": False,
        "status": "drifted",
        "reason": "graph_data_drifted",
        "main_graph_synced": True,
        "entity_graph_synced": False,
        "nodes": 5,
        "edges": 8,
    }


@pytest.mark.asyncio
async def test_sync_domain_pack_returns_unchanged_without_reseeding(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)
    get_graph_entity_metadata = AsyncMock(
        return_value={
            **service._build_graph_entity_metadata(pack),
            "is_empty": False,
        }
    )

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    main_graph_metadata = AsyncMock(return_value=service._build_main_graph_metadata(pack))
    monkeypatch.setattr(service, "_get_main_graph_metadata", main_graph_metadata)
    monkeypatch.setattr("app.services.graph_sync_service.get_graph_entity_metadata", get_graph_entity_metadata)
    seed_graph = AsyncMock()
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": False,
        "reason": "unchanged",
        "nodes": 5,
        "edges": 8,
    }
    service._get_sync_state.assert_awaited_once_with("machine_learning")
    main_graph_metadata.assert_awaited_once_with("machine_learning")
    get_graph_entity_metadata.assert_awaited_once_with(service.driver, "machine_learning")
    seed_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_domain_pack_reseeds_when_entity_graph_drifted(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)
    drifted_metadata = {
        **service._build_graph_entity_metadata(pack),
        "is_empty": False,
    }
    drifted_metadata["stages"][1]["resource_ids"] = []
    drifted_metadata["resources"][0]["stage_ids"] = []
    drifted_metadata["relationships"]["stage_resources"] = []

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    get_graph_entity_metadata = AsyncMock(return_value=drifted_metadata)
    monkeypatch.setattr("app.services.graph_sync_service.get_graph_entity_metadata", get_graph_entity_metadata)
    main_graph_metadata = AsyncMock(return_value=service._build_main_graph_metadata(pack))
    monkeypatch.setattr(service, "_get_main_graph_metadata", main_graph_metadata)
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    main_graph_metadata.assert_awaited_once_with("machine_learning")
    get_graph_entity_metadata.assert_awaited_once_with(service.driver, "machine_learning")
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )


@pytest.mark.asyncio
async def test_sync_domain_pack_reseeds_when_main_graph_drifted(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)
    drifted_main_graph = service._build_main_graph_metadata(pack)
    drifted_main_graph["relationships"]["requires"] = []

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    main_graph_metadata = AsyncMock(return_value=drifted_main_graph)
    monkeypatch.setattr(service, "_get_main_graph_metadata", main_graph_metadata)
    get_graph_entity_metadata = AsyncMock(
        return_value={
            **service._build_graph_entity_metadata(pack),
            "is_empty": False,
        }
    )
    monkeypatch.setattr("app.services.graph_sync_service.get_graph_entity_metadata", get_graph_entity_metadata)
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    main_graph_metadata.assert_awaited_once_with("machine_learning")
    get_graph_entity_metadata.assert_not_awaited()
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )


@pytest.mark.asyncio
async def test_sync_domain_pack_seeds_when_pack_changed(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack(version="1.1.0")

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": "stale"}),
    )
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")
    expected_hash = service._build_pack_hash(pack)

    assert result == {
        "domain": "machine_learning",
        "version": "1.1.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.1.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )


@pytest.mark.asyncio
async def test_force_sync_domain_pack_reseeds_even_when_pack_unchanged(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    get_domain_pack_service = Mock(return_value=pack)
    monkeypatch.setattr("app.services.graph_sync_service.get_domain_pack_service", get_domain_pack_service)
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.force_sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": True,
        "reason": "forced",
        "nodes": 5,
        "edges": 8,
    }
    get_domain_pack_service.assert_called_once_with("machine_learning", force_reload=True)
    seed_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_domain_pack_raises_validation_error(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack(field_errors=["missing category"])

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )

    with pytest.raises(ValueError, match="Domain Pack 字段校验失败: missing category"):
        await service.sync_domain_pack("machine_learning")


@pytest.mark.asyncio
async def test_sync_domain_pack_propagates_seed_graph_runtime_error(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack(version="1.1.0")

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(service, "_get_sync_state", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.graph_sync_service.seed_graph",
        AsyncMock(side_effect=RuntimeError("Neo4j 写事务执行失败")),
    )

    with pytest.raises(RuntimeError, match="Neo4j 写事务执行失败"):
        await service.sync_domain_pack("machine_learning")


@pytest.mark.asyncio
async def test_sync_domain_pack_reseeds_when_graph_read_fails(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    monkeypatch.setattr(
        service,
        "_is_main_graph_synced",
        AsyncMock(side_effect=Neo4jDriverError("Neo4j 查询执行失败: read failed")),
    )
    entity_graph_check = AsyncMock()
    monkeypatch.setattr(service, "_is_entity_graph_synced", entity_graph_check)
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    entity_graph_check.assert_not_awaited()
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )


@pytest.mark.asyncio
async def test_sync_domain_pack_reseeds_when_entity_graph_read_fails(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    monkeypatch.setattr(service, "_is_main_graph_synced", AsyncMock(return_value=True))
    monkeypatch.setattr(
        service,
        "_is_entity_graph_synced",
        AsyncMock(side_effect=Neo4jDriverError("Neo4j 查询执行失败: boom")),
    )
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )


@pytest.mark.asyncio
async def test_sync_domain_pack_propagates_non_driver_runtime_error_from_graph_check(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    monkeypatch.setattr(service, "_is_main_graph_synced", AsyncMock(side_effect=RuntimeError("bug")))
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    with pytest.raises(RuntimeError, match="bug"):
        await service.sync_domain_pack("machine_learning")

    seed_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_domain_pack_reseeds_when_sync_state_read_fails(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(side_effect=Neo4jDriverError("Neo4j 查询执行失败: state failed")),
    )
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")
    expected_hash = service._build_pack_hash(pack)

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )


@pytest.mark.asyncio
async def test_sync_domain_pack_converges_after_reseeding_duplicate_relationship_drift(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)
    drifted_main_graph = service._build_main_graph_metadata(pack)
    drifted_main_graph["relationships"]["requires"] = [
        drifted_main_graph["relationships"]["requires"][0],
        drifted_main_graph["relationships"]["requires"][0],
    ]
    synced_entity_graph = {
        **service._build_graph_entity_metadata(pack),
        "is_empty": False,
    }

    monkeypatch.setattr(
        "app.services.graph_sync_service.get_domain_pack_service",
        lambda domain, force_reload=False: pack,
    )
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(
            side_effect=[
                {"version": "1.0.0", "pack_hash": expected_hash},
                {"version": "1.0.0", "pack_hash": expected_hash},
            ]
        ),
    )
    main_graph_metadata = AsyncMock(
        side_effect=[
            drifted_main_graph,
            service._build_main_graph_metadata(pack),
        ]
    )
    monkeypatch.setattr(service, "_get_main_graph_metadata", main_graph_metadata)
    get_graph_entity_metadata = AsyncMock(return_value=synced_entity_graph)
    monkeypatch.setattr("app.services.graph_sync_service.get_graph_entity_metadata", get_graph_entity_metadata)
    seed_graph = AsyncMock(return_value={"nodes": 5, "edges": 8})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    changed_result = await service.sync_domain_pack("machine_learning")
    unchanged_result = await service.sync_domain_pack("machine_learning")

    assert changed_result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": False,
        "reason": "changed",
        "nodes": 5,
        "edges": 8,
    }
    assert unchanged_result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": False,
        "reason": "unchanged",
        "nodes": 5,
        "edges": 8,
    }
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.0.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
        stages=pack.stages,
        resources=pack.resources,
    )
    assert get_graph_entity_metadata.await_count == 1


@pytest.mark.asyncio
async def test_main_graph_metadata_deduplicates_duplicate_relationships():
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    pack.requires_edges = [
        {"source": "ml_c01", "target": "ml_c02", "reason": "old"},
        {"source": "ml_c01", "target": "ml_c02", "reason": "same"},
    ]
    pack.related_edges = [
        {"source": "ml_c02", "target": "ml_c01", "reason": "legacy"},
        {"source": "ml_c02", "target": "ml_c01", "reason": "peer"},
    ]
    pack.nodes = [pack.nodes[0], {**pack.nodes[0]}, pack.nodes[1]]

    metadata = service._build_main_graph_metadata(pack)

    assert metadata["nodes"] == [
        {
            "id": "ml_c01",
            "name": "监督学习",
            "group_id": "C",
            "category": "foundation",
            "description": "foundation node",
            "difficulty": 2,
            "importance": 5,
            "estimated_hours": 6,
            "is_main_path": True,
            "is_foundation": True,
            "is_practice": False,
            "req_math": 2,
            "req_coding": 2,
            "req_ml": 1,
            "theory_weight": 0.7,
            "practice_weight": 0.3,
            "bridge_value": 0.5,
            "optional_level": None,
        },
        {
            "id": "ml_c02",
            "name": "损失函数",
            "group_id": "C",
            "category": "algorithm",
            "description": "core node",
            "difficulty": 3,
            "importance": 4,
            "estimated_hours": 4,
            "is_main_path": True,
            "is_foundation": False,
            "is_practice": False,
            "req_math": 2,
            "req_coding": 2,
            "req_ml": 1,
            "theory_weight": 0.6,
            "practice_weight": 0.4,
            "bridge_value": 0.4,
            "optional_level": None,
        },
    ]
    assert metadata["relationships"]["requires"] == [
        {
            "source": "ml_c01",
            "target": "ml_c02",
            "reason": "same",
            "type": "REQUIRES",
        }
    ]
    assert metadata["relationships"]["related"] == [
        {
            "source": "ml_c02",
            "target": "ml_c01",
            "reason": "peer",
            "type": "RELATED_TO",
        }
    ]


@pytest.mark.asyncio
async def test_graph_entity_metadata_deduplicates_stage_node_ids():
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    pack.stages = [
        {**pack.stages[0], "node_ids": ["ml_c01", "ml_c01"]},
        pack.stages[1],
    ]

    metadata = service._build_graph_entity_metadata(pack)

    assert metadata["stages"][0]["node_ids"] == ["ml_c01"]
    assert metadata["relationships"]["stage_nodes"] == [
        {
            "stage_id": "stage_core",
            "node_id": "ml_c02",
            "type": "CONTAINS",
        },
        {
            "stage_id": "stage_foundation",
            "node_id": "ml_c01",
            "type": "CONTAINS",
        },
    ]


@pytest.mark.asyncio
async def test_seed_hash_changes_when_stage_or_resource_data_changes():
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    original_hash = service._build_pack_hash(pack)

    changed_stage_pack = _pack()
    changed_stage_pack.stages = [
        {**stage} if stage["id"] != "stage_core" else {**stage, "description": "updated core"}
        for stage in changed_stage_pack.stages
    ]
    changed_resource_pack = _pack()
    changed_resource_pack.resources = [
        {**resource, "title": "更新后的资源标题"} for resource in changed_resource_pack.resources
    ]

    assert service._build_pack_hash(changed_stage_pack) != original_hash
    assert service._build_pack_hash(changed_resource_pack) != original_hash


@pytest.mark.asyncio
async def test_seed_hash_is_stable_for_semantically_equivalent_ordering_changes():
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    original_hash = service._build_pack_hash(pack)

    reordered_pack = _pack()
    reordered_pack.nodes = list(reversed(reordered_pack.nodes))
    reordered_pack.requires_edges = list(reversed(reordered_pack.requires_edges))
    reordered_pack.related_edges = list(reversed(reordered_pack.related_edges))
    reordered_pack.stages = list(reversed(reordered_pack.stages))
    reordered_pack.resources = list(reversed(reordered_pack.resources))
    reordered_pack.manifest = {
        "version": reordered_pack.manifest["version"],
        "domain": reordered_pack.manifest["domain"],
    }

    assert service._build_pack_hash(reordered_pack) == original_hash
