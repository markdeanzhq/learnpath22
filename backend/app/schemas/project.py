"""项目相关 schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal_text: str = Field(min_length=1)
    domain: Optional[str] = None
    resolution_session_id: str = Field(min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    goal_type: Optional[str] = Field(default=None, pattern="^(domain|concept|problem)$")


class UpdateProjectGoalResolutionRequest(BaseModel):
    goal_text: str = Field(min_length=1)
    domain: Optional[str] = None
    resolution_session_id: str = Field(min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    goal_type: Optional[str] = Field(default=None, pattern="^(domain|concept|problem)$")


class ProjectGoalResolutionSummary(BaseModel):
    requested_goal_type: Optional[str] = None
    auto_detected_goal_type: Optional[str] = None
    selected_candidate_id: str
    confirmed_target_node_ids: list[str]


class ProjectResponse(BaseModel):
    id: str
    title: str
    goal_text: str
    goal_type: str
    domain: str
    status: str
    created_at: datetime
    updated_at: datetime
    goal_resolution: ProjectGoalResolutionSummary | None = None

    model_config = {"from_attributes": True}


class DeleteProjectResponse(BaseModel):
    id: str
    message: str
