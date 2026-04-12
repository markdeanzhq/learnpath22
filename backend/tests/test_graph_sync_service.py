"""Graph sync service tests."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.services.graph_sync_service import GraphSyncService


def _pack(*, domain="machine_learning", version="1.0.0", field_errors=None):
    pack = SimpleNamespace(
        domain=domain,
        manifest={"domain": domain, "version": version},
        nodes=[{"id": "ml_c01"}, {"id": "ml_c02"}],
        requires_edges=[{"source": "ml_c01", "target": "ml_c02"}],
        related_edges=[{"source": "ml_c02", "target": "ml_c01"}],
    )
    pack.validate_fields = lambda: field_errors or []
    pack.validate_dag = lambda: None
    return pack


@pytest.mark.asyncio
async def test_sync_domain_pack_returns_unchanged_without_reseeding(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack()
    expected_hash = service._build_pack_hash(pack)

    monkeypatch.setattr("app.services.graph_sync_service.get_domain_pack_service", lambda domain, force_reload=False: pack)
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": expected_hash}),
    )
    seed_graph = AsyncMock()
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": False,
        "reason": "unchanged",
        "nodes": 2,
        "edges": 2,
    }
    service._get_sync_state.assert_awaited_once_with("machine_learning")
    seed_graph.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_domain_pack_seeds_when_pack_changed(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack(version="1.1.0")

    monkeypatch.setattr("app.services.graph_sync_service.get_domain_pack_service", lambda domain, force_reload=False: pack)
    monkeypatch.setattr(
        service,
        "_get_sync_state",
        AsyncMock(return_value={"version": "1.0.0", "pack_hash": "stale"}),
    )
    seed_graph = AsyncMock(return_value={"nodes": 2, "edges": 2})
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
        "nodes": 2,
        "edges": 2,
    }
    seed_graph.assert_awaited_once_with(
        service.driver,
        domain="machine_learning",
        version="1.1.0",
        pack_hash=expected_hash,
        nodes=pack.nodes,
        requires_edges=pack.requires_edges,
        related_edges=pack.related_edges,
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
    seed_graph = AsyncMock(return_value={"nodes": 2, "edges": 2})
    monkeypatch.setattr("app.services.graph_sync_service.seed_graph", seed_graph)

    result = await service.force_sync_domain_pack("machine_learning")

    assert result == {
        "domain": "machine_learning",
        "version": "1.0.0",
        "pack_hash": expected_hash,
        "synced": True,
        "forced": True,
        "reason": "forced",
        "nodes": 2,
        "edges": 2,
    }
    get_domain_pack_service.assert_called_once_with("machine_learning", force_reload=True)
    seed_graph.assert_awaited_once()


@pytest.mark.asyncio
async def test_sync_domain_pack_raises_validation_error(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack(field_errors=["missing category"])

    monkeypatch.setattr("app.services.graph_sync_service.get_domain_pack_service", lambda domain, force_reload=False: pack)

    with pytest.raises(ValueError, match="Domain Pack 字段校验失败: missing category"):
        await service.sync_domain_pack("machine_learning")


@pytest.mark.asyncio
async def test_sync_domain_pack_propagates_seed_graph_runtime_error(monkeypatch):
    service = GraphSyncService(driver=AsyncMock())
    pack = _pack(version="1.1.0")

    monkeypatch.setattr("app.services.graph_sync_service.get_domain_pack_service", lambda domain, force_reload=False: pack)
    monkeypatch.setattr(service, "_get_sync_state", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.graph_sync_service.seed_graph",
        AsyncMock(side_effect=RuntimeError("Neo4j 写事务执行失败")),
    )

    with pytest.raises(RuntimeError, match="Neo4j 写事务执行失败"):
        await service.sync_domain_pack("machine_learning")
