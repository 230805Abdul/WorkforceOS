"""Create (or promote) a Super Administrator from the command line. This is the ONLY way to get the first admin:
public registration always gives the restricted "Employee" role.

    python -m app.create_admin --email you@example.com --name "Your Name"
        -> asks for the password twice (nothing is shown while you type)

    python -m app.create_admin --email someone@example.com --promote
        -> gives an EXISTING account the Super Administrator role (and re-enables it if disabled)

    echo 'a long password' | python -m app.create_admin --email ... --name ... --password-stdin
        -> for scripts; the password never appears in the command line or shell history
"""
import argparse
import getpass
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.auth.models import Role
from app.auth.passwords import POLICY_TEXT, hash_password, policy_problem
from app.auth.permissions import SUPER_ADMIN_ROLE
from app.auth.service import find_user_by_email, normalize_email
from app.db import SessionLocal, describe_url
from app.models import utcnow
from app.services import log_activity


def _read_password(args, email: str, name: str) -> str:
    if args.password_stdin:
        password = sys.stdin.readline().rstrip("\n")
    else:
        print(f"Password policy: {POLICY_TEXT}")
        password = getpass.getpass("Password: ")
        if getpass.getpass("Repeat password: ") != password:
            raise SystemExit("Passwords do not match. Nothing was changed.")
    if (problem := policy_problem(password, email=email, full_name=name)) is not None:
        raise SystemExit(f"{problem}. Nothing was changed.")
    return password


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or promote a WorkforceOS Super Administrator.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", help="full name (required when creating a new account)")
    parser.add_argument("--promote", action="store_true", help="give an existing account the Super Administrator role")
    parser.add_argument("--password-stdin", action="store_true", help="read the password from standard input")
    args = parser.parse_args()

    try:
        email = normalize_email(validate_email(args.email, check_deliverability=False).normalized)
    except EmailNotValidError as exc:
        raise SystemExit(f"Invalid e-mail address: {exc}")
    print(f"Database: {describe_url()}")
    try:
        with SessionLocal() as db:
            role = db.scalar(select(Role).where(Role.name == SUPER_ADMIN_ROLE))
            if role is None:
                raise SystemExit("The roles table is empty. Run:  alembic upgrade head")
            user = find_user_by_email(db, email)
            if args.promote:
                if user is None:
                    raise SystemExit(f"No account with e-mail {email}. Leave out --promote to create one.")
                if role not in user.roles:
                    user.roles.append(role)
                user.status = "active"
                log_activity(db, "user", f"{user.full_name} was made Super Administrator (command line)")
                db.commit()
                print(f"{user.full_name} <{email}> is now a Super Administrator.")
                return 0
            if user is not None:
                raise SystemExit(f"An account with e-mail {email} already exists. Use --promote to make it a Super Administrator.")
            if not args.name or len(args.name.strip()) < 2:
                raise SystemExit("--name is required when creating a new account.")
            password = _read_password(args, email, args.name.strip())
            from app.auth.models import User

            user = User(full_name=args.name.strip(), email=email, password_hash=hash_password(password), status="active",
                        roles=[role], password_changed_at=utcnow())
            db.add(user)
            log_activity(db, "user", f"{user.full_name} was created as Super Administrator (command line)")
            db.commit()
            print(f"Created Super Administrator {user.full_name} <{email}>. Sign in at the website with this e-mail.")
    except SQLAlchemyError as exc:
        print(f"Database error: {type(exc).__name__}. Is PostgreSQL running, DATABASE_URL correct, and `alembic upgrade head` done?")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
