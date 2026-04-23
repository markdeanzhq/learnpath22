"""路径后增强式资源推荐服务"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.repositories.plan_repository import get_plan_by_id
from app.repositories.resource_repository import (
    create_resource_binding,
    delete_auto_resource_bindings,
    list_resource_bindings,
)
from app.repositories.project_repository import get_project
from app.schemas.resource import PlanResourcesResponse, ResourceItem, StageResourceGroup
from app.services import search_service
from app.services.domain_pack_service import get_domain_pack_service


def _load_path_stage_list(path: Any) -> list[dict[str, Any]]:
    raw_stages = json.loads(path.plan_json) if path.plan_json else {}
    if isinstance(raw_stages, list):
        return raw_stages

    stages: list[dict[str, Any]] = []
    for idx, (stage_name, tasks) in enumerate(raw_stages.items()):
        stages.append(
            {
                "stage_index": idx,
                "stage_name": stage_name,
                "tasks": tasks,
                "estimated_hours": sum(task.get("estimated_hours", 0) for task in tasks),
            }
        )
    return stages


def _build_static_stage_resources(stage_name: str, pack: Any) -> list[dict[str, Any]]:
    stage_id = None
    for stage in pack.stages:
        if stage.get("name") == stage_name:
            stage_id = stage.get("id")
            break

    results: list[dict[str, Any]] = []
    for resource in pack.resources:
        if stage_id and stage_id in resource.get("stage_ids", []):
            results.append(
                {
                    "id": resource["id"],
                    "title": resource["title"],
                    "url": "",
                    "snippet": resource.get("description"),
                    "score": None,
                    "source_type": "static",
                    "stage_name": stage_name,
                    "node_id": None,
                    "created_at": None,
                }
            )
    return results


def _build_stage_query(project: Any, stage: dict[str, Any]) -> str:
    task_names = [task.get("name", "") for task in stage.get("tasks", [])[:4] if task.get("name")]
    query_parts = [project.goal_text, stage["stage_name"], *task_names, "学习资料"]
    return " ".join(part for part in query_parts if part).strip()


async def get_plan_resources(
    db: AsyncSession,
    *,
    project_id: str,
    path_id: str,
) -> PlanResourcesResponse:
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_plan_by_id(db, path_id)
    if not path or path.project_id != project_id:
        raise NotFoundError("学习路径不存在")

    pack = get_domain_pack_service(project.domain)
    stages = _load_path_stage_list(path)
    dynamic_resources = await list_resource_bindings(db, project_id, path_id)

    stage_groups: list[StageResourceGroup] = []
    for stage in stages:
        stage_name = stage["stage_name"]
        resources = [
            ResourceItem.model_validate(item)
            for item in _build_static_stage_resources(stage_name, pack)
        ]
        resources.extend(
            ResourceItem(
                id=item.id,
                title=item.title,
                url=item.url,
                snippet=item.snippet,
                score=item.score,
                source_type=item.source_type,
                stage_name=item.stage_name,
                node_id=item.node_id,
                created_at=item.created_at,
            )
            for item in dynamic_resources
            if item.stage_name == stage_name and item.node_id is None
        )
        stage_groups.append(StageResourceGroup(stage_name=stage_name, resources=resources))

    return PlanResourcesResponse(path_id=path_id, stages=stage_groups)


async def recommend_plan_resources(
    db: AsyncSession,
    *,
    project_id: str,
    path_id: str,
) -> PlanResourcesResponse:
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_plan_by_id(db, path_id)
    if not path or path.project_id != project_id:
        raise NotFoundError("学习路径不存在")

    stages = _load_path_stage_list(path)
    await delete_auto_resource_bindings(db, project_id=project_id, path_id=path_id)

    for stage in stages:
        query = _build_stage_query(project, stage)
        results = await search_service.search(query, max_results=3)
        for item in results:
            await create_resource_binding(
                db,
                project_id=project_id,
                path_id=path_id,
                stage_name=stage["stage_name"],
                title=item.get("title", ""),
                url=item.get("url", ""),
                snippet=item.get("snippet"),
                score=item.get("score"),
                source_type="tavily_auto",
            )

    return await get_plan_resources(db, project_id=project_id, path_id=path_id)


async def bind_manual_resource(
    db: AsyncSession,
    *,
    project_id: str,
    path_id: str,
    stage_name: str | None,
    node_id: str | None,
    title: str,
    url: str,
    snippet: str | None,
) -> ResourceItem:
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_plan_by_id(db, path_id)
    if not path or path.project_id != project_id:
        raise NotFoundError("学习路径不存在")

    stages = _load_path_stage_list(path)
    stage_names = {stage["stage_name"] for stage in stages}
    if stage_name and stage_name not in stage_names:
        raise AppError(code=422, message="目标阶段不存在")

    binding = await create_resource_binding(
        db,
        project_id=project_id,
        path_id=path_id,
        stage_name=stage_name,
        node_id=node_id,
        title=title,
        url=url,
        snippet=snippet,
        source_type="manual",
    )
    return ResourceItem(
        id=binding.id,
        title=binding.title,
        url=binding.url,
        snippet=binding.snippet,
        score=binding.score,
        source_type=binding.source_type,
        stage_name=binding.stage_name,
        node_id=binding.node_id,
        created_at=binding.created_at,
    )
