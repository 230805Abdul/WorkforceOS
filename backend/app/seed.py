"""Sample data + a command to manage it.

    python -m app.seed                 # add any MISSING sample records (safe to run repeatedly: no duplicates)
    python -m app.seed --remove-sample # delete only records flagged is_sample (never touches your own data)
    python -m app.seed --reset         # WIPE all business data, then load samples (accounts are kept; dev only)

    python -m app.seed --demo-users    # also create one sign-in per role (development only)

Every sample record has is_sample = true, so it is always distinguishable from real data
(SELECT * FROM jobs WHERE is_sample;).  Dates are relative to 'now' so the dashboard always looks current.
"""
import argparse
import sys
from collections import Counter
from datetime import date, timedelta

from sqlalchemy import delete, exists, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import IS_PRODUCTION
from app.db import Base, SessionLocal, describe_url
from app.models import ActivityLog, Application, Candidate, Department, Employee, Job, utcnow

DEPARTMENTS = [
    # name, code, description
    ("Engineering", "ENG", "Builds and runs the product: software, infrastructure and data."),
    ("Product", "PRD", "Decides what to build next and why."),
    ("Design", "DSN", "Research, UX and visual design."),
    ("Sales", "SAL", "Finds and closes new customers."),
    ("Marketing", "MKT", "Brand, content and demand generation."),
    ("Operations", "OPS", "Keeps day-to-day delivery running smoothly."),
    ("People", "PPL", "Hiring, onboarding, benefits and culture."),
    ("Finance", "FIN", "Accounting, planning and reporting."),
]

JOBS = [
    # title, department, location, type, status, openings, description, days_ago
    ("Senior Backend Engineer", "Engineering", "Remote (EU)", "full_time", "open", 2,
     "Own services that power our scheduling and payroll integrations. Python, PostgreSQL and a strong testing culture.", 34),
    ("Frontend Engineer", "Engineering", "Berlin, DE", "full_time", "open", 1,
     "Build accessible, fast interfaces in React and TypeScript for our customer-facing workforce tools.", 28),
    ("Product Designer", "Design", "London, UK", "full_time", "open", 1,
     "Shape end-to-end workflows for managers and employees, from research through polished UI.", 21),
    ("Product Manager, Workforce Planning", "Product", "New York, US", "full_time", "open", 1,
     "Define the roadmap for scheduling and forecasting. You'll work closely with design, engineering and customers.", 18),
    ("Account Executive", "Sales", "Austin, US", "full_time", "open", 3,
     "Run full-cycle sales for mid-market HR and operations leaders. Prior SaaS quota experience required.", 15),
    ("People Operations Coordinator", "People", "Remote (US)", "contract", "open", 1,
     "Support onboarding, benefits administration and day-to-day People operations for a growing team.", 10),
    ("Content Marketing Intern", "Marketing", "Remote", "internship", "draft", 1,
     "Help research and draft blog posts, case studies and newsletters. A great first role in B2B marketing.", 4),
    ("Financial Analyst", "Finance", "Chicago, US", "full_time", "closed", 1,
     "Support monthly close, forecasting and board reporting. This role has been filled.", 70),
]

CANDIDATES = [
    # name, email, phone, source, days_ago
    ("Amara Okafor", "amara.okafor@example.com", "+1 415 555 0142", "linkedin", 30),
    ("Daniel Weber", "daniel.weber@example.com", "+49 30 5550 1180", "careers_page", 27),
    ("Priya Raman", "priya.raman@example.com", "+44 20 5550 0173", "referral", 25),
    ("Lucas Moreau", "lucas.moreau@example.com", None, "careers_page", 22),
    ("Sofia Martins", "sofia.martins@example.com", "+351 21 555 0190", "linkedin", 20),
    ("Ethan Brooks", "ethan.brooks@example.com", "+1 212 555 0116", "agency", 19),
    ("Mei Lin Chen", "mei.chen@example.com", "+1 512 555 0127", "referral", 17),
    ("Omar Haddad", "omar.haddad@example.com", "+1 646 555 0151", "linkedin", 15),
    ("Hannah Fischer", "hannah.fischer@example.com", None, "careers_page", 13),
    ("Tomás Rivera", "tomas.rivera@example.com", "+1 737 555 0164", "careers_page", 12),
    ("Grace Kimani", "grace.kimani@example.com", "+254 20 555 0138", "referral", 9),
    ("Noah Patel", "noah.patel@example.com", "+1 312 555 0109", "agency", 8),
    ("Isabella Rossi", "isabella.rossi@example.com", "+39 06 5550 1122", "linkedin", 6),
    ("Kenji Watanabe", "kenji.watanabe@example.com", None, "other", 3),
]

