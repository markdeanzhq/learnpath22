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
    ("path_mode", "VARCHAR(30) DEFAULT 'standard'"),
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

_PROFILE_COLUMNS = [
    ("path_mode_preference", "VARCHAR(30)"),
    ("persona_label", "VARCHAR(100)"),
    ("persona_summary", "TEXT"),
    ("persona_evidence", "TEXT"),
]

_SESSION_COLUMNS = [
    ("domain", "VARCHAR(50)"),
    ("pack_hash", "VARCHAR(64)"),
    ("graph_hash", "VARCHAR(64)"),
]

_OVERLAY_SOURCE_COLUMNS = [
    ("summary", "TEXT"),
    ("quality_status", "VARCHAR(30)"),
]

_OVERLAY_BINDING_COLUMNS = [
    ("source_result_id", "VARCHAR(36)"),
]

_PERSISTED_SEARCH_RESULT_COLUMNS = [
    ("source_id", "VARCHAR(36)"),
]


def _is_duplicate_column_error(exc: OperationalError) -> bool:
    return "duplicate column name" in str(exc).lower()


async def _add_column_if_missing(
    conn: AsyncConnection,
    *,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    try:
        await conn.execute(
            text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
        )
    except OperationalError as exc:
        if _is_duplicate_column_error(exc):
            return
        raise


_OVERLAY_INDEXES = [
    ("idx_project_overlay_sources_project_id", "project_overlay_sources", "project_id"),
    ("idx_project_overlay_extraction_sessions_project_id", "project_overlay_extraction_sessions", "project_id"),
    ("idx_project_overlay_nodes_project_id", "project_overlay_nodes", "project_id"),
    ("idx_project_overlay_nodes_session_id", "project_overlay_nodes", "session_id"),
    ("idx_project_overlay_edges_project_id", "project_overlay_edges", "project_id"),
    ("idx_project_overlay_edges_session_id", "project_overlay_edges", "session_id"),
    ("idx_project_overlay_resources_project_id", "project_overlay_resources", "project_id"),
    ("idx_project_overlay_resources_session_id", "project_overlay_resources", "session_id"),
    ("idx_project_overlay_resource_bindings_project_id", "project_overlay_resource_bindings", "project_id"),
    ("idx_project_overlay_resource_bindings_resource_id", "project_overlay_resource_bindings", "resource_id"),
    ("idx_project_overlay_resource_bindings_source_result_id", "project_overlay_resource_bindings", "source_result_id"),
    ("idx_project_overlay_projection_states_project_id", "project_overlay_projection_states", "project_id"),
    ("idx_project_overlay_promotion_batches_project_id", "project_overlay_promotion_batches", "project_id"),
    ("idx_project_overlay_promotion_items_project_id", "project_overlay_promotion_items", "project_id"),
    ("idx_project_overlay_promotion_items_batch_id", "project_overlay_promotion_items", "batch_id"),
    ("idx_persisted_search_results_project_id", "persisted_search_results", "project_id"),
    ("idx_persisted_search_results_source_id", "persisted_search_results", "source_id"),
    ("idx_persisted_search_results_result_id", "persisted_search_results", "result_id"),
]


async def upgrade_learning_projects_schema(conn: AsyncConnection) -> None:
    for col_name, col_type in _RESOLUTION_COLUMNS:
        await _add_column_if_missing(
            conn,
            table_name="learning_projects",
            column_name=col_name,
            column_type=col_type,
        )
    await conn.execute(
        text("UPDATE learning_projects SET path_mode = 'standard' WHERE path_mode IS NULL")
    )


async def upgrade_learner_profiles_schema(conn: AsyncConnection) -> None:
    for col_name, col_type in _PROFILE_COLUMNS:
        await _add_column_if_missing(
            conn,
            table_name="learner_profiles",
            column_name=col_name,
            column_type=col_type,
        )


async def upgrade_goal_resolution_sessions_schema(conn: AsyncConnection) -> None:
    for col_name, col_type in _SESSION_COLUMNS:
        await _add_column_if_missing(
            conn,
            table_name="goal_resolution_sessions",
            column_name=col_name,
            column_type=col_type,
        )


async def upgrade_project_overlay_schema(conn: AsyncConnection) -> None:
    for col_name, col_type in _OVERLAY_SOURCE_COLUMNS:
        await _add_column_if_missing(
            conn,
            table_name="project_overlay_sources",
            column_name=col_name,
            column_type=col_type,
        )
    for col_name, col_type in _OVERLAY_BINDING_COLUMNS:
        await _add_column_if_missing(
            conn,
            table_name="project_overlay_resource_bindings",
            column_name=col_name,
            column_type=col_type,
        )
    for col_name, col_type in _PERSISTED_SEARCH_RESULT_COLUMNS:
        await _add_column_if_missing(
            conn,
            table_name="persisted_search_results",
            column_name=col_name,
            column_type=col_type,
        )


async def create_project_overlay_indexes(conn: AsyncConnection) -> None:
    for index_name, table_name, column_name in _OVERLAY_INDEXES:
        await conn.execute(
            text(
                f"CREATE INDEX IF NOT EXISTS {index_name} "
                f"ON {table_name} ({column_name})"
            )
        )


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
        await upgrade_learner_profiles_schema(conn)
        await upgrade_goal_resolution_sessions_schema(conn)
        await upgrade_project_overlay_schema(conn)
        await create_project_overlay_indexes(conn)

    async with async_session() as db:
        await cleanup_expired_sessions(db)
        await backfill_all_legacy_projects(db)
        await db.commit()
