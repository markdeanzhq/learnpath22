"""进度追踪 schemas"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class AddTrackingEventRequest(BaseModel):
    node_id: str
    event_type: str = Field(pattern="^(start|complete|skip)$")
    note: str | None = None


class TrackingEventResponse(BaseModel):
    id: str
    project_id: str
    node_id: str
    event_type: str
    note: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class TrackingSummary(BaseModel):
    total_nodes: int
    completed: int
    in_progress: int
    skipped: int
    pending: int
    completion_rate: float


class ReplanRequest(BaseModel):
    reason: str = "画像更新后重规划"
    mode: str = Field(default="profile_update", pattern="^(progress_aware|profile_update)$")