# candidate index, job index, status, days_ago applied
APPLICATIONS = [
    (0, 0, "interview", 29), (1, 0, "screening", 26), (2, 0, "offer", 24), (3, 1, "applied", 21),
    (4, 1, "interview", 19), (5, 0, "rejected", 18), (6, 4, "hired", 16), (7, 4, "offer", 14),
    (8, 2, "screening", 12), (9, 4, "applied", 11), (10, 3, "interview", 8), (11, 3, "applied", 7),
    (12, 2, "applied", 5), (13, 5, "applied", 2), (1, 1, "applied", 25), (4, 3, "screening", 15),
    (2, 3, "rejected", 20), (10, 5, "screening", 6), (7, 3, "applied", 9), (0, 1, "rejected", 28),
]

EMPLOYEES = [
    # code, first, last, email, phone, job title, department, status, days since joining
    ("E-0001", "Olivia", "Hart", "olivia.hart@example.com", "+1 415 555 0101", "VP of Engineering", "Engineering", "active", 1650),
    ("E-0002", "Marcus", "Lindqvist", "marcus.lindqvist@example.com", None, "Staff Software Engineer", "Engineering", "active", 1180),
    ("E-0003", "Aisha", "Rahman", "aisha.rahman@example.com", "+44 20 5550 0112", "Senior Software Engineer", "Engineering", "active", 720),
    ("E-0004", "Jonas", "Keller", "jonas.keller@example.com", "+49 30 5550 1144", "Senior Product Manager", "Product", "active", 900),
    ("E-0005", "Chloe", "Dubois", "chloe.dubois@example.com", None, "Senior Product Designer", "Design", "on_leave", 610),
    ("E-0006", "Rafael", "Santos", "rafael.santos@example.com", "+1 512 555 0166", "Sales Director", "Sales", "active", 1400),
    ("E-0007", "Yuki", "Tanaka", "yuki.tanaka@example.com", "+1 512 555 0172", "Account Executive", "Sales", "active", 330),
    ("E-0008", "Fatima", "Zahra", "fatima.zahra@example.com", None, "Marketing Manager", "Marketing", "active", 540),
    ("E-0009", "Ben", "Carter", "ben.carter@example.com", "+1 312 555 0123", "Operations Lead", "Operations", "active", 800),
    ("E-0010", "Lena", "Novak", "lena.novak@example.com", "+44 20 5550 0188", "HR Business Partner", "People", "active", 450),
    ("E-0011", "Victor", "Almeida", "victor.almeida@example.com", "+351 21 555 0144", "Finance Controller", "Finance", "active", 1020),
    ("E-0012", "Sara", "Eriksson", "sara.eriksson@example.com", None, "Software Engineer", "Engineering", "terminated", 960),
]
# A hired candidate who was turned into an employee (shows the Candidate -> Employee link).
HIRED_EMPLOYEE = ("E-0013", "mei.chen@example.com", "Mei Lin", "Chen", "Account Executive", "Sales", 9)


# ---------------------------------------------------------------- reset / seed / remove
# Business data only. User accounts, roles and sessions are NEVER touched by a reset (you'd lock yourself out).
BUSINESS_TABLES = [ActivityLog, Application, Employee, Job, Candidate, Department]  # children before parents


def reset_tables(db: Session) -> None:
    """Delete all BUSINESS rows and restart their ID counters (JOB-1001 again). Accounts stay; links from accounts to
    employee records become empty (users.employee_id is ON DELETE SET NULL) and seed() restores the demo links."""
    for model in BUSINESS_TABLES:
        db.execute(delete(model))
    if db.get_bind().dialect.name == "postgresql":
        # Not TRUNCATE ... CASCADE: users reference employees, and CASCADE would empty the users table too.
        for model in BUSINESS_TABLES:
            db.execute(text(f"SELECT setval(pg_get_serial_sequence('{model.__tablename__}', 'id'), 1, false)"))
    db.commit()


def _free_code(db: Session, code: str) -> str:
    candidate, n = code, 2
    while db.scalar(select(Department.id).where(Department.code == candidate)) is not None:
        candidate, n = f"{code}{n}", n + 1
    return candidate


