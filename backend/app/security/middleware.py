"""Pure-ASGI middlewares that every request passes through, outermost first:

  RequestContextMiddleware  request ID, client IP, security headers on EVERY response, one access-log line
  CrossSiteMiddleware       refuses state-changing requests that come from another site (Origin / Referer / Sec-Fetch-Site)
  RateLimitMiddleware       per-session / per-IP request budgets (429 + Retry-After)
  BodyLimitMiddleware       JSON-only bodies, at most MAX_REQUEST_BODY_BYTES (413 / 415) before anything is parsed

Pure ASGI (instead of @app.middleware) so a large body can be refused while it is still arriving.
"""
import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass
from urllib.parse import urlsplit

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from starlette.concurrency import run_in_threadpool
from starlette.requests import HTTPConnection
from starlette.responses import JSONResponse

from app.errors import SESSION_COOKIE
from app.observability import access_log, client_ip_var, request_id_var, security_log, user_agent_var
from app.security.headers import security_headers

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _error(status: int, detail: str, code: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"detail": detail, "code": code}, status_code=status, headers=headers)


def _report(action: str, outcome: str, **metadata) -> None:
    """Security event -> audit log (imported lazily: the audit module imports the database layer)."""
    from app.audit import record_event

    record_event(action, category="security", outcome=outcome, metadata=metadata)


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        conn = HTTPConnection(scope)
        incoming = conn.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID.match(incoming) else uuid.uuid4().hex
        tokens = (request_id_var.set(request_id), client_ip_var.set(conn.client.host if conn.client else None),
                  user_agent_var.set((conn.headers.get("user-agent") or "")[:200] or None))
        scope.setdefault("state", {})
        started, status, response_started = time.perf_counter(), 500, False

        async def send_with_headers(message):
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                status, response_started = message["status"], True
                existing = {k.lower() for k, _ in message.get("headers", [])}
                extra = [(k, v) for k, v in security_headers(scope["path"]) if k not in existing]
                message["headers"] = [*message.get("headers", []), *extra, (b"x-request-id", request_id.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            # Caught HERE (not by Starlette's outermost handler) so the reply still gets security headers and the
            # reference ID; the full traceback goes to the server log only.
            logging.getLogger("workforceos").exception("Unhandled error")
            if response_started:
                raise
            await _error(500, f"Something went wrong on the server (reference: {request_id}).", "server_error")(
                scope, receive, send_with_headers)
        finally:
            user = scope["state"].get("user_id")
            access_log.info("%s %s -> %s", scope["method"], scope["path"], status, extra={"fields": {
                "status": status, "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "client_ip": client_ip_var.get(), **({"user_id": user} if user else {})}})
            for var, token in zip((request_id_var, client_ip_var, user_agent_var), tokens):
                var.reset(token)


class CrossSiteMiddleware:
    """Defence in depth against CSRF, in addition to SameSite cookies and the per-session CSRF token:
    a state-changing request is refused if the browser says it came from another site."""

    def __init__(self, app, allowed_origins: list[str]):
        self.app = app
        self.allowed = {o.rstrip("/") for o in allowed_origins}

    def _refusal(self, headers) -> str | None:
        origin = headers.get("origin")
        if origin:  # browsers send Origin on cross-origin requests and on all POST/PUT/PATCH/DELETE from fetch()
            return None if origin.rstrip("/") in self.allowed else f"origin {origin}"
        if headers.get("sec-fetch-site") == "cross-site":
            return "sec-fetch-site cross-site"
        referer = headers.get("referer")
        if referer:
            parts = urlsplit(referer)
            if f"{parts.scheme}://{parts.netloc}" not in self.allowed:
                return "referer from another site"
        return None  # no browser signals at all (e.g. curl, scripts): the session cookie + CSRF token checks still apply

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["method"] in UNSAFE_METHODS:
            reason = self._refusal(HTTPConnection(scope).headers)
            if reason:
                security_log.warning("Cross-site request refused", extra={"fields": {"reason": reason, "path": scope["path"]}})
                await run_in_threadpool(_report, "security.cross_site_refused", "denied", reason=reason, path=scope["path"])
                return await _error(403, "Cross-site request refused.", "bad_origin")(scope, receive, send)
        return await self.app(scope, receive, send)


@dataclass(frozen=True)
class RateLimits:
    read: str
    write: str
    auth: str
    sensitive: str
    per_ip: str


AUTH_PATHS = {"/api/auth/login", "/api/auth/register", "/api/auth/reset-password", "/api/auth/reauthenticate",
              "/api/auth/change-password"}
_SENSITIVE = [re.compile(p) for p in (
    r"^/api/users$", r"^/api/users/[^/]+/(reset-link|revoke-sessions|roles|status)$", r"^/api/roles(/[^/]+)?$",
    r"^/api/demo/reset$")]


def classify(method: str, path: str) -> str:
    if method not in UNSAFE_METHODS:
        return "read"
    if path in AUTH_PATHS:
        return "auth"
    if any(p.match(path) for p in _SENSITIVE):
        return "sensitive"
    return "write"


class RateLimitMiddleware:
    """Budgets per signed-in session (or per IP address when not signed in), stricter for sign-in and admin actions,
    plus one generous budget per IP address for everything. In-memory: correct for ONE backend process. Several
    processes/servers need a shared store such as Redis (limits supports it: docs/SECURITY.md)."""

    def __init__(self, app, limits: RateLimits):
        self.app = app
        self.limiter = MovingWindowRateLimiter(MemoryStorage())
        self.items = {name: parse(getattr(limits, name)) for name in ("read", "write", "auth", "sensitive", "per_ip")}
        self._reported: dict[str, float] = {}

    def _identity(self, conn: HTTPConnection, category: str, ip: str) -> str:
        cookie = conn.cookies.get(SESSION_COOKIE)
        if cookie and category != "auth":  # sign-in attempts are counted per address, signed in or not
            return "s:" + hashlib.sha256(cookie.encode()).hexdigest()[:32]
        return "ip:" + ip

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        conn = HTTPConnection(scope)
        ip = conn.client.host if conn.client else "unknown"
        category = classify(scope["method"], scope["path"])
        checks = [("per_ip", "ip:" + ip), (category, self._identity(conn, category, ip))]
        for name, key in checks:
            item = self.items[name]
            if not self.limiter.hit(item, name, key):
                retry = self._retry_after(item, name, key)
                await self._log_once(name, key, scope["path"], retry)
                return await _error(429, f"Too many requests. Please wait {retry} seconds and try again.", "rate_limited",
                                    {"Retry-After": str(retry)})(scope, receive, send)
        return await self.app(scope, receive, send)

    def _retry_after(self, item, name: str, key: str) -> int:
        stats = self.limiter.get_window_stats(item, name, key)
        return max(1, int(stats.reset_time - time.time()) + 1)

    async def _log_once(self, name: str, key: str, path: str, retry: int) -> None:
        """Record abuse once per key and window, not for every refused request (that would flood the audit log)."""
        now = time.time()
        if self._reported.get(f"{name}|{key}", 0) > now:
            return
        self._reported[f"{name}|{key}"] = now + retry
        who = key.split(":", 1)[0]
        security_log.warning("Rate limit exceeded", extra={"fields": {"limit": name, "by": who, "path": path}})
        await run_in_threadpool(_report, "security.rate_limited", "denied", limit=name, path=path,
                                keyed_by="session" if who == "s" else "ip address")


class BodyLimitMiddleware:
    def __init__(self, app, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in UNSAFE_METHODS:
            return await self.app(scope, receive, send)
        headers = HTTPConnection(scope).headers
        too_big = _error(413, f"The request is too large (limit {self.max_bytes // 1024} KB).", "payload_too_large")
        length = headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > self.max_bytes):
            return await too_big(scope, receive, send)

        # Read the body ourselves (it's small by definition), stopping as soon as it exceeds the limit,
        # then hand the app an identical stream.
        body, more = b"", True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body += message.get("body", b"")
            more = message.get("more_body", False)
            if len(body) > self.max_bytes:
                return await too_big(scope, receive, send)

        content_type = headers.get("content-type", "").split(";")[0].strip().lower()
        if body and content_type != "application/json":
            return await _error(415, "Send the request body as JSON (Content-Type: application/json).",
                                "unsupported_media_type")(scope, receive, send)

        delivered = False

        async def replay():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await self.app(scope, replay, send)
