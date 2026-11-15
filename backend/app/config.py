"""Settings come from environment variables; backend/.env is loaded automatically if it exists.

There is deliberately NO default database URL here: a password must never live in source code.
Copy .env.example to .env and edit it (development), or set real environment variables (production).
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Real environment variables win over .env (override=False), which also lets tests point elsewhere.
load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)


class ConfigError(RuntimeError):
    pass


def _flag(name: str, default: str) -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes", "on")


APP_ENV = os.getenv("APP_ENV", "development").strip().lower()  # "development" or "production"
IS_PRODUCTION = APP_ENV == "production"

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    raise ConfigError(
        "DATABASE_URL is not set.\n"
        "  Development: copy backend/.env.example to backend/.env and fill it in  (cp .env.example .env)\n"
        "  Production:  set DATABASE_URL as a real environment variable, never in a committed file."
    )

# The destructive "reset demo data" endpoint and `seed --reset` are development conveniences only.
ENABLE_DEMO_RESET = _flag("ENABLE_DEMO_RESET", "true") and not IS_PRODUCTION


def _int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    return int(value) if value else default


def _list(name: str, default: str) -> list[str]:
    return [item.strip().rstrip("/") for item in os.getenv(name, default).split(",") if item.strip()]


# ---------------------------------------------------------------- Phase 3: authentication
# Who may call the API from a browser. Narrow on purpose: only the real frontend origin(s).
FRONTEND_ORIGINS = _list("FRONTEND_ORIGINS", "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173")
# Base URL put into password-reset / invitation links that an administrator hands to a user.
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", FRONTEND_ORIGINS[0]).rstrip("/")

# Anyone can create an account (with the restricted "Employee" role). Set false to allow invitations only.
REGISTRATION_ENABLED = _flag("REGISTRATION_ENABLED", "true")

# Sessions (see docs/AUTH.md). A normal sign-in lasts until the browser is closed, at most SESSION_ABSOLUTE_HOURS,
# and ends after SESSION_IDLE_MINUTES without activity. "Remember me" keeps the cookie for REMEMBER_ME_DAYS.
SESSION_IDLE_MINUTES = _int("SESSION_IDLE_MINUTES", 120)
SESSION_ABSOLUTE_HOURS = _int("SESSION_ABSOLUTE_HOURS", 12)
REMEMBER_ME_DAYS = _int("REMEMBER_ME_DAYS", 30)
REMEMBER_ME_IDLE_DAYS = _int("REMEMBER_ME_IDLE_DAYS", 7)
MAX_SESSIONS_PER_USER = _int("MAX_SESSIONS_PER_USER", 5)  # signing in on a 6th device ends the oldest session
RESET_LINK_MINUTES = _int("RESET_LINK_MINUTES", 60)
INVITE_LINK_HOURS = _int("INVITE_LINK_HOURS", 72)

# Cookies are only sent over HTTPS when Secure is set. Local development runs on plain http, so it defaults to off
# there and is FORCED on in production.
COOKIE_SECURE = IS_PRODUCTION or _flag("COOKIE_SECURE", "false")

# Argon2id cost. "standard" = the library's recommended RFC 9106 profile (64 MiB, 3 passes). "fast" exists only so the
# automated tests don't take minutes; it is refused in production.
PASSWORD_HASH_PROFILE = os.getenv("PASSWORD_HASH_PROFILE", "standard").strip().lower()
if IS_PRODUCTION and PASSWORD_HASH_PROFILE != "standard":  # nosec B105 # hash-profile name, not a password
    raise ConfigError("PASSWORD_HASH_PROFILE must be 'standard' in production.")


# ---------------------------------------------------------------- Phase 4: security hardening (see docs/SECURITY.md)
# Migrations (alembic) connect as the database OWNER; the running app can use a separate, less privileged user.
# Without MIGRATION_DATABASE_URL both use DATABASE_URL (fine for development, refused in production).
MIGRATION_DATABASE_URL = os.getenv("MIGRATION_DATABASE_URL", "").strip() or DATABASE_URL

# Requests: JSON bodies bigger than this are refused with 413 before they are read into memory.
MAX_REQUEST_BODY_BYTES = _int("MAX_REQUEST_BODY_BYTES", 64 * 1024)
# PostgreSQL aborts any single query running longer than this (protects against slow-query denial of service).
DB_STATEMENT_TIMEOUT_MS = _int("DB_STATEMENT_TIMEOUT_MS", 15_000)

# Re-authentication ("sudo mode"): high-impact admin actions need a password confirmation this recent.
REAUTH_MINUTES = _int("REAUTH_MINUTES", 10)

# General API rate limits, "<count>/<period>" (period: second, minute, hour, day; e.g. "300/minute", "30/10 minutes").
# Applied per signed-in session (or per IP address when not signed in). Login/registration ALSO keep their
# per-e-mail limits stored in the database (Phase 3). See docs/SECURITY.md, "Rate limiting".
RATE_LIMIT_ENABLED = _flag("RATE_LIMIT_ENABLED", "true")
RATE_LIMIT_READ = os.getenv("RATE_LIMIT_READ", "300/minute")             # GET requests
RATE_LIMIT_WRITE = os.getenv("RATE_LIMIT_WRITE", "60/minute")            # POST/PUT/PATCH/DELETE
RATE_LIMIT_AUTH = os.getenv("RATE_LIMIT_AUTH", "20/minute")              # sign-in, sign-up, reset, reauth (per IP)
RATE_LIMIT_SENSITIVE = os.getenv("RATE_LIMIT_SENSITIVE", "30/hour")      # reset links, ending sessions, roles (per user)
RATE_LIMIT_PER_IP = os.getenv("RATE_LIMIT_PER_IP", "1200/minute")        # safety net for everything from one address

# HTTP security headers. HSTS tells browsers "only ever use HTTPS for this site": only safe once HTTPS works, so it
# is sent only in production (where HTTPS is required) unless set explicitly.
HSTS_MAX_AGE = _int("HSTS_MAX_AGE", 31_536_000 if IS_PRODUCTION else 0)

# The interactive API docs (/docs, /redoc, /openapi.json) map out the whole attack surface: off in production.
EXPOSE_API_DOCS = _flag("EXPOSE_API_DOCS", "false" if IS_PRODUCTION else "true")

LOG_FORMAT = os.getenv("LOG_FORMAT", "json" if IS_PRODUCTION else "text").strip().lower()  # "json" or "text"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").strip().upper()

# Audit log integrity key (HMAC-SHA256). Keep it OUTSIDE the database: whoever has the database but not this key
# can't rewrite audit history without the verification noticing. Generate with:
#     python -c "import secrets; print(secrets.token_hex(32))"
# Rotation: move the old key to AUDIT_HMAC_OLD_KEYS (comma-separated) and set a new AUDIT_HMAC_KEY.
_DEV_AUDIT_KEY = "development-only-audit-key-do-not-use-in-production"
AUDIT_HMAC_KEY = os.getenv("AUDIT_HMAC_KEY", "").strip() or _DEV_AUDIT_KEY
AUDIT_HMAC_OLD_KEYS = [k.strip() for k in os.getenv("AUDIT_HMAC_OLD_KEYS", "").split(",") if k.strip()]
AUDIT_KEY_IS_DEVELOPMENT_DEFAULT = AUDIT_HMAC_KEY == _DEV_AUDIT_KEY


def _user_of(url: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).username or ""


def production_problems() -> list[str]:
    """Settings that would make a production deployment insecure. Production refuses to start if any are found."""
    problems = []
    if any(not o.startswith("https://") for o in FRONTEND_ORIGINS):
        problems.append("FRONTEND_ORIGINS must list only https:// origins")
    if not PUBLIC_APP_URL.startswith("https://"):
        problems.append("PUBLIC_APP_URL must start with https://")
    if DATABASE_URL.startswith("sqlite"):
        problems.append("DATABASE_URL must point to PostgreSQL, not SQLite")
    elif _user_of(DATABASE_URL) == _user_of(MIGRATION_DATABASE_URL):
        problems.append("the app must not connect as the database owner: set DATABASE_URL to the restricted app user "
                        "and MIGRATION_DATABASE_URL to the owner (docs/SECURITY.md, 'Least-privilege database access')")
    if AUDIT_KEY_IS_DEVELOPMENT_DEFAULT or len(AUDIT_HMAC_KEY) < 32:
        problems.append("AUDIT_HMAC_KEY must be set to a random secret of at least 32 characters")
    if HSTS_MAX_AGE < 86_400:
        problems.append("HSTS_MAX_AGE must be at least 86400 (1 day) in production")
    return problems


# Settings that are wrong in every environment.
if any(o == "*" for o in FRONTEND_ORIGINS):
    raise ConfigError("FRONTEND_ORIGINS must list explicit origins; '*' is not allowed (cookies are sent with requests).")
if LOG_FORMAT not in ("json", "text"):
    raise ConfigError("LOG_FORMAT must be 'json' or 'text'.")
if IS_PRODUCTION and (problems := production_problems()):
    raise ConfigError("Refusing to start in production with insecure settings:\n  - " + "\n  - ".join(problems))
