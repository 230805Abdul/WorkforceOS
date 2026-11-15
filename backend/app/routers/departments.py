from typing import Literal

from fastapi import APIRouter, Depends, Response, Request
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require
from app.audit import actor_from, field_changes, record_event
from app.db import get_db
from app.validation import SearchQuery
from app.errors import ApiError
from app.ids import parse_id_loose, public_id
from app.models import Department, Employee, Job, utcnow
from app.schemas import DepartmentIn, DepartmentOut
from app.services import (department_dict, department_out, departments_with_counts, get_department_or_404, like,
                          log_activity, order_by)

router = APIRouter(prefix="/departments", tags=["departments"])

SortKey = Literal["name", "code", "employees_count", "jobs_count", "created_at"]


def _ensure_unique(db: Session, payload: DepartmentIn, ignore_pk: int | None = None) -> None:
    """Friendly field errors first; the unique indexes in the database remain the final guard."""
    errors = {}
    for field, column, value, message in (
        ("name", func.lower(Department.name), payload.name.lower(), "A department with this name already exists"),
        ("code", Department.code, payload.code, "A department with this code already exists"),
    ):
        stmt = select(Department.id).where(column == value)
        if ignore_pk is not None:
            stmt = stmt.where(Department.id != ignore_pk)
        if db.scalar(stmt) is not None:
            errors[field] = message
    if errors:
        raise ApiError(409, "Please fix the highlighted fields.", errors)


@router.get("", response_model=list[DepartmentOut], dependencies=[Depends(require("departments:read"))])
def list_departments(
    search: SearchQuery = None,
    sort: SortKey = "name",
    order: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
):
    stmt, employees_count, jobs_count = departments_with_counts()
    if search and search.strip():
        q = search.strip()
        conditions = [like(Department.name, q), like(Department.code, q)]
        if (pk := parse_id_loose("department", q)) is not None:
            conditions.append(Department.id == pk)
        stmt = stmt.where(or_(*conditions))
    sort_columns = {"name": [func.lower(Department.name)], "code": [Department.code], "employees_count": [employees_count],
                    "jobs_count": [jobs_count], "created_at": [Department.created_at]}
    stmt = stmt.order_by(*order_by(sort_columns[sort], order, Department.id))
    return [department_dict(*row) for row in db.execute(stmt).all()]


@router.get("/{department_id}", response_model=DepartmentOut, dependencies=[Depends(require("departments:read"))])
def get_department(department_id: str, db: Session = Depends(get_db)):
    return department_out(db, get_department_or_404(db, department_id))


@router.post("", response_model=DepartmentOut, status_code=201, dependencies=[Depends(require("departments:manage"))])
def create_department(payload: DepartmentIn, request: Request, db: Session = Depends(get_db)):
    _ensure_unique(db, payload)
    department = Department(**payload.model_dump())
    db.add(department)
    db.flush()
    log_activity(db, "department", f"Department '{department.name}' was created")
    db.commit()
    record_event("department.created", category="department", actor=actor_from(request),
                 target=("department", public_id("department", department.id)), metadata={"name": department.name, "code": department.code})
    return department_out(db, department)


@router.put("/{department_id}", response_model=DepartmentOut, dependencies=[Depends(require("departments:manage"))])
def update_department(department_id: str, payload: DepartmentIn, request: Request, db: Session = Depends(get_db)):
    department = get_department_or_404(db, department_id)
    _ensure_unique(db, payload, ignore_pk=department.id)
    before = {field: getattr(department, field) for field in payload.model_dump()}
    for field, value in payload.model_dump().items():
        setattr(department, field, value)
    department.updated_at = utcnow()
    log_activity(db, "department", f"Department '{department.name}' was updated")
    db.commit()
    changes = field_changes(before, payload.model_dump())
    if changes["fields"]:
        record_event("department.updated", category="department", actor=actor_from(request),
                     target=("department", public_id("department", department.id)), metadata=changes)
    return department_out(db, department)


@router.delete("/{department_id}", status_code=204, dependencies=[Depends(require("departments:manage"))])
def delete_department(department_id: str, request: Request, db: Session = Depends(get_db)):
    """RESTRICTED: a department that still has employees or jobs cannot be deleted (move or remove them first)."""
    department = get_department_or_404(db, department_id)
    employees = db.scalar(select(func.count()).select_from(Employee).where(Employee.department_id == department.id))
    jobs = db.scalar(select(func.count()).select_from(Job).where(Job.department_id == department.id))
    if employees or jobs:
        parts = [f"{n} {word}{'' if n == 1 else 's'}" for n, word in ((employees, "employee"), (jobs, "job")) if n]
        raise ApiError(409, f"Cannot delete '{department.name}': it still has {' and '.join(parts)}. "
                            "Move or delete them first.")
    log_activity(db, "department", f"Department '{department.name}' was deleted")
    target, name = ("department", public_id("department", department.id)), department.name
    db.delete(department)
    db.commit()  # if someone adds an employee in the meantime, the foreign key (RESTRICT) refuses and the 409 handler answers
    record_event("department.deleted", category="department", actor=actor_from(request), target=target, metadata={"name": name})
    return Response(status_code=204)
