"""Audit log: a long-lived, append-only record of security-relevant activity (who did what, to what, when, from where,
and whether it worked). Separate from the dashboard's activity feed (friendly sentences) and from the server log
(diagnostics that rotate away).

How records are protected (details and limits: docs/SECURITY.md, "Audit logging"):
  1. Prevention  - no API can change or delete audit records; a database trigger refuses UPDATE/DELETE/TRUNCATE;
                   with least-privilege setup the app's database user isn't even allowed to.
  2. Detection   - every record carries HMAC-SHA256(key, record + previous record's hash): a hash chain. Editing,
                   inserting or deleting a record in the middle breaks the chain, and the key lives outside the
                   database (AUDIT_HMAC_KEY), so someone with only database access can't forge a valid chain.
                   `GET /api/audit/verify` or `python -m app.audit_verify` checks the whole chain.

Records NEVER contain passwords, tokens, session IDs or full personal records: only identifiers and the names of
fields that changed (values only for non-personal fields such as job title or status).
"""
import hashlib
import hmac
import json
import logging
import threading
import time
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, CheckConstraint, Index, Integer, String, select, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.config import AUDIT_HMAC_KEY, AUDIT_HMAC_OLD_KEYS
from app.db import Base, SessionLocal, UTCDateTime
from app.observability import client_ip_var, request_id_var, security_log, user_agent_var

log = logging.getLogger("workforceos.audit")

CATEGORIES = ("auth", "user", "role", "employee", "department", "job", "candidate", "application", "system", "security")
OUTCOMES = ("success", "failure", "denied")
_LOCK_KEY = 7_340_001  # arbitrary constant for pg_advisory_xact_lock: one audit writer at a time keeps the chain linear


def _one_of(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        CheckConstraint(_one_of("category", CATEGORIES), name="category_valid"),
        CheckConstraint(_one_of("outcome", OUTCOMES), name="outcome_valid"),
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)          # e.g. "auth.login", "user.roles_changed"
    outcome: Mapped[str] = mapped_column(String(10), index=True)
    actor_user_id: Mapped[int | None] = mapped_column(Integer, index=True)  # no foreign key: history outlives accounts
    actor_email: Mapped[str | None] = mapped_column(String(254))            # snapshot at the time of the event
    target_type: Mapped[str | None] = mapped_column(String(30))
    target_id: Mapped[str | None] = mapped_column(String(40))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    request_id: Mapped[str | None] = mapped_column(String(64))
    details: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"), default=dict)
    key_id: Mapped[str] = mapped_column(String(16))
    prev_hash: Mapped[str | None] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)


Index("ix_audit_events_target", AuditEvent.target_type, AuditEvent.target_id)


# ---------------------------------------------------------------- integrity
def key_id_for(key: str) -> str:
    """A short public fingerprint of a key, stored with each record so verification knows which key signed it."""
    return hashlib.sha256(key.encode()).hexdigest()[:12]


KEYS = {key_id_for(k): k for k in [*AUDIT_HMAC_OLD_KEYS, AUDIT_HMAC_KEY]}
CURRENT_KEY_ID = key_id_for(AUDIT_HMAC_KEY)


def _canonical(e: AuditEvent) -> bytes:
    occurred = e.occurred_at.astimezone(timezone.utc).isoformat(timespec="microseconds")
    body = {"occurred_at": occurred, "category": e.category, "action": e.action, "outcome": e.outcome,
            "actor_user_id": e.actor_user_id, "actor_email": e.actor_email, "target_type": e.target_type,
            "target_id": e.target_id, "ip": e.ip, "user_agent": e.user_agent, "request_id": e.request_id,
            "details": e.details or {}, "key_id": e.key_id, "prev_hash": e.prev_hash}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def compute_hash(e: AuditEvent, key: str) -> str:
    return hmac.new(key.encode(), _canonical(e), hashlib.sha256).hexdigest()


# ---------------------------------------------------------------- writing
def actor_from(request) -> object | None:
    """The signed-in user of this request (stored on request.state by the auth dependency), as an audit actor."""
    from types import SimpleNamespace

    user_id = getattr(request.state, "user_id", None)
    return SimpleNamespace(id=user_id, email=getattr(request.state, "user_email", None)) if user_id else None


PERSONAL_FIELDS = {"first_name", "last_name", "full_name", "email", "phone", "joining_date"}
LONG_TEXT_FIELDS = {"description", "notes"}  # recorded as "changed", without copying paragraphs into the audit log


