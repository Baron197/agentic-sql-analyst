"""JSON structured logs: one line per request, plus one per finished run (with its run_id).

Never logged: questions, answers, passwords, cookies, or tokens.
"""

import json
import logging
import sys
import time
import uuid
from datetime import UTC, datetime

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

_FIELDS = ("request_id", "method", "path", "status", "ms", "user_id", "run_id", "stream", "code")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        line.update({k: getattr(record, k) for k in _FIELDS if hasattr(record, k)})
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(line, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    logger = logging.getLogger("sql_analyst.api")
    if not any(isinstance(h.formatter, JsonFormatter) for h in logger.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False


class RequestLogMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        request.state.request_id = request_id
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        logging.getLogger("sql_analyst.api").info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "ms": round((time.perf_counter() - started) * 1000, 1),
                "user_id": getattr(request.state, "user_id", None),
                "run_id": getattr(request.state, "run_id", None),
            },
        )
        return response
