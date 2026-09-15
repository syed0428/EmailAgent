import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Float, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.db.database import Base


class EmailAnalysis(Base):
    __tablename__ = "email_analysis"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, unique=True)

    # AI classification
    category = Column(String(100), nullable=True)          # e.g. job, newsletter, promotional, personal
    importance = Column(String(20), nullable=True)         # high / medium / low
    importance_score = Column(Float, nullable=True)        # 0.0 – 1.0
    sentiment = Column(String(20), nullable=True)          # positive / neutral / negative
    summary = Column(Text, nullable=True)

    # Cleanup
    cleanup_recommended = Column(Boolean, default=False)
    cleanup_reason = Column(Text, nullable=True)
    cleanup_approved_by_user = Column(Boolean, nullable=True)

    # Job-specific
    is_job_related = Column(Boolean, default=False)
    company_name = Column(String(255), nullable=True)
    job_title = Column(String(255), nullable=True)
    job_status = Column(String(100), nullable=True)        # applied / interview / offer / rejected

    model_used = Column(String(100), nullable=True)
    analyzed_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)

    email = relationship("Email", back_populates="analysis")
