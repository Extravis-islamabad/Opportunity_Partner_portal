from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class DocRequestCreateRequest(BaseModel):
    description: str = Field(..., min_length=1)
    reason: Optional[str] = None
    urgency: str = Field("medium", pattern="^(low|medium|high)$")


class DocRequestFulfillRequest(BaseModel):
    add_to_kb: bool = False
    kb_title: Optional[str] = None
    kb_category: Optional[str] = None


class DocRequestDeclineRequest(BaseModel):
    decline_reason: str = Field(..., min_length=1)


class DocRequestResponse(BaseModel):
    id: int
    company_id: int
    company_name: Optional[str] = None
    requested_by: int
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    description: str
    reason: Optional[str] = None
    urgency: str
    status: str
    fulfilled_by: Optional[int] = None
    fulfiller_name: Optional[str] = None
    fulfilled_at: Optional[datetime] = None
    fulfilled_file_url: Optional[str] = None
    fulfilled_file_name: Optional[str] = None
    decline_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocRequestListResponse(BaseModel):
    id: int
    company_name: Optional[str] = None
    requester_name: Optional[str] = None
    description: str
    urgency: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
