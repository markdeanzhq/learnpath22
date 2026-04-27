from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, Field

GoalType = Literal["domain", "concept", "problem"]
PathMode = Literal["standard", "compressed", "theory_first", "practice_first"]
CoverageStatus = Literal[
    "covered",
    "partial",
    "in_domain_uncovered",
    "adjacent_domain",
    "cross_domain",
    "out_of_domain",
    "ambiguous",
]
DomainDecision = Literal["in_domain", "cross_domain", "out_of_domain", "ambiguous"]
MlRelevance = Literal["core", "prerequisite", "application", "none", "unclear"]
CoverageResultType = Literal[
    "select_candidate",
    "confirm_partial",
    "answer_clarification",
    "review_extension_draft",
    "boundary_reject",
]
FeedbackIntentType = Literal[
    "compress_time",
    "increase_practice",
    "increase_theory",
    "adjust_deadline",
    "mark_known_nodes",
]


class GoalResolutionPreviewRequest(BaseModel):
    goal_text: str = Field(min_length=1)
    requested_goal_type: Optional[str] = None
    domain: Optional[str] = None


class GoalResolutionNodeRef(BaseModel):
    node_id: str
    node_name: str


class GoalResolutionCandidateResponse(BaseModel):
    candidate_id: str
    goal_type: GoalType
    target_node_ids: list[str]
    target_node_names: list[str] = Field(default_factory=list)
    target_nodes: list[GoalResolutionNodeRef] = Field(default_factory=list)
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
    auto_detected_goal_type: GoalType
    effective_goal_type: GoalType
    recommended_candidate_id: str
    candidates: list[GoalResolutionCandidateResponse]
    result_type: Literal["select_candidate"] = "select_candidate"
    coverage_status: Literal["covered", "adjacent_domain"] = "covered"
    goal_frame: Optional["GoalFrameV1"] = None
    goal_understanding: Optional["GoalUnderstandingV1"] = None
    pack_hash: Optional[str] = None
    project_graph_hash: Optional[str] = None
    audit_trace: Optional["AuditTraceRef"] = None
    warnings: list[str] = Field(default_factory=list)


class GoalUnderstandingEvidence(BaseModel):
    span: str
    label: str
    reason: str


class GoalUnderstandingV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    raw_text: str
    domain_decision: DomainDecision
    primary_domain: str
    ml_relevance: MlRelevance
    goal_type: Optional[GoalType] = None
    target_concepts: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    uncertainties: list[str] = Field(default_factory=list)
    clarification_question: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: list[GoalUnderstandingEvidence] = Field(default_factory=list)
    prompt_version: Optional[str] = None
    model: Optional[str] = None
    warnings: list[str] = Field(default_factory=list)


class GoalFramePlannerParameters(BaseModel):
    path_mode: Optional[PathMode] = None
    theory_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    practice_weight: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    weekly_hours: Optional[float] = Field(default=None, gt=0.0)
    deadline_weeks: Optional[int] = Field(default=None, gt=0)
    explanation_focus: list[str] = Field(default_factory=list)


class GoalFrameSource(BaseModel):
    source: Literal["rules", "llm", "fallback"]
    evidence: str
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class GoalFrameV1(BaseModel):
    schema_version: Literal["v1"] = "v1"
    raw_text: str
    domain: str
    goal_type: Optional[GoalType] = None
    target_concepts: list[str] = Field(default_factory=list)
    target_node_ids: list[str] = Field(default_factory=list)
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    planner_parameters: GoalFramePlannerParameters = Field(default_factory=GoalFramePlannerParameters)
    uncertainties: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    sources: list[GoalFrameSource] = Field(default_factory=list)


class AuditTraceRef(BaseModel):
    trace_type: Literal[
        "goal_resolution",
        "clarification",
        "variant_preview",
        "feedback_preview",
        "known_node_draft",
    ]
    trace_id: str
    pack_hash: Optional[str] = None
    project_graph_hash: Optional[str] = None


class CoverageResponseBase(BaseModel):
    result_type: CoverageResultType
    coverage_status: CoverageStatus
    goal_frame: GoalFrameV1
    goal_understanding: GoalUnderstandingV1
    pack_hash: Optional[str] = None
    project_graph_hash: Optional[str] = None
    audit_trace: Optional[AuditTraceRef] = None


class SelectCandidateCoverageResponse(CoverageResponseBase):
    result_type: Literal["select_candidate"]
    coverage_status: Literal["covered", "adjacent_domain"]
    session_id: str
    expires_at: datetime
    recommended_candidate_id: str
    candidates: list[GoalResolutionCandidateResponse]
    auto_detected_goal_type: GoalType
    effective_goal_type: GoalType
    warnings: list[str] = Field(default_factory=list)


