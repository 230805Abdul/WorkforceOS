# WorkforceOS authentication & authorization (Phase 3, updated in Phase 4)

**Authentication** answers *who are you?* **Authorization** answers *what may you do?* Both are decided by the
**backend** on every request. The React app only mirrors the answer to hide buttons you couldn't use anyway.

## 1. The chosen mechanism: server-side sessions in an HttpOnly cookie

WorkforceOS is a browser app whose frontend and API share one origin (Vite proxies `/api`), so it uses classic
**server-side sessions** rather than JWTs:

| | Sessions (chosen) | JWT access + refresh tokens |
|---|---|---|
| Sign out / disable a user | instant: delete the row | needs a revocation list anyway |
| Where the secret lives in the browser | HttpOnly cookie: unreadable by JavaScript, so an XSS bug can't steal it | often `localStorage`, readable by any script |
| Moving parts | 1 table, 1 cookie | 2 token types, rotation, reuse detection, clock skew |
| Good for | same-origin web apps (this one) | many independent APIs/services, mobile apps |

So there is no `/api/auth/refresh`: the server extends nothing, it just checks the session row on every request.

### Session lifecycle
```
sign in ──► server creates random 256-bit token ──► Set-Cookie: wos_session=<token>; HttpOnly; SameSite=Lax; Path=/ (+ Secure in production)
            DB stores sessions(token_hash = sha256(token), csrf_token, expires_at, last_seen_at, remember)
every request ──► cookie ──► sha256 ──► row? not expired? not idle too long? user still active? ──► permissions ──► allowed?
sign out ──► row deleted + cookie cleared            password changed/reset ──► all OTHER sessions deleted
account disabled ──► all its sessions deleted       idle / too old ──► 401 "session_expired" + cookie cleared
```

| Setting (`backend/.env`) | Default | Meaning |
|---|---|---|
| `SESSION_IDLE_MINUTES` | 120 | normal sign-in ends after this long without activity |
| `SESSION_ABSOLUTE_HOURS` | 12 | …and at the latest after this long; the cookie also disappears when the browser closes |
| `REMEMBER_ME_DAYS` / `REMEMBER_ME_IDLE_DAYS` | 30 / 7 | "Keep me signed in": persistent cookie, longer limits |
| `MAX_SESSIONS_PER_USER` | 5 | **concurrent-session policy**: a 6th sign-in ends the oldest session |
| `COOKIE_SECURE` | false (dev) | forced **on** when `APP_ENV=production` (HTTPS only) |

### CSRF protection (because cookies are sent automatically)
1. `SameSite=Lax`: browsers don't attach the cookie to cross-site POST/PUT/PATCH/DELETE.
2. **Per-session CSRF token**: `GET /api/auth/me` returns `csrf_token`; every state-changing request must send it in
   `X-CSRF-Token`. Another site can't read our responses, so it can't know the token. Missing/wrong → `403 csrf_failed`.
3. **Origin check** (Phase 4: also `Referer` and `Sec-Fetch-Site`): a write whose `Origin` (or, without one, `Referer`)
   isn't in `FRONTEND_ORIGINS`, or that the browser marks `cross-site`, is refused (`403 bad_origin`) and audited.
4. The API only accepts JSON bodies, which a plain HTML `<form>` on another site can't send.

## 2. Passwords

* **Argon2id** via `argon2-cffi` (the RFC 9106 recommended profile: 64 MiB memory, 3 passes, 4 lanes, random salt).
  Stored as e.g. `$argon2id$v=19$m=65536,t=3,p=4$<salt>$<hash>`. Never plaintext, never reversible encryption.
  If the parameters are raised later, hashes are upgraded automatically at the next sign-in.
* **Policy** (NIST SP 800-63B style, length over composition rules): 12–128 characters, not a common password, must not
  contain your e-mail name or your name.
* Change password: requires the current password; signs out every other browser.
* Unknown e-mail and wrong password give the **same** message and take the same time (a dummy hash is checked), so the
  sign-in form can't be used to find out who has an account.

## 3. Password reset & invitations (no e-mail yet)

WorkforceOS can't send e-mail, so instead of a fake "we sent you a link" page:
1. A Super Administrator opens **Administration → Users → (user) → Create password-reset link** (or invites a new user).
2. The server creates a random token, stores only its SHA-256 hash, valid **once**, for 60 minutes (invitations: 72 hours).
   Creating a new link cancels older unused ones.
3. The admin gives the link to the person privately. They open `/reset-password?token=…`, the page removes the token from
   the address bar, and they choose a password. All their sessions are ended.

## 4. Roles and permissions

Permissions are defined once in `backend/app/auth/permissions.py`, stored in the `permissions` table, and bundled into
roles (`roles`, `role_permissions`). A user can have several roles (`user_roles`); their rights are the union.
The API checks **permissions, never role names**:

```python
@router.delete("/{employee_id}", dependencies=[Depends(require("employees:delete"))])
```

| Permission | Super Admin | HR Admin | HR Manager | Recruiter | Employee |
|---|:-:|:-:|:-:|:-:|:-:|
| `dashboard:view` (sections follow the read permissions) | ✓ | ✓ | ✓ | ✓ | |
| `employees:read` | ✓ | ✓ | ✓ | | own record via My profile |
| `employees:create` / `employees:update` | ✓ | ✓ | | | own phone only |
| `employees:delete` | ✓ | | | | |
| `departments:read` | ✓ | ✓ | ✓ | ✓ | |
| `departments:manage` | ✓ | ✓ | | | |
| `jobs:*`, `candidates:*` (read / manage) | ✓ | ✓ | read | ✓ | |
| `applications:read` / `applications:manage` (pipeline) | ✓ | ✓ | ✓ | ✓ | |
| `users:read`, `users:manage` | ✓ | | | | |
| `roles:assign`, `roles:manage` | ✓ | | | | |
| `system:demo_reset` | ✓ | | | | |
| `profile:own` | ✓ | ✓ | ✓ | ✓ | ✓ |

