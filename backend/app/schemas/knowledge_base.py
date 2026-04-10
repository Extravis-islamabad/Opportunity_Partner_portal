from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class KBDocumentCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    category: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class KBDocumentUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    category: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class KBDocumentResponse(BaseModel):
    id: int
    title: str
    category: str
    description: Optional[str] = None
    file_name: str
    file_url: str
    file_size: Optional[int] = None
    content_type: Optional[str] = None
    version: int
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
