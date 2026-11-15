import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.permissions import PERMISSIONS
from app.config import (AUDIT_KEY_IS_DEVELOPMENT_DEFAULT, DATABASE_URL, ENABLE_DEMO_RESET, MIGRATION_DATABASE_URL, EXPOSE_API_DOCS, FRONTEND_ORIGINS, MAX_REQUEST_BODY_BYTES, RATE_LIMIT_AUTH,
                        RATE_LIMIT_ENABLED, RATE_LIMIT_PER_IP, RATE_LIMIT_READ, RATE_LIMIT_SENSITIVE, RATE_LIMIT_WRITE)
from app.db import SessionLocal, describe_url, engine
from app.errors import register_error_handlers
from app.observability import setup_logging
from app.routers import (applications, audit, auth, candidates, dashboard, departments, employees, jobs, me, roles,
                         system, users)
from app.security.middleware import (BodyLimitMiddleware, CrossSiteMiddleware, RateLimitMiddleware, RateLimits,
                                     RequestContextMiddleware)

uvicorn_log = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(_: FastAPI):
    """On startup, say clearly whether the database is reachable and migrated. Never crash: /docs should still load."""
    try:
        tables = inspect(engine).get_table_names()
        uvicorn_log.info("Database connected: %s", describe_url())
        if "alembic_version" not in tables:
            uvicorn_log.warning("No migrations have been applied yet. Run:  alembic upgrade head   (then: python -m app.seed)")
        elif "users" not in tables or "employees" not in tables:
            uvicorn_log.warning("The database schema is out of date. Run:  alembic upgrade head")
        else:
            from app.auth.models import Permission, User

            with SessionLocal() as db:
                in_db = set(db.scalars(select(Permission.code)).all())
                if in_db != set(PERMISSIONS):
                    uvicorn_log.warning("Permissions in the database differ from app/auth/permissions.py: missing %s, extra %s. "
                                        "A migration is needed.", sorted(set(PERMISSIONS) - in_db), sorted(in_db - set(PERMISSIONS)))
                if "audit_events" not in tables:
                    uvicorn_log.warning("The database schema is out of date. Run:  alembic upgrade head")
                if db.scalar(select(User.id).limit(1)) is None:
                    uvicorn_log.warning("No user accounts yet. Create the first Super Administrator:  python -m app.create_admin")
        if AUDIT_KEY_IS_DEVELOPMENT_DEFAULT:
            uvicorn_log.warning("AUDIT_HMAC_KEY is not set: audit records are signed with the public development key "
                                "(fine for development; production refuses to start). See docs/SECURITY.md.")
        if DATABASE_URL == MIGRATION_DATABASE_URL and not DATABASE_URL.startswith("sqlite"):
            uvicorn_log.warning("The app connects as the database owner (no MIGRATION_DATABASE_URL). Fine for development; "
                                "production needs the least-privilege setup in docs/SECURITY.md.")
    except SQLAlchemyError as exc:
        uvicorn_log.error("Cannot connect to the database %s -> %s\nIs PostgreSQL running? Is DATABASE_URL in backend/.env correct?", describe_url(), type(exc).__name__)
    yield


DEFAULT_LIMITS = RateLimits(read=RATE_LIMIT_READ, write=RATE_LIMIT_WRITE, auth=RATE_LIMIT_AUTH,
                            sensitive=RATE_LIMIT_SENSITIVE, per_ip=RATE_LIMIT_PER_IP)


def create_app(enable_demo_reset: bool = ENABLE_DEMO_RESET, rate_limits: RateLimits | None = DEFAULT_LIMITS
               if RATE_LIMIT_ENABLED else None) -> FastAPI:
    setup_logging()
    app = FastAPI(
        title="WorkforceOS API",
        version="0.5.0",
        description="Phase 4: PostgreSQL, sessions in an HttpOnly cookie, role/permission-based authorization, plus "
                    "security hardening (headers, rate limits, audit log). Sign in via POST /api/auth/login first.",
        lifespan=lifespan,
        # The interactive docs describe every endpoint: useful while developing, a map for attackers in production.
        docs_url="/docs" if EXPOSE_API_DOCS else None,
        redoc_url="/redoc" if EXPOSE_API_DOCS else None,
        openapi_url="/openapi.json" if EXPOSE_API_DOCS else None,
    )

    # Middleware runs outside-in in the REVERSE order of add_middleware: the last one added sees the request first.
    app.add_middleware(BodyLimitMiddleware, max_bytes=MAX_REQUEST_BODY_BYTES)  # 4. size + JSON-only, before parsing
    if rate_limits is not None:
        app.add_middleware(RateLimitMiddleware, limits=rate_limits)           # 3. request budgets
    # 2. Only our own frontend may call the API from a browser, WITH cookies (allow_credentials).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=FRONTEND_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(CrossSiteMiddleware, allowed_origins=FRONTEND_ORIGINS)  # 1b. cross-site write refusal
    app.add_middleware(RequestContextMiddleware)                               # 1a. request ID, headers, access log

    register_error_handlers(app)
    for r in (system.router, auth.router, me.router, users.router, roles.router, audit.router, dashboard.router,
              departments.router, employees.router, jobs.router, candidates.router, applications.router):
        app.include_router(r, prefix="/api")
    if enable_demo_reset:
        from app.routers import demo  # imported lazily: sample-data code stays out of the app unless asked for

        app.include_router(demo.router, prefix="/api")
    return app


app = create_app()
