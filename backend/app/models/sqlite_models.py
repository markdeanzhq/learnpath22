from __future__ import annotations

import uuid
from typing import Optional
from datetime import datetime, timedelta, timezone

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
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
    requested_goal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    auto_detected_goal_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    effective_goal_type: Mapped[str] = mapped_column(String(30))
    pack_version: Mapped[str] = mapped_column(String(20))
    graph_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    candidates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_candidate_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    expires_at: Mapped[datetime] = mapped_column(default=_default_expires_at)
    created_at: Mapped[datetime] = mapped_column(default=_naive_utc_now)
