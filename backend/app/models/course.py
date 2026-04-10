import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Enum, Text, JSON
from sqlalchemy.orm import relationship
from app.core.database import Base


class CourseStatus(str, enum.Enum):
    DRAFT = "draft"
    PUBLISHED = "published"


class Course(Base):
    __tablename__ = "courses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False, index=True)
    description = Column(Text, nullable=True)
    status = Column(Enum(CourseStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=CourseStatus.DRAFT)
    modules_json = Column(JSON, nullable=True, default=list)
    assessment_json = Column(JSON, nullable=True, default=list)
    passing_score = Column(Integer, default=70, nullable=False)
    duration_hours = Column(Integer, nullable=True)
    thumbnail_url = Column(String(1000), nullable=True)
    created_by = Column(Integer, nullable=False)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    enrollments = relationship("Enrollment", back_populates="course")
