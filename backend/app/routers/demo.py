"""Development-only helper. This module (and with it every import of the sample-data code) is only loaded when
ENABLE_DEMO_RESET is true, so a production deployment never even registers the endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import record_event
from app.auth.dependencies import Auth, require_recent
from app.db import get_db
from app.seed import relink_demo_users, reset_tables, seed

router = APIRouter(tags=["demo (development only)"])


@router.post("/demo/reset")
def reset_demo_data(auth: Auth = Depends(require_recent("system:demo_reset")), db: Session = Depends(get_db)):
    """DESTRUCTIVE: wipes all business data (your own records too) and reloads the sample data.
    User accounts, roles and sessions are kept, so nobody is signed out or locked out."""
    reset_tables(db)
    seed(db)
    relink_demo_users(db)
    record_event("system.demo_reset", category="system", actor=auth.user, metadata={"scope": "all business data"})
    return {"detail": "Demo data has been reset to the original sample data."}