class ConfirmPartialCoverageResponse(CoverageResponseBase):
    result_type: Literal["confirm_partial"]
    coverage_status: Literal["partial"]
    session_id: str
    expires_at: datetime
    covered_target_node_ids: list[str]
    missing_concepts: list[str]
    candidates: list[GoalResolutionCandidateResponse] = Field(default_factory=list)


class ClarificationQuestionOption(BaseModel):
    option_id: str
    label: str
    value: dict[str, Any] = Field(default_factory=dict)


class ClarificationQuestion(BaseModel):
    question_id: str
    field: str
    prompt: str
    options: list[ClarificationQuestionOption] = Field(default_factory=list)
    allow_free_text: bool = False


class AnswerClarificationCoverageResponse(CoverageResponseBase):
    result_type: Literal["answer_clarification"]
    coverage_status: Literal["ambiguous", "cross_domain"]
    clarification_session_id: str
    expires_at: datetime
    turn_count: int = 0
    max_turns: int = 3
    questions: list[ClarificationQuestion]


class ReviewExtensionDraftCoverageResponse(CoverageResponseBase):
    result_type: Literal["review_extension_draft"]
    coverage_status: Literal["in_domain_uncovered"]
    missing_concepts: list[str]
    draft_entry: dict[str, Any] = Field(default_factory=dict)
    session_id: Optional[str] = None
    expires_at: Optional[datetime] = None


class BoundaryRejectCoverageResponse(CoverageResponseBase):
    result_type: Literal["boundary_reject"]
    coverage_status: Literal["out_of_domain", "adjacent_domain"]
    reason_code: str
    reason_text: str
    rewrite_suggestions: list[str] = Field(default_factory=list)


CoveragePreviewResponse = Annotated[
    Union[
        SelectCandidateCoverageResponse,
        ConfirmPartialCoverageResponse,
        AnswerClarificationCoverageResponse,
        ReviewExtensionDraftCoverageResponse,
        BoundaryRejectCoverageResponse,
    ],
    Field(discriminator="result_type"),
]


class ClarificationAnswer(BaseModel):
    question_id: str
    selected_option_id: Optional[str] = None
    free_text: Optional[str] = None


class ClarificationAnswerRequest(BaseModel):
    answers: list[ClarificationAnswer] = Field(min_length=1)


class ClarificationSessionResponse(BaseModel):
    clarification_session_id: str
    status: Literal["active", "resolved", "rejected", "expired", "stale"]
    expires_at: datetime
    turn_count: int
    max_turns: int
    questions: list[ClarificationQuestion] = Field(default_factory=list)
    goal_frame: Optional[GoalFrameV1] = None
    coverage_response: Optional[CoveragePreviewResponse] = None


class VariantSummary(BaseModel):
    variant_id: str
    path_mode: PathMode
    budget_summary: dict[str, Any] = Field(default_factory=dict)
    included_node_ids: list[str] = Field(default_factory=list)
    excluded_node_ids: list[str] = Field(default_factory=list)
    audit_summary: dict[str, Any] = Field(default_factory=dict)


class VariantPreviewSessionResponse(BaseModel):
    variant_preview_id: str
    project_id: str
    status: Literal["active", "confirmed", "expired", "stale"]
    expires_at: datetime
    pack_hash: Optional[str] = None
    project_graph_hash: Optional[str] = None
    profile_hash: Optional[str] = None
    parameter_hash: Optional[str] = None
    variants: list[VariantSummary]


class KnownNodeConfirmationDraftResponse(BaseModel):
    draft_id: str
    feedback_preview_id: str
    project_id: str
    node_ids: list[str]
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["draft", "confirmed", "rejected", "expired", "stale"]
    expires_at: datetime


class FeedbackPreviewSessionResponse(BaseModel):
    feedback_preview_id: str
    project_id: str
    intent_type: FeedbackIntentType
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    controlled_parameters: dict[str, Any] = Field(default_factory=dict)
    diff: dict[str, Any] = Field(default_factory=dict)
    budget_delta: dict[str, Any] = Field(default_factory=dict)
    blocked_actions: list[str] = Field(default_factory=list)
    requires_confirmation: bool = True
    requires_second_confirm: bool = False
    variant_preview_id: Optional[str] = None
    known_node_draft: Optional[KnownNodeConfirmationDraftResponse] = None
    status: Literal["active", "confirmed", "expired", "stale", "rejected"]
    expires_at: datetime
    pack_hash: Optional[str] = None
    project_graph_hash: Optional[str] = None
