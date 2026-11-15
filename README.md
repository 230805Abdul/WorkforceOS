# WorkforceOS

**WorkforceOS is a workforce and hiring platform for small and mid-sized companies.** It brings an organization's
people and its hiring into one place. HR teams manage departments and employees, recruiters run hiring from job
posting to hire, and every person gets exactly the access their role allows.

It is built the way a production business application should be: a clear separation between frontend and API, a
relational database with versioned migrations, server-enforced permissions, security throughout, and automated
tests.

## The idea

Most small companies track employees in spreadsheets and hiring in e-mail threads. WorkforceOS connects the two:

```
 Departments ──► Employees ◄── hired ◄── Applications ◄── Candidates
                                              ▲
                                            Jobs
```

A job is opened in a department, candidates apply, applications move through a hiring pipeline, and a hired
candidate becomes an employee in one step, without retyping anything.

## What it does

| Area | Capabilities |
|---|---|
| **Organization** | Departments, and an employee directory with search and filters |
| **Recruiting** | Job postings, a candidate database, and a pipeline board (applied → screening → interview → offer → hired) |
| **Dashboard** | Headcount, open positions, pipeline status and recent activity |
| **People & access** | Invitations, self-registration, password resets, user management, custom roles |
| **Self-service** | Employees see and update their own profile, password and active devices |
| **Accountability** | An audit log of who did what, when and from where |

### Roles

| Role | Can do |
|---|---|
| Super Administrator | Everything, including users, roles and the audit log |
| HR Administrator | Manage employees, departments and recruiting |
| HR Manager | View the workforce; move candidates through the pipeline |
| Recruiter | Manage jobs, candidates and applications |
| Employee | View their own record |

Administrators can create custom roles from a fine-grained permission list. The server checks every request; the
interface only hides what a role can't use.

## How it's built

```
Browser ──► React SPA ──/api──► FastAPI ──► PostgreSQL
                                   │
        security headers · CSRF & origin checks · rate limits · input validation
        session → permission check → business logic → audit record
```

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, React Router |
| Backend | Python, FastAPI, Pydantic 2 |
| Database | PostgreSQL, SQLAlchemy 2, Alembic migrations |
| Auth | Server-side sessions (HttpOnly cookie), Argon2id passwords, role-based access control |
| Testing | pytest (backend), Vitest + Testing Library (UI), Playwright |
| Security tooling | Bandit, pip-audit, npm audit, Trivy |

## Security by design

- Passwords hashed with Argon2id; sessions in HttpOnly cookies with CSRF protection
- Permissions enforced on the server for every endpoint; protection against IDOR and privilege escalation
- Strict input validation, request size limits and rate limiting
- Content-Security-Policy and other security headers
- Password re-confirmation for sensitive admin actions; new-device sign-in alerts
- An append-only, signed audit log
- A least-privilege database user, and backups with verified restore
- A documented OWASP Top 10 assessment, with known limitations stated honestly

Details: [docs/SECURITY.md](docs/SECURITY.md) · [docs/SECURITY_ASSESSMENT.md](docs/SECURITY_ASSESSMENT.md)

## Getting started (Ubuntu)

Requires Python 3.10+, Node 20.19+ and PostgreSQL.

```bash
# database
sudo -u postgres psql -c "CREATE USER workforceos WITH PASSWORD 'choose-a-password';"
sudo -u postgres psql -c "CREATE DATABASE workforceos OWNER workforceos;"

# backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # set DATABASE_URL and AUDIT_HMAC_KEY
alembic upgrade head
python -m app.seed --demo-users # optional sample data and demo accounts
python -m app.create_admin --email you@example.com --name "Your Name"
uvicorn app.main:app --reload

# frontend (second terminal)
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:5173**. The full guide is in [docs/SETUP.md](docs/SETUP.md).

## Documentation

[Setup guide](docs/SETUP.md) · [Database design](docs/DATABASE.md) · [Authentication & roles](docs/AUTH.md) ·
[Security](docs/SECURITY.md) · [Security assessment](docs/SECURITY_ASSESSMENT.md)
