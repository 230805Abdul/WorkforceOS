# WorkforceOS security assessment (Phase 4)

**Scope:** the Phase 3 code base (FastAPI backend, React frontend, PostgreSQL schema, helper scripts), reviewed
against the **OWASP Top 10 (2021)**, then re-tested after the Phase 4 changes.
**Method:** reading the code; probing a running Phase 3 instance with crafted requests (oversized and malformed bodies,
NUL bytes, form posts, cross-site requests, request floods, injection-shaped search terms); automated tests; Bandit,
pip-audit and npm audit; a real Chromium browser against the production build.
**Date:** November 2026. **Status column:** *Fixed* = changed in Phase 4 and covered by a test. *Mitigated* = risk
reduced, some remains. *Accepted* = deliberately left, with the reason. *Later* = belongs to a later phase.

> **This is not a certificate.** It lists what was looked for and found. No scan or review proves the absence of
> vulnerabilities; scanners only recognise *known* problems. Re-assess after every significant change.

## 1. What was already sound (Phase 3, re-checked)

| Area | Evidence |
|---|---|
| SQL injection (A03) | All queries go through SQLAlchemy with bound parameters, no string-built SQL. Re-tested: searching for `' OR 1=1--` and `a'; DROP TABLE employees;--` returns 0 rows, tables intact. `%` and `_` in searches are escaped, so `%` matches literally, not "everything". |
| Passwords (A02/A07) | Argon2id (RFC 9106 profile), breached/common-password checks, per-e-mail and per-IP login throttling stored in the database. |
| Sessions (A07) | Random 256-bit token in an `HttpOnly`, `SameSite=Lax` cookie; only its SHA-256 is stored; idle + absolute expiry; revocation. |
| Authorization (A01) | Every endpoint checks a permission on the server; role × endpoint matrix test; privilege-escalation and last-admin rules; IDOR tests (users can't read others' records by changing an ID). |
| XSS (A03) | React escapes text by default; no `dangerouslySetInnerHTML`, `eval` or `innerHTML` anywhere in `src/`. Re-tested with a stored `<img src=x onerror=…>` department name: rendered as text, nothing executed. |
| Secrets in the repo (A05) | `.env` git-ignored; examples contain placeholders only. |
| Dependencies (A06) | Phase 3 upgraded Vite/React Router: `npm audit` 0 vulnerabilities. |

## 2. Findings and what was done

Severity reflects impact × likelihood **for this app as deployed after Phase 6** (on the internet, behind HTTPS).

