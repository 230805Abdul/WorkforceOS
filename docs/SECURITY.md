# WorkforceOS security (Phase 4)

How WorkforceOS defends itself, how to operate those defences, and what they do **not** cover.
Findings that led to each control: [SECURITY_ASSESSMENT.md](SECURITY_ASSESSMENT.md). Sign-in, sessions, roles:
[AUTH.md](AUTH.md).

```
Browser ──► (Phase 6: HTTPS proxy) ──► FastAPI
             every /api request passes, in order:
             1 request ID + security headers + access log   (RequestContextMiddleware)
             2 cross-site write refusal (Origin/Referer/Sec-Fetch-Site)   (CrossSiteMiddleware)
             3 CORS (only FRONTEND_ORIGINS, with cookies)
             4 rate limits (per IP, per session, per tier)   (RateLimitMiddleware)
             5 body: JSON only, ≤ 64 KB, read in a stream    (BodyLimitMiddleware)
             6 session → CSRF token → permission → (sudo mode) (auth dependencies)
             7 strict schema validation (unknown fields refused, lengths, characters)
             8 SQLAlchemy, bound parameters, least-privileged DB user, 15 s statement timeout
             9 audit record (own transaction) · structured log line · errors without internals
```

## 1. Input validation and request hardening

* **Strict schemas** (`app/schemas.py`, `app/auth/schemas.py`, `app/validation.py`): every input model forbids unknown
  fields (`422 "This field cannot be changed here"`), so sending `role`, `id`, `status` or `password_hash` where they
  don't belong fails loudly instead of being silently ignored. **Mass assignment** is impossible by construction:
  handlers copy fields from the validated model, never from the raw body.
