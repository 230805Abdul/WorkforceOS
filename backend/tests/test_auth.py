"""Authentication: registration, sign-in, sessions, sign-out, password change/reset, invitations, rate limits, CSRF."""
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.auth.models import AuthAttempt, PasswordResetToken, Session, User
from app.main import app
from app.models import utcnow
from tests.conftest import PASSWORD, USERS, sign_in

NEW = {"full_name": "Nadia Newcomer", "email": "nadia@example.org", "password": "violet-tram-orbit-91", "password_confirm": "violet-tram-orbit-91"}
GOOD_NEW_PASSWORD = "lantern-pebble-quartz-77"


def _browser():
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------- registration
def test_registration_creates_restricted_account_and_signs_in(db):
    b = _browser()
    r = b.post("/api/auth/register", json=NEW)
    assert r.status_code == 201, r.text
    body = r.json()
    assert [role["name"] for role in body["roles"]] == ["employee"] and body["permissions"] == ["profile:own"]
    assert "password" not in r.text.lower().replace('"has_password"', "")  # no password or hash in the response
    assert "wos_session=" in r.headers["set-cookie"]
    assert b.get("/api/auth/me").json()["email"] == "nadia@example.org"
    stored = db.scalar(select(User).where(User.email == "nadia@example.org"))
    assert stored.password_hash.startswith("$argon2id$") and NEW["password"] not in stored.password_hash


def test_registration_cannot_choose_a_role_or_status():
    for extra in ({"roles": ["super_admin"]}, {"role": "super_admin"}, {"status": "active"}, {"is_admin": True}):
        r = _browser().post("/api/auth/register", json={**NEW, **extra})
        assert r.status_code == 422 and set(r.json()["errors"]) == set(extra), r.text


def test_registration_validation():
    b = _browser()
    r = b.post("/api/auth/register", json={**NEW, "email": "not-an-email"})
    assert r.status_code == 422 and r.json()["errors"]["email"] == "Enter a valid email address"
    r = b.post("/api/auth/register", json={**NEW, "password": "short", "password_confirm": "short"})
    assert r.status_code == 422 and "at least 12" in r.json()["errors"]["password"]
    r = b.post("/api/auth/register", json={**NEW, "password": "password1234", "password_confirm": "password1234"})
    assert "too common" in r.json()["errors"]["password"]
    r = b.post("/api/auth/register", json={**NEW, "password_confirm": "something-else-entirely"})
    assert r.json()["errors"] == {"password_confirm": "Passwords do not match"}
    r = b.post("/api/auth/register", json={**NEW, "password": "nadia-loves-trams-1", "password_confirm": "nadia-loves-trams-1"})
    assert "e-mail" in r.json()["errors"]["password"]


def test_duplicate_registration_is_rejected_case_insensitively():
    assert _browser().post("/api/auth/register", json=NEW).status_code == 201
    r = _browser().post("/api/auth/register", json={**NEW, "email": "NADIA@Example.ORG"})
    assert r.status_code == 409 and "email" in r.json()["errors"]


def test_registration_can_be_switched_off(monkeypatch):
    monkeypatch.setattr("app.routers.auth.REGISTRATION_ENABLED", False)
    r = _browser().post("/api/auth/register", json=NEW)
    assert r.status_code == 403 and r.json()["code"] == "registration_disabled"
    assert _browser().get("/api/auth/config").json()["registration_enabled"] is False  # the sign-up page hides itself


def test_registration_is_rate_limited_per_ip():
    for i in range(10):
        _browser().post("/api/auth/register", json={**NEW, "email": f"user{i}@example.org"})
    r = _browser().post("/api/auth/register", json={**NEW, "email": "one.more@example.org"})
    assert r.status_code == 429 and r.json()["code"] == "rate_limited" and int(r.headers["retry-after"]) > 0


# ---------------------------------------------------------------- sign-in
def test_login_sets_a_hardened_session_cookie():
    r = _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "path=/" in cookie
    assert "max-age" not in cookie  # without "remember me": a browser-session cookie
    assert r.json()["csrf_token"] and r.json()["permissions"]


def test_remember_me_sets_a_persistent_cookie():
    r = _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD, "remember": True})
    assert "max-age=" in r.headers["set-cookie"].lower()


def test_wrong_password_and_unknown_email_look_identical():
    b = _browser()
    wrong = b.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "not-the-password"})
    ghost = b.post("/api/auth/login", json={"email": "nobody@example.org", "password": "not-the-password"})
    assert wrong.status_code == ghost.status_code == 401
    assert wrong.json() == ghost.json() == {"detail": "Incorrect email or password.", "code": "invalid_credentials"}
    assert "set-cookie" not in wrong.headers


