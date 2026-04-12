"""将 Domain Pack 数据严格镜像同步到 Neo4j"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.db.neo4j import Neo4jDriver


NODE_LABEL = "KnowledgeNode"
DOMAIN_KEY = "domain"
RELATIONSHIP_TYPES = ("REQUIRES", "RELATED_TO")


async def initialize_knowledge_node_schema(driver: Neo4jDriver) -> None:
    await driver.execute_query(
        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_LABEL}) REQUIRE n.id IS UNIQUE"
    )


def _build_node_payload(node: dict[str, Any], domain: str) -> dict[str, Any]:
    return {
        "id": node["id"],
        "domain": domain,
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


async def _run_strict_mirror_sync(
    tx: Any,
    *,
    domain: str,
    version: str,
    pack_hash: str,
    nodes: Sequence[dict[str, Any]],
    requires_edges: Sequence[dict[str, Any]],
    related_edges: Sequence[dict[str, Any]],
) -> dict[str, int]:
    node_payloads = [_build_node_payload(node, domain) for node in nodes]
    await tx.run(
        f"""
        UNWIND $nodes AS node
        MERGE (n:{NODE_LABEL} {{id: node.id}})
        SET n += node,
            n.synced_version = $version,
            n.synced_pack_hash = $pack_hash,
            n.synced_at = datetime()
        """,
        nodes=node_payloads,
        version=version,
        pack_hash=pack_hash,
    )

    node_ids = [node["id"] for node in nodes]
    await tx.run(
        f"""
        MATCH (n:{NODE_LABEL})
        WHERE n.{DOMAIN_KEY} = $domain
          AND NOT n.id IN $node_ids
        DETACH DELETE n
        """,
        domain=domain,
        node_ids=node_ids,
    )

    edge_payloads = [
        {
            "source": edge["source"],
            "target": edge["target"],
            "reason": edge.get("reason", ""),
        }
        for edge in [*requires_edges, *related_edges]
    ]
    await tx.run(
        f"""
        MATCH (a:{NODE_LABEL})-[r]->(b:{NODE_LABEL})
        WHERE a.{DOMAIN_KEY} = $domain
          AND b.{DOMAIN_KEY} = $domain
          AND type(r) IN $relationship_types
          AND NOT {{
            source: a.id,
            target: b.id,
            reason: coalesce(r.reason, "")
          }} IN $edges
        DELETE r
        """,
        domain=domain,
        relationship_types=list(RELATIONSHIP_TYPES),
        edges=edge_payloads,
    )

    await tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (a:{NODE_LABEL} {{id: edge.source, {DOMAIN_KEY}: $domain}})
        MATCH (b:{NODE_LABEL} {{id: edge.target, {DOMAIN_KEY}: $domain}})
        MERGE (a)-[r:REQUIRES]->(b)
        SET r.reason = edge.reason,
            r.domain = $domain,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        domain=domain,
        version=version,
        pack_hash=pack_hash,
        edges=[
            {
                "source": edge["source"],
                "target": edge["target"],
                "reason": edge.get("reason", ""),
            }
            for edge in requires_edges
        ],
    )

    await tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (a:{NODE_LABEL} {{id: edge.source, {DOMAIN_KEY}: $domain}})
        MATCH (b:{NODE_LABEL} {{id: edge.target, {DOMAIN_KEY}: $domain}})
        MERGE (a)-[r:RELATED_TO]->(b)
        SET r.reason = edge.reason,
            r.domain = $domain,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        domain=domain,
        version=version,
        pack_hash=pack_hash,
        edges=[
            {
                "source": edge["source"],
                "target": edge["target"],
                "reason": edge.get("reason", ""),
            }
            for edge in related_edges
        ],
    )

    return {
        "nodes": len(nodes),
        "edges": len(requires_edges) + len(related_edges),
    }


async def seed_graph(
    driver: Neo4jDriver,
    *,
    domain: str,
    version: str,
    pack_hash: str,
    nodes: list[dict[str, Any]],
    requires_edges: list[dict[str, Any]],
    related_edges: list[dict[str, Any]],
) -> dict[str, int]:
    """按 domain 严格镜像同步：更新、补齐并清理陈旧节点和关系。"""

    async def _operation(tx: Any) -> dict[str, int]:
        return await _run_strict_mirror_sync(
            tx,
            domain=domain,
            version=version,
            pack_hash=pack_hash,
            nodes=nodes,
            requires_edges=requires_edges,
            related_edges=related_edges,
        )

    return await driver.execute_write(_operation)