* **Text fields** (`text()` in `validation.py`): trimmed, length limits on every string, control characters and NUL
  bytes refused (PostgreSQL can't store NUL; before Phase 4 it caused a 500 with values in the log). Multi-line fields
  (descriptions) allow newlines and tabs only.
* **Search terms**: at most 100 characters; `%` and `_` are escaped so they match literally.
* **Bodies**: JSON only (`415` otherwise; an empty body is fine); **64 KB maximum**, enforced while the body streams in
  (`413`), so a huge request is never held in memory. Malformed JSON → `400`. Change with `MAX_REQUEST_BODY_BYTES`.
* **IDs** in URLs are validated public IDs (`EMP-5001`); anything else is a clean `404`.
* **SQL injection**: all database access uses SQLAlchemy with bound parameters. There is no string-built SQL in the
  app. Even so, the app's database user has no rights to change the schema (§8), limiting the damage of a future bug.

## 2. Output hardening and IDOR

* Responses are built from explicit output models (`response_model`): password hashes, tokens, session IDs and internal
  numeric IDs never leave the server, whatever the database row contains.
* Every record endpoint checks a permission; "own" data (`/api/me/...`) is looked up from the session, never from an ID
  the client sends. Users with only `profile:own` get `403` on `/api/employees/{id}` for every ID, including their own.
* Errors never contain stack traces, SQL, or values. A `500` returns
  `{"detail": "Something went wrong on the server (reference: <request id>).", "code": "server_error"}`; the same ID is
  on the log line and in the `X-Request-ID` header, so support can find it.
* `Cache-Control: no-store` on all API responses (personal data shouldn't sit in browser or proxy caches).

## 3. HTTP security headers

| Header | API (`/api/*`) | Frontend (production build) | Why |
|---|---|---|---|
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` | `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'` | Only our own files may run; an injected `<script>` or inline `onerror=` is blocked. |
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` **only when `HSTS_MAX_AGE` > 0** (default: production only) | set by the HTTPS proxy (Phase 6) | Forces HTTPS. Never on plain http://127.0.0.1: browsers would remember it and refuse http for a year. |
| `X-Content-Type-Options` | `nosniff` | `nosniff` | No guessing file types. |
| `X-Frame-Options` / `frame-ancestors` | `DENY` | `DENY` | No clickjacking via iframes. |
| `Referrer-Policy` | `no-referrer` | `strict-origin-when-cross-origin` | URLs (with IDs) don't leak to other sites. |
| `Permissions-Policy` | camera, microphone, geolocation, payment, USB… all `()` | same | Features the app doesn't use can't be abused. |
| `Cross-Origin-Opener-Policy` / `-Resource-Policy` | `same-origin` | — | Isolation from other sites' windows. |

**Compatibility with React (tested):** the old inline theme script in `index.html` was moved to
`public/theme-init.js`; the production build has no inline scripts or styles. Checked in Chromium on all 10 pages
(sign-in, dashboard, employees, departments, jobs, candidates, pipeline, users, roles, audit log, profile): **zero CSP
violations**. The **dev server** (`npm run dev`) uses a relaxed policy (`'unsafe-inline'`, `ws:`) because Vite's hot
reload injects inline scripts; `npm run preview` (port 4173) serves the build with the strict production headers so
you can test them locally. Both header sets live in `frontend/security-headers.js`; the production web server/proxy
(Phase 6) must send the same `productionHeaders`.

## 4. CSRF

Cookies are sent automatically, so writes need more than the cookie:
1. `SameSite=Lax` session cookie.
2. A per-session **CSRF token** in `X-CSRF-Token` on every POST/PUT/PATCH/DELETE (`403 csrf_failed`).
3. **Origin validation:** a write is refused (`403 bad_origin`) if `Origin` is present and not in `FRONTEND_ORIGINS`;
   if `Origin` is absent, the `Referer`'s origin must match; `Sec-Fetch-Site: cross-site` is always refused.
4. JSON-only bodies: a plain HTML form on another site can't produce one.
Refusals are recorded in the audit log (`security.cross_site_refused`).

## 5. Audit logging

**What is recorded** (`audit_events` table, PostgreSQL): sign-in success and failure (with the e-mail tried),
sign-out, registration, password change/reset, re-authentication; user invitations, profile/status/role changes,
reset links, ended sessions; role create/update/delete; create/update/delete of employees, departments, jobs,
candidates, applications (status changes with from/to); demo reset; and security events: refused requests
(`security.access_denied`, `security.cross_site_refused`), rate-limit blocks, too many attempts, sign-ins from a new
device. Each record: time, category, action, outcome (`success`/`failure`/`denied`), actor (user ID + e-mail), target
(public ID), IP, user agent, request ID, details.

**Never recorded:** passwords (even wrong ones), tokens, cookies, CSRF tokens, request bodies, or personal field
*values* (names, e-mails, phones, dates of joining): for those only the *names* of changed fields are stored. Long
texts (job descriptions) are recorded as "changed", not copied.

**Who can see it:** only roles with `audit:read` (Super Administrator by default): *Administration → Audit log*, with
filters, a 24-hour summary (sign-ins, failures, refusals, rate-limit blocks, new devices) and **Verify integrity**.
API: `GET /api/audit/events`, `/api/audit/summary`, `/api/audit/verify`. There is no API to edit or delete records.

**How records are protected, and the limits of it.** These raise the cost of tampering and make most tampering
*detectable*. They do **not** make the log tamper-proof:
1. *The app can only append.* No endpoint changes records; with the least-privilege setup (§8) the app's database user
   lacks `UPDATE`/`DELETE`/`TRUNCATE` on the table.
2. *The database refuses edits*: triggers reject `UPDATE`, `DELETE`, `TRUNCATE` on `audit_events` for everyone,
   including the owner. But an owner or superuser can disable the triggers, and a superuser can do anything.
3. *Hash chain*: each record stores `HMAC-SHA256(AUDIT_HMAC_KEY, record + previous record's hash)`. Changing, inserting
   or removing a record in the middle breaks verification. The key lives **outside** the database, so someone with
   database access alone can't recompute valid signatures. **Not detected:** someone who has both database-owner
   access **and** the key; deleting the newest records (the chain still verifies; write down the latest hash printed
   by `python -m app.audit_verify` periodically to notice); and anything done before a record was written.
4. Records are written in their **own transaction** right after the business change commits, so a failed request's
   rollback can't erase "access denied" records. Consequence: if the database fails *between* the two commits, a change
   could exist without its audit record. Writes are serialized with a PostgreSQL advisory lock to keep the chain linear.

For real tamper-resistance in production (Phase 6+): ship audit records to a separate, append-only system the
application's operators can't modify (e.g. a log service with retention lock / WORM storage), and verify daily:
`python -m app.audit_verify` (exit code 1 on a problem).

**Retention.** Records are kept indefinitely (roughly 0.5–1 KB each). Pruning isn't automated: deleting old records
requires the owner to disable the trigger deliberately (`ALTER TABLE audit_events DISABLE TRIGGER
audit_events_no_update_delete;` … `ENABLE TRIGGER`), which is itself the kind of action to approve and document.
Export first (`pg_dump -t audit_events`). After pruning, verification will report the oldest remaining record as a
chain break: expected, and the reason to record the last hash of the archived part.

## 6. Rate limiting

Library: [`limits`](https://limits.readthedocs.io) (maintained, used by `slowapi`), moving-window algorithm,
implemented as an ASGI middleware so it covers every endpoint without decorators.

| Tier | Applies to | Counted per | Default (`.env`) |
|---|---|---|---|
| `read` | GET requests | session (or IP if not signed in) | `RATE_LIMIT_READ=300/minute` |
| `write` | POST/PUT/PATCH/DELETE | session (or IP) | `RATE_LIMIT_WRITE=60/minute` |
| `auth` | login, register, reset-password, reauthenticate, change-password | **IP** | `RATE_LIMIT_AUTH=20/minute` |
| `sensitive` | inviting users, reset links, ending sessions, status/role changes, roles, demo reset | session | `RATE_LIMIT_SENSITIVE=30/hour` |
| `per_ip` | everything | IP | `RATE_LIMIT_PER_IP=1200/minute` |

Over the limit: `429 {"code": "rate_limited"}` with a `Retry-After` header (seconds); the frontend shows the message.
Each block is logged and audited (`security.rate_limited`, at most once per minute per client so a flood can't flood
the audit log). Phase 3's database-backed limits stay on top: 5 failed sign-ins per e-mail per 15 minutes, etc.
`RATE_LIMIT_ENABLED=false` turns the middleware off (the automated tests do this, then test it separately).

**Shared store, multiple instances.** Counters live in the memory of the backend process. That is correct for one
process (how WorkforceOS runs now) and is why Redis was **not** added. With several processes (`uvicorn --workers 4`)
or several servers, each keeps its own counters, so the effective limit becomes N× the setting, and a restart resets
them. At that point use a shared store: `limits` supports Redis/Memcached, so it's a change in
`RateLimitMiddleware.__init__` (`MemoryStorage()` → `storage_from_string("redis://…")`) plus a Redis server.

**Client IPs.** Limits by IP use the TCP peer address. Behind the Vite proxy or any reverse proxy that is the proxy
(everyone looks like `127.0.0.1`). In production, run uvicorn with `--proxy-headers --forwarded-allow-ips=<proxy IP>`
so `X-Forwarded-For` is honoured **only** from your own proxy; never trust it from anywhere (clients could fake it).

## 7. Sessions and accounts

* **Fixation:** signing in always ends whatever session the browser presented and issues a new random token.
* **Re-authentication ("sudo mode")** for high-impact actions: inviting/editing/disabling users, assigning roles,
  creating reset links, ending someone's sessions, creating/editing/deleting roles, demo reset. The password must have
  been entered within `REAUTH_MINUTES` (10). Otherwise `403 reauth_required`; the UI asks for the password and then
  completes the original action. Cancelling cancels the action.
* **Suspicious sign-ins:** a sign-in from an IP + browser combination not among the user's last 20 successful sign-ins
  is recorded as `security.new_device_sign_in` and shown to the user under *My profile → Recent sign-ins*, together
  with failed attempts on their account. Admins see counts in the audit summary.
* Unchanged from Phase 3: idle/absolute expiry, revoke other sessions, password change ends other sessions,
  Argon2id, per-e-mail throttling.

## 8. Least-privilege database access

Two PostgreSQL users:

| User | Used by | Rights |
|---|---|---|
| `workforceos` (owner) | `alembic upgrade` (`MIGRATION_DATABASE_URL`), backups | owns the tables, can change the schema |
| `workforceos_app` | the running app (`DATABASE_URL`) | `SELECT/INSERT/UPDATE/DELETE` on data tables; **only `SELECT/INSERT`** on `audit_events`; **read-only** `permissions`, `alembic_version`; no `CREATE`, `DROP`, `ALTER`, `TRUNCATE` |

Set up (creates the user with a random password, applies `scripts/grant_app_privileges.sql`, updates `.env`, keeps a
copy of the old one, verifies):
```bash
cd backend && source .venv/bin/activate
./scripts/setup_least_privilege.sh      # asks for your sudo password (to act as the postgres superuser)
```
Run it again after each `alembic upgrade head` that adds tables (new tables get the default grants automatically, but
the audit/permissions restrictions are re-applied by the script). Production refuses to start if the app connects as
the same user as migrations. Also applied: `statement_timeout=15s` and `idle_in_transaction_session_timeout` on the
app's connections; SQL parameters are hidden from error logs (`hide_parameters=True`).

## 9. Backups and restore

```bash
cd backend && source .venv/bin/activate
./scripts/backup_db.sh                       # ~/workforceos-backups/workforceos-YYYYmmdd-HHMMSS.dump (+ .sha256)
BACKUP_DIR=/mnt/external KEEP_DAYS=30 ./scripts/backup_db.sh
./scripts/restore_db.sh ~/workforceos-backups/workforceos-20261115-101500.dump workforceos_restored
```
* Compressed custom format (`pg_dump -Fc`), created with `umask 077` (only you can read it), SHA-256 checksum, backups
  older than `KEEP_DAYS` (14) pruned.
* Restore goes into a **new** database, never over the live one; refuses on a checksum mismatch; afterwards it prints
  table counts, the migration version, and verifies the audit chain. To switch over, point `DATABASE_URL` (and
  `MIGRATION_DATABASE_URL`) at the new database and re-run `setup_least_privilege.sh` if you use it.
* A backup contains password **hashes** and the audit log: keep it as protected as the database. Copy it off the
  machine, encrypted (e.g. `gpg --symmetric file.dump`), and **test a restore** every month; an untested backup isn't
  one. Daily automatic backups at 02:30 (`crontab -e`, adjust the path):
  ```
  30 2 * * * cd $HOME/Downloads/workforceos-phase4/workforceos/backend && PATH=$PWD/.venv/bin:$PATH ./scripts/backup_db.sh >> $HOME/workforceos-backups/backup.log 2>&1
  ```

## 10. Secrets and configuration

* No credentials in code or in the repository. `backend/.env` (development) is git-ignored; production uses real
  environment variables or a secret manager (`.env.production.example` lists them).
* `APP_ENV=production` **refuses to start** with: non-`https://` origins, the app using the owner DB user, SQLite, a
  missing/short `AUDIT_HMAC_KEY`, HSTS off, `*` in `FRONTEND_ORIGINS` (refused everywhere). It also forces `Secure`
  cookies, the standard Argon2 profile, disables demo data/reset and the API docs.
* CORS: only the listed `FRONTEND_ORIGINS`, with credentials, only the methods and headers the app uses.
* Run production uvicorn with `--no-server-header` (don't advertise the server software).

### Secret rotation procedures
**Database password** (do it when someone with access leaves, or yearly):
```bash
NEW=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
sudo -u postgres psql -c "ALTER USER workforceos_app PASSWORD '$NEW';"
# update the password inside DATABASE_URL in backend/.env (or the production secret store), then restart the backend
```
For the owner user, the same with `workforceos` and `MIGRATION_DATABASE_URL`. (`setup_least_privilege.sh` also
generates a fresh app password each time it runs.)

**`AUDIT_HMAC_KEY`** (yearly, or immediately if it may have leaked):
1. Generate: `python -c "import secrets; print(secrets.token_hex(32))"`.
2. Move the current key into `AUDIT_HMAC_OLD_KEYS` (comma-separated), put the new one in `AUDIT_HMAC_KEY`, restart.
3. New records are signed with the new key (each record stores a short key fingerprint); old ones still verify with the
   old key. Never delete an old key while records signed with it exist, or verification reports "unknown key".
4. If the old key **leaked**, an attacker could have forged history signed with it: verify now, and keep the result
   (and the latest hash) as your trusted reference point.

**Sessions** (after a suspected compromise, or when rotating everything): end every session for everyone:
```bash
psql -h localhost -U workforceos -d workforceos -c "DELETE FROM sessions;"
```
Everyone must sign in again. For one account: *Users → (person) → End all sessions*. Session tokens aren't signed with a
server secret (they are random values whose hash is stored), so there is no session key to rotate.

**Reset links** expire on their own (Phase 3); to invalidate all pending ones: `DELETE FROM password_reset_tokens WHERE used_at IS NULL;`

## 11. Dependency scanning

```bash
cd backend && source .venv/bin/activate && pip install -r requirements-security.txt   # bandit, pip-audit (once)
cd .. && ./scripts/security_scan.sh            # bandit + pip-audit + npm audit (+ trivy if installed)
./scripts/security_scan.sh --strict            # same, exit code 1 if anything is found (for CI in Phase 7)
```
Reports are saved in `security-reports/<date>/` (git-ignored). Optional Trivy (scans lockfiles and finds accidentally
committed secrets):
```bash
sudo apt install -y wget gnupg
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor | sudo tee /usr/share/keyrings/trivy.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] https://aquasecurity.github.io/trivy-repo/deb generic main" | sudo tee /etc/apt/sources.list.d/trivy.list
sudo apt update && sudo apt install -y trivy
```
**Process:** run monthly and before every release. For each finding: read the advisory → is the vulnerable code path
used by WorkforceOS? → upgrade the **one** affected package to the first fixed version (not "upgrade everything"),
run the full test suites, re-scan. If it can't be fixed yet, record it in SECURITY_ASSESSMENT.md with the reason and a
date to look again. Bandit false positives are suppressed only with a reason: `# nosec B105 # <why>`.

## 12. Security testing

* **Automated tests** (`backend/tests/test_security.py`, `test_audit.py`, plus the Phase 3 auth tests): headers,
  rate limits (each tier, `Retry-After`, per-IP), body limits, JSON-only, unknown fields, NUL bytes, malformed JSON,
  cross-site writes (Origin, Referer, Sec-Fetch-Site), sudo mode on every high-impact endpoint, session fixation,
  new-device detection, audit content (no secrets), audit access control, chain verification and tamper detection,
  database triggers (PostgreSQL), production configuration refusals.
* **Browser-level UI tests** (40, React Testing Library against the real backend): including the password prompt,
  the audit log page, and stored XSS rendering as text.
* **Real browser**: production build in Chromium under the strict CSP.
* **Optional OWASP ZAP baseline scan** (passive; run only against your own local instance):
  ```bash
  sudo snap install zaproxy --classic
  # start backend + `npm run build && npm run preview`, then:
  zaproxy -cmd -quickurl http://127.0.0.1:4173 -quickout ~/zap-report.html
  ```
  Expect informational alerts about the development setup (no HTTPS, so no HSTS). Treat the report as leads to check,
  not as a verdict, and record conclusions in SECURITY_ASSESSMENT.md.

## 13. Logging

* `LOG_FORMAT=text` (development) or `json` (production: one JSON object per line, for log tools); `LOG_LEVEL`.
* Every request: one access line with request ID, method, path (no query string, which may contain search terms),
  status, duration, client IP, user ID. Security events also go to the `workforceos.security` logger.
* **Never logged:** passwords, tokens, cookies, CSRF tokens, request bodies, SQL parameter values.
* Server logs are for diagnosis and rotate away; the audit log is the accountable record.

## 14. Frontend

* No `dangerouslySetInnerHTML`, `eval`, `innerHTML`, or `target="_blank"` without `rel="noopener"`; React escapes all
  text (tested with stored `<img onerror>` payloads).
* The session cookie is `HttpOnly`: JavaScript (including injected script) can't read it. The CSRF token is kept in
  memory only, not in `localStorage`. `localStorage` holds only UI preferences (theme, sidebar), wrapped in try/catch.
* Forms send only editable fields; the UI hides what a role can't use, but **the server enforces every permission**.
* Production build: no source maps, strict CSP; external script `theme-init.js` instead of inline code.

## 15. Not covered yet (by design or later phases)

No HTTPS locally (Phase 6) · no MFA · no e-mail (verification, reset, alerts) · IP-based limits need trusted-proxy
configuration · in-memory rate limits (single process) · audit log not shipped off-site · no automated scanning in CI
(Phase 7) · no file uploads exist, so no upload hardening was added · no WAF/DDoS protection (hosting layer).
