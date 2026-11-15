"""Public IDs (JOB-1001) <-> database primary keys (1).

The database uses plain integers; the API shows friendlier prefixed IDs so the frontend,
URLs and your muscle memory keep working exactly as in Phase 1.
"""
_KINDS = {"job": ("JOB", 1000), "candidate": ("CAN", 2000), "application": ("APP", 3000), "department": ("DEP", 4000), "employee": ("EMP", 5000), "user": ("USR", 6000), "role": ("ROL", 7000), "activity": ("ACT", 0)}


def public_id(kind: str, pk: int) -> str:
    prefix, offset = _KINDS[kind]
    return f"{prefix}-{offset + pk}"


def parse_id(kind: str, value: str | None) -> int | None:
    """'JOB-1001' -> 1. Returns None for anything that is not a valid ID of that kind."""
    prefix, offset = _KINDS[kind]
    if not value or not value.upper().startswith(prefix + "-"):
        return None
    number = value[len(prefix) + 1 :]
    if not number.isdigit() or len(number) > 9:
        return None
    pk = int(number) - offset
    return pk if pk >= 1 else None


def parse_id_loose(kind: str, value: str) -> int | None:
    """Like parse_id, but also accepts just the number ('1001'), handy for search boxes."""
    prefix, _ = _KINDS[kind]
    return parse_id(kind, f"{prefix}-{value}" if value.isdigit() else value)
