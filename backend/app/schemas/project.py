"""项目相关 schemas"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal_text: str = Field(min_length=1)
    goal_type: str = Field(default="domain", pattern="^(domain|concept|problem)$")
    domain: str = Field(default="machine_learning")


class ProjectResponse(BaseModel):
    id: str
    title: str
    goal_text: str
    goal_type: str
    domain: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DeleteProjectResponse(BaseModel):
    id: str
    message: str
