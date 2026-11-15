"""/api/me: self-service for the signed-in person's OWN employee record.

There is deliberately no employee id in these URLs: the record is found through the caller's own account
(users.employee_id), so nobody can read or edit someone else's record by changing a number in the URL (IDOR).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.auth.dependencies import Auth, require
from app.auth.schemas import OwnEmployeeUpdate
from app.audit import actor_from, field_changes, record_event
from app.db import get_db
from app.errors import ApiError
from app.ids import public_id
from app.models import Employee, utcnow
from app.schemas import EmployeeOut
from app.services import employee_out, log_activity

router = APIRouter(prefix="/me", tags=["self-service"])


def _own_employee(db: DbSession, auth: Auth) -> Employee:
    employee = db.get(Employee, auth.user.employee_id) if auth.user.employee_id else None
    if employee is None:
        raise ApiError(404, "No employee record is linked to your account yet. Ask HR or an administrator to link it.",
                       code="no_employee_record")
    return employee


@router.get("/employee", response_model=EmployeeOut)
def my_employee_record(auth: Auth = Depends(require("profile:own")), db: DbSession = Depends(get_db)):
    return employee_out(db, _own_employee(db, auth))


@router.patch("/employee", response_model=EmployeeOut)
def update_my_employee_record(payload: OwnEmployeeUpdate, auth: Auth = Depends(require("profile:own")),
                              db: DbSession = Depends(get_db)):
    """Employees may change only their phone number. Everything else (title, department, status...) is HR's job."""
    employee = _own_employee(db, auth)
    changed = employee.phone != payload.phone
    employee.phone = payload.phone
    employee.updated_at = utcnow()
    log_activity(db, "employee", f"{employee.first_name} {employee.last_name} updated their phone number")
    db.commit()
    if changed:
        record_event("employee.updated", category="employee", actor=auth.user,
                     target=("employee", public_id("employee", employee.id)), metadata={"fields": ["phone"], "self_service": True})
    return employee_out(db, employee)
