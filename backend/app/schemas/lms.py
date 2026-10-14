from pydantic import BaseModel, Field, StrictInt, field_validator
from typing import Optional, List, Any, Dict, Union
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
    id: str = Field(..., min_length=1, max_length=100)
    title: str
    type: str = Field(..., pattern="^(video|pdf|text|quiz)$")
    content_url: Optional[str] = None
    description: Optional[str] = None
    duration_minutes: Optional[int] = None
    order: int = 0


class QuizQuestionSchema(BaseModel):
    """One multiple-choice question in a course's `assessment_json`.

    The shape is dictated by lms_service.submit_assessment, which scores by
    comparing `answers[str(id)]` against `correct_answer` (an index into
    `options`) and weights by `points`. Anything that doesn't fit that shape
    used to be stored anyway and then silently scored as wrong for everybody,
    so it is rejected at the door instead.
    """
    id: Union[StrictInt, str]
    question: str = Field(..., min_length=1, max_length=2000)
    options: List[str] = Field(..., min_length=2, max_length=10)
    # Strict so `true` can't stand in for 1: the scorer uses ==, and True == 1.
    correct_answer: StrictInt = Field(..., ge=0)
    points: StrictInt = Field(1, ge=1, le=100)

    @field_validator("id")
    @classmethod
    def _id_not_blank(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError("question id must not be blank")
        return v

    @field_validator("options")
    @classmethod
    def _options_not_blank(cls, v: List[str]) -> List[str]:
        if any(not o.strip() for o in v):
            raise ValueError("options must not be blank")
        return v

    @field_validator("correct_answer")
    @classmethod
    def _answer_in_range(cls, v: int, info) -> int:
        options = info.data.get("options")
        if options is not None and v >= len(options):
            raise ValueError("correct_answer must be the index of one of the options")
        return v


def _unique_module_ids(modules):
    # Progress is keyed by module id, so two lessons sharing an id would be
    # ticked off together.
    if modules is not None:
        ids = [m.id for m in modules]
        if len(ids) != len(set(ids)):
            raise ValueError("module ids must be unique")
    return modules


def _unique_question_ids(questions):
    # Answers arrive keyed by str(id), so 1 and "1" are the same question too.
    if questions is not None:
        ids = [str(q.id) for q in questions]
        if len(ids) != len(set(ids)):
            raise ValueError("question ids must be unique")
    return questions


class CourseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    modules_json: List[CourseModuleSchema] = []
    assessment_json: List[QuizQuestionSchema] = []
    passing_score: int = Field(70, ge=1, le=100)
    duration_hours: Optional[int] = Field(None, gt=0)
    status: str = Field("draft", pattern="^(draft|published)$")

    _modules = field_validator("modules_json")(_unique_module_ids)
    _questions = field_validator("assessment_json")(_unique_question_ids)


class CourseUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    modules_json: Optional[List[CourseModuleSchema]] = None
    assessment_json: Optional[List[QuizQuestionSchema]] = None
    passing_score: Optional[int] = Field(None, ge=1, le=100)
    duration_hours: Optional[int] = Field(None, gt=0)
    status: Optional[str] = Field(None, pattern="^(draft|published)$")

    # Optional here means "may be omitted", not "may be cleared": these columns
    # are NOT NULL (or, for the JSON lists, meaningless as null — send [] to
    # empty them). Pydantic only runs validators on values that were actually
    # sent, so an omitted field still passes while an explicit null is a 422
    # rather than a 500 from the database or a confusing enum error.
    @field_validator("title", "status", "passing_score", "modules_json", "assessment_json")
    @classmethod
    def _no_explicit_null(cls, v, info):
        if v is None:
            raise ValueError(f"{info.field_name} cannot be null")
        return v

    _modules = field_validator("modules_json")(_unique_module_ids)
    _questions = field_validator("assessment_json")(_unique_question_ids)


class CourseResponse(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    modules_json: List[Any] = []
    # For non-admins the service strips correct_answer out of each question —
    # the scorer relies on it, so shipping it to the browser hands out the key.
    assessment_json: List[Any] = []
    passing_score: int = 70
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
    certificate_url: Optional[str] = None
    certificate_issued_at: Optional[datetime] = None
    enrolled_at: datetime

    model_config = {"from_attributes": True}


class EnrollmentUpdateRequest(BaseModel):
    """What a partner may ask of their own enrolment.

    `status: completed` is a request, not an assertion: the service grants it
    only when the course's completion rules are already met. `progress_json`
    is accepted here only so a malformed value (a string, a list) is a 422
    rather than being stored and breaking /progress later — the service
    refuses it outright, because progress is recorded one module at a time
    through /progress, which checks the module exists and isn't the quiz.
    """
    status: Optional[str] = Field(None, pattern="^(enrolled|in_progress|completed)$")
    progress_json: Optional[Dict[str, bool]] = None


class ModuleProgressRequest(BaseModel):
    module_id: str = Field(..., min_length=1, max_length=100)


class AssessmentSubmitRequest(BaseModel):
    answers: dict = Field(..., description="Mapping of question ID to selected answer")


class AssessmentResultResponse(BaseModel):
    score: int
    passed: bool
    passing_score: int
    attempt_count: int
    # Passing the quiz doesn't by itself finish a course that still has
    # unread lessons, so the client can't infer completion from `passed`.
    course_completed: bool = False
    # Best score so far — what's stored on the enrolment. `score` is this attempt.
    best_score: Optional[int] = None
