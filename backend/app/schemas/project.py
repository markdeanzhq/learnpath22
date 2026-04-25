"""项目相关 schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator

DEFAULT_PATH_MODE = "standard"
ALLOWED_PATH_MODES = {"standard", "compressed", "theory_first", "practice_first"}


def validate_path_mode(path_mode: str | None) -> str:
    mode = path_mode or DEFAULT_PATH_MODE
    if mode not in ALLOWED_PATH_MODES:
        raise ValueError("INVALID_PATH_MODE")
    return mode


class CreateProjectRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    goal_text: str = Field(min_length=1)
    domain: Optional[str] = None
    resolution_session_id: str = Field(min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    path_mode: str = "standard"
    goal_type: Optional[str] = Field(default=None, pattern="^(domain|concept|problem)$")


class UpdateProjectGoalResolutionRequest(BaseModel):
    goal_text: str = Field(min_length=1)
    domain: Optional[str] = None
    resolution_session_id: str = Field(min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    path_mode: str | None = None
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
    path_mode: str = "standard"
    created_at: datetime
    updated_at: datetime
    goal_resolution: ProjectGoalResolutionSummary | None = None

    @field_validator("path_mode", mode="before")
    @classmethod
    def normalize_path_mode(cls, value: str | None) -> str:
        return validate_path_mode(value)

    model_config = {"from_attributes": True}


class DeleteProjectResponse(BaseModel):
    id: str
    message: str
