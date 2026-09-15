import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Text, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector
from app.db.database import Base
from app.core.config import get_settings

settings = get_settings()


class EmailEmbedding(Base):
    __tablename__ = "email_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_id = Column(UUID(as_uuid=True), ForeignKey("emails.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_id = Column(Integer, default=0)          # 0 = full email, >0 = chunk index
    content = Column(Text, nullable=False)          # text that was embedded
    embedding = Column(Vector(settings.embedding_dimensions), nullable=False)
    embedding_model = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    email = relationship("Email", back_populates="embeddings")
