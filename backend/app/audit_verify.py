"""Check the audit log's hash chain from the command line:   python -m app.audit_verify
Exit code 0 = intact, 1 = problem found (useful for a scheduled check)."""
import sys

from app.audit import verify_chain
from app.config import AUDIT_KEY_IS_DEVELOPMENT_DEFAULT
from app.db import SessionLocal, describe_url


def main() -> int:
    print(f"Database: {describe_url()}")
    if AUDIT_KEY_IS_DEVELOPMENT_DEFAULT:
        print("WARNING: AUDIT_HMAC_KEY is not set; records are signed with the public development key, so the check "
              "proves nothing against someone who has read this code.")
    with SessionLocal() as db:
        result = verify_chain(db)
    if result["ok"]:
        print(f"OK: {result['checked']} audit records, chain intact. Latest hash (write it down to detect truncation "
              f"later): {result['last_hash']}")
        return 0
    print(f"PROBLEM after {result['checked']} intact records: {result['problem']} (record id {result['first_problem_id']})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