def seed(db: Session) -> Counter:
    """Insert every sample record that does not exist yet (matched by name / email / code). Returns what was created."""
    now, made, log = utcnow(), Counter(), []

    departments: dict[str, Department] = {}
    for name, code, description in DEPARTMENTS:
        d = db.scalar(select(Department).where(func.lower(Department.name) == name.lower()))
        if d is None:
            d = Department(name=name, code=_free_code(db, code), description=description, is_sample=True,
                           created_at=now - timedelta(days=400), updated_at=now - timedelta(days=400))
            db.add(d)
            made["departments"] += 1
        departments[name] = d
    db.flush()

    jobs: list[Job] = []
    for title, dept, location, kind, status, openings, description, days in JOBS:
        j = db.scalar(select(Job).where(func.lower(Job.title) == title.lower()))
        if j is None:
            when = now - timedelta(days=days)
            j = Job(title=title, department_id=departments[dept].id, location=location, employment_type=kind, status=status,
                    openings=openings, description=description, is_sample=True, created_at=when, updated_at=when)
            db.add(j)
            made["jobs"] += 1
            log.append(ActivityLog(kind="job", message=f"Job '{title}' was created", created_at=when))
        jobs.append(j)

    candidates: list[Candidate] = []
    for name, email, phone, source, days in CANDIDATES:
        c = db.scalar(select(Candidate).where(func.lower(Candidate.email) == email.lower()))
        if c is None:
            when = now - timedelta(days=days)
            c = Candidate(full_name=name, email=email, phone=phone, source=source, is_sample=True, created_at=when)
            db.add(c)
            made["candidates"] += 1
            log.append(ActivityLog(kind="candidate", message=f"{name} was added as a candidate", created_at=when))
        candidates.append(c)
    db.flush()

    for ci, ji, status, days in APPLICATIONS:
        if db.scalar(select(Application.id).where(Application.candidate_id == candidates[ci].id, Application.job_id == jobs[ji].id)):
            continue
        created = now - timedelta(days=days)
        updated = created + timedelta(days=min(days - 1, 3)) if status != "applied" else created
        db.add(Application(candidate_id=candidates[ci].id, job_id=jobs[ji].id, status=status, created_at=created, updated_at=updated))
        made["applications"] += 1
        name, title = candidates[ci].full_name, jobs[ji].title
        log.append(ActivityLog(kind="application", message=f"{name} applied for '{title}'", created_at=created))
        if status != "applied":
            log.append(ActivityLog(kind="application", message=f"{name} moved to {status} for '{title}'", created_at=updated))

    def _employee_exists(code: str, email: str) -> bool:
        return db.scalar(select(Employee.id).where((Employee.employee_code == code) | (func.lower(Employee.email) == email.lower()))) is not None

    for code, first, last, email, phone, title, dept, status, days in EMPLOYEES:
        if _employee_exists(code, email):
            continue
        when = now - timedelta(days=days)
        db.add(Employee(employee_code=code, first_name=first, last_name=last, email=email, phone=phone, job_title=title,
                        department_id=departments[dept].id, employment_status=status, joining_date=date.today() - timedelta(days=days),
                        is_sample=True, created_at=when, updated_at=when))
        made["employees"] += 1
        log.append(ActivityLog(kind="employee", message=f"{first} {last} joined as an employee", created_at=when))

    code, email, first, last, title, dept, days = HIRED_EMPLOYEE
    mei = next(c for c in candidates if c.email.lower() == email)
    if not _employee_exists(code, email) and db.scalar(select(Employee.id).where(Employee.candidate_id == mei.id)) is None:
        when = now - timedelta(days=days)
        db.add(Employee(employee_code=code, first_name=first, last_name=last, email=email, phone=mei.phone, job_title=title,
                        department_id=departments[dept].id, employment_status="active", joining_date=date.today() - timedelta(days=days),
                        candidate_id=mei.id, is_sample=True, created_at=when, updated_at=when))
        made["employees"] += 1
        log.append(ActivityLog(kind="employee", message=f"{first} {last} joined as an employee (hired candidate)", created_at=when))

    db.add_all(log)
    db.commit()
    return made


DEMO_PASSWORD = "WorkforceOS-demo-2026"  # nosec B105 # public demo password; `--demo-users` refuses to run in production
DEMO_USERS = [
    # email, full name, role, linked employee (by employee code) or None
    ("admin@demo.example.com", "Sam Super-Admin", "super_admin", None),
    ("hr.admin@demo.example.com", "Lena Novak", "hr_admin", "E-0010"),
    ("hr.manager@demo.example.com", "Ben Carter", "hr_manager", "E-0009"),
    ("recruiter@demo.example.com", "Rita Recruiter", "recruiter", None),
    ("employee@demo.example.com", "Aisha Rahman", "employee", "E-0003"),
]