| # | Finding (affected component) | OWASP | Severity | Impact | Mitigation in Phase 4 | Status |
|---|---|---|---|---|---|---|
| P1 | **No general rate limiting.** Only sign-in/registration/reset were throttled; 100+ requests/second to any other endpoint (e.g. `GET /api/employees`) all succeeded. (`backend/app/main.py`) | A04, A05 | Medium | Data scraping by a stolen session at full speed, cheap denial of service, brute force against endpoints added later. | Tiered limits (`limits` library, moving window): read 300/min, write 60/min per session; sign-in endpoints 20/min per IP; admin-sensitive 30/hour per session; 1200/min per IP safety net. `429` + `Retry-After`; blocks recorded in the audit log (once per minute per key). All configurable. | Fixed (`test_security.py::test_rate_limit_*`) |
| P2 | **Database errors became 500s and logged the raw values.** A NUL byte (`\x00`) in any text field crashed the request; the traceback in the log contained the SQL **parameters** (`[parameters: {'lower_1': 'bad\x00name'}]`). (`app/db.py`, `app/errors.py`) | A09, A04 | Medium | Personal data, and anything typed into a field, copied into log files that are often widely readable and retained for a long time. | Input types reject control characters; `hide_parameters=True` on the engine; a central `DataError` handler (400); integrity errors log only class/SQLSTATE/constraint. | Fixed |
| P3 | **No request size limit.** A 5 MB JSON body was read and parsed fully. (all write endpoints) | A04 | Medium | Memory exhaustion / slow requests with a handful of large uploads. | 64 KB limit enforced **while streaming**, before parsing (`413`); `Content-Length` checked up front. | Fixed |
| P4 | **Unknown fields silently ignored; forms accepted.** `{"role": "super_admin"}` added to a registration body was dropped without notice; `application/x-www-form-urlencoded` bodies were parsed. The frontend sent whole objects (including read-only fields) back on edit. | A01, A08 | Low | Not exploitable today (models whitelist fields), but one future careless `**payload` would become mass assignment. Silent ignoring hides client bugs. | All input models are `extra="forbid"` (unknown field → `422 "This field cannot be changed here"`); text length limits on every string; JSON-only bodies (`415` otherwise); malformed JSON → `400`; the frontend now sends only editable fields. | Fixed |
| P5 | **No HTTP security headers** on the API or the frontend (no CSP, `nosniff`, framing protection, Referrer/Permissions-Policy). The app's inline theme `<script>` would have been blocked by any strict CSP. (`main.py`, `index.html`, `vite.config.js`) | A05 | Medium | No second line of defence if an XSS bug appears; clickjacking of admin pages possible. | Strict API headers (`default-src 'none'`), strict production frontend CSP (`script-src 'self'`, `style-src 'self'`, `frame-ancestors 'none'`, no `unsafe-inline`); inline script moved to `/theme-init.js`; HSTS only when HTTPS is in use (production). A relaxed CSP is used **only** by the dev server, because Vite's hot reload needs inline scripts. | Fixed (0 CSP violations in Chromium on all 10 pages, production build) |
| P6 | **No audit trail.** The Phase 2 "activity" feed covers business records only, is editable by the app, and records neither who acted, from where, nor failed/refused actions. | A09 | High | After a misuse or compromise, nobody could say who did what, and an attacker could not be distinguished from a legitimate admin. | Append-only `audit_events` table: sign-ins (success/failure), account and role changes, every data change, refused requests, rate-limit blocks; HMAC hash chain; database triggers block `UPDATE`/`DELETE`/`TRUNCATE`; admin-only page with filters and integrity check. Limits: see SECURITY.md §5. | Fixed |
| P7 | **A hijacked admin session had full power immediately.** Granting roles, disabling users, creating reset links needed only a valid session. | A07, A01 | Medium | A briefly unattended unlocked laptop, or a stolen cookie, is enough to create a backdoor admin. | "Sudo mode": those actions require the password typed within the last 10 minutes (`403 reauth_required` → the UI asks, then continues the action). Sign-in rotates the session (no fixation). Sign-ins from a new device/IP are flagged in the audit log and shown to the user under *Recent sign-ins*. | Fixed |
| P8 | **The app connected as the database owner**, with no statement timeout. (`DATABASE_URL`) | A05, A04 | Medium | Any SQL injection or app bug would be able to `DROP`/`ALTER` tables and rewrite the audit log; one slow query could tie up the database indefinitely. | Separate `workforceos_app` role with data-only rights (no DDL, no UPDATE/DELETE on the audit log, read-only permission catalogue); migrations use the owner via `MIGRATION_DATABASE_URL`; production refuses to start if both are the same user. `statement_timeout` 15 s and `idle_in_transaction_session_timeout`. | Fixed (optional in development, enforced in production) |
| P9 | **CSRF origin check relied on the `Origin` header alone.** A write without `Origin` was accepted (some older browsers and privacy tools omit it). | A01 | Low | Defence-in-depth gap only: the CSRF token and SameSite cookie still applied. | Writes are refused when `Origin` **or**, if absent, `Referer` is foreign, or when `Sec-Fetch-Site: cross-site`. Refusals are audited. | Fixed |
| P10 | **Unsafe production configuration was possible**: `http://` origins, the dev audit key, owner DB user, no HSTS, API docs (`/docs`, `/openapi.json`) public; unhandled errors returned no reference and plain-text logs had no request IDs. | A05, A09 | Medium | One forgotten setting silently weakens a production deployment; incidents can't be traced. | `APP_ENV=production` **refuses to start** with insecure settings (listed in `config.py`); docs off by default in production; structured JSON logs with request ID, user ID, status, duration (never bodies, passwords, tokens or cookies); 500 responses carry a reference ID matching the log line; `X-Request-ID` header. | Fixed |
| P11 | Jobs and applications changes were missing from the new audit log during development of this phase. | A09 | Low | Gaps in accountability for hiring decisions. | Added `job.*` and `application.*` events. | Fixed |
| P12 | **Rate-limit and per-IP counts use the connecting address.** Behind the Vite dev proxy everyone is `127.0.0.1`; in production behind a reverse proxy the same would be true unless the proxy's `X-Forwarded-For` is trusted. | A04 | Low (dev) / Medium (prod) | Per-IP limits shared by all users, or bypassable if forwarded headers were trusted blindly. | Documented. uvicorn's `--proxy-headers --forwarded-allow-ips=<proxy IP>` is the fix once a known proxy exists (Phase 5/6). Per-session and per-e-mail limits are unaffected. | Later |
| P13 | **In-memory rate-limit counters.** They reset on restart and are per process. | A04 | Low | With N backend processes the effective limit is N× the configured one. | Documented; switching `MemoryStorage` to the `limits` Redis storage is a one-line change when there is more than one instance. Not introduced now: one process doesn't need it. | Accepted |
| P14 | No MFA; no e-mail (so no "new sign-in" e-mail, no self-service reset, registration reveals whether an e-mail exists). | A07 | Medium | Account takeover relies on the password alone. | Out of scope for this phase (needs an e-mail provider). New-device sign-ins are at least visible in the UI and audit log. | Later |
| P15 | Development-only conveniences: demo users with a public password, the demo-reset endpoint, `COOKIE_SECURE=false` on http. | A05, A07 | Low | Only if a development configuration were exposed. | Each is refused or forced off when `APP_ENV=production`. | Accepted |

