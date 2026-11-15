# WorkforceOS

A cloud-native workforce & recruitment operations platform — production-engineered, not a CRUD demo.
Built to demonstrate backend engineering, security, and DevOps practices together in one real system.

**Stack**: FastAPI (async) · PostgreSQL · Redis · Celery · React · Docker · GitHub Actions · Terraform (AWS) · Prometheus/Grafana

## What this actually demonstrates

| Area | What's here |
|---|---|
| **Backend engineering** | Async FastAPI, SQLAlchemy 2.0, Alembic migrations, Pydantic v2 schemas, a real state machine for application status transitions |
| **Security** | JWT + refresh tokens, RBAC via dependency injection, bcrypt hashing, rate limiting, security headers, audit logging, least-privilege IAM, encryption at rest/in transit — see `docs/SECURITY.md` |
| **DevOps** | Multi-stage Docker builds, docker-compose orchestration, GitHub Actions CI/CD (lint → test → security scan → build → push → deploy), Terraform IaC for AWS (VPC, ECS Fargate, RDS Multi-AZ, ElastiCache, ALB, autoscaling) |
| **Testing** | 14 pytest tests covering auth, RBAC enforcement, and caching behavior, with coverage reporting wired into CI |
| **Observability** | Prometheus metrics endpoint, Grafana dashboard, structured audit logs |

## Quick start (local)

```bash
cp backend/.env.example backend/.env
docker compose up --build
```

- API: http://localhost:8000 — interactive docs at `/api/docs`
- Frontend: http://localhost:5173
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

## Running the backend without Docker

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # point DATABASE_URL at a local Postgres, or use SQLite for a quick spin

alembic upgrade head
uvicorn app.main:app --reload
```

## Running the tests

```bash
cd backend
pytest                      # full suite with coverage
ruff check .                # lint
```

The suite runs against an in-memory SQLite DB and a local Redis — no AWS or real Postgres needed. All 14 tests
pass clean; coverage sits around 80% on the touched modules.

## Project layout

```
backend/
  app/
    core/        # config, JWT/password security, auth dependency + RBAC guard
    models/      # SQLAlchemy models (User, Job, Candidate, Application, AuditLog)
    schemas/     # Pydantic request/response schemas
    api/v1/      # route handlers
    services/    # cache, rate limiting, audit logging
    workers/     # Celery app + background tasks
    middleware/  # security headers
  alembic/       # DB migrations
  tests/         # pytest suite
frontend/        # React + Vite dashboard
terraform/       # AWS infrastructure as code
.github/workflows/ci-cd.yml
monitoring/      # Prometheus config
docs/
  ARCHITECTURE.md
  SECURITY.md
```

## Deploying to AWS

```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars   # fill in real values — never commit this file
terraform init
terraform plan
terraform apply
```

Requires: an ACM certificate already issued for your domain, and `api_image`/`worker_image` pointing at images
already pushed to a registry (the GitHub Actions workflow builds and pushes these to GHCR on every merge to `main`).

## Honest notes on what's a scaffold vs. production-ready

This is built to be genuinely run and tested — not pseudocode — but a few things are intentionally left as
documented next steps rather than over-built for a portfolio project:

- Resume parsing / AI matching (`score_resume_match` Celery task) is a stub — wire in PyMuPDF + an LLM call
  the way the TALAASH project already does, and this becomes a real feature.
- Rate limiting uses in-memory storage; multi-instance production deployments should back it with Redis.
- No blue/green deploys yet — ECS does a standard rolling deployment.

See `docs/ARCHITECTURE.md` for the full reasoning behind each infrastructure choice, and `docs/SECURITY.md` for
the security posture in detail — both are written to be something you can talk through in an interview, not
just files that exist.
