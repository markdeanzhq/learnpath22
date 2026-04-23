import asyncio, json, sys
from datetime import datetime, timezone
from pathlib import Path

repo = Path(r"E:/dailyfile/myfiles/project_all/learnpath322/backend")
sys.path.insert(0, str(repo))

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.api.deps import get_neo4j
from app.core.config import replace_runtime_settings
from app.core.exceptions import register_exception_handlers
from app.db.sqlite import get_db
from app.models.sqlite_models import Base
from app.services.domain_pack_service import get_domain_pack_service
from app.services.graph_sync_service import GraphSyncService
from scripts.generate_thesis_validation_evidence import (
    build_requires_lookup,
    build_run_metadata,
    build_summary,
    build_validation_contract,
    capture_context,
    get_actual_online_dependency_usage,
    index_by_id,
    load_matrix,
    load_requires_edges,
    run_scenario,
)

BASE_URL = "http://127.0.0.1:8010/api/v1"
OUTPUT_FILE = repo / "artifacts" / "thesis_validation" / "latest.json"
MATRIX_FILE = repo / "scripts" / "thesis_validation_matrix.json"
REQUIRES_FILE = repo / "app" / "domain_packs" / "machine_learning" / "requires_edges.json"

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

async def _override_get_db():
    async with _TestSession() as session:
        yield session

class _FakeNeo4j:
    def __init__(self):
        self.pack = get_domain_pack_service("machine_learning", force_reload=True)
        helper = GraphSyncService(self)
        self.pack_hash = helper._build_pack_hash(self.pack)
        self.version = str(self.pack.manifest.get("version", ""))

        self.nodes = [
            {
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
                "synced_pack_hash": self.pack_hash,
                "synced_version": self.version,
            }
            for node in sorted(self.pack.nodes, key=lambda item: item["id"])
        ]
        ordered_stages = sorted(self.pack.stages, key=lambda item: (item["order"], item["id"]))
        self.stages = [
            {
                "id": stage["id"],
                "name": stage["name"],
                "order": stage["order"],
                "description": stage.get("description", ""),
                "category_keys": list(stage.get("category_keys", [])),
            }
            for stage in ordered_stages
        ]
        self.resources = [
            {
                "id": resource["id"],
                "title": resource["title"],
                "resource_type": resource["resource_type"],
                "description": resource.get("description", ""),
            }
            for resource in sorted(self.pack.resources, key=lambda item: item["id"])
        ]
        self.stage_sequences = [
            {"source": previous["id"], "target": current["id"]}
            for previous, current in zip(ordered_stages, ordered_stages[1:])
        ]
        self.stage_nodes = [
            {"stage_id": stage["id"], "node_id": node_id}
            for stage in ordered_stages
            for node_id in sorted(set(stage.get("node_ids", [])))
        ]
        self.stage_resources = [
            {"stage_id": stage_id, "resource_id": resource["id"]}
            for resource in sorted(self.pack.resources, key=lambda item: item["id"])
            for stage_id in sorted(set(resource.get("stage_ids", [])))
        ]
        self.resource_nodes = [
            {"resource_id": resource["id"], "node_id": node_id}
            for resource in sorted(self.pack.resources, key=lambda item: item["id"])
            for node_id in sorted(set(resource.get("node_ids", [])))
        ]

    async def execute_query(self, query, params=None):
        text = " ".join((query or "").split())
        if "RETURN 1 AS ok" in text:
            return [{"ok": 1}]
        if "RETURN n.synced_pack_hash AS pack_hash, n.synced_version AS version" in text:
            return [{"pack_hash": self.pack_hash, "version": self.version}]
        if "MATCH (n:KnowledgeNode) WHERE n.domain = $domain RETURN n ORDER BY n.id" in text:
            return [{"n": node} for node in self.nodes]
        if "MATCH (a:KnowledgeNode)-[r:REQUIRES]->(b:KnowledgeNode)" in text:
            return [
                {"source": edge["source"], "target": edge["target"], "reason": edge.get("reason", "")}
                for edge in sorted(self.pack.requires_edges, key=lambda item: (item["source"], item["target"], item.get("reason", "")))
            ]
        if "MATCH (a:KnowledgeNode)-[r:RELATED_TO]->(b:KnowledgeNode)" in text:
            return [
                {"source": edge["source"], "target": edge["target"], "reason": edge.get("reason", "")}
                for edge in sorted(self.pack.related_edges, key=lambda item: (item["source"], item["target"], item.get("reason", "")))
            ]
        if "MATCH (s:Stage) WHERE s.domain = $domain RETURN s ORDER BY s.order, s.id" in text:
            return [{"s": stage} for stage in self.stages]
        if "MATCH (r:Resource) WHERE r.domain = $domain RETURN r ORDER BY r.id" in text:
            return [{"r": resource} for resource in self.resources]
        if "MATCH (a:Stage)-[:PRECEDES]->(b:Stage)" in text:
            return list(self.stage_sequences)
        if "MATCH (s:Stage)-[:CONTAINS]->(n:KnowledgeNode)" in text:
            return list(self.stage_nodes)
        if "MATCH (s:Stage)-[:HAS_RESOURCE]->(r:Resource)" in text:
            return list(self.stage_resources)
        if "MATCH (r:Resource)-[:COVERS]->(n:KnowledgeNode)" in text:
            return list(self.resource_nodes)
        raise RuntimeError(f"Unsupported query: {text}")

async def _override_get_neo4j():
    return _FakeNeo4j()

async def main():
    replace_runtime_settings({})
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_neo4j] = _override_get_neo4j

    matrix = load_matrix(MATRIX_FILE)
    requires_lookup = build_requires_lookup(load_requires_edges(REQUIRES_FILE))
    goals_by_id = index_by_id(matrix["goal_templates"])
    profiles_by_id = index_by_id(matrix["profile_templates"])

    started_at = datetime.now(timezone.utc)
    async with AsyncClient(transport=ASGITransport(app=app), base_url=BASE_URL, timeout=30.0) as client:
        health, readiness, context_errors = await capture_context(client)
        results = []
        for scenario in matrix["scenarios"]:
            result = await run_scenario(
                client,
                scenario,
                goals_by_id,
                profiles_by_id,
                runtime_mode="offline",
            )
            results.append(result)
    finished_at = datetime.now(timezone.utc)

    summary = build_summary(results, context_errors, requires_lookup)
    actual_usage = get_actual_online_dependency_usage(results)
    run_metadata = build_run_metadata(
        requested_runtime_mode="offline",
        started_at=started_at,
        finished_at=finished_at,
        health=health,
        readiness=readiness,
        actual_usage=actual_usage,
    )

    evidence = {
        "matrix_id": matrix["matrix_id"],
        "change": matrix.get("change"),
        "description": matrix.get("description"),
        "matrix_file": str(MATRIX_FILE),
        "base_url": BASE_URL,
        "run_metadata": run_metadata,
        "validation_contract": build_validation_contract(run_metadata["readiness_contract"]),
        "health": health,
        "readiness": readiness,
        "summary": summary,
        "results": results,
    }

    OUTPUT_FILE.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "readiness": readiness}, ensure_ascii=False, indent=2))

asyncio.run(main())
