from collections.abc import AsyncGenerator

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import (
    RUNTIME_SETTING_KEYS,
    RuntimeSettingsUpdate,
    decode_runtime_setting_value,
    encode_runtime_setting_value,
    get_settings,
    serialize_runtime_bool,
)
from app.models.sqlite_models import RuntimeSetting

settings = get_settings()
engine = create_async_engine(settings.SQLITE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session


async def get_runtime_settings_map(db: AsyncSession) -> dict[str, str]:
    result = await db.execute(select(RuntimeSetting))
    settings_rows = result.scalars().all()
    runtime_settings: dict[str, str] = {}
    requires_migration = False

    for row in settings_rows:
        if row.setting_key not in RUNTIME_SETTING_KEYS:
            continue
        decoded_value, needs_migration = decode_runtime_setting_value(
            row.setting_key,
            row.setting_value,
        )
        runtime_settings[row.setting_key] = decoded_value
        if needs_migration:
            row.setting_value = encode_runtime_setting_value(row.setting_key, decoded_value)
            requires_migration = True

    if requires_migration:
        await db.commit()

    return runtime_settings


async def persist_runtime_settings(
    db: AsyncSession,
    payload: RuntimeSettingsUpdate,
) -> dict[str, str]:
    updates = payload.model_dump(exclude_none=True)
    if not updates:
        return await get_runtime_settings_map(db)

    if isinstance(updates.get("llm_explanation_polish"), bool):
        updates["llm_explanation_polish"] = serialize_runtime_bool(updates["llm_explanation_polish"])

    result = await db.execute(
        select(RuntimeSetting).where(RuntimeSetting.setting_key.in_(tuple(updates.keys())))
    )
    existing_rows = {
        row.setting_key: row
        for row in result.scalars().all()
    }

    for key, value in updates.items():
        row = existing_rows.get(key)
        persisted_value = encode_runtime_setting_value(key, value)
        if row is None:
            db.add(RuntimeSetting(setting_key=key, setting_value=persisted_value))
            continue
        row.setting_value = persisted_value

    await db.commit()
    return await get_runtime_settings_map(db)
