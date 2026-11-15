# WorkforceOS — Phase 4 (security hardening)

A workforce and hiring platform: **Departments → Employees** and **Jobs → Candidates → Applications**, with sign-in,
roles and permissions, and now **security hardening**: rate limits, strict input validation, security headers,
an append-only audit log, password confirmation for admin actions, least-privilege database access, backups and
dependency scanning. React frontend → FastAPI backend → PostgreSQL.

> **Still a local development build.** The protections are real and tested, but HTTPS, a reverse proxy and off-site
> logs arrive with Phases 5–6. Don't put it on the internet yet.

```
Browser ─► Vite :5173 ─(proxies /api)─► FastAPI :8000 ─► PostgreSQL :5432
  HttpOnly session cookie + X-CSRF-Token     │  headers · cross-site check · rate limit · size/JSON check
                                             │  → session → permission (→ password re-check) → strict schema
                                             └─ audit record for every security-relevant action
```
Details: **[docs/SECURITY.md](docs/SECURITY.md)** (every control, how to operate it, limits) ·
**[docs/SECURITY_ASSESSMENT.md](docs/SECURITY_ASSESSMENT.md)** (OWASP review, findings, scan results) ·
**[docs/AUTH.md](docs/AUTH.md)** · **[docs/DATABASE.md](docs/DATABASE.md)**.

---

## A. Upgrading from Phase 3 (keeps your data and accounts)

**1. Stop both servers (Ctrl+C), back up, unzip next to the old version:**
```bash
PGPASSWORD=workforceos pg_dump -h localhost -U workforceos -Fc workforceos > ~/workforceos-before-phase4.dump
cd ~/Downloads
unzip workforceos-phase4.zip -d workforceos-phase4
cd workforceos-phase4/workforceos
cp ~/Downloads/workforceos-phase3/workforceos/backend/.env backend/.env
```

**2. Give the audit log its own secret key** (signs every audit record; keep it out of the database and out of git):
```bash
echo "AUDIT_HMAC_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> backend/.env
echo "FRONTEND_ORIGINS=http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173" >> backend/.env
```
(The second line lets the production preview on port 4173 sign in; the last value in `.env` wins.)
**Keep a copy of the key somewhere safe** (password manager): without it, old audit records can't be verified.

