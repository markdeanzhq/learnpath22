"""Neo4j 图谱同步服务。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.db.neo4j import Neo4jDriver
from app.db.seed_graph import seed_graph
from app.services.domain_pack_service import DomainPackService, get_domain_pack_service


class GraphSyncService:
    def __init__(self, driver: Neo4jDriver):
        self.driver = driver

    def _validate_pack(self, pack: DomainPackService) -> None:
        field_errors = pack.validate_fields()
        if field_errors:
            raise ValueError("Domain Pack 字段校验失败: " + "; ".join(field_errors))
        pack.validate_dag()
        manifest_domain = pack.manifest.get("domain")
        if manifest_domain != pack.domain:
            raise ValueError(
                f"Domain Pack manifest domain 不匹配: {manifest_domain} != {pack.domain}"
            )

    def _build_pack_hash(self, pack: DomainPackService) -> str:
        payload = {
            "manifest": pack.manifest,
            "nodes": pack.nodes,
            "requires_edges": pack.requires_edges,
            "related_edges": pack.related_edges,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    async def _get_sync_state(self, domain: str) -> dict[str, str] | None:
        rows = await self.driver.execute_query(
            """
            MATCH (n:KnowledgeNode)
            WHERE n.domain = $domain
            RETURN n.synced_pack_hash AS pack_hash, n.synced_version AS version
            ORDER BY n.synced_at DESC
            LIMIT 1
            """,
            {"domain": domain},
        )
        if not rows:
            return None
        return {
            "pack_hash": rows[0].get("pack_hash") or "",
            "version": rows[0].get("version") or "",
        }

    async def sync_domain_pack(self, domain: str = "machine_learning") -> dict[str, Any]:
        pack = get_domain_pack_service(domain, force_reload=False)
        return await self._sync_pack(pack, force=False)

    async def force_sync_domain_pack(self, domain: str = "machine_learning") -> dict[str, Any]:
        pack = get_domain_pack_service(domain, force_reload=True)
        return await self._sync_pack(pack, force=True)

    async def _sync_pack(self, pack: DomainPackService, force: bool) -> dict[str, Any]:
        self._validate_pack(pack)
        version = str(pack.manifest.get("version", ""))
        if not version:
            raise ValueError(f"Domain Pack 缺少 version: {pack.domain}")
        pack_hash = self._build_pack_hash(pack)
        current_state = await self._get_sync_state(pack.domain)

        if (
            not force
            and current_state is not None
            and current_state["version"] == version
            and current_state["pack_hash"] == pack_hash
        ):
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "synced": False,
                "reason": "unchanged",
                "nodes": len(pack.nodes),
                "edges": len(pack.requires_edges) + len(pack.related_edges),
            }

        result = await seed_graph(
            self.driver,
            domain=pack.domain,
            version=version,
            pack_hash=pack_hash,
            nodes=pack.nodes,
            requires_edges=pack.requires_edges,
            related_edges=pack.related_edges,
        )
        return {
            "domain": pack.domain,
            "version": version,
            "pack_hash": pack_hash,
            "synced": True,
            "forced": force,
            "reason": "forced" if force else "changed",
            "nodes": result["nodes"],
            "edges": result["edges"],
        }


_graph_sync_service: GraphSyncService | None = None


def get_graph_sync_service(driver: Neo4jDriver) -> GraphSyncService:
    global _graph_sync_service
    if _graph_sync_service is None or _graph_sync_service.driver is not driver:
        _graph_sync_service = GraphSyncService(driver)
    return _graph_sync_service
