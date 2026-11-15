"""Query helpers and response builders shared by the routers."""
import re

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, contains_eager

from app.errors import ApiError
from app.ids import parse_id, public_id
from app.models import ActivityLog, Application, Candidate, Department, Employee, Job, utcnow
from app.schemas import VALID_TRANSITIONS


# ---------- generic helpers ----------
def like(column, text: str):
    """Case-insensitive 'contains' that treats % and _ in the user's text literally."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def log_activity(db: Session, kind: str, message: str) -> None:
    db.add(ActivityLog(kind=kind, message=message, created_at=utcnow()))


def order_by(columns: list, order: str, tiebreak):
    """ORDER BY the given columns in the requested direction, with a stable tie-break on the primary key."""
    desc = order == "desc"
    return [*(c.desc() if desc else c.asc() for c in columns), tiebreak.desc() if desc else tiebreak.asc()]


def _pk_or_404(kind: str, public: str, label: str) -> int:
    pk = parse_id(kind, public)
    if pk is None:
        raise ApiError(404, f"{label} not found")
    return pk


def field_error(field: str, message: str, status: int = 422) -> ApiError:
    return ApiError(status, "Please fix the highlighted fields.", {field: message})


# ---------- departments ----------
def departments_with_counts():
    emp = (
        select(Employee.department_id.label("did"), func.count().label("n"),
               func.sum(case((Employee.employment_status == "active", 1), else_=0)).label("active"))
        .group_by(Employee.department_id).subquery()
    )
    jobs = select(Job.department_id.label("did"), func.count().label("n")).group_by(Job.department_id).subquery()
    employees_count = func.coalesce(emp.c.n, 0).label("employees_count")
    active_count = func.coalesce(emp.c.active, 0).label("active_employees_count")
    jobs_count = func.coalesce(jobs.c.n, 0).label("jobs_count")
    stmt = (select(Department, employees_count, active_count, jobs_count)
            .outerjoin(emp, emp.c.did == Department.id).outerjoin(jobs, jobs.c.did == Department.id))
    return stmt, employees_count, jobs_count


def department_dict(d: Department, employees_count: int, active_count: int, jobs_count: int) -> dict:
    return {
        "id": public_id("department", d.id), "name": d.name, "code": d.code, "description": d.description,
        "is_sample": d.is_sample, "employees_count": int(employees_count), "active_employees_count": int(active_count),
        "jobs_count": int(jobs_count), "created_at": d.created_at, "updated_at": d.updated_at,
    }


def get_department_or_404(db: Session, department_id: str) -> Department:
    department = db.get(Department, _pk_or_404("department", department_id, "Department"))
    if department is None:
        raise ApiError(404, "Department not found")
    return department


def department_out(db: Session, department: Department) -> dict:
    stmt, *_ = departments_with_counts()
    row = db.execute(stmt.where(Department.id == department.id).execution_options(populate_existing=True)).one()
    return department_dict(*row)


def resolve_department(db: Session, public: str) -> Department:
    """For request bodies: a bad department is a field error (422) the form can show, not a 404."""
    pk = parse_id("department", public)
    department = db.get(Department, pk) if pk else None
    if department is None:
        raise field_error("department_id", "Select a valid department")
    return department


# ---------- jobs ----------
def jobs_with_counts():
    """SELECT job, applications_count, hired_count  (counted in SQL, not in Python); the department is joined in."""
    c = (
        select(
            Application.job_id.label("job_id"),
            func.count().label("n"),
            func.sum(case((Application.status == "hired", 1), else_=0)).label("hired"),
        )
        .group_by(Application.job_id)
        .subquery()
    )
    n = func.coalesce(c.c.n, 0).label("applications_count")
    h = func.coalesce(c.c.hired, 0).label("hired_count")
    stmt = (select(Job, n, h).join(Job.department).outerjoin(c, c.c.job_id == Job.id)
            .options(contains_eager(Job.department)))
    return stmt, n


def job_dict(j: Job, applications_count: int, hired_count: int) -> dict:
    return {
        "id": public_id("job", j.id), "title": j.title, "department_id": public_id("department", j.department_id),
        "department": j.department.name, "location": j.location, "employment_type": j.employment_type,
        "status": j.status, "openings": j.openings, "description": j.description, "is_sample": j.is_sample,
        "created_at": j.created_at, "updated_at": j.updated_at,
        "applications_count": int(applications_count), "hired_count": int(hired_count),
    }


def get_job_or_404(db: Session, job_id: str, *, lock: bool = False) -> Job:
    stmt = select(Job).where(Job.id == _pk_or_404("job", job_id, "Job"))
    job = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if job is None:
        raise ApiError(404, "Job not found")
    return job


def job_out(db: Session, job: Job) -> dict:
    stmt, _ = jobs_with_counts()
    row = db.execute(stmt.where(Job.id == job.id).execution_options(populate_existing=True)).one()
    return job_dict(*row)


def hired_count(db: Session, job_pk: int) -> int:
    return db.scalar(select(func.count()).select_from(Application).where(Application.job_id == job_pk, Application.status == "hired")) or 0


# ---------- candidates ----------
def candidates_with_counts():
    c = select(Application.candidate_id.label("cid"), func.count().label("n")).group_by(Application.candidate_id).subquery()
    n = func.coalesce(c.c.n, 0).label("applications_count")
    return select(Candidate, n).outerjoin(c, c.c.cid == Candidate.id), n


def candidate_dict(c: Candidate, applications_count: int) -> dict:
    return {
        "id": public_id("candidate", c.id), "full_name": c.full_name, "email": c.email, "phone": c.phone,
        "source": c.source, "is_sample": c.is_sample, "created_at": c.created_at, "applications_count": int(applications_count),
    }


def get_candidate_or_404(db: Session, candidate_id: str) -> Candidate:
    candidate = db.get(Candidate, _pk_or_404("candidate", candidate_id, "Candidate"))
    if candidate is None:
        raise ApiError(404, "Candidate not found")
    return candidate


def candidate_out(db: Session, candidate: Candidate) -> dict:
    stmt, _ = candidates_with_counts()
    return candidate_dict(*db.execute(stmt.where(Candidate.id == candidate.id).execution_options(populate_existing=True)).one())


# ---------- applications ----------
def applications_query():
    """Applications joined to their candidate, job, department and employee record in ONE query (no N+1 lookups)."""
    return (
        select(Application)
        .join(Application.candidate)
        .join(Application.job)
        .join(Job.department)
        .options(
            contains_eager(Application.candidate).joinedload(Candidate.employee),
            contains_eager(Application.job).contains_eager(Job.department),
        )
    )


def application_dict(a: Application) -> dict:
    employee = a.candidate.employee
    return {
        "id": public_id("application", a.id), "candidate_id": public_id("candidate", a.candidate_id),
        "candidate_name": a.candidate.full_name, "candidate_email": a.candidate.email,
        "job_id": public_id("job", a.job_id), "job_title": a.job.title,
        "department_id": public_id("department", a.job.department_id), "department": a.job.department.name,
        "status": a.status, "allowed_next": VALID_TRANSITIONS[a.status],
        "employee_id": public_id("employee", employee.id) if employee else None,
        "created_at": a.created_at, "updated_at": a.updated_at,
    }


def get_application_or_404(db: Session, application_id: str, *, lock: bool = False) -> Application:
    pk = _pk_or_404("application", application_id, "Application")
    stmt = select(Application).where(Application.id == pk)
    app = db.execute(stmt.with_for_update() if lock else stmt).scalar_one_or_none()
    if app is None:
        raise ApiError(404, "Application not found")
    return app


def application_out(db: Session, app: Application) -> dict:
    row = db.execute(applications_query().where(Application.id == app.id).execution_options(populate_existing=True)).unique().scalar_one()
    return application_dict(row)


# ---------- employees ----------
def employees_query():
    return select(Employee).join(Employee.department).options(contains_eager(Employee.department))


def employee_dict(e: Employee) -> dict:
    return {
        "id": public_id("employee", e.id), "employee_code": e.employee_code, "first_name": e.first_name,
        "last_name": e.last_name, "full_name": f"{e.first_name} {e.last_name}", "email": e.email, "phone": e.phone,
        "job_title": e.job_title, "department_id": public_id("department", e.department_id), "department": e.department.name,
        "employment_status": e.employment_status, "joining_date": e.joining_date,
        "candidate_id": public_id("candidate", e.candidate_id) if e.candidate_id else None,
        "is_sample": e.is_sample, "created_at": e.created_at, "updated_at": e.updated_at,
    }


def get_employee_or_404(db: Session, employee_id: str) -> Employee:
    employee = db.get(Employee, _pk_or_404("employee", employee_id, "Employee"))
    if employee is None:
        raise ApiError(404, "Employee not found")
    return employee


def employee_out(db: Session, employee: Employee) -> dict:
    row = db.execute(employees_query().where(Employee.id == employee.id).execution_options(populate_existing=True)).scalar_one()
    return employee_dict(row)


def next_employee_code(db: Session) -> str:
    """E-0001, E-0002, ... one higher than the highest existing E-number."""
    numbers = [int(m.group(1)) for (code,) in db.execute(select(Employee.employee_code)).all() if (m := re.fullmatch(r"E-(\d+)", code))]
    return f"E-{max(numbers, default=0) + 1:04d}"
