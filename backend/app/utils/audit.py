from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog


def _json_safe(value: Any) -> Any:
    """Coerce one value into something the JSON column can hold.

    Audit metadata is assembled from model attributes, so it routinely carries
    dates, Decimals and enums. The column is JSON, and psycopg serialises it at
    flush time — inside the request — so a single unconvertible value did not
    produce a bad audit row, it raised and failed the whole write. Editing an
    opportunity's closing date or worth failed this way: the edit itself was
    fine, the record of it was what threw.

    Decimals become strings rather than floats: this is money, and an audit
    trail is the last place to round it.
    """
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    # Anything else is recorded as its repr rather than dropped: a partial
    # audit line beats an exception on the path being audited.
    return str(value)


async def write_audit_log(
    db: AsyncSession,
    user_id: int,
    action: str,
    entity_type: str,
    entity_id: int,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        metadata_json=_json_safe(metadata or {}),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(entry)
    await db.flush()
    return entry
