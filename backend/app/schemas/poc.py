from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, datetime
from decimal import Decimal

from app.schemas.poc_team import PocTeamMemberResponse


# ==================== POC ====================

class PocStageState(BaseModel):
    """One of the five POC stages, resolved for display."""
    key: str
    label: str
    completed: bool
    completed_at: Optional[date] = None

    # Who on the POC team is responsible for this stage. All null when nobody
    # has been named — and all null for a partner viewer, who sees the team
    # roster but not the internal division of labour.
    owner_user_id: Optional[int] = None
    owner_name: Optional[str] = None
    # Their POC role ("Deployment Engineer"), so the tracker can say what kind
    # of person owns the stage as well as who.
    owner_role: Optional[str] = None
    owner_role_label: Optional[str] = None


class PocStartRequest(BaseModel):
    """Starting a POC == allocating the VM. vm_provisioning_completed_at is
    set to start_date, which is what moves the POC to `running`."""
    start_date: date
    target_end_date: Optional[date] = None
    notes: Optional[str] = None


class PocStageUpdateRequest(BaseModel):
    # None clears the stage (marks it not-done again) — used to undo a
    # mis-click, so it must be distinguishable from "field omitted".
    completed_at: Optional[date] = None


class PocUpdateRequest(BaseModel):
    target_end_date: Optional[date] = None
    notes: Optional[str] = None
    vm_provisioning_completed_at: Optional[date] = None
    deployment_completed_at: Optional[date] = None
    device_onboarding_completed_at: Optional[date] = None
    dashboarding_completed_at: Optional[date] = None
    fine_tuning_completed_at: Optional[date] = None


class PocStageOwnerRequest(BaseModel):
    # None clears the stage owner. Distinguishable from "field omitted" is not
    # needed here — the field is the whole body.
    owner_user_id: Optional[int] = None


class PocCloseRequest(BaseModel):
    successful: bool
    end_date: Optional[date] = None
    outcome_notes: Optional[str] = None
    # Only meaningful when successful=False; the service ignores it otherwise.
    failure_reason: Optional[str] = Field(None, max_length=255)


class PocResponse(BaseModel):
    id: int
    opportunity_id: int
    status: str

    start_date: Optional[date] = None
    target_end_date: Optional[date] = None
    end_date: Optional[date] = None

    vm_provisioning_completed_at: Optional[date] = None
    deployment_completed_at: Optional[date] = None
    device_onboarding_completed_at: Optional[date] = None
    dashboarding_completed_at: Optional[date] = None
    fine_tuning_completed_at: Optional[date] = None

    closed_at: Optional[datetime] = None
    outcome_notes: Optional[str] = None
    failure_reason: Optional[str] = None
    notes: Optional[str] = None

    # Derived
    stages: list[PocStageState] = []
    completed_stage_count: int = 0
    total_stage_count: int = 5
    current_stage: Optional[str] = None
    current_stage_label: Optional[str] = None
    days_running: Optional[int] = None
    is_overdue: bool = False

    # Resolved from the parent opportunity so the POC list needs one call.
    opportunity_name: Optional[str] = None
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    partner_name: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    region: Optional[str] = None
    product: Optional[str] = None
    worth: Optional[Decimal] = None
    sales_rep_name: Optional[str] = None
    closed_by_name: Optional[str] = None

    # The current roster — everyone from Extravis working this POC, over and
    # above the opportunity's one named sales rep. Empty until someone is
    # assigned, which is the normal state for a POC nobody has staffed yet.
    team: list[PocTeamMemberResponse] = []

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ==================== Customer licence (post-PO) ====================

class LicenseUpsertRequest(BaseModel):
    po_number: Optional[str] = Field(None, max_length=100)
    po_received_date: Optional[date] = None
    po_value: Optional[Decimal] = Field(None, ge=0)
    device_count: Optional[int] = Field(None, ge=0)
    node_count: Optional[int] = Field(None, ge=0)
    license_activated_at: Optional[date] = None
    license_expires_at: Optional[date] = None
    license_key: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None


class LicenseResponse(BaseModel):
    id: int
    opportunity_id: int
    po_number: Optional[str] = None
    po_received_date: Optional[date] = None
    po_value: Optional[Decimal] = None
    device_count: Optional[int] = None
    node_count: Optional[int] = None
    license_activated_at: Optional[date] = None
    license_expires_at: Optional[date] = None
    license_key: Optional[str] = None
    status: str
    notes: Optional[str] = None

    # Derived
    days_until_expiry: Optional[int] = None

    # Resolved from the parent opportunity
    opportunity_name: Optional[str] = None
    customer_name: Optional[str] = None
    company_name: Optional[str] = None
    country: Optional[str] = None
    product: Optional[str] = None

    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
