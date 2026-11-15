"""One consistent JSON error shape for the whole API:

    {"detail": "Human readable message", "errors": {"field": "What is wrong"}, "code": "machine_readable_reason"}

`errors` is only present for problems tied to specific form fields; `code` only where the frontend needs to react
to a specific situation (e.g. "session_expired", "csrf_failed", "rate_limited").
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy.exc import DataError, IntegrityError, OperationalError, ProgrammingError

from app.observability import request_id_var
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("workforceos")


SESSION_COOKIE = "wos_session"


class ApiError(Exception):
    def __init__(self, status_code: int, detail: str, errors: dict[str, str] | None = None, *, code: str | None = None,
                 headers: dict[str, str] | None = None, clear_session: bool = False):
        self.status_code = status_code
        self.detail = detail
        self.errors = errors or {}
        self.code = code
        self.headers = headers or {}
        self.clear_session = clear_session  # also delete the session cookie in the browser


def _friendly(err: dict, field: str) -> str:
    kind, ctx = err["type"], err.get("ctx", {})
    if kind == "missing":
        return "This field is required"
    if kind == "string_too_short":
        return "This field is required" if ctx.get("min_length") == 1 else f"Must be at least {ctx['min_length']} characters"
    if kind == "string_too_long":
        return f"Must be at most {ctx['max_length']} characters"
    if kind == "greater_than_equal":
        return f"Must be at least {ctx['ge']}"
    if kind == "less_than_equal":
        return f"Must be at most {ctx['le']}"
    if kind in ("enum", "literal_error"):
        return "Select a valid option"
    if kind == "string_pattern_mismatch":
        return "Invalid format"
    if kind == "extra_forbidden":
        return "This field cannot be changed here"
    if field == "email":
        return "Enter a valid email address"
    if kind == "value_error":
        return str(ctx.get("error", err["msg"])).removeprefix("Value error, ")
    return err["msg"]


def db_error_summary(exc: Exception) -> str:
    """What went wrong in the database, WITHOUT the data involved. (PostgreSQL's own messages can quote values, e.g.
    'Key (lower(email))=(someone@example.com) already exists', so we log the error class, code and constraint only.)"""
    orig = getattr(exc, "orig", exc)
    diag = getattr(orig, "diag", None)
    parts = [type(orig).__name__]
    if getattr(orig, "sqlstate", None):
        parts.append(f"sqlstate={orig.sqlstate}")
    if diag is not None and getattr(diag, "constraint_name", None):
        parts.append(f"constraint={diag.constraint_name}")
    return " ".join(parts)


def _body(detail: str, errors: dict[str, str] | None = None, code: str | None = None) -> dict:
    return {"detail": detail, **({"errors": errors} if errors else {}), **({"code": code} if code else {})}


# Refusals worth a security record: someone tried something they may not do. (Plain 401s, e.g. a browser asking
# "am I signed in?", are normal and not recorded; failed sign-ins are recorded by the auth router itself.)
AUDITED_REFUSALS = {"forbidden", "privilege_escalation", "self_change", "csrf_failed", "last_super_admin", "locked_role",
                    "registration_disabled"}


def _audit_refusal(request: Request, exc: ApiError) -> None:
    from app.audit import actor_from, record_event

    record_event("security.access_denied", category="security", outcome="denied", actor=actor_from(request),
                 metadata={"code": exc.code, "method": request.method, "path": request.url.path})


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, exc: ApiError):
        if exc.code in AUDITED_REFUSALS:
            await run_in_threadpool(_audit_refusal, request, exc)
        response = JSONResponse(_body(exc.detail, exc.errors, exc.code), status_code=exc.status_code, headers=exc.headers)
        if exc.clear_session:
            response.delete_cookie(SESSION_COOKIE, path="/")
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        errors: dict[str, str] = {}
        for err in exc.errors():
            if err.get("type") == "json_invalid":  # malformed JSON: loc holds a character position, not a field
                return JSONResponse(_body("The request body is not valid JSON.", {"body": "Invalid JSON"}), status_code=400)
            parts = [str(p) for p in err["loc"] if p not in ("body", "query", "path")]
            field = ".".join(parts) or "body"
            errors.setdefault(field, _friendly(err, field))
        return JSONResponse(_body("Please fix the highlighted fields.", errors), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse(_body(str(exc.detail)), status_code=exc.status_code)

    @app.exception_handler(IntegrityError)
    async def integrity_error(_: Request, exc: IntegrityError):
        """Safety net: a database constraint refused the change (duplicate, still referenced, ...). Details stay in the log."""
        log.warning("Integrity error: %s", db_error_summary(exc))
        return JSONResponse(_body("This change conflicts with existing data. Refresh the page and try again."), status_code=409)

    @app.exception_handler(DataError)
    async def data_error(_: Request, exc: DataError):
        """Safety net: the database refused a value (validation should have caught it first)."""
        log.warning("Database rejected a value: %s", db_error_summary(exc))
        return JSONResponse(_body("Some of the submitted data is invalid."), status_code=400)

    @app.exception_handler(OperationalError)
    @app.exception_handler(ProgrammingError)
    async def database_problem(_: Request, exc: Exception):
        # Connection problems (refused, wrong password, timeout) carry no user data and are worth reading in full.
        detail = str(getattr(exc, "orig", exc)).strip().splitlines()[0] if isinstance(exc, OperationalError) else ""
        log.error("Database error: %s %s", db_error_summary(exc), detail)
        text = str(exc).lower()
        if "does not exist" in text or "no such table" in text:
            return JSONResponse(_body("The database is missing tables or is out of date. Run `alembic upgrade head` in the backend folder."), status_code=503)
        if isinstance(exc, OperationalError):
            return JSONResponse(_body("The database is unavailable. Check that PostgreSQL is running and DATABASE_URL is correct."), status_code=503)
        return JSONResponse(_body("Something went wrong on the server."), status_code=500)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception):
        log.exception("Unhandled error")  # full traceback stays in the server log only
        reference = request_id_var.get()
        return JSONResponse(_body(f"Something went wrong on the server (reference: {reference})." if reference
                                  else "Something went wrong on the server."), status_code=500)
