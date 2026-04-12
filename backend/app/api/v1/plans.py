"""路径规划 API"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import AppError, NotFoundError
from app.repositories.plan_repository import (
    get_latest_plan,
    get_plan_version_count,
    save_plan,
)
from app.repositories.profile_repository import get_latest_profile
from app.repositories.project_repository import get_project
from app.repositories.graph_review_repository import get_removed_node_ids, get_removed_edge_ids
from app.schemas.explanation import ExplanationResponse
from app.services.domain_pack_service import get_domain_pack_service
from app.services.explanation_service import build_explanation
from app.services.planner_service import plan_with_profile

router = APIRouter()


def _dict_stages_to_list(stage_dict: dict) -> list[dict]:
    """将 {阶段名: [tasks]} 转换为 [{stage_index, stage_name, tasks, estimated_hours}]"""
    result = []
    for idx, (name, tasks) in enumerate(stage_dict.items()):
        result.append({
            "stage_index": idx,
            "stage_name": name,
            "tasks": tasks,
            "estimated_hours": sum(t.get("estimated_hours", 0) for t in tasks),
        })
    return result


@router.post("/projects/{project_id}/plans")
async def generate_plan(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    profile_row = await get_latest_profile(db, project_id)
    if not profile_row:
        raise AppError(code=400, message="请先完成画像测评再生成路径")

    profile = {
        "math_level": profile_row.math_level,
        "coding_level": profile_row.coding_level,
        "ml_level": profile_row.ml_level,
        "theory_weight": profile_row.theory_weight,
        "weekly_hours": profile_row.weekly_hours,
        "deadline_weeks": profile_row.deadline_weeks,
    }

    pack = get_domain_pack_service(project.domain)
    removed_nodes = await get_removed_node_ids(db, project_id)
    removed_edges = await get_removed_edge_ids(db, project_id)

    plan_result = plan_with_profile(
        goal_text=project.goal_text,
        goal_type=project.goal_type,
        profile=profile,
        pack=pack,
        removed_node_ids=removed_nodes,
        removed_edge_ids=removed_edges,
    )

    version = await get_plan_version_count(db, project_id) + 1
    path = await save_plan(db, project_id, plan_result, version=version)

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": _dict_stages_to_list(plan_result["stage_plan"]),
        "budget_status": plan_result["budget_summary"]["status"],
        "total_hours": plan_result["total_hours"],
        "node_count": plan_result["node_count"],
        "reinforced_ids": plan_result["reinforced_ids"],
        "text_output": plan_result["text_output"],
    }


@router.get("/projects/{project_id}/plans/latest")
async def get_latest_plan_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径")

    raw_stages = json.loads(path.plan_json) if path.plan_json else {}
    audit = json.loads(path.audit_json) if path.audit_json else None

    # raw_stages 可能是 dict 或 list，统一为 list
    if isinstance(raw_stages, dict):
        stages = _dict_stages_to_list(raw_stages)
    else:
        stages = raw_stages

    return {
        "id": path.id,
        "project_id": path.project_id,
        "version": path.version,
        "stages": stages,
        "budget_status": path.budget_status,
        "total_hours": path.total_hours,
        "audit": audit,
    }


@router.get("/projects/{project_id}/explanation", response_model=ExplanationResponse)
async def get_explanation(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取最新路径的结构化解释。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    path = await get_latest_plan(db, project_id)
    if not path:
        raise NotFoundError("暂无学习路径")

    audit = json.loads(path.audit_json) if path.audit_json else None
    if not audit:
        raise NotFoundError("暂无审计数据")

    pack = get_domain_pack_service(project.domain)
    return build_explanation(audit, pack.nodes_by_id)