**3. Backend:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt     # adds "limits" (rate limiting)
alembic upgrade head                # migration 0006: audit log + its protections (your data stays)
alembic current                    # → 0006 (head)
```

**4. Frontend:**
```bash
cd ../frontend
npm install                         # "found 0 vulnerabilities"
```
Start everything (section C) and sign in as before. Your Super Administrator now also sees **Audit log**.

**5. Optional but recommended: least-privilege database user** (the app stops connecting as the table owner):
```bash
cd ../backend && source .venv/bin/activate
./scripts/setup_least_privilege.sh   # asks for your sudo password; rewrites DATABASE_URL, keeps a backup of .env
```
Restart the backend afterwards. It prints what it checked. Details: [SECURITY.md §8](docs/SECURITY.md#8-least-privilege-database-access).

## B. Fresh installation (new machine)

Prerequisites: Python 3.10+, **Node 20.19+**, PostgreSQL (`sudo apt install -y python3 python3-venv postgresql postgresql-contrib`).
`pg_lsclusters` must show `online` (`sudo systemctl status postgresql` saying "active (exited)" is normal on Ubuntu).

```bash
sudo -u postgres psql
```
```sql
CREATE USER workforceos WITH PASSWORD 'choose-a-password';
CREATE DATABASE workforceos OWNER workforceos;
CREATE DATABASE workforceos_test OWNER workforceos;
\q
```
```bash
cd workforceos/backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env && nano .env        # put your password into DATABASE_URL, and set AUDIT_HMAC_KEY (see A, step 2)
alembic upgrade head
python -m app.seed                       # optional sample business data
python -m app.create_admin --email you@example.com --name "Your Name"
cd ../frontend && npm install
```

## C. Every day: start everything

**Terminal 1:** `cd ~/Downloads/workforceos-phase4/workforceos/backend && source .venv/bin/activate && uvicorn app.main:app --reload`
**Terminal 2:** `cd ~/Downloads/workforceos-phase4/workforceos/frontend && npm run dev`

Open **http://127.0.0.1:5173** → you're sent to **Sign in**. API docs: http://127.0.0.1:8000/docs.

To try the **production build with the strict security headers**: `npm run build && npm run preview` → http://127.0.0.1:4173
(the backend must be running too).

Use the same address every time: cookies belong to one host, so signing in at `127.0.0.1:5173` doesn't sign you in at
`localhost:5173` (and vice versa).

## D. Accounts

| Task | How |
|---|---|
| **First Super Administrator** | `python -m app.create_admin --email you@example.com --name "Your Name"` (asks for the password twice; there is no other way to create the first admin) |
| Make an existing account Super Admin | `python -m app.create_admin --email them@example.com --promote` |
| **Register** (anyone) | **Create an account** on the sign-in page. New accounts get the restricted **Employee** role. Turn it off with `REGISTRATION_ENABLED=false` |
| **Invite** someone | Administration → **Users** → **Invite user**: choose roles (and optionally their employee record), copy the one-time link and send it privately. They choose their own password |
| **Assign roles** | Users → click a name → tick roles → **Save roles** (you can't change your own) |
| Link an account to an employee record | Users → click a name → *Linked employee record* → **Save details**. That person then sees their record under **My profile** |
| Someone forgot their password | Users → click the name → **Create password-reset link** (works once, 60 minutes) |
| Lock someone out now | Users → **Disable account** (ends all their sessions immediately) or **End all sessions** |
| Edit what a role may do / new roles | Administration → **Roles** |
| Your own name, password, phone, other devices | **My profile** (avatar menu, top right) |
| **Demo sign-ins** (development only) | `python -m app.seed --demo-users` creates one per role, password `WorkforceOS-demo-2026`: `admin@demo.example.com`, `hr.admin@…`, `hr.manager@…`, `recruiter@…`, `employee@demo.example.com`. Remove with `python -m app.seed --remove-sample` |

## E. Roles at a glance

| | Super Admin | HR Admin | HR Manager | Recruiter | Employee |
|---|:-:|:-:|:-:|:-:|:-:|
| Dashboard | all | all | all | recruiting only | — |
| Employees | full | view, add, edit (no delete) | view | — | own record (+ own phone) |
| Departments | full | full | view | view | — |
| Jobs / Candidates | full | full | view | full | — |
| Pipeline | full | full | view + move | full | — |
| Users & Roles | full | — | — | — | — |
| Audit log | view | — | — | — | — |

Full permission list and the reasoning: [docs/AUTH.md](docs/AUTH.md).

## F. Test the permissions yourself

1. `python -m app.seed --demo-users`, then sign in as **employee@demo.example.com** (`WorkforceOS-demo-2026`): only
   **My profile**, showing Aisha Rahman's record. Type `http://127.0.0.1:5173/employees` in the address bar →
   "You don't have access to this page".
2. Prove the **server** refuses it too (not just the page):
   ```bash
   curl -s -c /tmp/c.txt -X POST http://127.0.0.1:8000/api/auth/login -H 'content-type: application/json' \
        -d '{"email":"employee@demo.example.com","password":"WorkforceOS-demo-2026"}' > /dev/null
   curl -s -b /tmp/c.txt http://127.0.0.1:8000/api/employees      # {"detail":"You don't have permission…","code":"forbidden"}
   curl -s http://127.0.0.1:8000/api/employees                     # no cookie: {"detail":"Please sign in…","code":"not_authenticated"}
   ```
