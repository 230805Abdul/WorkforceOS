from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_roles
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User, UserRole

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/audit-logs")
async def list_audit_logs(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    result = await db.execute(select(AuditLog).order_by(AuditLog.created_at.desc()).limit(min(limit, 500)))
    logs = result.scalars().all()
    return [
        {
            "id": str(log.id),
            "actor_id": str(log.actor_id) if log.actor_id else None,
            "action": log.action,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "ip_address": log.ip_address,
            "metadata": log.metadata_,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
