from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime


class CourseModuleSchema(BaseModel):
    """A single lesson inside a course.

    Allowed `type` values:
    - video: content_url is a YouTube URL, Vimeo URL, or direct .mp4 URL
    - pdf:   content_url points to a PDF (will be rendered in an iframe)
    - text:  content lives in `description` (markdown-friendly plain text)
    - quiz:  the course's `assessment_json` block is the quiz; this entry
             marks the position of the quiz in the lesson sequence
    """
    id: str
    title: str
    type: str = Field(..., pattern="^(video|pdf|text|quiz)$")
    content_url: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int = 0


class CourseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    modules_json: List[CourseModuleSchema] = []
    duration_hours: Optional[int] = Field(None, gt=0)
    status: str = Field("draft", pattern="^(draft|published)$")


class CourseUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    modules_json: Optional[List[CourseModuleSchema]] = None
    duration_hours: Optional[int] = Field(None, gt=0)
    status: Optional[str] = Field(None, pattern="^(draft|published)$")


class CourseResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    modules_json: List[Any] = []
    duration_hours: Optional[int] = None
    thumbnail_url: Optional[str] = None
    enrollment_count: int = 0
    completion_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CourseListResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    duration_hours: Optional[int] = None
    thumbnail_url: Optional[str] = None
    enrollment_count: int = 0
    completion_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


class EnrollmentResponse(BaseModel):
    id: int
    user_id: int
    user_name: Optional[str] = None
    course_id: int
    course_title: Optional[str] = None
    status: str
    progress_json: Optional[Any] = None
    completed_at: Optional[datetime] = None
    score: Optional[int] = None
    attempt_count: int = 0
    certificate_requested: bool = False
    certificate_requested_at: Optional[datetime] = None
    certificate_url: Optional[str] = None
    certificate_issued_at: Optional[datetime] = None
    enrolled_at: datetime

    model_config = {"from_attributes": True}


class EnrollmentUpdateRequest(BaseModel):
    status: Optional[str] = Field(None, pattern="^(enrolled|in_progress|completed)$")
    progress_json: Optional[Any] = None


class ModuleProgressRequest(BaseModel):
    module_id: str = Field(..., min_length=1)


class AssessmentSubmitRequest(BaseModel):
    answers: dict = Field(..., description="Mapping of question ID to selected answer")


class AssessmentResultResponse(BaseModel):
    score: int
    passed: bool
    passing_score: int
    attempt_count: int
