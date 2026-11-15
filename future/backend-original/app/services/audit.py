import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


async def record_audit_event(
    db: AsyncSession,
    actor_id: uuid.UUID | None,
    action: str,
    resource_type: str,
    resource_id: str,
    ip_address: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        ip_address=ip_address,
        metadata_=metadata,
    )
    db.add(entry)
    await db.commit()
