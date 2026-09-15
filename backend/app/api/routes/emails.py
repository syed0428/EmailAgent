import logging
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import get_db
from app.models.email import Email
from app.models.email_analysis import EmailAnalysis
from app.services.email_processor import EmailProcessor
from app.services.search_service import SearchService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/emails", tags=["Emails"])


# ── List emails ───────────────────────────────────────────────────────────────
@router.get("/")
def list_emails(
    account_id: Optional[str] = None,
    category: Optional[str] = None,
    importance: Optional[str] = None,
    cleanup_recommended: Optional[bool] = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    from app.models.email_account import EmailAccount

    target_account_id = account_id
    if not target_account_id:
        active_account = (
            db.query(EmailAccount)
            .filter(
                EmailAccount.is_active == True,
                EmailAccount.refresh_token.isnot(None),
                EmailAccount.refresh_token != "",
            )
            .order_by(EmailAccount.created_at.desc())
            .first()
        )
        if active_account:
            target_account_id = str(active_account.id)
        else:
            return {
                "total": 0,
                "skip": skip,
                "limit": limit,
                "emails": [],
            }

    q = db.query(Email).filter(Email.account_id == target_account_id)

    if category or importance or cleanup_recommended is not None:
        q = q.join(EmailAnalysis, isouter=True)
        if category:
            q = q.filter(EmailAnalysis.category == category)
        if importance:
            q = q.filter(EmailAnalysis.importance == importance)
        if cleanup_recommended is not None:
            q = q.filter(EmailAnalysis.cleanup_recommended == cleanup_recommended)

    q = q.order_by(Email.received_at.desc())
    total = q.count()
    emails = q.offset(skip).limit(limit).all()

    return {
        "total": total,
        "skip": skip,
        "limit": limit,
        "emails": [_email_dict(e) for e in emails],
    }


# ── Get single email ──────────────────────────────────────────────────────────
@router.get("/{email_id}")
def get_email(email_id: UUID, db: Session = Depends(get_db)):
    email = db.query(Email).filter(Email.id == email_id).first()
    if not email:
        raise HTTPException(status_code=404, detail="Email not found")
    d = _email_dict(email)
    if email.analysis:
        d["analysis"] = _analysis_dict(email.analysis)
    return d


# ── Ingest a mock/test email (used during dev before Gmail is wired) ──────────
@router.post("/ingest")
def ingest_email(payload: dict, db: Session = Depends(get_db)):
    """
    Accepts a raw email dict and runs the full processing pipeline.
    Used for testing without Gmail connectivity.

    Required fields: account_id, gmail_id, subject, body_text
    """
    account_id = payload.get("account_id")
    if not account_id:
        raise HTTPException(status_code=422, detail="account_id is required")

    processor = EmailProcessor(db)
    result = processor.process_email(account_id, payload)
    return {"status": "processed", **result}


# ── Semantic search ───────────────────────────────────────────────────────────
@router.get("/search/semantic")
def semantic_search(
    q: str = Query(..., min_length=2),
    account_id: Optional[str] = None,
    limit: int = Query(10, le=50),
    min_similarity: float = Query(0.3, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
):
    svc = SearchService(db)
    results = svc.semantic_search(q, account_id=account_id, limit=limit, min_similarity=min_similarity)
    return {"query": q, "results": results}


# ── Cleanup suggestions ───────────────────────────────────────────────────────
@router.get("/cleanup/suggestions")
def get_cleanup_suggestions(
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    q = (
        db.query(Email, EmailAnalysis)
        .join(EmailAnalysis, Email.id == EmailAnalysis.email_id)
        .filter(EmailAnalysis.cleanup_recommended == True)
    )
    if account_id:
        q = q.filter(Email.account_id == account_id)

    rows = q.all()
    by_category: dict = {}
    items = []
    for email, analysis in rows:
        cat = analysis.category or "other"
        by_category[cat] = by_category.get(cat, 0) + 1
        items.append({
            "email_id": str(email.id),
            "gmail_id": email.gmail_id,
            "subject": email.subject,
            "sender": email.sender,
            "received_at": email.received_at.isoformat() if email.received_at else None,
            "category": cat,
            "cleanup_reason": analysis.cleanup_reason,
        })
    return {
        "total": len(items),
        "by_category": by_category,
        "items": items,
    }


# ── Mark cleanup as approved by user ─────────────────────────────────────────
@router.post("/cleanup/approve")
def approve_cleanup(payload: dict, db: Session = Depends(get_db)):
    """
    User explicitly approves cleanup for a list of email IDs.
    Does NOT delete anything — marks cleanup_approved_by_user = True.
    Actual deletion is a separate, confirmed action.
    """
    email_ids = payload.get("email_ids", [])
    if not email_ids:
        raise HTTPException(status_code=422, detail="email_ids list is required")

    updated = (
        db.query(EmailAnalysis)
        .filter(EmailAnalysis.email_id.in_(email_ids))
        .update({"cleanup_approved_by_user": True}, synchronize_session=False)
    )
    db.commit()
    return {"approved": updated}


# ── Sync emails from live Gmail API ───────────────────────────────────────────
@router.post("/sync")
def sync_gmail_emails(
    max_results: int = Query(15, ge=1, le=50),
    db: Session = Depends(get_db),
):
    """
    Fetch recent emails directly from connected Gmail account.
    Runs full processing pipeline (Store ➔ Embed ➔ Ollama Analyze).
    Duplicate emails are automatically skipped using Gmail message ID.
    """
    from app.models.email_account import EmailAccount
    from app.services.gmail_service import get_gmail_service

    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.is_active == True,
            EmailAccount.refresh_token.isnot(None),
            EmailAccount.refresh_token != "",
        )
        .order_by(EmailAccount.created_at.desc())
        .first()
    )
    if not account:
        raise HTTPException(
            status_code=400,
            detail="No connected Gmail account found. Please connect Gmail from the Dashboard first."
        )

    gmail_svc = get_gmail_service()
    try:
        token = gmail_svc.get_valid_access_token(db, account)
    except Exception as exc:
        raise HTTPException(status_code=401, detail=f"Gmail authentication error: {exc}")

    try:
        inbox_data = gmail_svc.fetch_inbox_messages(db, account, max_results=max_results)
        messages_ref = inbox_data.get("messages", [])
        if not messages_ref:
            return {
                "status": "success",
                "synced_count": 0,
                "skipped_count": 0,
                "total_fetched": 0,
                "message": "No messages found in Gmail inbox."
            }

        processor = EmailProcessor(db)
        synced_count = 0
        skipped_count = 0

        for msg_ref in messages_ref:
            msg_id = msg_ref.get("id")
            if not msg_id:
                continue

            # Duplicate check using Gmail ID
            existing = db.query(Email).filter(Email.gmail_id == msg_id).first()
            if existing:
                skipped_count += 1
                continue

            # Fetch detail and parse base64 MIME
            raw = gmail_svc.fetch_message_detail(token, msg_id)
            if not raw or not raw.get("gmail_id"):
                continue

            raw["account_id"] = str(account.id)
            processor.process_email(str(account.id), raw)
            synced_count += 1

        account.last_synced_at = datetime.utcnow()
        db.commit()

        return {
            "status": "success",
            "gmail_address": account.gmail_address,
            "synced_count": synced_count,
            "skipped_count": skipped_count,
            "total_fetched": len(messages_ref),
        }
    except Exception as exc:
        logger.error(f"Gmail sync failed: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to sync Gmail inbox: {exc}")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _email_dict(e: Email) -> dict:
    return {
        "id": str(e.id),
        "gmail_id": e.gmail_id,
        "account_id": str(e.account_id),
        "subject": e.subject,
        "sender": e.sender,
        "snippet": e.snippet,
        "received_at": e.received_at.isoformat() if e.received_at else None,
        "is_read": e.is_read,
        "has_attachments": e.has_attachments,
        "labels": e.labels,
    }


def _analysis_dict(a: EmailAnalysis) -> dict:
    return {
        "category": a.category,
        "importance": a.importance,
        "importance_score": a.importance_score,
        "sentiment": a.sentiment,
        "summary": a.summary,
        "cleanup_recommended": a.cleanup_recommended,
        "cleanup_reason": a.cleanup_reason,
        "is_job_related": a.is_job_related,
        "company_name": a.company_name,
        "job_title": a.job_title,
        "job_status": a.job_status,
    }