def test_login_email_is_case_insensitive_and_validated():
    assert _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0].upper(), "password": PASSWORD}).status_code == 200
    r = _browser().post("/api/auth/login", json={"email": "nope", "password": PASSWORD})
    assert r.status_code == 422 and "email" in r.json()["errors"]


def test_disabled_account_cannot_sign_in(db):
    db.execute(update(User).where(User.email == USERS["recruiter"][0]).values(status="disabled"))
    db.commit()
    wrong = _browser().post("/api/auth/login", json={"email": USERS["recruiter"][0], "password": "not-the-password"})
    assert wrong.status_code == 401  # wrong password: no hint that the account exists or is disabled
    right = _browser().post("/api/auth/login", json={"email": USERS["recruiter"][0], "password": PASSWORD})
    assert right.status_code == 403 and right.json()["code"] == "account_disabled"


def test_failed_logins_are_rate_limited_per_email():
    b = _browser()
    for _ in range(5):
        assert b.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "guess-guess-guess"}).status_code == 401
    r = b.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD})  # even the right one
    assert r.status_code == 429 and r.headers["retry-after"] == "900"
    assert b.post("/api/auth/login", json={"email": USERS["hr_manager"][0], "password": PASSWORD}).status_code == 200


def test_a_successful_login_resets_the_per_email_counter():
    b = _browser()
    for _ in range(4):
        b.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "guess-guess-guess"})
    assert b.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD}).status_code == 200
    for _ in range(4):
        assert b.post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "guess-guess-guess"}).status_code == 401


def test_attempts_are_stored_without_passwords(db):
    _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": "secret-guess-123"})
    row = db.scalar(select(AuthAttempt))
    assert row.kind == "login" and row.email == USERS["hr_admin"][0] and row.succeeded is False
    assert "secret-guess-123" not in repr(row.__dict__)


# ---------------------------------------------------------------- sessions
def test_unauthenticated_request_gets_401_and_session_lives_in_db(db):
    assert _browser().get("/api/employees").json()["code"] == "not_authenticated"
    c = sign_in(USERS["hr_admin"][0])
    token = c.cookies.get("wos_session")
    stored = db.scalars(select(Session.token_hash)).all()
    assert len(stored) == 1 and token not in stored and len(stored[0]) == 64  # only the SHA-256 hash is stored


def test_logout_ends_the_session_on_the_server():
    c = sign_in(USERS["hr_admin"][0])
    stolen_cookie = c.cookies.get("wos_session")
    r = c.post("/api/auth/logout")
    assert r.status_code == 204 and 'wos_session=""' in r.headers["set-cookie"]
    assert c.get("/api/employees").status_code == 401
    replay = _browser()
    replay.cookies.set("wos_session", stolen_cookie)  # the old cookie is worthless now
    assert replay.get("/api/auth/me").json()["code"] == "session_expired"


def test_logout_requires_the_csrf_token():
    c = sign_in(USERS["hr_admin"][0])
    del c.headers["X-CSRF-Token"]
    assert c.post("/api/auth/logout").json()["code"] == "csrf_failed"
    assert c.get("/api/auth/me").status_code == 200  # still signed in


def test_idle_session_expires(db):
    c = sign_in(USERS["hr_admin"][0])
    db.execute(update(Session).values(last_seen_at=utcnow() - timedelta(minutes=121)))
    db.commit()
    r = c.get("/api/employees")
    assert r.status_code == 401 and r.json()["code"] == "session_expired"
    assert 'wos_session=""' in r.headers["set-cookie"]  # the browser is told to drop the cookie
    assert db.scalar(select(Session.id)) is None


