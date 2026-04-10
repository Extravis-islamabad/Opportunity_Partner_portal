from pydantic import BaseModel
from datetime import datetime
from typing import Any, Dict, List, Optional


class AuditLogResponse(BaseModel):
    id: int
    user_id: int
    user_full_name: str
    action: str
    entity_type: str
    entity_id: int
    metadata_json: Optional[Dict[str, Any]] = None
    timestamp: datetime

    model_config = {"from_attributes": True}


class AuditLogListResponse(BaseModel):
    items: List[AuditLogResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
