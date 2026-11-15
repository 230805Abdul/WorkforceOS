from typing import Literal

from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.audit import actor_from, field_changes, record_event
from app.db import get_db
from app.validation import SearchQuery
from app.errors import ApiError
from app.ids import parse_id, parse_id_loose, public_id
from app.models import Application, Candidate, Department, Employee, utcnow
from app.schemas import EmployeeCreate, EmployeeIn, EmployeeOut, EmploymentStatus
from app.services import (employee_dict, employee_out, employees_query, field_error, get_employee_or_404, like,
                          log_activity, next_employee_code, order_by, resolve_department)

router = APIRouter(prefix="/employees", tags=["employees"])

SortKey = Literal["employee_code", "name", "job_title", "department", "employment_status", "joining_date"]
CONFLICT = ApiError(409, "This change conflicts with existing data. Refresh the page and try again.")


def _ensure_unique(db: Session, payload: EmployeeIn, ignore_pk: int | None = None) -> None:
    errors = {}
    for field, column, value, message in (
        ("employee_code", Employee.employee_code, payload.employee_code, "An employee with this code already exists"),
        ("email", func.lower(Employee.email), payload.email.lower(), "An employee with this email already exists"),
    ):
        stmt = select(Employee.id).where(column == value)
        if ignore_pk is not None:
            stmt = stmt.where(Employee.id != ignore_pk)
        if db.scalar(stmt) is not None:
            errors[field] = message
    if errors:
        raise ApiError(409, "Please fix the highlighted fields.", errors)


def _values(db: Session, payload: EmployeeIn) -> dict:
    values = payload.model_dump(mode="json", exclude={"candidate_id"})
    values["department_id"] = resolve_department(db, payload.department_id).id
    values["joining_date"] = payload.joining_date
    return values


def _link_candidate(db: Session, public_id: str) -> int:
    """Business rule: only a candidate who has been HIRED can be turned into an employee, and only once."""
    pk = parse_id("candidate", public_id)
    candidate = db.get(Candidate, pk) if pk else None
    if candidate is None:
        raise field_error("candidate_id", "Candidate not found")
    hired = db.scalar(select(Application.id).where(Application.candidate_id == candidate.id, Application.status == "hired"))
    if hired is None:
        raise field_error("candidate_id", "This candidate has not been hired yet", 409)
    if db.scalar(select(Employee.id).where(Employee.candidate_id == candidate.id)) is not None:
        raise field_error("candidate_id", "This candidate already has an employee record", 409)
    return candidate.id


@router.get("", response_model=list[EmployeeOut], dependencies=[Depends(require("employees:read"))])
def list_employees(
    search: SearchQuery = None,
    employment_status: EmploymentStatus | None = None,
    department_id: str | None = None,
    sort: SortKey = "name",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
):
    stmt = employees_query()
    if search and search.strip():
        q = search.strip()
        conditions = [like(Employee.first_name, q), like(Employee.last_name, q), like(Employee.email, q),
                      like(Employee.employee_code, q), like(Employee.job_title, q),
                      like(Employee.first_name + " " + Employee.last_name, q)]
        if (pk := parse_id_loose("employee", q)) is not None:
            conditions.append(Employee.id == pk)
        stmt = stmt.where(or_(*conditions))
    if employment_status:
        stmt = stmt.where(Employee.employment_status == employment_status.value)
    if department_id:
        if (pk := parse_id("department", department_id)) is None:
            return []
        stmt = stmt.where(Employee.department_id == pk)

    sort_columns = {
        "employee_code": [Employee.employee_code], "name": [func.lower(Employee.last_name), func.lower(Employee.first_name)],
        "job_title": [func.lower(Employee.job_title)], "department": [func.lower(Department.name)],
        "employment_status": [Employee.employment_status], "joining_date": [Employee.joining_date],
    }
    stmt = stmt.order_by(*order_by(sort_columns[sort], order, Employee.id))
    return [employee_dict(e) for e in db.execute(stmt).scalars().all()]


@router.get("/next-code", dependencies=[Depends(require("employees:create"))])
def suggest_employee_code(db: Session = Depends(get_db)):
    """Used by the 'Add employee' form to pre-fill a free employee code."""
    return {"employee_code": next_employee_code(db)}


@router.get("/{employee_id}", response_model=EmployeeOut, dependencies=[Depends(require("employees:read"))])
def get_employee(employee_id: str, db: Session = Depends(get_db)):
    return employee_out(db, get_employee_or_404(db, employee_id))


@router.post("", response_model=EmployeeOut, status_code=201, dependencies=[Depends(require("employees:create"))])
def create_employee(payload: EmployeeCreate, request: Request, db: Session = Depends(get_db)):
    values = _values(db, payload)
    _ensure_unique(db, payload)
    employee = Employee(**values, candidate_id=_link_candidate(db, payload.candidate_id) if payload.candidate_id else None)
    db.add(employee)
    db.flush()
    suffix = " (hired candidate)" if employee.candidate_id else ""
    log_activity(db, "employee", f"{employee.first_name} {employee.last_name} joined as an employee{suffix}")
    try:
        db.commit()
    except IntegrityError:  # two people submitting the same code/email/candidate at once: the unique indexes decide
        db.rollback()
        raise CONFLICT
    record_event("employee.created", category="employee", actor=actor_from(request),
                 target=("employee", public_id("employee", employee.id)),
                 metadata={"employee_code": employee.employee_code, "from_candidate": employee.candidate_id is not None})
    return employee_out(db, employee)


@router.put("/{employee_id}", response_model=EmployeeOut, dependencies=[Depends(require("employees:update"))])
def update_employee(employee_id: str, payload: EmployeeIn, request: Request, db: Session = Depends(get_db)):
    employee = get_employee_or_404(db, employee_id)
    values = _values(db, payload)
    _ensure_unique(db, payload, ignore_pk=employee.id)
    before = {field: getattr(employee, field) for field in values}
    for field, value in values.items():
        setattr(employee, field, value)
    employee.updated_at = utcnow()
    log_activity(db, "employee", f"{employee.first_name} {employee.last_name}'s record was updated")
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise CONFLICT
    changes = field_changes(before, values)
    if changes["fields"]:
        record_event("employee.updated", category="employee", actor=actor_from(request),
                     target=("employee", public_id("employee", employee.id)), metadata=changes)
    return employee_out(db, employee)


@router.delete("/{employee_id}", status_code=204, dependencies=[Depends(require("employees:delete"))])
def delete_employee(employee_id: str, request: Request, db: Session = Depends(get_db)):
    """Permanently deletes the record (use for mistakes). To keep history, set the status to 'terminated' instead."""
    employee = get_employee_or_404(db, employee_id)
    log_activity(db, "employee", f"{employee.first_name} {employee.last_name}'s employee record was deleted")
    target, code = ("employee", public_id("employee", employee.id)), employee.employee_code
    db.delete(employee)
    db.commit()
    record_event("employee.deleted", category="employee", actor=actor_from(request), target=target, metadata={"employee_code": code})
    return Response(status_code=204)