def test_absolute_session_lifetime_is_enforced(db):
    c = sign_in(USERS["hr_admin"][0])
    db.execute(update(Session).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert c.get("/api/auth/me").json()["code"] == "session_expired"


def test_remembered_sessions_tolerate_longer_idle(db):
    c = sign_in(USERS["hr_admin"][0], remember=True)
    db.execute(update(Session).values(last_seen_at=utcnow() - timedelta(days=3)))
    db.commit()
    assert c.get("/api/auth/me").status_code == 200


def test_at_most_five_sessions_per_user(db):
    first = sign_in(USERS["hr_admin"][0])
    others = [sign_in(USERS["hr_admin"][0]) for _ in range(5)]
    assert len(db.scalars(select(Session.id)).all()) == 5
    assert first.get("/api/auth/me").json()["code"] == "session_expired"  # the oldest was ended
    assert all(o.get("/api/auth/me").status_code == 200 for o in others)


def test_logout_other_sessions():
    here, there = sign_in(USERS["hr_admin"][0]), sign_in(USERS["hr_admin"][0])
    assert here.post("/api/auth/logout-others").json() == {"ended": 1}
    assert there.get("/api/auth/me").status_code == 401 and here.get("/api/auth/me").status_code == 200


def test_disabling_a_user_ends_their_sessions_immediately(client):
    victim = sign_in(USERS["recruiter"][0])
    me = victim.get("/api/auth/me").json()
    assert client.patch(f"/api/users/{me['id']}/status", json={"status": "disabled"}).status_code == 200
    assert victim.get("/api/jobs").status_code == 401


# ---------------------------------------------------------------- CSRF and cross-site protection
def test_state_changing_requests_need_the_csrf_token():
    c = sign_in(USERS["hr_admin"][0])
    good = c.headers.pop("X-CSRF-Token")
    assert c.post("/api/departments", json={"name": "Research", "code": "RES"}).json()["code"] == "csrf_failed"
    c.headers["X-CSRF-Token"] = "x" * len(good)
    assert c.post("/api/departments", json={"name": "Research", "code": "RES"}).status_code == 403
    assert c.get("/api/departments").status_code == 200  # reads don't need it
    c.headers["X-CSRF-Token"] = good
    assert c.post("/api/departments", json={"name": "Research", "code": "RES"}).status_code == 201


def test_another_sessions_csrf_token_does_not_work():
    a, b = sign_in(USERS["hr_admin"][0]), sign_in(USERS["hr_admin"][0])
    a.headers["X-CSRF-Token"] = b.headers["X-CSRF-Token"]
    assert a.post("/api/departments", json={"name": "Research", "code": "RES"}).status_code == 403


def test_cross_site_requests_are_refused_by_origin():
    r = _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD},
                        headers={"Origin": "https://evil.example"})
    assert r.status_code == 403 and r.json()["code"] == "bad_origin"
    ok = _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD},
                         headers={"Origin": "http://127.0.0.1:5173"})
    assert ok.status_code == 200


def test_cors_only_allows_the_frontend_origin():
    pre = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type,x-csrf-token"}
    evil = _browser().options("/api/auth/login", headers={"Origin": "https://evil.example", **pre})
    assert "access-control-allow-origin" not in evil.headers
    ours = _browser().options("/api/auth/login", headers={"Origin": "http://127.0.0.1:5173", **pre})
    assert ours.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"
    assert ours.headers["access-control-allow-credentials"] == "true"


def test_json_only_bodies_block_html_form_posts():
    r = _browser().post("/api/auth/login", data={"email": USERS["hr_admin"][0], "password": PASSWORD})
    assert r.status_code == 415 and r.json()["code"] == "unsupported_media_type"  # refused before any parsing


def test_api_responses_are_not_cached(client):
    assert client.get("/api/auth/me").headers["cache-control"] == "no-store"


# ---------------------------------------------------------------- profile and password change
def test_profile_update_only_changes_the_name(client):
    r = client.patch("/api/auth/me", json={"full_name": "Root Renamed"})
    assert r.status_code == 200 and r.json()["full_name"] == "Root Renamed"
    for extra in ({"email": "x@example.org"}, {"status": "disabled"}, {"roles": []}, {"permissions": ["roles:manage"]}):
        assert client.patch("/api/auth/me", json={"full_name": "X Y", **extra}).status_code == 422


def test_change_password_flow():
    here, elsewhere = sign_in(USERS["hr_admin"][0]), sign_in(USERS["hr_admin"][0])
    body = {"current_password": "wrong-current-pass", "new_password": GOOD_NEW_PASSWORD, "new_password_confirm": GOOD_NEW_PASSWORD}
    r = here.post("/api/auth/change-password", json=body)
    assert r.status_code == 422 and r.json()["errors"] == {"current_password": "Current password is incorrect"}
    r = here.post("/api/auth/change-password", json={**body, "current_password": PASSWORD, "new_password_confirm": "nope"})
    assert r.json()["errors"] == {"new_password_confirm": "Passwords do not match"}
    r = here.post("/api/auth/change-password", json={**body, "current_password": PASSWORD, "new_password": PASSWORD,
                                                      "new_password_confirm": PASSWORD})
    assert "haven't used" in r.json()["errors"]["new_password"]
    assert here.post("/api/auth/change-password", json={**body, "current_password": PASSWORD}).status_code == 204
    assert here.get("/api/auth/me").status_code == 200           # this browser stays signed in
    assert elsewhere.get("/api/auth/me").status_code == 401      # every other browser is signed out
    assert _browser().post("/api/auth/login", json={"email": USERS["hr_admin"][0], "password": PASSWORD}).status_code == 401
    sign_in(USERS["hr_admin"][0], GOOD_NEW_PASSWORD)


