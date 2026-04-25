"""将 Domain Pack 数据严格镜像同步到 Neo4j"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from app.db.neo4j import Neo4jDriver


NODE_LABEL = "KnowledgeNode"
STAGE_LABEL = "Stage"
RESOURCE_LABEL = "Resource"
DOMAIN_KEY = "domain"
RELATIONSHIP_TYPES = ("REQUIRES", "RELATED_TO")
STAGE_SEQUENCE_RELATIONSHIP = "PRECEDES"
STAGE_NODE_RELATIONSHIP = "CONTAINS"
STAGE_RESOURCE_RELATIONSHIP = "HAS_RESOURCE"
RESOURCE_NODE_RELATIONSHIP = "COVERS"
BASELINE_OWNER = "domain_pack"
BASELINE_ORIGIN = "baseline"


async def initialize_knowledge_node_schema(driver: Neo4jDriver) -> None:
    await driver.execute_query(
        f"CREATE CONSTRAINT IF NOT EXISTS FOR (n:{NODE_LABEL}) REQUIRE n.id IS UNIQUE"
    )
    await driver.execute_query(
        f"CREATE CONSTRAINT IF NOT EXISTS FOR (s:{STAGE_LABEL}) REQUIRE s.id IS UNIQUE"
    )
    await driver.execute_query(
        f"CREATE CONSTRAINT IF NOT EXISTS FOR (r:{RESOURCE_LABEL}) REQUIRE r.id IS UNIQUE"
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
        "owner": BASELINE_OWNER,
        "origin": BASELINE_ORIGIN,
    }


def _build_stage_sequence_edges(stages: Sequence[dict[str, Any]]) -> list[dict[str, str]]:
    ordered_stages = sorted(stages, key=lambda stage: stage["order"])
    return [
        {
            "source": previous["id"],
            "target": current["id"],
        }
        for previous, current in zip(ordered_stages, ordered_stages[1:])
    ]


async def _run_strict_mirror_sync(
    tx: Any,
    *,
    domain: str,
    version: str,
    pack_hash: str,
    nodes: Sequence[dict[str, Any]],
    requires_edges: Sequence[dict[str, Any]],
    related_edges: Sequence[dict[str, Any]],
    stages: Sequence[dict[str, Any]],
    resources: Sequence[dict[str, Any]],
) -> dict[str, int]:
    node_payloads = [_build_node_payload(node, domain) for node in nodes]
    stage_sequence_edges = _build_stage_sequence_edges(stages)
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

    stage_payloads = [
        {
            "id": stage["id"],
            "domain": domain,
            "name": stage["name"],
            "order": stage["order"],
            "description": stage.get("description", ""),
            "category_keys": stage.get("category_keys", []),
            "owner": BASELINE_OWNER,
            "origin": BASELINE_ORIGIN,
        }
        for stage in stages
    ]
    await tx.run(
        f"""
        UNWIND $stages AS stage
        MERGE (s:{STAGE_LABEL} {{id: stage.id}})
        SET s += stage,
            s.synced_version = $version,
            s.synced_pack_hash = $pack_hash,
            s.synced_at = datetime()
        """,
        stages=stage_payloads,
        version=version,
        pack_hash=pack_hash,
    )

    resource_payloads = [
        {
            "id": resource["id"],
            "domain": domain,
            "title": resource["title"],
            "resource_type": resource["resource_type"],
            "description": resource.get("description", ""),
            "owner": BASELINE_OWNER,
            "origin": BASELINE_ORIGIN,
        }
        for resource in resources
    ]
    await tx.run(
        f"""
        UNWIND $resources AS resource
        MERGE (r:{RESOURCE_LABEL} {{id: resource.id}})
        SET r += resource,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        resources=resource_payloads,
        version=version,
        pack_hash=pack_hash,
    )

    node_ids = [node["id"] for node in nodes]
    await tx.run(
        f"""
        MATCH (n:{NODE_LABEL})
        WHERE n.{DOMAIN_KEY} = $domain
          AND coalesce(n.owner, $baseline_owner) = $baseline_owner
          AND NOT n.id IN $node_ids
        DETACH DELETE n
        """,
        domain=domain,
        node_ids=node_ids,
        baseline_owner=BASELINE_OWNER,
    )

    stage_ids = [stage["id"] for stage in stages]
    await tx.run(
        f"""
        MATCH (s:{STAGE_LABEL})
        WHERE s.{DOMAIN_KEY} = $domain
          AND coalesce(s.owner, $baseline_owner) = $baseline_owner
          AND NOT s.id IN $stage_ids
        DETACH DELETE s
        """,
        domain=domain,
        stage_ids=stage_ids,
        baseline_owner=BASELINE_OWNER,
    )

    resource_ids = [resource["id"] for resource in resources]
    await tx.run(
        f"""
        MATCH (r:{RESOURCE_LABEL})
        WHERE r.{DOMAIN_KEY} = $domain
          AND coalesce(r.owner, $baseline_owner) = $baseline_owner
          AND NOT r.id IN $resource_ids
        DETACH DELETE r
        """,
        domain=domain,
        resource_ids=resource_ids,
        baseline_owner=BASELINE_OWNER,
    )

    await tx.run(
        f"""
        MATCH (a:{NODE_LABEL})-[r]->(b:{NODE_LABEL})
        WHERE a.{DOMAIN_KEY} = $domain
          AND b.{DOMAIN_KEY} = $domain
          AND type(r) IN $relationship_types
        DELETE r
        """,
        domain=domain,
        relationship_types=list(RELATIONSHIP_TYPES),
    )

    await tx.run(
        f"""
        MATCH (a:{STAGE_LABEL})-[r:{STAGE_SEQUENCE_RELATIONSHIP}]->(b:{STAGE_LABEL})
        WHERE a.{DOMAIN_KEY} = $domain
          AND b.{DOMAIN_KEY} = $domain
        DELETE r
        """,
        domain=domain,
    )

    await tx.run(
        f"""
        MATCH (s:{STAGE_LABEL})-[r:{STAGE_NODE_RELATIONSHIP}]->(n:{NODE_LABEL})
        WHERE s.{DOMAIN_KEY} = $domain
          AND n.{DOMAIN_KEY} = $domain
        DELETE r
        """,
        domain=domain,
    )

    await tx.run(
        f"""
        MATCH (s:{STAGE_LABEL})-[r:{STAGE_RESOURCE_RELATIONSHIP}]->(resource:{RESOURCE_LABEL})
        WHERE s.{DOMAIN_KEY} = $domain
          AND resource.{DOMAIN_KEY} = $domain
        DELETE r
        """,
        domain=domain,
    )

    await tx.run(
        f"""
        MATCH (resource:{RESOURCE_LABEL})-[r:{RESOURCE_NODE_RELATIONSHIP}]->(n:{NODE_LABEL})
        WHERE resource.{DOMAIN_KEY} = $domain
          AND n.{DOMAIN_KEY} = $domain
        DELETE r
        """,
        domain=domain,
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

    await tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (a:{STAGE_LABEL} {{id: edge.source, {DOMAIN_KEY}: $domain}})
        MATCH (b:{STAGE_LABEL} {{id: edge.target, {DOMAIN_KEY}: $domain}})
        MERGE (a)-[r:{STAGE_SEQUENCE_RELATIONSHIP}]->(b)
        SET r.domain = $domain,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        domain=domain,
        version=version,
        pack_hash=pack_hash,
        edges=stage_sequence_edges,
    )

    await tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (s:{STAGE_LABEL} {{id: edge.stage_id, {DOMAIN_KEY}: $domain}})
        MATCH (n:{NODE_LABEL} {{id: edge.node_id, {DOMAIN_KEY}: $domain}})
        MERGE (s)-[r:{STAGE_NODE_RELATIONSHIP}]->(n)
        SET r.domain = $domain,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        domain=domain,
        version=version,
        pack_hash=pack_hash,
        edges=[
            {
                "stage_id": stage["id"],
                "node_id": node_id,
            }
            for stage in stages
            for node_id in stage.get("node_ids", [])
        ],
    )

    await tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (s:{STAGE_LABEL} {{id: edge.stage_id, {DOMAIN_KEY}: $domain}})
        MATCH (resource:{RESOURCE_LABEL} {{id: edge.resource_id, {DOMAIN_KEY}: $domain}})
        MERGE (s)-[r:{STAGE_RESOURCE_RELATIONSHIP}]->(resource)
        SET r.domain = $domain,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        domain=domain,
        version=version,
        pack_hash=pack_hash,
        edges=[
            {
                "stage_id": stage_id,
                "resource_id": resource["id"],
            }
            for resource in resources
            for stage_id in resource.get("stage_ids", [])
        ],
    )

    await tx.run(
        f"""
        UNWIND $edges AS edge
        MATCH (resource:{RESOURCE_LABEL} {{id: edge.resource_id, {DOMAIN_KEY}: $domain}})
        MATCH (n:{NODE_LABEL} {{id: edge.node_id, {DOMAIN_KEY}: $domain}})
        MERGE (resource)-[r:{RESOURCE_NODE_RELATIONSHIP}]->(n)
        SET r.domain = $domain,
            r.synced_version = $version,
            r.synced_pack_hash = $pack_hash,
            r.synced_at = datetime()
        """,
        domain=domain,
        version=version,
        pack_hash=pack_hash,
        edges=[
            {
                "resource_id": resource["id"],
                "node_id": node_id,
            }
            for resource in resources
            for node_id in resource.get("node_ids", [])
        ],
    )

    return {
        "nodes": len(nodes) + len(stages) + len(resources),
        "edges": (
            len(requires_edges)
            + len(related_edges)
            + len(stage_sequence_edges)
            + sum(len(stage.get("node_ids", [])) for stage in stages)
            + sum(len(resource.get("stage_ids", [])) for resource in resources)
            + sum(len(resource.get("node_ids", [])) for resource in resources)
        ),
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
    stages: list[dict[str, Any]],
    resources: list[dict[str, Any]],
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
            stages=stages,
            resources=resources,
        )

    return await driver.execute_write(_operation)
