from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, details: Any = None):
        self.status, self.code, self.details = status, code, details


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(_req: Request, err: ApiError):
        body = {"error": err.code}
        if err.details is not None:
            body["details"] = err.details
        return JSONResponse(body, status_code=err.status)

    @app.exception_handler(RequestValidationError)
    async def invalid(_req: Request, err: RequestValidationError):
        details = [
            {"field": ".".join(map(str, e["loc"][1:])), "message": e["msg"]} for e in err.errors()
        ]
        return JSONResponse({"error": "invalid_request", "details": details}, status_code=422)
