"""学习者画像 schemas"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SubmitProfileRequest(BaseModel):
    math_level: int = Field(default=1, ge=1, le=5)
    coding_level: int = Field(default=1, ge=1, le=5)
    ml_level: int = Field(default=1, ge=1, le=5)
    theory_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    practice_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    weekly_hours: float = Field(default=10.0, gt=0)
    deadline_weeks: int | None = Field(default=None, ge=1)
    raw_answers_json: str | None = None
    collector_trace_json: str | None = None


class ProfileResponse(BaseModel):
    id: str
    project_id: str
    math_level: int
    coding_level: int
    ml_level: int
    theory_weight: float
    practice_weight: float
    weekly_hours: float
    deadline_weeks: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionOption(BaseModel):
    label: str
    value: float | int


class CollectorQuestion(BaseModel):
    id: str
    field: str
    question: str
    options: list[QuestionOption]


class CollectorQuestionsResponse(BaseModel):
    questions: list[CollectorQuestion]
    source: str  # "llm" or "static"


class AnswerItem(BaseModel):
    question_id: str = ""
    field: str = ""  # LLM 问卷用 field 映射
    value: float | int


class SubmitAnswersRequest(BaseModel):
    answers: list[AnswerItem]
