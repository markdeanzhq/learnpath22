"""学习路径 schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class GeneratePlanRequest(BaseModel):
    pass  # 使用项目已有的 goal_text + 最新 profile 自动生成


class PathTaskItem(BaseModel):
    node_id: str
    name: str
    difficulty: int
    importance: int
    estimated_hours: float
    order_in_stage: int


class PathStageItem(BaseModel):
    stage_index: int
    stage_name: str
    tasks: list[PathTaskItem]
    estimated_hours: float
    empty_reason: str | None = None


class PlanResponse(BaseModel):
    id: str
    project_id: str
    version: int
    stages: list[PathStageItem]
    budget_status: str | None
    total_hours: float | None
    reinforced_ids: list[str] = []
    audit: dict[str, Any] | None = None
    text_output: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