# ---------------------------------------------------------------- reset links and invitations
def _user_id(client, email):
    return next(u["id"] for u in client.get("/api/users", params={"search": email}).json())


def test_password_reset_link_is_single_use_and_signs_out_everywhere(client):
    victim = sign_in(USERS["recruiter"][0])
    link = client.post(f"/api/users/{_user_id(client, USERS['recruiter'][0])}/reset-link").json()
    token = link["url"].split("token=")[1]
    assert link["url"].startswith("http://127.0.0.1:5173/reset-password?token=")
    body = {"token": token, "new_password": GOOD_NEW_PASSWORD, "new_password_confirm": GOOD_NEW_PASSWORD}
    assert _browser().post("/api/auth/reset-password", json={**body, "new_password": "short", "new_password_confirm": "short"}).status_code == 422
    assert _browser().post("/api/auth/reset-password", json=body).status_code == 204
    assert victim.get("/api/auth/me").status_code == 401
    again = _browser().post("/api/auth/reset-password", json=body)
    assert again.status_code == 400 and again.json()["code"] == "invalid_reset_token"
    sign_in(USERS["recruiter"][0], GOOD_NEW_PASSWORD)


def test_reset_links_expire_and_newer_links_replace_older_ones(client, db):
    uid = _user_id(client, USERS["recruiter"][0])
    old = client.post(f"/api/users/{uid}/reset-link").json()["url"].split("token=")[1]
    new = client.post(f"/api/users/{uid}/reset-link").json()["url"].split("token=")[1]
    body = {"new_password": GOOD_NEW_PASSWORD, "new_password_confirm": GOOD_NEW_PASSWORD}
    assert _browser().post("/api/auth/reset-password", json={**body, "token": old}).status_code == 400
    db.execute(update(PasswordResetToken).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert _browser().post("/api/auth/reset-password", json={**body, "token": new}).status_code == 400
    assert all(len(t) == 64 for t in db.scalars(select(PasswordResetToken.token_hash)).all())  # stored hashed


def test_reset_token_guessing_is_rate_limited():
    b = _browser()
    body = {"new_password": GOOD_NEW_PASSWORD, "new_password_confirm": GOOD_NEW_PASSWORD}
    for i in range(10):
        assert b.post("/api/auth/reset-password", json={**body, "token": f"guess-{i:020d}"}).status_code == 400
    assert b.post("/api/auth/reset-password", json={**body, "token": "guess-x" * 4}).status_code == 429


def test_invitation_flow(client):
    r = client.post("/api/users", json={"full_name": "Ivy Invited", "email": "ivy@example.org"})
    assert r.status_code == 201, r.text
    user, invite = r.json()["user"], r.json()["invite"]
    assert user["has_password"] is False and [x["name"] for x in user["roles"]] == ["employee"]
    # no password yet: signing in is impossible, even with an empty or guessed one
    assert _browser().post("/api/auth/login", json={"email": "ivy@example.org", "password": "anything-at-all"}).status_code == 401
    token = invite["url"].split("token=")[1]
    assert _browser().post("/api/auth/reset-password", json={"token": token, "new_password": GOOD_NEW_PASSWORD,
                                                             "new_password_confirm": GOOD_NEW_PASSWORD}).status_code == 204
    me = sign_in("ivy@example.org", GOOD_NEW_PASSWORD).get("/api/auth/me").json()
    assert me["has_password"] is True and me["permissions"] == ["profile:own"]


def test_no_secret_ever_appears_in_responses(client, db):
    texts = [client.get(p).text for p in ("/api/auth/me", "/api/users", "/api/roles")]
    texts.append(client.get(f"/api/users/{_user_id(client, USERS['hr_admin'][0])}").text)
    hashes = db.scalars(select(User.password_hash)).all() + db.scalars(select(Session.token_hash)).all()
    for t in texts:
        assert "$argon2" not in t and "password_hash" not in t and "token_hash" not in t
        assert not any(h and h in t for h in hashes)
