import json
from datetime import datetime, timezone

from sqlalchemy import delete, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession

from app.db.sqlite import async_session, engine
from app.models.sqlite_models import Base, GoalResolutionSession, LearningProject
from app.services.domain_pack_service import get_domain_pack_service
from app.services.goal_service import identify_goal_type, resolve_goal

# Columns to add to learning_projects for confirmed-resolution fields (task 1.2)
_RESOLUTION_COLUMNS = [
    ("requested_goal_type", "VARCHAR(30)"),
    ("auto_detected_goal_type", "VARCHAR(30)"),
    ("confirmed_target_node_ids_json", "TEXT"),
    ("confirmed_mode", "VARCHAR(30)"),
    ("confirmed_description", "TEXT"),
    ("confirmed_template_id", "VARCHAR(100)"),
    ("confirmed_resolve_source", "VARCHAR(50)"),
    ("confirmed_source_breakdown_json", "TEXT"),
    ("confirmed_candidate_id", "VARCHAR(100)"),
    ("resolution_pack_version", "VARCHAR(20)"),
    ("resolution_confirmed_at", "DATETIME"),
]

_SESSION_COLUMNS = [
    ("domain", "VARCHAR(50)"),
    ("pack_hash", "VARCHAR(64)"),
    ("graph_hash", "VARCHAR(64)"),
]


async def upgrade_learning_projects_schema(conn: AsyncConnection) -> None:
    """Add confirmed-resolution columns to learning_projects if they don't exist yet.

    Idempotent: safe to call multiple times; existing columns are skipped silently.
    Accepts an AsyncConnection (e.g. from engine.begin()) so callers can manage
    the transaction boundary themselves.
    """
    for col_name, col_type in _RESOLUTION_COLUMNS:
        try:
            await conn.execute(
                text(
                    f"ALTER TABLE learning_projects ADD COLUMN {col_name} {col_type} DEFAULT NULL"
                )
            )
        except OperationalError:
            # Column already exists — SQLite raises OperationalError in this case
            pass


async def upgrade_goal_resolution_sessions_schema(conn: AsyncConnection) -> None:
    for col_name, col_type in _SESSION_COLUMNS:
        try:
            await conn.execute(
                text(
                    f"ALTER TABLE goal_resolution_sessions ADD COLUMN {col_name} {col_type} DEFAULT NULL"
                )
            )
        except OperationalError:
            pass


async def cleanup_expired_sessions(db: AsyncSession) -> int:
    """Delete GoalResolutionSession rows whose expires_at is in the past.

    Returns the number of rows deleted.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC
    result = await db.execute(
        delete(GoalResolutionSession).where(GoalResolutionSession.expires_at < now)
    )
    return result.rowcount


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_legacy_confirmed_resolution_data(project: LearningProject) -> dict[str, object]:
    pack = get_domain_pack_service(project.domain)
    goal_result = resolve_goal(
        project.goal_text,
        project.goal_type,
        pack.goal_templates,
        pack.nodes_by_id,
        supported_goal_types=pack.contract.supported_goal_types if pack.contract is not None else (),
        allow_llm=False,
        allow_default_policy_fallback=True,
        default_goal_policy=pack.contract.default_goal_policy if pack.contract is not None else None,
    )

    resolve_source = goal_result["resolve_source"]
    target_node_ids = list(goal_result.get("target_node_ids") or [])

    if resolve_source == "fallback":
        raise ValueError(
            f"Illegal legacy backfill resolve_source for project {project.id}: {resolve_source}"
        )

    if not target_node_ids:
        raise ValueError(
            f"Legacy backfill produced empty target_node_ids for project {project.id}"
        )

    invalid_node_ids = [nid for nid in target_node_ids if nid not in pack.nodes_by_id]
    if invalid_node_ids:
        raise ValueError(
            "Legacy backfill produced unknown target_node_ids for "
            f"project {project.id}: {invalid_node_ids}"
        )

    return {
        "requested_goal_type": project.goal_type,
        "auto_detected_goal_type": identify_goal_type(project.goal_text),
        "confirmed_target_node_ids_json": json.dumps(
            target_node_ids,
            ensure_ascii=False,
            sort_keys=True,
        ),
        "confirmed_mode": goal_result["mode"],
        "confirmed_description": goal_result["description"],
        "confirmed_template_id": goal_result["template_id"],
        "confirmed_resolve_source": resolve_source,
        "confirmed_source_breakdown_json": json.dumps(
            {resolve_source: 1.0},
            ensure_ascii=False,
            sort_keys=True,
        ),
        "confirmed_candidate_id": f"legacy:{project.id}",
        "resolution_pack_version": pack.manifest.get("version", "unknown"),
        "resolution_confirmed_at": _naive_utc_now(),
    }


def backfill_legacy_project_resolution(project: LearningProject) -> None:
    resolution_data = build_legacy_confirmed_resolution_data(project)
    for field_name, value in resolution_data.items():
        setattr(project, field_name, value)


async def backfill_all_legacy_projects(db: AsyncSession) -> int:
    result = await db.execute(
        select(LearningProject)
        .where(LearningProject.confirmed_target_node_ids_json.is_(None))
        .order_by(LearningProject.created_at, LearningProject.id)
    )
    projects = result.scalars().all()

    backfilled_count = 0
    for project in projects:
        backfill_legacy_project_resolution(project)
        backfilled_count += 1

    return backfilled_count


async def init_sqlite():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await upgrade_learning_projects_schema(conn)
        await upgrade_goal_resolution_sessions_schema(conn)

    async with async_session() as db:
        await cleanup_expired_sessions(db)
        await backfill_all_legacy_projects(db)
        await db.commit()
