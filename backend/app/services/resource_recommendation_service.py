"""路径后增强式资源推荐服务"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError, NotFoundError
from app.repositories.plan_repository import get_plan_by_id
from app.repositories.profile_repository import get_latest_profile
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
RESOURCE_PREFERENCE_HINTS = {
    "mixed": "图文 视频 代码 综合学习资料",
    "text": "文字讲义 教材 笔记 tutorial notes",
    "video": "视频课程 讲解 lecture video",
    "code": "代码示例 Notebook GitHub Colab 实战",
    "paper": "论文 文档 paper arxiv survey",
}
RESOURCE_PREFERENCE_LABELS = {
    "mixed": "混合资料",
    "text": "文字讲义",
    "video": "视频课程",
    "code": "代码示例",
    "paper": "论文文档",
}
RESOURCE_PREFERENCE_KEYWORDS = {
    "text": ("文字", "讲义", "教材", "教程", "笔记", "article", "tutorial", "notes"),
    "video": ("视频", "课程", "讲解", "bilibili", "youtube", "lecture", "video"),
    "code": ("代码", "示例", "notebook", "github", "colab", "code", "python"),
    "paper": ("论文", "文档", "arxiv", "paper", "survey", "documentation"),
}
PREFERENCE_SCORE_BOOST = 0.08


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


def _resource_value(resource: Any, key: str) -> Any:
    if isinstance(resource, dict):
        return resource.get(key)
    return getattr(resource, key, None)


def _normalize_resource_preference(value: Any) -> str:
    return value if isinstance(value, str) and value in RESOURCE_PREFERENCE_HINTS else "mixed"


def _resource_preference_from_profile(profile: Any) -> str:
    return _normalize_resource_preference(getattr(profile, "resource_preference", None))


def _resource_search_hint(resource_preference: str) -> str:
    return RESOURCE_PREFERENCE_HINTS[_normalize_resource_preference(resource_preference)]


def _resource_text(resource: Any) -> str:
    values = [
        _resource_value(resource, "title"),
        _resource_value(resource, "snippet"),
        _resource_value(resource, "description"),
        _resource_value(resource, "url"),
        _resource_value(resource, "source_type"),
    ]
    return " ".join(str(value).lower() for value in values if value)


def _resource_preference_metadata(resource: Any, resource_preference: str) -> tuple[str, str, float]:
    preference = _normalize_resource_preference(resource_preference)
    if preference == "mixed":
        return "mixed", "保留混合资料偏好，不按单一资料形态过滤。", 0.0

    label = RESOURCE_PREFERENCE_LABELS[preference]
    text = _resource_text(resource)
    if any(keyword in text for keyword in RESOURCE_PREFERENCE_KEYWORDS.get(preference, ())):
        return "preferred", f"匹配学习者偏好的{label}形态。", PREFERENCE_SCORE_BOOST
    return "available", f"未明显命中{label}偏好，但因内容相关仍保留。", 0.0


def _score_with_preference(score: Any, boost: float) -> float | None:
    if not isinstance(score, (int, float)):
        return None
    return round(min(1.0, float(score) + boost), 3)


def _resource_item_from_static(
    resource: dict[str, Any],
    *,
    stage_name: str | None,
    node_id: str | None,
    resource_preference: str,
) -> dict[str, Any]:
    match, reason, _boost = _resource_preference_metadata(resource, resource_preference)
    return {
        "id": resource["id"],
        "title": resource["title"],
        "url": "",
        "snippet": resource.get("description"),
        "score": None,
        "source_type": "static",
        "stage_name": stage_name,
        "node_id": node_id,
        "preference_match": match,
        "preference_reason": reason,
        "created_at": None,
    }


def _build_static_stage_resources(stage_name: str, pack: Any, resource_preference: str) -> list[dict[str, Any]]:
    stage_id = None
    for stage in pack.stages:
        if stage.get("name") == stage_name:
            stage_id = stage.get("id")
            break

    results: list[dict[str, Any]] = []
    for resource in pack.resources:
        if stage_id and stage_id in resource.get("stage_ids", []):
            results.append(
                _resource_item_from_static(
                    resource,
                    stage_name=stage_name,
                    node_id=None,
                    resource_preference=resource_preference,
                )
            )
    return results


def _build_static_node_resources(node_id: str, pack: Any, resource_preference: str) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for resource in pack.resources:
        if node_id in resource.get("node_ids", []):
            results.append(
                _resource_item_from_static(
                    resource,
                    stage_name=None,
                    node_id=node_id,
                    resource_preference=resource_preference,
                )
            )
    return results


def _build_node_query(
    project: Any,
    stage: dict[str, Any],
    task: dict[str, Any],
    resource_preference: str,
) -> str:
    query_parts = [
        task.get("name", ""),
        project.goal_text,
        stage["stage_name"],
        "机器学习",
        "入门",
        "学习资料",
        _resource_search_hint(resource_preference),
    ]
    return " ".join(part for part in query_parts if part).strip()


def _resource_item_from_binding(item: Any, resource_preference: str) -> ResourceItem:
    match, reason, _boost = _resource_preference_metadata(item, resource_preference)
    return ResourceItem(
        id=item.id,
        title=item.title,
        url=item.url,
        snippet=item.snippet,
        score=item.score,
        source_type=item.source_type,
        stage_name=item.stage_name,
        node_id=item.node_id,
        preference_match=match,
        preference_reason=reason,
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
    profile = await get_latest_profile(db, project_id)
    resource_preference = _resource_preference_from_profile(profile)

    stage_groups: list[StageResourceGroup] = []
    for stage in stages:
        stage_name = stage["stage_name"]
        stage_resources = [
            ResourceItem.model_validate(item)
            for item in _build_static_stage_resources(stage_name, pack, resource_preference)
        ]
        stage_resources.extend(
            _resource_item_from_binding(item, resource_preference)
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
                for item in _build_static_node_resources(node_id, pack, resource_preference)
            ]
            node_resources.extend(
                _resource_item_from_binding(item, resource_preference)
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
    profile = await get_latest_profile(db, project_id)
    resource_preference = _resource_preference_from_profile(profile)

    searched_node_count = 0
    for stage in stages:
        for task in stage.get("tasks", []):
            node_id = task.get("node_id")
            if (
                not node_id
                or _build_static_node_resources(node_id, pack, resource_preference)
                or _has_dynamic_node_resource(dynamic_resources, node_id)
            ):
                continue
            if searched_node_count >= MAX_AUTO_SEARCH_NODES:
                break
            query = _build_node_query(project, stage, task, resource_preference)
            results = await search_service.search(query, max_results=AUTO_SEARCH_RESULTS_PER_NODE)
            searched_node_count += 1
            for item in results:
                _match, _reason, boost = _resource_preference_metadata(item, resource_preference)
                await create_resource_binding(
                    db,
                    project_id=project_id,
                    path_id=path_id,
                    stage_name=stage["stage_name"],
                    node_id=node_id,
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet"),
                    score=_score_with_preference(item.get("score"), boost),
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
