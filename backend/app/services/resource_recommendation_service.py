"""路径后增强式资源推荐服务"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.repositories.plan_repository import get_plan_by_id
from app.repositories.resource_repository import (
    create_resource_binding,
    list_resource_bindings,
)
from app.repositories.project_repository import get_project
from app.schemas.resource import (
    NodeResourceGroup,
    PlanResourcesResponse,
    ResourceItem,
    StageResourceGroup,
)
from app.services import search_service
from app.services.domain_pack_service import get_domain_pack_service

AUTO_SEARCH_RESULTS_PER_NODE = 2
MAX_AUTO_SEARCH_NODES = 12


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


def _resource_item_from_static(
    resource: dict[str, Any],
    *,
    stage_name: str | None,
    node_id: str | None,
) -> dict[str, Any]:
    return {
        "id": resource["id"],
        "title": resource["title"],
        "url": "",
        "snippet": resource.get("description"),
        "score": None,
        "source_type": "static",
        "stage_name": stage_name,
        "node_id": node_id,
        "created_at": None,
    }


def _build_static_stage_resources(stage_name: str, pack: Any) -> list[dict[str, Any]]:
    stage_id = None
    for stage in pack.stages:
        if stage.get("name") == stage_name:
            stage_id = stage.get("id")
            break

    results: list[dict[str, Any]] = []
    for resource in pack.resources:
        if stage_id and stage_id in resource.get("stage_ids", []):
            results.append(_resource_item_from_static(resource, stage_name=stage_name, node_id=None))
    return results


def _build_static_node_resources(node_id: str, pack: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for resource in pack.resources:
        if node_id in resource.get("node_ids", []):
            results.append(_resource_item_from_static(resource, stage_name=None, node_id=node_id))
    return results


def _build_node_query(project: Any, stage: dict[str, Any], task: dict[str, Any]) -> str:
    query_parts = [
        task.get("name", ""),
        project.goal_text,
        stage["stage_name"],
        "机器学习",
        "入门",
        "学习资料",
    ]
    return " ".join(part for part in query_parts if part).strip()


def _resource_item_from_binding(item: Any) -> ResourceItem:
    return ResourceItem(
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


def _path_node_ids(stages: list[dict[str, Any]]) -> set[str]:
    return {
        task.get("node_id")
        for stage in stages
        for task in stage.get("tasks", [])
        if task.get("node_id")
    }


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
        stage_resources = [
            ResourceItem.model_validate(item)
            for item in _build_static_stage_resources(stage_name, pack)
        ]
        stage_resources.extend(
            _resource_item_from_binding(item)
            for item in dynamic_resources
            if item.stage_name == stage_name and item.node_id is None
        )

        node_groups: list[NodeResourceGroup] = []
        for task in stage.get("tasks", []):
            node_id = task.get("node_id")
            if not node_id:
                continue
            node_resources = [
                ResourceItem.model_validate(item)
                for item in _build_static_node_resources(node_id, pack)
            ]
            node_resources.extend(
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
                if item.node_id == node_id
            )
            node_groups.append(
                NodeResourceGroup(
                    node_id=node_id,
                    node_name=task.get("name") or pack.nodes_by_id.get(node_id, {}).get("name") or node_id,
                    resources=node_resources,
                )
            )

        stage_groups.append(
            StageResourceGroup(
                stage_name=stage_name,
                stage_resources=stage_resources,
                nodes=node_groups,
            )
        )

    return PlanResourcesResponse(path_id=path_id, stages=stage_groups)


def _has_dynamic_node_resource(resources: list[Any], node_id: str) -> bool:
    return any(item.node_id == node_id for item in resources)


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

    pack = get_domain_pack_service(project.domain)
    stages = _load_path_stage_list(path)
    dynamic_resources = await list_resource_bindings(db, project_id, path_id)

    searched_node_count = 0
    for stage in stages:
        for task in stage.get("tasks", []):
            node_id = task.get("node_id")
            if (
                not node_id
                or _build_static_node_resources(node_id, pack)
                or _has_dynamic_node_resource(dynamic_resources, node_id)
            ):
                continue
            if searched_node_count >= MAX_AUTO_SEARCH_NODES:
                break
            query = _build_node_query(project, stage, task)
            results = await search_service.search(query, max_results=AUTO_SEARCH_RESULTS_PER_NODE)
            searched_node_count += 1
            for item in results:
                await create_resource_binding(
                    db,
                    project_id=project_id,
                    path_id=path_id,
                    stage_name=stage["stage_name"],
                    node_id=node_id,
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet"),
                    score=item.get("score"),
                    source_type="tavily_auto",
                )
        if searched_node_count >= MAX_AUTO_SEARCH_NODES:
            break

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
    path_node_ids = _path_node_ids(stages)
    if stage_name and stage_name not in stage_names:
        raise AppError(code=422, message="目标阶段不存在")
    if node_id and node_id not in path_node_ids:
        raise AppError(code=422, message="目标知识点不存在于当前路径")

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
