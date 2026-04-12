"""画像管理 API"""
import json

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db
from app.core.exceptions import NotFoundError
from app.repositories.profile_repository import create_profile, get_latest_profile
from app.repositories.project_repository import get_project
from app.schemas.profile import (
    CollectorQuestionsResponse,
    ProfileResponse,
    SubmitAnswersRequest,
    SubmitProfileRequest,
)
from app.services.profile_collector_service import (
    get_collector_questions,
    map_answers_to_profile,
)

router = APIRouter()


@router.post("/projects/{project_id}/profiles", response_model=ProfileResponse)
async def submit_profile(
    project_id: str,
    req: SubmitProfileRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    profile = await create_profile(
        db,
        project_id=project_id,
        math_level=req.math_level,
        coding_level=req.coding_level,
        ml_level=req.ml_level,
        theory_weight=req.theory_weight,
        practice_weight=req.practice_weight,
        weekly_hours=req.weekly_hours,
        deadline_weeks=req.deadline_weeks,
        raw_answers_json=req.raw_answers_json,
        collector_trace_json=req.collector_trace_json,
    )
    return profile


@router.get("/projects/{project_id}/profiles/latest", response_model=ProfileResponse)
async def get_latest_profile_endpoint(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    profile = await get_latest_profile(db, project_id)
    if not profile:
        raise NotFoundError("暂无画像数据")
    return profile


@router.post(
    "/projects/{project_id}/collector/questions",
    response_model=CollectorQuestionsResponse,
)
async def get_questions(
    project_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取画像澄清问题（LLM 生成或静态兜底）。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")
    questions, source = await get_collector_questions(project.goal_text)
    return CollectorQuestionsResponse(questions=questions, source=source)


@router.post(
    "/projects/{project_id}/collector/submit",
    response_model=ProfileResponse,
)
async def submit_answers(
    project_id: str,
    req: SubmitAnswersRequest,
    db: AsyncSession = Depends(get_db),
):
    """提交问卷答案，自动映射为画像参数并保存。"""
    project = await get_project(db, project_id)
    if not project:
        raise NotFoundError("项目不存在")

    mapped = map_answers_to_profile([a.model_dump() for a in req.answers])
    profile = await create_profile(
        db,
        project_id=project_id,
        math_level=mapped.get("math_level", 1),
        coding_level=mapped.get("coding_level", 1),
        ml_level=mapped.get("ml_level", 1),
        theory_weight=mapped.get("theory_weight", 0.5),
        practice_weight=mapped.get("practice_weight", 0.5),
        weekly_hours=mapped.get("weekly_hours", 10.0),
        raw_answers_json=json.dumps([a.model_dump() for a in req.answers], ensure_ascii=False),
        collector_trace_json=json.dumps({"source": "collector", "mapped": mapped}, ensure_ascii=False),
    )
    return profile
