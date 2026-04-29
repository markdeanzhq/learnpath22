"""Neo4j 图谱同步服务。"""
from __future__ import annotations

from typing import Any

from app.db.neo4j import Neo4jDriver, Neo4jDriverError
from app.db.seed_graph import seed_graph
from app.services.domain_pack_service import (
    DomainPackService,
    build_canonical_pack_hash,
    get_domain_pack_registry,
    get_domain_pack_service,
)
from app.services.graph_service import (
    build_graph_entity_metadata_from_pack,
    get_graph_entity_metadata,
)


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
        return build_canonical_pack_hash(pack)

    def _build_pack_counts(self, pack: DomainPackService) -> dict[str, int]:
        return {
            "nodes": len(pack.nodes) + len(pack.stages) + len(pack.resources),
            "edges": (
                len(pack.requires_edges)
                + len(pack.related_edges)
                + max(len(pack.stages) - 1, 0)
                + sum(len(stage.get("node_ids", [])) for stage in pack.stages)
                + sum(len(resource.get("stage_ids", [])) for resource in pack.resources)
                + sum(len(resource.get("node_ids", [])) for resource in pack.resources)
            ),
        }

    def _build_graph_entity_metadata(self, pack: DomainPackService) -> dict[str, Any]:
        return build_graph_entity_metadata_from_pack(pack, include_empty=False)

    def _build_main_graph_metadata(self, pack: DomainPackService) -> dict[str, Any]:
        node_records = {
            node["id"]: {
                "id": node["id"],
                "name": node["name"],
                "group_id": node["group"],
                "category": node["category"],
                "description": node.get("description", ""),
                "difficulty": node["difficulty_final"],
                "importance": node["importance_final"],
                "estimated_hours": node["estimated_hours"],
                "is_main_path": node.get("is_main_path", False),
                "is_foundation": node.get("is_foundation", False),
                "is_practice": node.get("is_practice", False),
                "req_math": node.get("req_math", 1),
                "req_coding": node.get("req_coding", 1),
                "req_ml": node.get("req_ml", 1),
                "theory_weight": node.get("theory_weight"),
                "practice_weight": node.get("practice_weight"),
                "bridge_value": node.get("bridge_value"),
                "optional_level": node.get("optional_level"),
            }
            for node in pack.nodes
        }
        nodes = [node_records[node_id] for node_id in sorted(node_records)]
        requires_by_pair: dict[tuple[str, str], dict[str, str]] = {}
        for edge in pack.requires_edges:
            requires_by_pair[(edge["source"], edge["target"])] = {
                "source": edge["source"],
                "target": edge["target"],
                "reason": edge.get("reason", ""),
                "type": "REQUIRES",
            }
        related_by_pair: dict[tuple[str, str], dict[str, str]] = {}
        for edge in pack.related_edges:
            related_by_pair[(edge["source"], edge["target"])] = {
                "source": edge["source"],
                "target": edge["target"],
                "reason": edge.get("reason", ""),
                "type": "RELATED_TO",
            }
        return {
            "domain": pack.domain,
            "nodes": nodes,
            "relationships": {
                "requires": sorted(
                    requires_by_pair.values(),
                    key=lambda edge: (edge["source"], edge["target"], edge["reason"]),
                ),
                "related": sorted(
                    related_by_pair.values(),
                    key=lambda edge: (edge["source"], edge["target"], edge["reason"]),
                ),
            },
        }

    async def _get_main_graph_metadata(self, domain: str) -> dict[str, Any]:
        nodes_data = await self.driver.execute_query(
            "MATCH (n:KnowledgeNode) WHERE n.domain = $domain RETURN n ORDER BY n.id",
            {"domain": domain},
        )
        requires_data = await self.driver.execute_query(
            "MATCH (a:KnowledgeNode)-[r:REQUIRES]->(b:KnowledgeNode) "
            "WHERE a.domain = $domain AND b.domain = $domain "
            "RETURN a.id AS source, b.id AS target, coalesce(r.reason, '') AS reason "
            "ORDER BY source, target, reason",
            {"domain": domain},
        )
        related_data = await self.driver.execute_query(
            "MATCH (a:KnowledgeNode)-[r:RELATED_TO]->(b:KnowledgeNode) "
            "WHERE a.domain = $domain AND b.domain = $domain "
            "RETURN a.id AS source, b.id AS target, coalesce(r.reason, '') AS reason "
            "ORDER BY source, target, reason",
            {"domain": domain},
        )
        return {
            "domain": domain,
            "nodes": [
                {
                    "id": record["n"].get("id"),
                    "name": record["n"].get("name"),
                    "group_id": record["n"].get("group_id"),
                    "category": record["n"].get("category"),
                    "description": record["n"].get("description", ""),
                    "difficulty": record["n"].get("difficulty"),
                    "importance": record["n"].get("importance"),
                    "estimated_hours": record["n"].get("estimated_hours"),
                    "is_main_path": record["n"].get("is_main_path", False),
                    "is_foundation": record["n"].get("is_foundation", False),
                    "is_practice": record["n"].get("is_practice", False),
                    "req_math": record["n"].get("req_math", 1),
                    "req_coding": record["n"].get("req_coding", 1),
                    "req_ml": record["n"].get("req_ml", 1),
                    "theory_weight": record["n"].get("theory_weight"),
                    "practice_weight": record["n"].get("practice_weight"),
                    "bridge_value": record["n"].get("bridge_value"),
                    "optional_level": record["n"].get("optional_level"),
                }
                for record in nodes_data
            ],
            "relationships": {
                "requires": [
                    {
                        "source": record["source"],
                        "target": record["target"],
                        "reason": record["reason"],
                        "type": "REQUIRES",
                    }
                    for record in requires_data
                ],
                "related": [
                    {
                        "source": record["source"],
                        "target": record["target"],
                        "reason": record["reason"],
                        "type": "RELATED_TO",
                    }
                    for record in related_data
                ],
            },
        }

    async def _is_main_graph_synced(self, pack: DomainPackService) -> bool:
        current_main_metadata = await self._get_main_graph_metadata(pack.domain)
        return current_main_metadata == self._build_main_graph_metadata(pack)

    async def _is_graph_synced(self, pack: DomainPackService) -> bool:
        try:
            return (
                await self._is_main_graph_synced(pack)
                and await self._is_entity_graph_synced(pack)
            )
        except Neo4jDriverError:
            return False

    async def _is_entity_graph_synced(self, pack: DomainPackService) -> bool:
        entity_metadata = await get_graph_entity_metadata(self.driver, pack.domain)
        relationships = entity_metadata.get("relationships", {})
        comparable_metadata = {
            "domain": entity_metadata.get("domain"),
            "stages": entity_metadata.get("stages", []),
            "resources": entity_metadata.get("resources", []),
            "relationships": {
                "stage_sequences": relationships.get("stage_sequences", []),
                "stage_nodes": relationships.get("stage_nodes", []),
                "stage_resources": relationships.get("stage_resources", []),
                "resource_nodes": relationships.get("resource_nodes", []),
            },
        }
        return comparable_metadata == self._build_graph_entity_metadata(pack)

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

    def _resolve_domain(self, domain: str | None = None) -> str:
        return get_domain_pack_registry().resolve_domain(domain)

    async def get_sync_status(self, domain: str | None = None) -> dict[str, Any]:
        pack = get_domain_pack_service(self._resolve_domain(domain), force_reload=False)
        self._validate_pack(pack)
        version = str(pack.manifest.get("version", ""))
        if not version:
            raise ValueError(f"Domain Pack 缺少 version: {pack.domain}")
        pack_hash = self._build_pack_hash(pack)
        counts = self._build_pack_counts(pack)

        try:
            current_state = await self._get_sync_state(pack.domain)
        except Neo4jDriverError as exc:
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "in_sync": False,
                "ready": False,
                "status": "error",
                "reason": str(exc),
                **counts,
            }

        if current_state is None:
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "in_sync": False,
                "ready": False,
                "status": "missing",
                "reason": "domain_pack_not_seeded",
                **counts,
            }

        if current_state["version"] != version or current_state["pack_hash"] != pack_hash:
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "in_sync": False,
                "ready": False,
                "status": "stale",
                "reason": "seed_metadata_stale",
                "seeded_version": current_state["version"],
                "seeded_pack_hash": current_state["pack_hash"],
                **counts,
            }

        try:
            main_graph_synced = await self._is_main_graph_synced(pack)
            entity_graph_synced = main_graph_synced and await self._is_entity_graph_synced(pack)
        except Neo4jDriverError as exc:
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "in_sync": False,
                "ready": False,
                "status": "error",
                "reason": str(exc),
                **counts,
            }

        if not main_graph_synced or not entity_graph_synced:
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "in_sync": False,
                "ready": False,
                "status": "drifted",
                "reason": "graph_data_drifted",
                "main_graph_synced": main_graph_synced,
                "entity_graph_synced": entity_graph_synced,
                **counts,
            }

        return {
            "domain": pack.domain,
            "version": version,
            "pack_hash": pack_hash,
            "in_sync": True,
            "ready": True,
            "status": "ok",
            "reason": "synced",
            "main_graph_synced": True,
            "entity_graph_synced": True,
            **counts,
        }

    async def sync_domain_pack(self, domain: str | None = None) -> dict[str, Any]:
        pack = get_domain_pack_service(self._resolve_domain(domain), force_reload=False)
        return await self._sync_pack(pack, force=False)

    async def force_sync_domain_pack(self, domain: str | None = None) -> dict[str, Any]:
        pack = get_domain_pack_service(self._resolve_domain(domain), force_reload=True)
        return await self._sync_pack(pack, force=True)

    async def _sync_pack(self, pack: DomainPackService, force: bool) -> dict[str, Any]:
        self._validate_pack(pack)
        version = str(pack.manifest.get("version", ""))
        if not version:
            raise ValueError(f"Domain Pack 缺少 version: {pack.domain}")
        pack_hash = self._build_pack_hash(pack)
        try:
            current_state = await self._get_sync_state(pack.domain)
        except Neo4jDriverError:
            current_state = None

        counts = self._build_pack_counts(pack)

        if (
            not force
            and current_state is not None
            and current_state["version"] == version
            and current_state["pack_hash"] == pack_hash
            and await self._is_graph_synced(pack)
        ):
            return {
                "domain": pack.domain,
                "version": version,
                "pack_hash": pack_hash,
                "synced": False,
                "reason": "unchanged",
                **counts,
            }

        result = await seed_graph(
            self.driver,
            domain=pack.domain,
            version=version,
            pack_hash=pack_hash,
            nodes=pack.nodes,
            requires_edges=pack.requires_edges,
            related_edges=pack.related_edges,
            stages=pack.stages,
            resources=pack.resources,
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
