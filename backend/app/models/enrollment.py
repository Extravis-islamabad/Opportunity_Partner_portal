import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Boolean, JSON, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base


class EnrollmentStatus(str, enum.Enum):
    ENROLLED = "enrolled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("user_id", "course_id", name="uq_enrollment_user_course"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    course_id = Column(Integer, ForeignKey("courses.id"), nullable=False, index=True)
    status = Column(Enum(EnrollmentStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=EnrollmentStatus.ENROLLED)
    progress_json = Column(JSON, default=dict, nullable=True)
    attempt_count = Column(Integer, default=0, nullable=False)
    score = Column(Integer, nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    certificate_requested = Column(Boolean, default=False, nullable=False)
    certificate_requested_at = Column(DateTime(timezone=True), nullable=True)
    certificate_url = Column(String(1000), nullable=True)
    certificate_issued_at = Column(DateTime(timezone=True), nullable=True)

    enrolled_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    user = relationship("User", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")
