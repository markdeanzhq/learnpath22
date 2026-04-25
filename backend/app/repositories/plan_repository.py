"""路径数据访问层"""
from __future__ import annotations

import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sqlite_models import LearningPath, PathStage, PathTask


async def save_plan(
    db: AsyncSession,
    project_id: str,
    plan_result: dict,
    version: int = 1,
) -> LearningPath:
    path = LearningPath(
        project_id=project_id,
        version=version,
        plan_json=json.dumps(plan_result["stage_plan"], ensure_ascii=False),
        audit_json=json.dumps(plan_result["audit"], ensure_ascii=False),
        budget_status=plan_result["budget_summary"]["status"],
        total_hours=plan_result["total_hours"],
    )
    db.add(path)
    await db.flush()

    for idx, (stage_name, tasks) in enumerate(plan_result["stage_plan"].items()):
        if not tasks:
            continue
        stage_hours = sum(t["estimated_hours"] for t in tasks)
        stage = PathStage(
            path_id=path.id,
            stage_index=idx,
            stage_name=stage_name,
            node_count=len(tasks),
            estimated_hours=stage_hours,
        )
        db.add(stage)
        await db.flush()

        for task_data in tasks:
            task = PathTask(
                stage_id=stage.id,
                node_id=task_data["node_id"],
                node_name=task_data["name"],
                order_in_stage=task_data.get("order_in_stage", 0),
                difficulty=task_data["difficulty"],
                importance=task_data["importance"],
                estimated_hours=task_data["estimated_hours"],
            )
            db.add(task)

    await db.commit()
    await db.refresh(path)
    return path


async def get_latest_plan(
    db: AsyncSession, project_id: str
) -> LearningPath | None:
    result = await db.execute(
        select(LearningPath)
        .where(LearningPath.project_id == project_id)
        .order_by(
            LearningPath.version.desc(),
            LearningPath.created_at.desc(),
            LearningPath.id.desc(),
        )
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_plan_by_id(
    db: AsyncSession, path_id: str
) -> LearningPath | None:
    result = await db.execute(
        select(LearningPath).where(LearningPath.id == path_id).limit(1)
    )
    return result.scalar_one_or_none()


async def get_plan_version_count(db: AsyncSession, project_id: str) -> int:
    result = await db.execute(
        select(func.count())
        .select_from(LearningPath)
        .where(LearningPath.project_id == project_id)
    )
    return int(result.scalar() or 0)


async def get_all_planned_node_ids(
    db: AsyncSession, project_id: str
) -> list[str]:
    result = await db.execute(
        select(LearningPath)
        .where(LearningPath.project_id == project_id)
        .order_by(LearningPath.created_at.asc())
    )
    paths = result.scalars().all()

    node_ids: set[str] = set()
    for path in paths:
        plan_data = json.loads(path.plan_json) if path.plan_json else {}
        if isinstance(plan_data, dict):
            for tasks in plan_data.values():
                node_ids.update(t["node_id"] for t in tasks)
        elif isinstance(plan_data, list):
            for stage in plan_data:
                node_ids.update(t["node_id"] for t in stage.get("tasks", []))

    return list(node_ids)


def extract_plan_node_ids(plan_json: str | None) -> list[str]:
    if not plan_json:
        return []

    plan_data = json.loads(plan_json)
    node_ids: set[str] = set()
    if isinstance(plan_data, dict):
        for tasks in plan_data.values():
            if not isinstance(tasks, list):
                continue
            node_ids.update(
                task["node_id"]
                for task in tasks
                if isinstance(task, dict) and "node_id" in task
            )
    elif isinstance(plan_data, list):
        for stage in plan_data:
            if not isinstance(stage, dict):
                continue
            node_ids.update(
                task["node_id"]
                for task in stage.get("tasks", [])
                if isinstance(task, dict) and "node_id" in task
            )

    return sorted(node_ids)


async def get_latest_plan_node_ids(
    db: AsyncSession, project_id: str
) -> list[str]:
    path = await get_latest_plan(db, project_id)
    if not path:
        return []
    return extract_plan_node_ids(path.plan_json)
