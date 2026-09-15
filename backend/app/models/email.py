import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Boolean, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from app.db.database import Base


class Email(Base):
    __tablename__ = "emails"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id = Column(UUID(as_uuid=True), ForeignKey("email_accounts.id", ondelete="CASCADE"), nullable=False)
    gmail_id = Column(String(255), unique=True, nullable=False, index=True)
    thread_id = Column(String(255), nullable=True, index=True)

    subject = Column(Text, nullable=True)
    sender = Column(String(512), nullable=True)
    recipients = Column(Text, nullable=True)   # comma-separated
    body_text = Column(Text, nullable=True)
    body_html = Column(Text, nullable=True)
    snippet = Column(Text, nullable=True)
    labels = Column(Text, nullable=True)       # comma-separated Gmail labels

    received_at = Column(DateTime, nullable=True, index=True)
    is_read = Column(Boolean, default=False)
    has_attachments = Column(Boolean, default=False)
    size_bytes = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    account = relationship("EmailAccount", back_populates="emails")
    analysis = relationship("EmailAnalysis", back_populates="email", uselist=False, cascade="all, delete-orphan")
    embeddings = relationship("EmailEmbedding", back_populates="email", cascade="all, delete-orphan")
