from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

# Mirrors PocTeamRole. Written out rather than derived so the OpenAPI schema
# shows the literal values a client may send.
POC_TEAM_ROLE_PATTERN = (
    "^(presales_lead|solution_architect|deployment_engineer"
    "|project_manager|qa|support)$"
)


class PocTeamMemberCreateRequest(BaseModel):
    user_id: int
    role: str = Field(..., pattern=POC_TEAM_ROLE_PATTERN)


class PocTeamRoleUpdateRequest(BaseModel):
    role: str = Field(..., pattern=POC_TEAM_ROLE_PATTERN)


class PocTeamMemberResponse(BaseModel):
    id: int
    poc_id: int
    user_id: int
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    # The person's role in the portal (admin / sales_rep) — distinct from
    # `role` below, which is what they do on this POC.
    user_role: Optional[str] = None
    job_title: Optional[str] = None

    role: str
    role_label: str

    assigned_by: Optional[int] = None
    assigned_by_name: Optional[str] = None
    assigned_at: datetime
    # Set only on rows returned by a history read; the current roster is all
    # nulls here.
    removed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PocTeamRoleOption(BaseModel):
    """One selectable role, so the picker doesn't hardcode the list."""
    value: str
    label: str
