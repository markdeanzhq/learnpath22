import uuid
from datetime import datetime

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def gen_uuid() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


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
    deadline_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_answers_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    collector_trace_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    url: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200))
    source_type: Mapped[str] = mapped_column(String(50))
    content_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    plan_json: Mapped[str] = mapped_column(Text)
    audit_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    total_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class PathStage(Base):
    __tablename__ = "path_stages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    path_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_paths.id"))
    stage_index: Mapped[int] = mapped_column(Integer)
    stage_name: Mapped[str] = mapped_column(String(50))
    node_count: Mapped[int] = mapped_column(Integer)
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)


class PathTask(Base):
    __tablename__ = "path_tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    stage_id: Mapped[str] = mapped_column(String(36), ForeignKey("path_stages.id"))
    node_id: Mapped[str] = mapped_column(String(50))
    node_name: Mapped[str] = mapped_column(String(200))
    order_in_stage: Mapped[int] = mapped_column(Integer)
    difficulty: Mapped[int] = mapped_column(Integer)
    importance: Mapped[int] = mapped_column(Integer)
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    node_id: Mapped[str] = mapped_column(String(50))
    event_type: Mapped[str] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)


class GraphReviewStatus(Base):
    """项目级别的图谱节点/边审核状态。"""
    __tablename__ = "graph_review_status"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("learning_projects.id"))
    element_type: Mapped[str] = mapped_column(String(10))  # 'node' or 'edge'
    element_id: Mapped[str] = mapped_column(String(100))   # node_id or "source->target"
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/confirmed/removed
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)
