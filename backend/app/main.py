from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.db.init_db import init_sqlite
from app.db.neo4j import neo4j_driver
from app.db.seed_graph import initialize_knowledge_node_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_sqlite()
    await neo4j_driver.connect()
    await initialize_knowledge_node_schema(neo4j_driver)
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