def seed_demo_users(db: Session) -> Counter:
    """One sign-in per built-in role, all with DEMO_PASSWORD. Idempotent; also restores their employee links."""
    from app.auth.models import Role, User  # local import: the business seed must not depend on the auth package
    from app.auth.passwords import hash_password

    made, password_hash = Counter(), None
    for email, name, role_name, code in DEMO_USERS:
        employee_id = db.scalar(select(Employee.id).where(Employee.employee_code == code)) if code else None
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if user is None:
            password_hash = password_hash or hash_password(DEMO_PASSWORD)
            role = db.scalar(select(Role).where(Role.name == role_name))
            user = User(full_name=name, email=email, password_hash=password_hash, status="active", is_sample=True,
                        roles=[role], password_changed_at=utcnow())
            db.add(user)
            made["users"] += 1
        if user.employee_id is None and employee_id is not None and not db.scalar(select(User.id).where(User.employee_id == employee_id)):
            user.employee_id = employee_id
    db.commit()
    return made


def relink_demo_users(db: Session) -> None:
    """After a business-data reset, demo accounts that still exist get their employee records back."""
    from app.auth.models import User

    for email, _, _, code in DEMO_USERS:
        user = db.scalar(select(User).where(func.lower(User.email) == email, User.is_sample.is_(True)))
        if user is not None and user.employee_id is None and code:
            employee_id = db.scalar(select(Employee.id).where(Employee.employee_code == code))
            if employee_id is not None and not db.scalar(select(User.id).where(User.employee_id == employee_id)):
                user.employee_id = employee_id
    db.commit()


def remove_sample(db: Session) -> Counter:
    """Delete ONLY sample records, and only those nothing real depends on."""
    removed = Counter()
    removed["applications"] = db.execute(delete(Application).where(
        Application.candidate_id.in_(select(Candidate.id).where(Candidate.is_sample)),
        Application.job_id.in_(select(Job.id).where(Job.is_sample)))).rowcount
    from app.auth.models import User

    removed["users"] = db.execute(delete(User).where(User.is_sample)).rowcount
    removed["employees"] = db.execute(delete(Employee).where(Employee.is_sample)).rowcount
    removed["jobs"] = db.execute(delete(Job).where(Job.is_sample, ~exists().where(Application.job_id == Job.id))).rowcount
    removed["candidates"] = db.execute(delete(Candidate).where(
        Candidate.is_sample, ~exists().where(Application.candidate_id == Candidate.id),
        ~exists().where(Employee.candidate_id == Candidate.id))).rowcount
    removed["departments"] = db.execute(delete(Department).where(
        Department.is_sample, ~exists().where(Job.department_id == Department.id), ~exists().where(Employee.department_id == Department.id))).rowcount
    db.commit()
    return removed


# ---------------------------------------------------------------- command line
def main() -> int:
    parser = argparse.ArgumentParser(description="Manage WorkforceOS sample data.")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--reset", action="store_true", help="delete ALL existing data first (development only)")
    group.add_argument("--remove-sample", action="store_true", help="delete only the records flagged as sample data")
    parser.add_argument("--demo-users", action="store_true",
                        help=f"also create one sign-in per role, password {DEMO_PASSWORD!r} (development only)")
    args = parser.parse_args()
    print(f"Database: {describe_url()}")
    if (args.reset or args.demo_users) and IS_PRODUCTION:
        print("Refusing to --reset / create demo users: APP_ENV=production.")
        return 2
    try:
        with SessionLocal() as db:
            if args.remove_sample:
                removed = remove_sample(db)
                print("Removed sample records: " + (", ".join(f"{n} {k}" for k, n in removed.items() if n) or "none found") + ".")
                return 0
            if args.reset:
                reset_tables(db)
            made = seed(db)
            relink_demo_users(db)
            print("Added sample records: " + (", ".join(f"{n} {k}" for k, n in made.items()) or "none (everything already exists)") + ".")
            if args.demo_users:
                created = seed_demo_users(db)
                print(f"Demo sign-ins ({created['users']} new), all with the password {DEMO_PASSWORD!r}:")
                for email, name, role, _ in DEMO_USERS:
                    print(f"  {role:<12} {email}")
    except SQLAlchemyError as exc:
        print(f"\nCould not seed the database: {type(exc).__name__}\n"
              "  - Is PostgreSQL running and is DATABASE_URL in backend/.env correct?\n"
              "  - Did you create the tables?  Run:  alembic upgrade head")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
