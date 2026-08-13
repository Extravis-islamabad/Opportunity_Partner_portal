from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime


# ==================== Sales activity log ====================

_TYPE_PATTERN = r"^(call|meeting|demo|email|site_visit|follow_up|training|other)$"


class ActivityCreateRequest(BaseModel):
    activity_date: date
    activity_type: str = Field(pattern=_TYPE_PATTERN)
    customer_name: Optional[str] = Field(None, max_length=255)
    opportunity_id: Optional[int] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=24 * 60)
    notes: Optional[str] = None


class ActivityUpdateRequest(BaseModel):
    activity_date: Optional[date] = None
    activity_type: Optional[str] = Field(None, pattern=_TYPE_PATTERN)
    customer_name: Optional[str] = Field(None, max_length=255)
    opportunity_id: Optional[int] = None
    duration_minutes: Optional[int] = Field(None, ge=1, le=24 * 60)
    notes: Optional[str] = None


class ActivityResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    activity_date: date
    activity_type: str
    activity_type_label: str
    customer_name: Optional[str] = None
    opportunity_id: Optional[int] = None
    opportunity_name: Optional[str] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ActivityTypeTotal(BaseModel):
    activity_type: str
    label: str
    count: int


class ActivityDay(BaseModel):
    """One calendar day in the month view, with that day's entries."""
    date: date
    weekday: int  # 0 = Monday … 6 = Sunday
    items: list[ActivityResponse]


class ActivityMonthResponse(BaseModel):
    """A rep's activity month: every day that has entries, plus totals.

    The frontend builds the Mon–Fri grid itself from the month; this response
    only carries days that actually contain activities.
    """
    user_id: int
    user_name: Optional[str] = None
    month: str  # "YYYY-MM"
    days: list[ActivityDay]
    totals_by_type: list[ActivityTypeTotal]
    total_activities: int
    total_duration_minutes: int
