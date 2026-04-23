"""学习者画像 schemas"""
from __future__ import annotations

from datetime import datetime
from typing import Optional, Union

from pydantic import BaseModel, Field


class SubmitProfileRequest(BaseModel):
    math_level: int = Field(default=1, ge=1, le=5)
    coding_level: int = Field(default=1, ge=1, le=5)
    ml_level: int = Field(default=1, ge=1, le=5)
    theory_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    practice_weight: float = Field(default=0.5, ge=0.0, le=1.0)
    weekly_hours: float = Field(default=10.0, gt=0)
    deadline_weeks: Optional[int] = Field(default=None, ge=1)
    raw_answers_json: Optional[str] = None
    collector_trace_json: Optional[str] = None


class ProfileResponse(BaseModel):
    id: str
    project_id: str
    math_level: int
    coding_level: int
    ml_level: int
    theory_weight: float
    practice_weight: float
    weekly_hours: float
    deadline_weeks: Optional[int]
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionOption(BaseModel):
    label: str
    value: Union[float, int]


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
    value: Union[float, int]


class SubmitAnswersRequest(BaseModel):
    source: Optional[str] = None
    answers: list[AnswerItem]
