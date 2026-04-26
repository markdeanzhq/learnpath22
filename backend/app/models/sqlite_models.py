from __future__ import annotations

import uuid
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Float, ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class RuntimeSetting(Base):
    __tablename__ = "runtime_settings"

    setting_key: Mapped[str] = mapped_column(String(50), primary_key=True)
    setting_value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class LearningProject(Base):
    __tablename__ = "learning_projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    title: Mapped[str] = mapped_column(String(200))
    goal_text: Mapped[str] = mapped_column(Text)
    goal_type: Mapped[str] = mapped_column(String(20))
    domain: Mapped[str] = mapped_column(String(50), default="machine_learning")
    status: Mapped[str] = mapped_column(String(20), default="active")
    path_mode: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, default="standard")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # confirmed-resolution fields (task 1.2) — all nullable for backward compatibility
    requested_goal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    auto_detected_goal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confirmed_target_node_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed_mode: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    confirmed_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed_template_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    confirmed_resolve_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    confirmed_source_breakdown_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confirmed_candidate_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolution_pack_version: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    resolution_confirmed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)


class LearnerProfile(Base):
    __tablename__ = "learner_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    math_level: Mapped[int] = mapped_column(Integer, default=1)
    coding_level: Mapped[int] = mapped_column(Integer, default=1)
    ml_level: Mapped[int] = mapped_column(Integer, default=1)
    theory_weight: Mapped[float] = mapped_column(Float, default=0.5)
    practice_weight: Mapped[float] = mapped_column(Float, default=0.5)
    weekly_hours: Mapped[float] = mapped_column(Float, default=10.0)
    deadline_weeks: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    path_mode_preference: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    persona_label: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    persona_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    persona_evidence: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_answers_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    collector_trace_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50))
    content_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_json: Mapped[str] = mapped_column(Text)
    audit_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    budget_status: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    total_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class PathStage(Base):
    __tablename__ = "path_stages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"))
    stage_index: Mapped[int] = mapped_column(Integer)
    stage_name: Mapped[str] = mapped_column(String(50))
    node_count: Mapped[int] = mapped_column(Integer)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class PathTask(Base):
    __tablename__ = "path_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    stage_id: Mapped[str] = mapped_column(String(36), ForeignKey("path_stages.id"))
    node_id: Mapped[str] = mapped_column(String(50))
    node_name: Mapped[str] = mapped_column(String(200))
    order_in_stage: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer)
    importance: Mapped[int] = mapped_column(Integer)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class PlanExplanationCache(Base):
    __tablename__ = "plan_explanation_cache"
    __table_args__ = (
        UniqueConstraint("path_id", "polish_requested", name="uq_plan_explanation_cache_path_polish"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"))
    plan_version: Mapped[int] = mapped_column(Integer)
    polish_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    explanation_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    node_id: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(20))
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class GraphReviewStatus(Base):
    """项目级别的图谱节点/边审核状态。"""
    __tablename__ = "graph_review_status"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    element_type: Mapped[str] = mapped_column(String(10))  # 'node' or 'edge'
    element_id: Mapped[str] = mapped_column(String(100))   # node_id or "source->target::type"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/removed
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ResourceBinding(Base):
    __tablename__ = "resource_bindings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"))
    stage_name: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    node_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    title: Mapped[str] = mapped_column(String(200))
    url: Mapped[str] = mapped_column(String(500))
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_type: Mapped[str] = mapped_column(String(20), default="manual")
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class ProjectOverlaySource(Base):
    __tablename__ = "project_overlay_sources"
    __table_args__ = (
        UniqueConstraint("project_id", "source_id", name="uq_overlay_sources_project_source"),
    )

    source_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    source_type: Mapped[str] = mapped_column(String(30))
    content_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    raw_text_excerpt: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provider: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayExtractionSession(Base):
    __tablename__ = "project_overlay_extraction_sessions"
    __table_args__ = (
        UniqueConstraint("project_id", "session_id", name="uq_overlay_sessions_project_session"),
    )

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    mode: Mapped[str] = mapped_column(String(30), default="default")
    session_status: Mapped[str] = mapped_column(String(30), default="drafted")
    source_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warnings_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayNode(Base):
    __tablename__ = "project_overlay_nodes"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["project_overlay_extraction_sessions.project_id", "project_overlay_extraction_sessions.session_id"],
        ),
        UniqueConstraint("project_id", "node_id", name="uq_overlay_nodes_project_node"),
    )

    node_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    difficulty_final: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    importance_final: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    estimated_hours: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    req_math: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    req_coding: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    req_ml: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    theory_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    practice_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(30), default="unchecked")
    review_status: Mapped[str] = mapped_column(String(30), default="pending")
    planning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    promotion_status: Mapped[str] = mapped_column(String(30), default="not_promoted")
    source_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duplicate_candidates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legality_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    canonical_payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayEdge(Base):
    __tablename__ = "project_overlay_edges"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["project_overlay_extraction_sessions.project_id", "project_overlay_extraction_sessions.session_id"],
        ),
        UniqueConstraint("project_id", "edge_id", name="uq_overlay_edges_project_edge"),
    )

    edge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_node_id: Mapped[str] = mapped_column(Text)
    target_node_id: Mapped[str] = mapped_column(Text)
    relation_type: Mapped[str] = mapped_column(String(30))
    validation_status: Mapped[str] = mapped_column(String(30), default="unchecked")
    review_status: Mapped[str] = mapped_column(String(30), default="pending")
    planning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    promotion_status: Mapped[str] = mapped_column(String(30), default="not_promoted")
    source_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duplicate_candidates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    legality_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    canonical_payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayResource(Base):
    __tablename__ = "project_overlay_resources"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "session_id"],
            ["project_overlay_extraction_sessions.project_id", "project_overlay_extraction_sessions.session_id"],
        ),
        UniqueConstraint("project_id", "resource_id", name="uq_overlay_resources_project_resource"),
    )

    resource_id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    title: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    resource_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    validation_status: Mapped[str] = mapped_column(String(30), default="unchecked")
    review_status: Mapped[str] = mapped_column(String(30), default="pending")
    planning_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    promotion_status: Mapped[str] = mapped_column(String(30), default="not_promoted")
    source_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    provenance_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    duplicate_candidates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    validation_errors_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    canonical_payload_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayResourceBinding(Base):
    __tablename__ = "project_overlay_resource_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "resource_id"],
            ["project_overlay_resources.project_id", "project_overlay_resources.resource_id"],
        ),
        ForeignKeyConstraint(
            ["project_id", "source_result_id"],
            ["persisted_search_results.project_id", "persisted_search_results.result_id"],
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    resource_id: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(String(30))
    target_id: Mapped[str] = mapped_column(Text)
    source_result_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    binding_source: Mapped[str] = mapped_column(String(30), default="overlay")
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayProjectionState(Base):
    __tablename__ = "project_overlay_projection_states"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_overlay_projection_state_project"),
    )

    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(30), default="never_synced")
    overlay_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    projected_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayPromotionBatch(Base):
    __tablename__ = "project_overlay_promotion_batches"
    __table_args__ = (
        UniqueConstraint("project_id", "batch_id", name="uq_overlay_promotion_batches_project_batch"),
    )

    batch_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    status: Mapped[str] = mapped_column(String(30), default="previewed")
    requested_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    baseline_pack_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resulting_pack_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    preview_report_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class ProjectOverlayPromotionItem(Base):
    __tablename__ = "project_overlay_promotion_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["project_id", "batch_id"],
            ["project_overlay_promotion_batches.project_id", "project_overlay_promotion_batches.batch_id"],
        ),
        ForeignKeyConstraint(
            ["project_id", "source_session_id"],
            ["project_overlay_extraction_sessions.project_id", "project_overlay_extraction_sessions.session_id"],
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    batch_id: Mapped[str] = mapped_column(String(36))
    element_type: Mapped[str] = mapped_column(String(30))
    element_id: Mapped[str] = mapped_column(Text)
    source_session_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    source_ids_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    provenance_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


class PersistedSearchResult(Base):
    __tablename__ = "persisted_search_results"
    __table_args__ = (
        UniqueConstraint("project_id", "result_id", name="uq_persisted_search_results_project_result"),
        ForeignKeyConstraint(
            ["project_id", "source_id"],
            ["project_overlay_sources.project_id", "project_overlay_sources.source_id"],
        ),
    )

    result_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    source_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    query: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(50))
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    retrieved_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quality_status: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)


def _naive_utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _default_expires_at() -> datetime:
    return _naive_utc_now() + timedelta(hours=24)


class GoalResolutionSession(Base):
    """Stores in-flight goal resolution state with a 24-hour TTL."""
    __tablename__ = "goal_resolution_sessions"

    session_id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    goal_text_hash: Mapped[str] = mapped_column(String(64))
    domain: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    requested_goal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    auto_detected_goal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    effective_goal_type: Mapped[str] = mapped_column(String(30))
    pack_version: Mapped[str] = mapped_column(String(20))
    pack_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    graph_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    candidates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_candidate_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(default=_default_expires_at)
    created_at: Mapped[datetime] = mapped_column(default=_naive_utc_now)
