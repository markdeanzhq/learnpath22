import asyncio, json, sys
from pathlib import Path

repo = Path(r"E:/dailyfile/myfiles/project_all/learnpath322/backend")
sys.path.insert(0, str(repo))

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.core.config import replace_runtime_settings
from app.core.exceptions import register_exception_handlers
from app.api.deps import get_neo4j
from app.db.sqlite import get_db
from app.models.sqlite_models import Base
from scripts.generate_thesis_validation_evidence import (
    load_matrix,
    load_requires_edges,
    build_requires_lookup,
    index_by_id,
    capture_context,
    run_scenario,
    compute_dependency_metrics,
)

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
_TestSession = async_sessionmaker(_test_engine, class_=AsyncSession, expire_on_commit=False)

async def _override_get_db():
    async with _TestSession() as session:
        yield session

async def _override_get_neo4j():
    return None

async def main():
    replace_runtime_settings({})
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(api_router, prefix="/api/v1")
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_neo4j] = _override_get_neo4j

    matrix = load_matrix(repo / "scripts" / "thesis_validation_matrix.json")
    requires_lookup = build_requires_lookup(load_requires_edges(repo / "app" / "domain_packs" / "machine_learning" / "requires_edges.json"))
    goals_by_id = index_by_id(matrix["goal_templates"])
    profiles_by_id = index_by_id(matrix["profile_templates"])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test/api/v1", timeout=30.0) as client:
        await capture_context(client)
        results = []
        for scenario in matrix["scenarios"]:
            result = await run_scenario(client, scenario, goals_by_id, profiles_by_id, runtime_mode="offline")
            results.append(result)

    initial = compute_dependency_metrics(results, requires_lookup)
    latest_results = []
    for result in results:
        copied = dict(result)
        copied["plan_response"] = result.get("latest_plan_response", {})
        latest_results.append(copied)
    latest = compute_dependency_metrics(latest_results, requires_lookup)
    print(json.dumps({"initial": initial, "latest_based": latest}, ensure_ascii=False, indent=2))

asyncio.run(main())
