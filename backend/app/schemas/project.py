"""项目相关 schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

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
    selected_candidate_id: Optional[str] = Field(default=None, min_length=1)
    path_mode: str = "standard"
    accept_partial: bool = False
    creation_mode: Literal["confirmed", "extension_review"] = "confirmed"
    goal_type: Optional[str] = Field(default=None, pattern="^(domain|concept|problem)$")


class UpdateProjectGoalResolutionRequest(BaseModel):
    goal_text: str = Field(min_length=1)
    domain: Optional[str] = None
    resolution_session_id: str = Field(min_length=1)
    selected_candidate_id: str = Field(min_length=1)
    path_mode: str | None = None
    accept_partial: bool = False
    goal_type: Optional[str] = Field(default=None, pattern="^(domain|concept|problem)$")


class ProjectGoalResolutionSummary(BaseModel):
    requested_goal_type: Optional[str] = None
    auto_detected_goal_type: Optional[str] = None
    selected_candidate_id: str
    confirmed_target_node_ids: list[str]
    partial_accepted: bool = False
    missing_concepts: list[str] = Field(default_factory=list)


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


class ProjectWorkflowAction(BaseModel):
    action: str
    label: str
    description: str
    route: str
    enabled: bool = True
    reason: str | None = None
    blockers: list[str] = Field(default_factory=list)
    route_query: dict[str, str] = Field(default_factory=dict)


class ProjectWorkflowStep(BaseModel):
    key: str
    label: str
    status: Literal["pending", "active", "completed", "blocked", "warning"]
    summary: str
    action: ProjectWorkflowAction | None = None


class ProjectWorkflowStateResponse(BaseModel):
    project_id: str
    project_status: str
    updated_at: datetime
    current_stage: str
    recommended_next_action: ProjectWorkflowAction
    steps: list[ProjectWorkflowStep]
    goal: dict[str, Any]
    profile: dict[str, Any]
    overlay: dict[str, Any]
    path: dict[str, Any]
    tracking: dict[str, Any]


class DeleteProjectResponse(BaseModel):
    id: str
    message: str
