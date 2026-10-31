"""Request correlation and log formatting.

Every request gets an id that appears in the response header, in every log line
written while handling it, and in the single access line logged when it finishes.
That id is the only way to tie a 500 in the log to the report a student sent.
"""

import json
import logging
import re
import secrets
import sys
import time
from contextvars import ContextVar

from app.core.config import settings

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

# A client-provided id is reused only when it is safe to echo back and log.
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")

# Attributes logging already provides, so extras do not overwrite them.
_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename", "funcName",
    "levelname", "levelno", "lineno", "message", "module", "msecs", "msg", "name",
    "pathname", "process", "processName", "relativeCreated", "stack_info",
    "taskName", "thread", "threadName", "request_id",
}


def new_request_id() -> str:
    return secrets.token_hex(8)


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "request_id": getattr(record, "request_id", "-"),
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                entry[key] = value
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str, separators=(",", ":"))


def configure_logging() -> None:
    """Send app and worker logs to stdout in one shape a log collector can parse."""
    if settings.log_json:
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s [%(request_id)s] %(message)s",
            "%H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIdFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(settings.log_level)

    # uvicorn configures its own handlers when the process starts. Sending its
    # records to the root handler keeps one shape for everything on stdout.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True

    # The middleware logs one line per request; uvicorn's copy would be a duplicate.
    access = logging.getLogger("uvicorn.access")
    access.handlers = [logging.NullHandler()]
    access.propagate = False


class RequestMiddleware:
    """Stamps every request with an id and logs the result when it completes."""

    def __init__(self, app):
        self.app = app
        self.log = logging.getLogger("access")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        provided = dict(scope["headers"]).get(b"x-request-id", b"").decode("latin-1")
        request_id = provided if _SAFE_ID.match(provided) else new_request_id()
        token = request_id_ctx.set(request_id)
        started = time.perf_counter()
        status = {"code": 500}

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status["code"] = message["status"]
                message["headers"].append((b"x-request-id", request_id.encode("latin-1")))
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
            client = scope.get("client")
            path = scope["path"]
            query = scope.get("query_string", b"").decode("latin-1")
            self.log.info(
                "%s %s -> %s in %s ms",
                scope["method"],
                f"{path}?{query}" if query else path,
                status["code"],
                elapsed_ms,
                extra={
                    "method": scope["method"],
                    "path": path,
                    "status": status["code"],
                    "duration_ms": elapsed_ms,
                    "client": client[0] if client else None,
                    "request_id": request_id,
                },
            )
            request_id_ctx.reset(token)
