"""结构化路径解释 schemas"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class NodeExplanation(BaseModel):
    node_id: str
    node_name: str
    reason: str
    gap: Optional[dict[str, float]] = None
    decision_type: str


class OrderExplanation(BaseModel):
    node_id: str
    node_name: str
    priority_score: float
    goal_relevance: float
    factors: list[str]


class StageExplanation(BaseModel):
    node_id: str
    node_name: str
    assigned_stage: str
    reasons: list[str]


class BudgetExplanation(BaseModel):
    total_hours: float
    weekly_hours: float
    estimated_weeks: float
    status: str
    suggestion: str


class ReinforcementExplanation(BaseModel):
    node_id: str
    node_name: str
    gap: dict[str, float]
    reinforce_score: float
    reasons: list[str]


class DependencyChainExplanation(BaseModel):
    target_node_id: str
    target_node_name: str
    chain_node_ids: list[str]
    chain_node_names: list[str]
    reason: str


class ExplanationResponse(BaseModel):
    node_explanations: list[NodeExplanation]
    ordering_explanations: list[OrderExplanation]
    stage_explanations: list[StageExplanation]
    budget_explanation: Optional[BudgetExplanation] = None
    reinforcement_explanations: list[ReinforcementExplanation]
    dependency_chain_explanations: list[DependencyChainExplanation]
