"""One shape for every error the API returns.

Clients read ``detail`` (unchanged from FastAPI's default) and can branch on
``error``. ``request_id`` is the value the student quotes when something breaks,
and it matches the id in the log line written for the same request. Internal
failures are logged with their traceback and reported as a plain sentence, so a
stack trace, a table name or a bucket key never reaches a student's browser.
"""

import logging

from botocore.exceptions import BotoCoreError, ClientError
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.observability import request_id_ctx

log = logging.getLogger("app.errors")

UNEXPECTED = "Something went wrong on our side. Please try again."
DB_DOWN = "The service is busy, please try again in a moment."
STORAGE_DOWN = "Files are unreachable right now, please try again in a moment."


def _body(error: str, detail, code: int) -> JSONResponse:
    return JSONResponse(
        status_code=code,
        content={"error": error, "detail": detail, "request_id": request_id_ctx.get()},
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        # Field messages are already safe summaries; log the raw input type only.
        log.info("validation failed", extra={"path": request.url.path, "errors": len(exc.errors())})
        return _body("validation_failed", exc.errors(), 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        # FastAPI HTTPException subclasses this, and headers carry Retry-After on a 429.
        response = _body("request_failed", exc.detail, exc.status_code)
        for key, value in (getattr(exc, "headers", None) or {}).items():
            response.headers[key] = value
        return response

    @app.exception_handler(OperationalError)
    @app.exception_handler(DBAPIError)
    async def database_error(request: Request, exc: DBAPIError):
        log.error("database failure", exc_info=exc, extra={"path": request.url.path})
        return _body("service_unavailable", DB_DOWN, 503)

    @app.exception_handler(ClientError)
    @app.exception_handler(BotoCoreError)
    async def storage_error(request: Request, exc: Exception):
        log.error("object storage failure", exc_info=exc, extra={"path": request.url.path})
        return _body(
            "storage_unavailable",
            STORAGE_DOWN,
            502,
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        log.exception("unhandled error", extra={"path": request.url.path})
        return _body("internal_error", UNEXPECTED, 500)
