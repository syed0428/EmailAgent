import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer, JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    filename = Column(String(255), nullable=False)
    file_path = Column(String(512), nullable=False)
    file_type = Column(String(50), nullable=False)  # pdf / docx
    raw_text = Column(Text, nullable=False)
    structured_data = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="resumes")
    job_applications = relationship("JobApplication", back_populates="resume")


class JobApplication(Base):
    __tablename__ = "job_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    resume_id = Column(UUID(as_uuid=True), ForeignKey("resumes.id", ondelete="SET NULL"), nullable=True)

    company_name = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=True)
    job_description = Column(Text, nullable=True)
    recipient_email = Column(String(255), nullable=True)
    status = Column(String(100), default="draft")          # draft / sent / interview / offer / rejected
    notes = Column(Text, nullable=True)

    # Phase 8 Match & ATS Analytics
    match_score = Column(Integer, nullable=True)
    score_breakdown = Column(JSON, nullable=True)
    match_analysis = Column(JSON, nullable=True)
    ats_suggestions = Column(JSON, nullable=True)
    optimized_resume_path = Column(String(512), nullable=True)

    applied_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="job_applications")
    resume = relationship("Resume", back_populates="job_applications")
    generated_emails = relationship("GeneratedEmail", back_populates="job_application", cascade="all, delete-orphan")


class GeneratedEmail(Base):
    __tablename__ = "generated_emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    job_application_id = Column(UUID(as_uuid=True), ForeignKey("job_applications.id", ondelete="SET NULL"), nullable=True)

    subject = Column(Text, nullable=True)
    body = Column(Text, nullable=False)
    recipient = Column(String(255), nullable=True)
    model_used = Column(String(100), nullable=True)
    was_sent = Column(Boolean, default=False)
    sent_at = Column(DateTime, nullable=True)
    gmail_message_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="generated_emails")
    job_application = relationship("JobApplication", back_populates="generated_emails")
