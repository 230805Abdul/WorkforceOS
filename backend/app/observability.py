"""Structured logging and per-request context (request ID, client IP).

Every log line carries the request ID, so a user-reported "reference: 3f2a…" leads straight to the server log entries
for that request. Logs never contain passwords, tokens, cookies or SQL parameter values (see app/db.py).

LOG_FORMAT=json -> one JSON object per line (for log collectors, production default)
LOG_FORMAT=text -> human-readable lines (development default)
"""
import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

from app.config import LOG_FORMAT, LOG_LEVEL

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
client_ip_var: ContextVar[str | None] = ContextVar("client_ip", default=None)
user_agent_var: ContextVar[str | None] = ContextVar("user_agent", default=None)

security_log = logging.getLogger("workforceos.security")
access_log = logging.getLogger("workforceos.access")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get() or "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
        }
        entry.update(getattr(record, "fields", {}))  # structured extras: logger.info("...", extra={"fields": {...}})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


class TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        fields = getattr(record, "fields", {})
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        line = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<7} [{record.request_id}] {record.name}: {record.getMessage()}"
        line = f"{line} {extra}".rstrip()
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter() if LOG_FORMAT == "json" else TextFormatter())
    handler.addFilter(_ContextFilter())
    app_logger = logging.getLogger("workforceos")
    app_logger.handlers = [handler]
    app_logger.setLevel(LOG_LEVEL)
    app_logger.propagate = False
    # Our access log (method, path, status, duration, user) replaces uvicorn's, which would print every line twice.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    _configured = True