**Not applicable:** *File uploads* — WorkforceOS has none, so no upload module was added. *SSRF (A10)* — the backend
makes no outbound requests based on user input. *XML/deserialization* — JSON only; no pickle/YAML loading of input.

## 3. Automated scan results (re-run with `./scripts/security_scan.sh`)

| Tool | What it checks | Result (15 Nov 2026) |
|---|---|---|
| **Bandit 1.9** | our Python code (3,381 lines) | Before triage: 7 low-severity items. 1 real: an `assert` used as a startup check (vanishes under `python -O`) → replaced with an explicit check. 6 false positives (`B105` "hardcoded password" on error-message strings like `"Incorrect password"`, the hash-profile name `"standard"`, and the public **demo** password which production refuses) → each marked `# nosec B105 # <reason>`. After: **0 issues** (6 documented suppressions). |
| **pip-audit 2.10** | Python packages in `requirements.txt` | **No known vulnerabilities.** |
| **npm audit** | frontend packages (runtime and development tools) | **0 vulnerabilities.** |
| **Trivy** | lockfiles, committed secrets, misconfigurations | **Not run here:** it couldn't be downloaded in the build environment (network restricted). The script runs it automatically when installed; install steps in SECURITY.md §11. |
| **OWASP ZAP** | dynamic scan of the running app | **Not run** (needs a GUI/Docker setup that this phase excludes). Manual optional procedure in SECURITY.md §12. The hand-made probes below cover the same request-level checks for the endpoints that exist. |

### Dynamic checks performed (against a running server, default settings)

| Probe | Phase 3 | Phase 4 |
|---|---|---|
| 25 wrong sign-ins from one address | throttled per e-mail after 5 | per e-mail after 5 **and** whole address after 20/min (`429`, `Retry-After: 60`) |
| JSON body of 200 KB | accepted and parsed | `413 payload_too_large` |
| form-encoded body | parsed (`422`) | `415 unsupported_media_type` |
| malformed JSON | `422 {"9": "JSON decode error"}` | `400 "The request body is not valid JSON."` |
| `"role": "super_admin"` in a registration | silently ignored | `422 role: "This field cannot be changed here"` |
| NUL byte in a name | `500`, values in the log | `422`, nothing logged |
| write with `Origin: https://evil.example` | `403` | `403` (and now also via `Referer` / `Sec-Fetch-Site`), audited |
| employee calling `/api/audit/events`, `/api/employees/1` | — / `403` | `403` / `403`, audited |
| security headers on `/api/health` | none | CSP `default-src 'none'`, `nosniff`, `DENY`, `no-referrer`, Permissions-Policy, CORP/COOP, `no-store` |
| production build in Chromium (10 pages) | inline script blocked by any strict CSP | strict CSP, **0 violations**, all pages work |
| automated tests | Phase 3 suite | **344** backend tests (PostgreSQL) + **40** browser-level UI tests |

## 4. Residual risks (honest summary)

1. **Anyone with database-superuser access *and* the audit key** can rewrite audit history undetectably. The design
   raises the bar (two separate secrets, triggers, verification) but is not tamper-proof. Ship logs off-site for that.
2. **XSS would still be powerful**: the CSP blocks injected scripts and the cookie is `HttpOnly`, but a script that did
   run could act as the user. React's escaping is the main defence; avoid `dangerouslySetInnerHTML`.
3. **No MFA** (P14), **no e-mail** notifications, **IP-based limits need proxy configuration** (P12).
4. **HTTPS is not yet set up** (Phase 6): until then cookies are not `Secure` and HSTS is off — fine on `127.0.0.1`,
   unacceptable on a network.
5. The dependency scans are **point-in-time**: new vulnerabilities are published daily. Re-run monthly and before
   each release (SECURITY.md §11).
