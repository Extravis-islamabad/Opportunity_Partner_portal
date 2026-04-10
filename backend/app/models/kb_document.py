from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from app.core.database import Base


class KBDocument(Base):
    __tablename__ = "kb_documents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(500), nullable=False, index=True)
    category = Column(String(100), nullable=False, index=True)
    description = Column(Text, nullable=True)
    file_name = Column(String(500), nullable=False)
    file_url = Column(String(1000), nullable=False)
    file_size = Column(Integer, nullable=True)
    content_type = Column(String(100), nullable=True)
    version = Column(Integer, default=1, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    previous_version_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=True)
    is_archived = Column(Integer, default=0, nullable=False)

    published_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    uploader = relationship("User", foreign_keys=[uploaded_by])
    previous_version = relationship("KBDocument", remote_side="KBDocument.id", foreign_keys=[previous_version_id])
    downloads = relationship("KBDownloadLog", back_populates="document")


class KBDownloadLog(Base):
    __tablename__ = "kb_download_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    document_id = Column(Integer, ForeignKey("kb_documents.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    downloaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    document = relationship("KBDocument", back_populates="downloads")
    user = relationship("User")
