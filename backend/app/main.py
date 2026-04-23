import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings, replace_runtime_settings
from app.core.exceptions import register_exception_handlers
from app.db.init_db import init_sqlite
from app.db.neo4j import neo4j_driver
from app.db.seed_graph import initialize_knowledge_node_schema
from app.db.sqlite import async_session, get_runtime_settings_map

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_sqlite()
    async with async_session() as session:
        replace_runtime_settings(await get_runtime_settings_map(session))
    try:
        await neo4j_driver.connect()
        await initialize_knowledge_node_schema(neo4j_driver)
    except Exception as exc:
        logger.warning("Neo4j startup skipped: %s", exc)
    try:
        yield
    finally:
        await neo4j_driver.close()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.PROJECT_NAME,
        version=settings.VERSION,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(api_router, prefix=settings.API_V1_PREFIX)

    return app


app = create_app()
