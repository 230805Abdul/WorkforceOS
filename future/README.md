# `future/` — your original WorkforceOS material (not used by the running app)

Nothing from your uploaded repository was deleted. What belongs to later phases lives here, untouched.

| Original file(s) | What it is | Status / comes back in |
|---|---|---|
| `backend-original/app/models/`, `app/db/`, `alembic/` | SQLAlchemy models + migration (UUID keys, native PG enums, `created_by` → users) | **Phase 2 is done** with a simpler schema (`backend/app/models.py`, `backend/migrations/`). Kept as reference for UUIDs / `created_by` in Phase 3 |
| `backend-original/app/api/v1/auth.py`, `app/core/security.py`, `app/core/deps.py`, `app/models/user.py`, `app/schemas/auth.py`, `frontend-original/src/pages/Login.jsx` | JWT login, password hashing, role checks | **Phase 3 is done** with server-side sessions instead of JWT (see docs/AUTH.md); kept as reference |
| `backend-original/app/middleware/security_headers.py`, `app/services/rate_limit.py`, `app/services/audit.py`, `app/models/audit_log.py`, `app/api/v1/admin.py`, `docs/SECURITY.md` | Security headers, rate limiting, audit log | Phase 4: Security |
| `backend-original/Dockerfile*`, `frontend-original/Dockerfile`, `frontend-original/nginx.conf`, `docker-compose.yml` | Containers | Phase 5: Docker |
| `terraform/` | Cloud infrastructure | Phase 6: Cloud |
| `.github/`, `.pre-commit-config.yaml`, `monitoring/prometheus.yml` | CI/CD, linting, monitoring | Phase 7: DevOps |
| `backend-original/app/workers/`, `app/services/cache.py` | Celery background tasks, caching | After Phase 3 |
| `docs/ARCHITECTURE.md`, `ORIGINAL_README.md` | Your original design notes | Reference |
