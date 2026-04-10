from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    message: str
    read: bool
    entity_type: Optional[str] = None
    entity_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class NotificationCountResponse(BaseModel):
    unread_count: int
    total_count: int


class MarkReadRequest(BaseModel):
    notification_ids: list[int]
