from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        code: int = 400,
        message: str = "Bad Request",
        *,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.details = details or {}


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(code=404, message=message)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation error"):
        super().__init__(code=422, message=message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        content = {"error": exc.message, "code": exc.code}
        if exc.details:
            content.update(exc.details)
        return JSONResponse(
            status_code=exc.code,
            content=content,
        )