3. Sign in as **recruiter@…**: no Employees in the menu, no workforce numbers on the dashboard.
4. As **hr.manager@…**: Employees visible but no Add/Edit/Delete buttons; the pipeline works.
5. As **admin@…** → Roles → Recruiter → tick *View all employee records* → save. The recruiter's next click already shows
   employees (permissions are checked on every request). Untick it again.
6. Sign in on two browsers as the same user, change the password in one: the other is signed out.

## G. Look inside the database

```bash
psql -h localhost -U workforceos -d workforceos
```
```sql
SELECT u.email, u.status, string_agg(r.name, ', ') AS roles FROM users u
  JOIN user_roles ur ON ur.user_id = u.id JOIN roles r ON r.id = ur.role_id GROUP BY u.id ORDER BY u.id;
SELECT email, left(password_hash, 30) FROM users;              -- Argon2id hashes, never passwords
SELECT user_id, remember, created_at, expires_at FROM sessions; -- one row per signed-in browser (token stored hashed)
SELECT r.name, count(*) FROM roles r JOIN role_permissions rp ON rp.role_id = r.id GROUP BY r.name;
SELECT kind, email, succeeded, created_at FROM auth_attempts ORDER BY id DESC LIMIT 10;
```

## H. Try the Phase 4 security features

Run these with the backend running (section C). `B=http://127.0.0.1:8000/api` saves typing.

1. **Security headers:**
   ```bash
   curl -s -D - -o /dev/null http://127.0.0.1:8000/api/health        # content-security-policy, x-frame-options, nosniff…
   npm run build && npm run preview   # (in frontend/) then: curl -sI http://127.0.0.1:4173 | grep -i content-security
   ```
2. **Rate limits:** 25 wrong sign-ins in a row → first `401`s, then `429` with `Retry-After`:
   ```bash
   B=http://127.0.0.1:8000/api
   for i in $(seq 1 25); do curl -s -o /dev/null -w "%{http_code} " -H 'content-type: application/json' \
     -d '{"email":"nobody@example.com","password":"wrong-password-1"}' $B/auth/login; done; echo
   ```
   Wait a minute (or restart the backend) to reset. Then look at **Audit log**: the attempts and the block are there.
3. **Strict input:** an extra field, a form post, and a too-large body are refused:
   ```bash
   curl -s -H 'content-type: application/json' -d '{"email":"x@example.com","password":"lantern-pebble-quartz-77","password_confirm":"lantern-pebble-quartz-77","full_name":"X Y","role":"super_admin"}' $B/auth/register; echo
   curl -s -d 'email=a&password=b' $B/auth/login; echo
   python3 -c "print('{\"x\":\"' + 'a'*100000 + '\"}')" | curl -s -H 'content-type: application/json' --data-binary @- $B/auth/login; echo
   ```
4. **Password confirmation for admin actions:** sign in as Super Administrator, wait 10 minutes (or set
   `REAUTH_MINUTES=1` in `.env` and restart), then Users → someone → **Disable account**: you're asked for your password
   first; after confirming, the action completes by itself.
5. **Audit log:** Administration → **Audit log**: filter by category/outcome, open a record, **Verify integrity**.
   From the terminal: `python -m app.audit_verify`. Then try to tamper (it must fail):
   ```bash
   psql -h localhost -U workforceos -d workforceos -c "DELETE FROM audit_events;"   # ERROR: audit_events is append-only
   ```
6. **Recent sign-ins:** sign in from another browser, then **My profile → Recent sign-ins** shows it as a new device.
7. **Dependency and code scans:**
   ```bash
   cd backend && source .venv/bin/activate && pip install -r requirements-security.txt && cd ..
   ./scripts/security_scan.sh                   # bandit, pip-audit, npm audit (+ trivy if installed)
   ```
