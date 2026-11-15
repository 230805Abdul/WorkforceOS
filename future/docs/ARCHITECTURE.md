# Architecture

## Overview

```
                        ┌─────────────┐
                        │   Browser   │
                        └──────┬──────┘
                               │ HTTPS
                        ┌──────▼──────┐
                        │     ALB     │  (TLS termination, health checks)
                        └──────┬──────┘
                               │
                ┌──────────────┴──────────────┐
                │                              │
         ┌──────▼──────┐               ┌───────▼──────┐
         │  Frontend    │               │   FastAPI     │  (2+ tasks, autoscaled on CPU)
         │  (nginx/S3)  │               │   API (ECS)   │
         └──────────────┘               └───────┬───────┘
                                                  │
                        ┌─────────────────────────┼─────────────────────────┐
                        │                          │                          │
                 ┌──────▼──────┐          ┌────────▼────────┐        ┌────────▼────────┐
                 │  PostgreSQL  │          │      Redis       │        │   S3 (resumes)   │
                 │  (RDS, Multi-AZ)│       │ (cache + broker) │        │   (encrypted)     │
                 └──────────────┘          └────────┬────────┘        └──────────────────┘
                                                      │
                                             ┌────────▼────────┐
                                             │  Celery Workers  │  (async email, AI scoring)
                                             │     (ECS)        │
                                             └──────────────────┘
```

## Why these choices

**FastAPI + async SQLAlchemy** — the API never blocks on I/O waiting for Postgres, so a small number of ECS
tasks can hold many concurrent connections open. Combined with Gunicorn/Uvicorn workers this is what lets
2 tasks comfortably serve moderate load before autoscaling needs to kick in.

**Redis for both cache and broker** — one piece of infrastructure doing two jobs keeps the stack smaller to
operate. The job listing endpoint is cached for 30s and explicitly invalidated on writes (cache-aside pattern)
rather than relying on a fixed expiry only, so changes are visible immediately to anyone creating or editing a job.

**Celery for background work** — anything that isn't needed for the HTTP response (status-change emails, future
resume-parsing/AI-scoring work) is pushed to a worker queue. This keeps p99 API latency low regardless of how
slow a downstream service (an email provider, an LLM call) is.

**RBAC via a FastAPI dependency, not middleware** — `require_roles(...)` is explicit at the route level, so
reading a single file (`app/api/v1/jobs.py`) tells you exactly who can call each endpoint, rather than having to
trace through global middleware logic.

**Audit log is an separate, append-only table** — sensitive actions (job changes, application status transitions)
write a row here in the same transaction as the business write. It's queried, never updated, by app code.

**Private subnets for everything except the load balancer** — RDS and ElastiCache have no route to the internet
at all; only the ALB is in a public subnet. ECS tasks reach the internet (for pulling images, calling external
APIs) through a NAT gateway, not the other way around.

## Request flow: changing an application's status

1. Recruiter calls `PATCH /api/v1/applications/{id}/status` with a new status.
2. The state machine in `VALID_TRANSITIONS` rejects illegal transitions (e.g. `hired` → `applied`) with a 400
   before touching the database.
3. On success: the DB row updates, an audit log entry is written in the same request, and a Celery task is
   queued (`.delay(...)`) to email the candidate — the API responds without waiting for that email to send.
4. A worker picks up the task from Redis and sends the email, retrying up to 3 times on transient failure.

## Scaling plan

- **API**: horizontally autoscaled on CPU (target 65%), 2–6 tasks behind the ALB.
- **Database**: read-heavy endpoints (job listings) are cached in Redis first; a read replica is the next lever
  if cache alone isn't enough, before resizing the primary instance.
- **Workers**: scaled by queue depth in production (CloudWatch custom metric on Celery queue length), not
  included in this scaffold but a natural next step — see `docs/ARCHITECTURE.md` "Next steps" below.

## Next steps not yet implemented

- Read replica + read/write DB routing for high read load
- WebSocket/SSE for live application-status updates to the dashboard
- Resume parsing pipeline (PyMuPDF a la TALAASH) feeding the `score_resume_match` Celery task
- Blue/green or canary ECS deployments instead of rolling
- OpenTelemetry tracing across API → worker → external calls
