from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: int = 400, message: str = "Bad Request"):
        self.code = code
        self.message = message


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found"):
        super().__init__(code=404, message=message)


class ValidationError(AppError):
    def __init__(self, message: str = "Validation error"):
        super().__init__(code=422, message=message)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.code,
            content={"error": exc.message, "code": exc.code},
        )