8. **Backup and restore test:**
   ```bash
   cd backend && source .venv/bin/activate
   ./scripts/backup_db.sh                                           # → ~/workforceos-backups/…dump (+ .sha256)
   ./scripts/restore_db.sh ~/workforceos-backups/<file>.dump workforceos_restore_test   # into a NEW database, verified
   sudo -u postgres dropdb workforceos_restore_test                 # clean up the test copy
   ```

## I. Sample data, migrations, configuration

```bash
python -m app.seed                  # add missing sample business records
python -m app.seed --demo-users     # + one sign-in per role (development only)
python -m app.seed --remove-sample  # delete sample records and demo users; your own data stays
python -m app.seed --reset          # ⚠ delete ALL business data, reload samples (accounts and audit log are kept)
alembic current / alembic history / alembic upgrade head
```
Settings live in `backend/.env` (`.env.example` lists them all with defaults, including rate limits, body size, sudo
mode window, log format; `.env.production.example` for later; production refuses to start with insecure values).

## J. Automated tests

```bash
cd backend && source .venv/bin/activate
pytest -q                                                       # quick: throw-away SQLite file
TEST_DATABASE_URL=postgresql+psycopg://workforceos:YOUR_PASSWORD@localhost:5432/workforceos_test pytest -q
```
344 tests. Phase 4 adds `tests/test_security.py` (headers, rate limits, body limits, strict schemas, cross-site checks,
sudo mode, session fixation, production config refusals) and `tests/test_audit.py` (what is recorded and what never is,
access control, hash-chain verification, tamper detection, database triggers). Tests never touch your real data.

## K. Common problems

| Symptom | Fix |
|---|---|
| Backend warns "AUDIT_HMAC_KEY is not set" | Section A, step 2. Harmless for trying things out, but set it before you care about the records |
| `429` / "Too many requests. Please wait N seconds" | A rate limit: wait N seconds. Limits are in `.env` (`RATE_LIMIT_*`) |
| "Please confirm your password to continue" | Sudo mode for admin actions: type your password (valid 10 minutes, `REAUTH_MINUTES`) |
| "Cross-site request refused" on port 4173 | Add the 4173 origins to `FRONTEND_ORIGINS` (section A, step 2) and restart the backend |
| `413 The request is too large` | Body over 64 KB (`MAX_REQUEST_BODY_BYTES`); no normal form gets near it |
| `422 "This field cannot be changed here"` | The request sent a field that isn't allowed (by design) |
| `ERROR: audit_events is append-only` | Working as intended: audit records can't be changed or deleted |
| `setup_least_privilege.sh` "permission denied" afterwards when running `alembic` | Alembic uses `MIGRATION_DATABASE_URL` (the owner); check it's in `.env` |
| `npm run dev` fails with a Node/`crypto`/syntax error | Node is older than 20.19: `curl -fsSL https://deb.nodesource.com/setup_22.x \| sudo -E bash - && sudo apt install -y nodejs` |
| Sign-in page, but you have no account | `python -m app.create_admin --email … --name …` |
| "Your session has expired" | Inactive for 2 hours, or 12 hours passed (tick "Keep me signed in" for 30 days) |
| "You don't have access to this page" | Your role lacks the permission; an admin can change it under Users/Roles |
| `alembic upgrade head` prints nothing new | Already up to date; `alembic current` should show `0006 (head)` |
| Other startup/database problems | `pg_lsclusters` (must be online), the password in `.env`, `alembic upgrade head` |

## L. Roadmap
1. ~~Phase 2 – Persistence~~ ✅  2. ~~Phase 3 – Authentication & authorization~~ ✅  3. ~~Phase 4 – Security~~ ✅
4. **Phase 5 – Docker** (reverse proxy with trusted client IPs, `--no-server-header`) · Phase 6 – Cloud (HTTPS + HSTS,
   managed PostgreSQL, secret manager, off-site audit logs) · Phase 7 – DevOps (CI running the tests and
   `security_scan.sh --strict`).
   Still open from the security list: e-mail (verification, reset, alerts), optional 2FA.
