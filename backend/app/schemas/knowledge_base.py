from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


# The categories the upload forms offer (frontend/src/utils/kbCategories.ts
# mirrors this list — keep them in step). The server accepts these, plus any
# category already in use so documents filed under a legacy category stay
# editable; see kb_service.validate_category.
KB_CANONICAL_CATEGORIES: tuple[str, ...] = (
    "Extravis", "MonetX", "SupportX", "GreenX", "PatchX", "AgentX",
    "Product Sheets", "Case Studies", "Technical Guides",
)
# Where a fulfilled document request lands in the KB when the admin picks no
# category. Always valid, so fulfilment can never fail on it.
KB_REQUESTED_DOCUMENTS_CATEGORY = "Requested Documents"

KB_TITLE_MAX_LENGTH = 500
KB_CATEGORY_MAX_LENGTH = 100


class KBDocumentCreateRequest(BaseModel):
    # Strip first so "   " is rejected by min_length rather than stored.
    model_config = {"str_strip_whitespace": True}

    title: str = Field(..., min_length=1, max_length=KB_TITLE_MAX_LENGTH)
    category: str = Field(..., min_length=1, max_length=KB_CATEGORY_MAX_LENGTH)
    description: Optional[str] = None


class KBDocumentUpdateRequest(BaseModel):
    """A partial update: only the fields the caller actually sent are applied
    (the service dumps with exclude_unset), so omitting description leaves it
    alone rather than wiping it."""
    model_config = {"str_strip_whitespace": True}

    title: Optional[str] = Field(None, min_length=1, max_length=KB_TITLE_MAX_LENGTH)
    category: Optional[str] = Field(None, min_length=1, max_length=KB_CATEGORY_MAX_LENGTH)
    description: Optional[str] = None

    @field_validator("title", "category")
    @classmethod
    def _not_null_when_sent(cls, v: Optional[str]) -> Optional[str]:
        # Only runs for values the caller supplied. Both columns are NOT NULL,
        # so an explicit null used to reach the flush and 500; refuse it here.
        if v is None:
            raise ValueError("cannot be empty")
        return v


class KBDocumentResponse(BaseModel):
    id: int
    title: str
    category: str
    description: Optional[str] = None
    file_name: str
    # Populated only by POST /documents/{id}/download. Handing a signed URL out
    # on list/detail let anyone fetch the file without the download being
    # logged, so every other response leaves it null.
    file_url: Optional[str] = None
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    version: int
    previous_version_id: Optional[int] = None
    is_archived: bool = False
    uploaded_by: int
    uploader_name: Optional[str] = None
    download_count: int = 0
    published_at: datetime
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class KBDocumentListResponse(BaseModel):
    id: int
    title: str
    category: str
    description: Optional[str] = None
    file_name: str
    file_size: Optional[int] = None
    version: int
    download_count: int = 0
    published_at: datetime

    model_config = {"from_attributes": True}


class KBCategoryResponse(BaseModel):
    name: str
    document_count: int
