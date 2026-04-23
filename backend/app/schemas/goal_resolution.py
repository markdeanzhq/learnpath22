from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class GoalResolutionPreviewRequest(BaseModel):
    goal_text: str = Field(min_length=1)
    requested_goal_type: Optional[str] = None
    domain: Literal["machine_learning"] = "machine_learning"


class GoalResolutionCandidateResponse(BaseModel):
    candidate_id: str
    goal_type: Literal["domain", "concept", "problem"]
    target_node_ids: list[str]
    mode: str
    description: str
    template_id: Optional[str] = None
    resolve_source: str
    source_breakdown: dict[str, float]
    score: float
    score_breakdown: dict[str, Any]
    explanation: str
    warnings: list[str] = Field(default_factory=list)


class GoalResolutionPreviewResponse(BaseModel):
    session_id: str
    expires_at: datetime
    auto_detected_goal_type: Literal["domain", "concept", "problem"]
    effective_goal_type: Literal["domain", "concept", "problem"]
    recommended_candidate_id: str
    candidates: list[GoalResolutionCandidateResponse]
