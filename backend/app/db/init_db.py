from app.db.sqlite import engine
from app.models.sqlite_models import Base


async def init_sqlite():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
