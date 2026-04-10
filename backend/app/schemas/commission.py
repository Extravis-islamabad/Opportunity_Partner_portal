from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, ConfigDict


class CommissionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    deal_id: int
    company_id: int
    company_name: Optional[str] = None
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    tier_at_calculation: str
    rate_percentage: Decimal
    deal_value: Decimal
    amount: Decimal
    currency: str
    status: str
    notes: Optional[str] = None
    calculated_at: datetime
    approved_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None

    # Light deal summary so the list view doesn't need a second fetch
    deal_customer_name: Optional[str] = None
    deal_expected_close_date: Optional[str] = None


class CommissionListResponse(BaseModel):
    items: List[CommissionRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class CommissionStatusUpdate(BaseModel):
    status: str  # "approved" | "paid" | "void"
    notes: Optional[str] = None


class StatementPeriodSummary(BaseModel):
    period_start: date
    period_end: date
    company_id: int
    company_name: Optional[str] = None
    total_amount: Decimal
    commission_count: int
    currency: str = "USD"


class Badge(BaseModel):
    key: str
    label: str
    description: str
    earned_at: Optional[datetime] = None


class ScorecardRead(BaseModel):
    company_id: int
    company_name: str
    tier: str
    next_tier: Optional[str] = None
    total_approved_deals: int
    total_closed_value: Decimal
    ytd_commission: Decimal
    lifetime_commission: Decimal
    tier_progress_pct: float
    rank: Optional[int] = None
    badges: List[Badge] = []
    monthly_commission: List["MonthlyCommissionPoint"] = []


class MonthlyCommissionPoint(BaseModel):
    month: str  # "2026-01"
    amount: Decimal


class LeaderboardEntry(BaseModel):
    rank: int
    company_id: int
    company_name: str
    tier: str
    total_amount: Decimal
    deal_count: int


class LeaderboardResponse(BaseModel):
    period: str
    entries: List[LeaderboardEntry]


ScorecardRead.model_rebuild()
