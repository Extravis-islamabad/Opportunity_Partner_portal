from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserBasicResponse"


class RefreshRequest(BaseModel):
    refresh_token: str


class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8, max_length=128)


class ActivateAccountRequest(BaseModel):
    token: str
    password: str = Field(..., min_length=8, max_length=128)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)


class UserBasicResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    status: str
    company_id: int | None = None
    company_name: str | None = None
    # The caller's own company type — null for admins and sales reps, who have
    # no company. The frontend derives its capability set from this, so a
    # customer company's user never sees deal registration, commissions,
    # scorecard or leaderboard in the sidebar, routes or command palette.
    company_type: str | None = None
    is_superadmin: bool = False
    is_channel_manager: bool = False
    managed_company_count: int = 0
    has_completed_onboarding: bool = False

    model_config = {"from_attributes": True}


LoginResponse.model_rebuild()


class MfaLoginRequest(BaseModel):
    """The second half of a login: proof the password step just happened, and
    a code from the authenticator (or a recovery code)."""

    challenge_token: str
    code: str = Field(..., min_length=4, max_length=32)


class MfaConfirmRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=10)
