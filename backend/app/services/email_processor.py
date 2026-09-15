"""
Email Processing Service
────────────────────────
Stores raw email data, generates embeddings, and runs AI analysis.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.models.email_embedding import EmailEmbedding
from app.services.embedding_service import get_embedding_service
from app.services.ai_service import get_ai_service
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmailProcessor:
    def __init__(self, db: Session):
        self.db = db
        self.embedder = get_embedding_service()
        self.ai = get_ai_service()

    def _get_or_create_account(self, account_id_raw: str):
        """Ensures a valid EmailAccount exists in the DB, returning its UUID."""
        from app.models.user import User
        from app.models.email_account import EmailAccount

        # Try parsing as UUID; if invalid string (e.g. 'demo-account-001'), use a fixed deterministic UUID
        try:
            account_uuid = uuid.UUID(account_id_raw)
        except ValueError:
            account_uuid = uuid.UUID("00000000-0000-0000-0000-000000000002")

        existing_acc = self.db.query(EmailAccount).filter(EmailAccount.id == account_uuid).first()
        if existing_acc:
            return existing_acc.id

        # Ensure demo user exists
        demo_user_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
        user = self.db.query(User).filter(User.id == demo_user_id).first()
        if not user:
            user = User(
                id=demo_user_id,
                email="demo@example.com",
                name="Demo User",
            )
            self.db.add(user)
            self.db.commit()

        # Create account
        acc = EmailAccount(
            id=account_uuid,
            user_id=user.id,
            gmail_address="demo@example.com",
            is_active=True,
        )
        self.db.add(acc)
        self.db.commit()
        return acc.id

    def store_email(self, account_id: str, raw: dict) -> Email:
        """Upsert an email from a Gmail API message dict."""
        account_uuid = self._get_or_create_account(account_id)
        gmail_id = raw.get("gmail_id") or raw.get("id")
        existing = self.db.query(Email).filter(Email.gmail_id == gmail_id).first()
        if existing:
            return existing

        email = Email(
            account_id=account_uuid,
            gmail_id=gmail_id,
            thread_id=raw.get("thread_id"),
            subject=raw.get("subject"),
            sender=raw.get("sender"),
            recipients=raw.get("recipients"),
            body_text=raw.get("body_text"),
            body_html=raw.get("body_html"),
            snippet=raw.get("snippet"),
            labels=raw.get("labels"),
            received_at=raw.get("received_at"),
            is_read=raw.get("is_read", False),
            has_attachments=raw.get("has_attachments", False),
            size_bytes=raw.get("size_bytes", 0),
        )
        self.db.add(email)
        self.db.commit()
        self.db.refresh(email)
        logger.info(f"Stored email {gmail_id}")
        return email

    def generate_and_store_embedding(self, email: Email) -> Optional[EmailEmbedding]:
        """Generate embedding for an email and store it in pgvector."""
        # Build content to embed: subject + snippet/body
        content_parts = []
        if email.subject:
            content_parts.append(f"Subject: {email.subject}")
        if email.sender:
            content_parts.append(f"From: {email.sender}")
        body = email.body_text or email.snippet or ""
        if body:
            content_parts.append(body[:1000])   # cap at 1000 chars for single-embedding

        content = "\n".join(content_parts).strip()
        if not content:
            logger.warning(f"Email {email.gmail_id} has no embeddable content – skipping")
            return None

        # Check if embedding already exists
        existing = self.db.query(EmailEmbedding).filter(
            EmailEmbedding.email_id == email.id,
            EmailEmbedding.chunk_id == 0,
        ).first()
        if existing:
            return existing

        vector = self.embedder.embed(content)

        emb = EmailEmbedding(
            email_id=email.id,
            chunk_id=0,
            content=content,
            embedding=vector,
            embedding_model=self.embedder.model_name,
        )
        self.db.add(emb)
        self.db.commit()
        self.db.refresh(emb)
        logger.info(f"Embedded email {email.gmail_id} ({len(vector)}d)")
        return emb

    def analyze_email(self, email: Email) -> EmailAnalysis:
        """Run AI analysis on an email and store the result."""
        existing = self.db.query(EmailAnalysis).filter(EmailAnalysis.email_id == email.id).first()
        if existing:
            return existing

        result = self.ai.analyze_email(
            subject=email.subject or "",
            body=email.body_text or email.snippet or "",
            sender=email.sender or "",
        )

        analysis = EmailAnalysis(
            email_id=email.id,
            category=result.get("category"),
            importance=result.get("importance"),
            importance_score=result.get("importance_score"),
            sentiment=result.get("sentiment"),
            summary=result.get("summary"),
            cleanup_recommended=result.get("cleanup_recommended", False),
            cleanup_reason=result.get("cleanup_reason"),
            is_job_related=result.get("is_job_related", False),
            company_name=result.get("company_name"),
            job_title=result.get("job_title"),
            job_status=result.get("job_status"),
            model_used=settings.llm_model,
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def process_email(self, account_id: str, raw: dict) -> dict:
        """Full pipeline: store → embed → analyze. Returns a summary dict."""
        email = self.store_email(account_id, raw)
        embedding = self.generate_and_store_embedding(email)
        analysis = self.analyze_email(email)
        return {
            "email_id": str(email.id),
            "gmail_id": email.gmail_id,
            "embedded": embedding is not None,
            "category": analysis.category,
            "importance": analysis.importance,
            "cleanup_recommended": analysis.cleanup_recommended,
        }
