from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from neo4j import AsyncGraphDatabase
from neo4j.exceptions import Neo4jError

from app.core.config import get_settings


class Neo4jDriverError(RuntimeError):
    pass


class Neo4jDriver:
    def __init__(self):
        self._driver = None

    async def connect(self):
        settings = get_settings()
        self._driver = AsyncGraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
        )

    async def close(self):
        if self._driver:
            await self._driver.close()

    def _wrap_driver_error(self, action: str, exc: Neo4jError) -> Neo4jDriverError:
        return Neo4jDriverError(f"Neo4j {action}失败: {exc}")

    async def execute_query(self, query: str, parameters: dict | None = None):
        async with self._driver.session() as session:
            try:
                result = await session.run(query, parameters or {})
                return [record.data() async for record in result]
            except Neo4jError as exc:
                raise self._wrap_driver_error("查询执行", exc) from exc

    async def execute_write(
        self,
        operation: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        async with self._driver.session() as session:
            try:
                return await session.execute_write(operation)
            except Neo4jError as exc:
                raise self._wrap_driver_error("写事务执行", exc) from exc


neo4j_driver = Neo4jDriver()


async def get_neo4j() -> Neo4jDriver:
    return neo4j_driver
