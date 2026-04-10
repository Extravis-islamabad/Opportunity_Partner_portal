from pydantic import BaseModel
from typing import Any, Dict, Generic, List, Optional, TypeVar
from datetime import datetime

T = TypeVar("T")


class ErrorResponse(BaseModel):
    code: str
    message: str
    details: Dict[str, Any] = {}


class PaginationParams(BaseModel):
    page: int = 1
    page_size: int = 20


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class MessageResponse(BaseModel):
    message: str


class TimestampMixin(BaseModel):
    created_at: datetime
    updated_at: datetime