Design choices: the HR Manager reviews and runs the pipeline but doesn't edit employee records; the Recruiter role exists
because WorkforceOS has a recruiting module and recruiters shouldn't see employee data. Administrators can create
more roles on the **Roles** page.

### Rules against privilege escalation and lock-outs
* Public registration always gives the **Employee** role; input models reject unknown fields (`extra="forbid"`), so
  `{"roles": ["super_admin"]}` in any request is a 422, not silently applied (mass assignment).
* Nobody can change their **own** roles or status. You can only grant permissions you hold yourself.
* The last active Super Administrator can't be disabled or demoted; the Super Administrator role's permissions are locked.
* Built-in roles can't be deleted; a role still assigned to someone can't be deleted.
* Employees read their own record through `/api/me/employee` (no id in the URL), so they can't fetch someone else's
  by changing a number (IDOR). The HR endpoints `/api/employees/...` need `employees:read`.
* Permission changes take effect on the user's next request (they're checked every time, not baked into a token).

### Accounts vs employee records
`users` and `employees` are separate tables. `users.employee_id` is an **optional, unique** link: an employee may have no
account, an account (e.g. an external recruiter) may have no employee record. Registration never links automatically by
e-mail (anyone could register with a colleague's address); an administrator links them on the Users page.

## 5. API endpoints

**Public:** `GET /api/health` · `GET /api/auth/config` · `POST /api/auth/register` · `POST /api/auth/login` ·
`POST /api/auth/logout` · `POST /api/auth/reset-password`

**Any signed-in user:** `GET /api/auth/me` · `GET /api/meta` · `POST /api/auth/change-password` ·
`PATCH /api/auth/me` (name), `POST /api/auth/logout-others`, `GET|PATCH /api/me/employee` (phone) – these need `profile:own`

**Administration:** `GET /api/users` · `GET /api/users/{id}` (users:read) · `POST /api/users` (invite) ·
`PATCH /api/users/{id}` (name, employee link) · `PATCH /api/users/{id}/status` · `POST /api/users/{id}/reset-link` ·
`POST /api/users/{id}/revoke-sessions` (users:manage) · `PUT /api/users/{id}/roles` (roles:assign) ·
`GET /api/roles`, `GET /api/permissions` (users:read, roles:assign or roles:manage) ·
`POST /api/roles`, `PUT /api/roles/{id}`, `DELETE /api/roles/{id}` (roles:manage)

**Phase 4:** `POST /api/auth/reauthenticate` (confirm your password for "sudo mode") · `GET /api/auth/me/sign-ins`
(your recent sign-ins and failed attempts) · `GET /api/audit/events`, `/api/audit/summary`, `/api/audit/verify`
(`audit:read`, Super Administrator by default).

**Sudo mode:** these also need the password typed within the last `REAUTH_MINUTES` (10): `POST /api/users`,
`PATCH /api/users/{id}`, `PATCH /api/users/{id}/status`, `PUT /api/users/{id}/roles`, `POST /api/users/{id}/reset-link`,
`POST /api/users/{id}/revoke-sessions`, `POST|PUT|DELETE /api/roles…`, `POST /api/demo/reset`. Otherwise
`403 reauth_required`; the frontend asks for the password, then retries the action automatically.

**Business endpoints:** unchanged URLs, each with its permission (see the table above).

Status codes: `401` not signed in / session ended (`code`: `not_authenticated`, `session_expired`, `account_disabled`,
`invalid_credentials`) · `403` signed in but not allowed (`forbidden`, `csrf_failed`, `bad_origin`, `self_change`,
`privilege_escalation`, `registration_disabled`, `reauth_required`) · `409` conflicts (`last_super_admin`, `locked_role`, `role_in_use`) ·
`429` rate limited (with `Retry-After`) · Phase 4: `400` malformed JSON / invalid data · `413` body over 64 KB ·
`415` body not JSON.

## 6. Rate limits (stored in `auth_attempts`, survive restarts)
Phase 4 adds general per-session and per-IP limits for every endpoint on top of these: see
[SECURITY.md §6](SECURITY.md#6-rate-limiting).
* sign-in: 5 failed attempts per e-mail per 15 min (reset by a successful sign-in) and 30 per IP per 15 min
* registration: 10 per IP per hour · reset links: 10 failed attempts per IP per 15 min
* changing your password with a wrong current password counts as a failed sign-in

## 7. Known limitations (honest list)
* **No e-mail**: no self-service "forgot password" and no e-mail verification. Registration therefore **does reveal**
  whether an e-mail already has an account (mitigated by the registration rate limit).
* **IP-based limits behind the dev proxy**: every request seems to come from 127.0.0.1, so the per-IP limits are shared by
  everyone. Proper client IPs need a trusted reverse proxy (Phase 5/6). Per-e-mail login limits are unaffected.
* **No MFA / 2FA** and no e-mail alerts. (Phase 4: sign-ins from a new device are flagged in the audit log and shown
  under *My profile → Recent sign-ins*.)
* ~~No security headers~~, ~~no audit log~~, ~~no re-authentication for admin actions~~: added in Phase 4
  ([SECURITY.md](SECURITY.md)).
* **HTTP in development**: cookies are not `Secure` locally. Production must run behind HTTPS (`APP_ENV=production` forces
  `Secure` cookies).
* E-mail addresses can't be changed through the UI yet. Accounts can be disabled but not deleted.
* Users with `users:manage` can generate a reset link for any account, including other administrators: that role is
  powerful by design and should be given to very few people.
