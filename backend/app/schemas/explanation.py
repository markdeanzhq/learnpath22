"""结构化路径解释 schemas"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


class NodeExplanation(BaseModel):
    node_id: str
    node_name: str
    reason: str
    gap: Optional[dict[str, float]] = None
    decision_type: str
    raw_reason: Optional[str] = None


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
    rationale: Optional[str] = None
    raw_rationale: Optional[str] = None


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


class ExplanationProvenance(BaseModel):
    truth_source: Literal["plan_audit_snapshot"] = "plan_audit_snapshot"
    fallback_used: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)
    live_pack_fields: list[str] = Field(default_factory=list)


class PolishMeta(BaseModel):
    requested: bool = False
    applied: bool = False
    scope: list[str] = Field(default_factory=list)
    fallback_reason: Optional[str] = None


class OverviewSummary(BaseModel):
    headline: str
    goal_names: list[str] = Field(default_factory=list)
    node_count: int = 0
    total_hours: Optional[float] = None
    budget_status: Optional[str] = None
    path_mode: Optional[str] = None
    notes: list[str] = Field(default_factory=list)


class GoalResolutionSummary(BaseModel):
    final_goal_text: Optional[str] = None
    goal_type: Optional[str] = None
    mode: Optional[str] = None
    resolve_source: Optional[str] = None
    target_node_ids: list[str] = Field(default_factory=list)
    target_node_names: list[str] = Field(default_factory=list)
    source_breakdown: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class GenerationStep(BaseModel):
    step_id: str
    title: str
    summary: str
    evidence_items: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)


class NodeGroupSummary(BaseModel):
    group_id: Literal["target", "prerequisite", "reinforced"]
    title: str
    summary: str
    node_ids: list[str] = Field(default_factory=list)
    nodes: list[dict[str, Any]] = Field(default_factory=list)


class OrderingSummary(BaseModel):
    summary: str
    mode: Optional[str] = None
    ordered_node_ids: list[str] = Field(default_factory=list)
    key_factors: list[str] = Field(default_factory=list)


class StageSummary(BaseModel):
    summary: str
    stage_count: int = 0
    stages: list[dict[str, Any]] = Field(default_factory=list)


class ReadableBudgetSummary(BaseModel):
    summary: str
    total_hours: Optional[float] = None
    weekly_hours: Optional[float] = None
    estimated_weeks: Optional[float] = None
    status: Optional[str] = None
    path_mode: Optional[str] = None
    compressed_dependency_note: Optional[str] = None


class TraceSummary(BaseModel):
    pack_version: Optional[str] = None
    project_graph_hash: Optional[str] = None
    overlay_node_count: int = 0
    overlay_edge_count: int = 0
    overlay_lineage_items: list[dict[str, Any]] = Field(default_factory=list)
    fallback_used: bool = False
    fallback_reasons: list[str] = Field(default_factory=list)
    live_pack_fields: list[str] = Field(default_factory=list)


class AuditHighlight(BaseModel):
    key: str
    title: str
    summary: str
    value: Optional[Any] = None
    source: Optional[str] = None


class ExplanationReadability(BaseModel):
    overview_summary: OverviewSummary
    goal_resolution_summary: GoalResolutionSummary
    generation_steps: list[GenerationStep] = Field(default_factory=list)
    node_groups: list[NodeGroupSummary] = Field(default_factory=list)
    ordering_summary: OrderingSummary
    stage_summary: StageSummary
    budget_summary: Optional[ReadableBudgetSummary] = None
    trace_summary: TraceSummary
    audit_highlights: list[AuditHighlight] = Field(default_factory=list)


class ExplanationMeta(BaseModel):
    plan_version: Optional[int] = None
    pack_version: Optional[str] = None
    project_graph_hash: Optional[str] = None
    provenance: ExplanationProvenance = Field(default_factory=ExplanationProvenance)
    polish: PolishMeta = Field(default_factory=PolishMeta)


class ExplanationResponse(BaseModel):
    node_explanations: list[NodeExplanation]
    ordering_explanations: list[OrderExplanation]
    stage_explanations: list[StageExplanation]
    budget_explanation: Optional[BudgetExplanation] = None
    reinforcement_explanations: list[ReinforcementExplanation]
    dependency_chain_explanations: list[DependencyChainExplanation]
    readability: Optional[ExplanationReadability] = None
    meta: Optional[ExplanationMeta] = None


ExplanationQuestionId = Literal[
    "why_path_order",
    "why_include_node",
    "why_stage_assignment",
    "budget_feasibility",
    "what_if_time_limited",
]


class EvidenceRef(BaseModel):
    source: str
    key: Optional[str] = None
    node_id: Optional[str] = None
    summary: Optional[str] = None


class ExplanationAskRequest(BaseModel):
    question_id: ExplanationQuestionId
    node_id: Optional[str] = None

    @model_validator(mode="after")
    def validate_node_specific_question(self):
        if self.question_id in {"why_include_node", "why_stage_assignment"} and not self.node_id:
            raise ValueError("node_id is required for node-specific explanation questions")
        return self


class ExplanationAskResponse(BaseModel):
    question_id: ExplanationQuestionId
    answer: str
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    ai_used: bool = False
    fallback_reason: Optional[str] = None