def field_changes(before: dict, after: dict) -> dict:
    """{"fields": [...changed names...], "values": {field: [old, new]} only for NON-personal fields}."""
    from app.ids import public_id

    def show(field, value):
        return public_id("department", value) if field == "department_id" and value is not None else str(value)

    changed = sorted(k for k in after if before.get(k) != after.get(k))
    values = {k: [show(k, before.get(k)), show(k, after.get(k))] for k in changed if k not in PERSONAL_FIELDS | LONG_TEXT_FIELDS}
    return {"fields": changed, **({"values": values} if values else {})}


_dedupe: dict[str, float] = {}
_dedupe_lock = threading.Lock()


def first_time_in(key: str, seconds: float) -> bool:
    """True once per `key` per time window: lets noisy events (a password-guessing script) be recorded once, not 10,000x."""
    now = time.time()
    with _dedupe_lock:
        if _dedupe.get(key, 0) > now:
            return False
        _dedupe[key] = now + seconds
        if len(_dedupe) > 10_000:  # keep memory bounded
            for k in [k for k, until in _dedupe.items() if until <= now]:
                del _dedupe[k]
        return True


def record_event(action: str, *, category: str, outcome: str = "success", actor=None, target: tuple[str, str] | None = None,
                 metadata: dict | None = None) -> None:
    """Write one audit record in its OWN transaction and commit it immediately.

    Own transaction: a failed or refused request still leaves its audit record (that's exactly when it matters), and
    business transactions never wait on the audit writer. Call it AFTER a successful business commit.
    Never raises: auditing problems are logged loudly but don't break the user's request.
    `actor` is a User (or None); `target` is (type, public id), e.g. ("employee", "EMP-5001").
    """
    try:
        with SessionLocal() as db:
            if db.get_bind().dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})  # serialise writers
            prev = db.scalar(select(AuditEvent.hash).order_by(AuditEvent.id.desc()).limit(1))
            event = AuditEvent(
                occurred_at=datetime.now(timezone.utc), category=category, action=action, outcome=outcome,
                actor_user_id=getattr(actor, "id", None), actor_email=getattr(actor, "email", None),
                target_type=target[0] if target else None, target_id=str(target[1]) if target else None,
                ip=client_ip_var.get(), user_agent=user_agent_var.get(), request_id=request_id_var.get(),
                details=metadata or {}, key_id=CURRENT_KEY_ID, prev_hash=prev,
            )
            event.hash = compute_hash(event, AUDIT_HMAC_KEY)
            db.add(event)
            db.commit()
        if outcome != "success" or category == "security":
            security_log.info("audit %s %s", action, outcome, extra={"fields": {"category": category,
                              **({"target": f"{target[0]}:{target[1]}"} if target else {})}})
    except Exception:  # noqa: BLE001 - auditing must never take the application down
        log.exception("AUDIT WRITE FAILED for %s (%s)", action, outcome)


# ---------------------------------------------------------------- verification
def verify_chain(db, *, batch: int = 2000) -> dict:
    """Walk every record in order and check (a) each links to the previous one and (b) each HMAC is valid."""
    checked, prev_hash, last_id = 0, None, 0
    unknown_keys: set[str] = set()
    while True:
        rows = db.scalars(select(AuditEvent).where(AuditEvent.id > last_id).order_by(AuditEvent.id).limit(batch)).all()
        if not rows:
            break
        for e in rows:
            if e.prev_hash != prev_hash:
                return {"ok": False, "checked": checked, "first_problem_id": e.id,
                        "problem": "The chain is broken here: a record before it was removed, added or altered."}
            key = KEYS.get(e.key_id)
            if key is None:
                unknown_keys.add(e.key_id)
            elif not hmac.compare_digest(compute_hash(e, key), e.hash):
                return {"ok": False, "checked": checked, "first_problem_id": e.id,
                        "problem": "This record's content doesn't match its signature: it was altered."}
            prev_hash, last_id, checked = e.hash, e.id, checked + 1
    if unknown_keys:
        return {"ok": False, "checked": checked, "first_problem_id": None,
                "problem": f"Signed with unknown key(s) {sorted(unknown_keys)}: add the old key to AUDIT_HMAC_OLD_KEYS."}
    return {"ok": True, "checked": checked, "first_problem_id": None, "problem": None, "last_hash": prev_hash}
