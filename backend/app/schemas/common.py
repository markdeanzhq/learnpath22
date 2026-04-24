"""通用响应模型"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ApiResponse(BaseModel):
    data: Any = None
    meta: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: str
    code: int
    reason_code: str | None = None
    reason_text: str | None = None
