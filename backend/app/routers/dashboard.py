"""GET /api/dashboard: one call, but each section is only computed and returned if the caller may see that data.
A Recruiter gets recruiting numbers and no employee figures; an HR Manager gets both. Filtering happens HERE, on the
server; the frontend just shows whatever sections arrive."""
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import Auth, require
from app.db import get_db
from app.ids import public_id
from app.models import ActivityLog, Application, Candidate, Department, Employee, Job
from app.schemas import EmploymentStatus, VALID_TRANSITIONS
from app.services import application_dict, applications_query

router = APIRouter(tags=["dashboard"])

# Which permission lets you see which kind of activity-feed entry.
ACTIVITY_VISIBILITY = {
    "employee": "employees:read", "department": "departments:read", "job": "jobs:read",
    "candidate": "candidates:read", "application": "applications:read", "user": "users:read", "role": "roles:manage",
}


def _workforce(db: Session) -> dict:
    emp_status = dict(db.execute(select(Employee.employment_status, func.count()).group_by(Employee.employment_status)).all())
    by_department = db.execute(
        select(Department.name, func.count().label("n"))
        .join(Employee, Employee.department_id == Department.id).where(Employee.employment_status != "terminated")
        .group_by(Department.id, Department.name).order_by(func.count().desc(), Department.name)
    ).all()
    return {
        "kpis": {
            "total_employees": sum(emp_status.values()),
            "active_employees": emp_status.get("active", 0),
            "total_departments": db.scalar(select(func.count()).select_from(Department)),
        },
        "employees_by_department": [{"department": name, "count": n} for name, n in by_department],
        "employment_status": [{"status": s.value, "count": emp_status.get(s.value, 0)} for s in EmploymentStatus],
    }


def _recruiting(db: Session) -> dict:
    by_status = dict(db.execute(select(Application.status, func.count()).group_by(Application.status)).all())
    open_roles, open_positions = db.execute(
        select(func.count(), func.coalesce(func.sum(Job.openings), 0)).where(Job.status == "open")
    ).one()
    open_by_department = db.execute(
        select(Department.name, func.count().label("roles"), func.sum(Job.openings))
        .join(Job, Job.department_id == Department.id).where(Job.status == "open")
        .group_by(Department.id, Department.name).order_by(func.count().desc(), Department.name)
    ).all()
    sources = db.execute(select(Candidate.source, func.count().label("n")).group_by(Candidate.source)
                         .order_by(func.count().desc(), Candidate.source)).all()
    recent = db.execute(applications_query().order_by(Application.created_at.desc(), Application.id.desc()).limit(6)).scalars().all()
    return {
        "kpis": {
            "open_roles": open_roles,
            "open_positions": int(open_positions),
            "total_candidates": db.scalar(select(func.count()).select_from(Candidate)),
            "active_applications": sum(by_status.get(s, 0) for s in ("applied", "screening", "interview", "offer")),
            "hired": by_status.get("hired", 0),
            "offers_pending": by_status.get("offer", 0),
        },
        "pipeline": [{"status": s, "count": by_status.get(s, 0)} for s in VALID_TRANSITIONS],
        "departments": [{"department": name, "open_roles": roles, "openings": int(openings)} for name, roles, openings in open_by_department],
        "sources": [{"source": s, "count": n} for s, n in sources],
        "recent_applications": [application_dict(a) for a in recent],
    }


@router.get("/dashboard")
def dashboard(auth: Auth = Depends(require("dashboard:view")), db: Session = Depends(get_db)):
    """Every number is aggregated by the database from the same tables the CRUD endpoints change."""
    sees_workforce = auth.can("employees:read")
    sees_recruiting = all(auth.can(p) for p in ("jobs:read", "candidates:read", "applications:read"))
    kinds = [kind for kind, permission in ACTIVITY_VISIBILITY.items() if auth.can(permission)]
    activity = db.execute(select(ActivityLog).where(ActivityLog.kind.in_(kinds))
                          .order_by(ActivityLog.created_at.desc(), ActivityLog.id.desc()).limit(8)).scalars().all() if kinds else []
    return {
        "workforce": _workforce(db) if sees_workforce else None,
        "recruiting": _recruiting(db) if sees_recruiting else None,
        "activity": [{"id": public_id("activity", a.id), "kind": a.kind, "message": a.message, "at": a.created_at.isoformat()} for a in activity],
    }
