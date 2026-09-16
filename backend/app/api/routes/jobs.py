import os
import re
import time
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.job_application import JobApplication, GeneratedEmail, Resume
from app.services.ai_service import get_ai_service
from app.services.resume_service import get_resume_service, STORAGE_DIR

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["Job Applications"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────
class MatchJobRequest(BaseModel):
    user_id: str
    resume_id: str
    job_description: str
    company_name: Optional[str] = ""
    job_title: Optional[str] = ""
    user_profile: Optional[str] = ""


class OptimizeResumeRequest(BaseModel):
    job_application_id: str
    approved_suggestions: List[Dict[str, Any]]


class GenerateEmailRequest(BaseModel):
    user_id: str
    job_description: str
    recipient_email: str
    company_name: Optional[str] = ""
    job_title: Optional[str] = ""
    additional_instructions: Optional[str] = ""
    user_profile: Optional[str] = ""
    job_application_id: Optional[str] = None


class UpdateApplicationStatus(BaseModel):
    status: str  # draft / sent / interview / offer / rejected


def _get_or_create_user(user_id_raw: str, db: Session):
    import uuid
    from app.models.user import User
    try:
        u_id = uuid.UUID(user_id_raw)
    except Exception:
        u_id = uuid.UUID("00000000-0000-0000-0000-000000000001")

    user = db.query(User).filter(User.id == u_id).first()
    if not user:
        user = User(
            id=u_id,
            email="demo@example.com",
            name="Demo User",
        )
        db.add(user)
        db.commit()
    return u_id


# ── 1. Upload Resume ─────────────────────────────────────────────────────────
@router.post("/resume/upload")
def upload_resume(
    user_id: str = Form("00000000-0000-0000-0000-000000000001"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """
    Securely upload, validate, and parse PDF or DOCX resume.
    Stores extracted plain text and structured JSON in database.
    """
    user_uuid = _get_or_create_user(user_id, db)
    resume_svc = get_resume_service()
    ai_svc = get_ai_service()

    # File validation & secure private saving
    filename, file_path, file_type = resume_svc.validate_and_save_file(file, str(user_uuid))

    # Text extraction
    raw_text = resume_svc.extract_text(file_path, file_type)

    # Structured entity extraction via LLM with deterministic hybrid fallback guarantee
    llm_structured_data = ai_svc.parse_resume_structured(raw_text)
    structured_data = resume_svc.parse_resume_hybrid(raw_text, llm_structured_data)

    resume = Resume(
        user_id=user_uuid,
        filename=filename,
        file_path=file_path,
        file_type=file_type,
        raw_text=raw_text,
        structured_data=structured_data,
    )
    db.add(resume)
    db.commit()
    db.refresh(resume)

    return {
        "resume_id": str(resume.id),
        "filename": resume.filename,
        "file_type": resume.file_type,
        "raw_text_snippet": raw_text[:300],
        "structured_data": structured_data,
    }


# ── 2. Delete Resume ─────────────────────────────────────────────────────────
@router.delete("/resume/{resume_id}")
def delete_resume(resume_id: UUID, db: Session = Depends(get_db)):
    """Delete uploaded resume file from storage and database."""
    resume = db.query(Resume).filter(Resume.id == resume_id).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")

    resume_svc = get_resume_service()
    resume_svc.delete_resume_file(resume.file_path)

    db.delete(resume)
    db.commit()
    return {"message": "Resume deleted successfully", "resume_id": str(resume_id)}


# ── 3. Match Resume vs Job Description ────────────────────────────────────────
@router.post("/match")
def match_resume_and_job(req: MatchJobRequest, db: Session = Depends(get_db)):
    """
    Compares candidate's resume against Job Description.
    Returns explainable match score, factor breakdown, and ATS suggestions.
    """
    user_uuid = _get_or_create_user(req.user_id, db)
    import uuid
    try:
        res_uuid = uuid.UUID(req.resume_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid resume_id format")

    resume = db.query(Resume).filter(Resume.id == res_uuid).first()
    if not resume:
        raise HTTPException(status_code=404, detail="Resume record not found")

    ai_svc = get_ai_service()

    # 1. Match analysis & explainable scoring
    match_result = ai_svc.analyze_job_match(
        resume_data=resume.structured_data or {},
        raw_resume_text=resume.raw_text,
        job_description=req.job_description,
        job_title=req.job_title,
        company_name=req.company_name,
    )

    # 2. Generate ATS Suggestions (Anti-Fabrication Enforced)
    ats_suggestions = ai_svc.generate_ats_suggestions(
        resume_data=resume.structured_data or {},
        raw_resume_text=resume.raw_text,
        user_profile=req.user_profile or "",
        job_description=req.job_description,
    )

    # 3. Create or update JobApplication record
    app = JobApplication(
        user_id=user_uuid,
        resume_id=resume.id,
        company_name=req.company_name,
        job_title=req.job_title,
        job_description=req.job_description,
        match_score=match_result.get("overall_score"),
        score_breakdown=match_result.get("score_breakdown"),
        match_analysis=match_result.get("match_analysis"),
        ats_suggestions=ats_suggestions,
        status="draft",
    )
    db.add(app)
    db.commit()
    db.refresh(app)

    return {
        "job_application_id": str(app.id),
        "resume_id": str(resume.id),
        "overall_score": app.match_score,
        "score_breakdown": app.score_breakdown,
        "match_analysis": app.match_analysis,
        "ats_suggestions": app.ats_suggestions,
    }


# ── 4. Optimize Resume ────────────────────────────────────────────────────────
@router.post("/optimize-resume")
def optimize_resume(req: OptimizeResumeRequest, db: Session = Depends(get_db)):
    """
    Applies user-approved ATS suggestions to the structured resume data, generates a new
    verified ATS-compliant PDF document, runs programmatic text verification & anti-fabrication
    safeguards, and associates the newly generated file with the JobApplication.
    """
    import os
    import re
    import uuid
    from datetime import datetime
    from app.services.resume_service import STORAGE_DIR

    try:
        app_uuid = uuid.UUID(req.job_application_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid job_application_id")

    app = db.query(JobApplication).filter(JobApplication.id == app_uuid).first()
    if not app or not app.resume:
        raise HTTPException(status_code=404, detail="Job application or associated resume not found")

    resume_svc = get_resume_service()
    ai_svc = get_ai_service()
    raw_resume = app.resume.raw_text

    # 1. Obtain base structured resume data with zero-data-loss guarantee
    base_structured_data = app.resume.structured_data
    is_incomplete = (
        not base_structured_data
        or not base_structured_data.get("education")
        or not base_structured_data.get("certifications")
        or not base_structured_data.get("career_objective")
        or len(base_structured_data.get("projects") or []) < 2
    )
    if is_incomplete:
        logger.info(f"Re-extracting complete structured resume for app {app.id} using hybrid parser to ensure zero data loss")
        base_structured_data = resume_svc.parse_resume_hybrid(raw_resume, base_structured_data)
        app.resume.structured_data = base_structured_data
        db.commit()

    # 2. Apply ONLY user-approved targeted modifications
    modified_data, applied_suggestions, modified_raw = resume_svc.apply_approved_suggestions(
        structured_data=base_structured_data,
        approved_suggestions=req.approved_suggestions,
        raw_text=raw_resume,
    )

    # 3. Whole-Resume Anti-Fabrication Safeguard Check
    approved_texts = [f"- {sug.get('suggested')}" for sug in req.approved_suggestions if sug.get("approved_by_user")]
    preview_text = f"# OPTIMIZED RESUME FOR {app.job_title or 'ROLE'} AT {app.company_name or 'COMPANY'}\n\n{raw_resume}\n\n"
    if approved_texts:
        preview_text += "## Approved ATS Improvements\n" + "\n".join(approved_texts)

    is_valid, violations = resume_svc.validate_anti_fabrication(
        source_resume_text=raw_resume,
        user_profile="",
        target_text=preview_text,
        approved_suggestions=req.approved_suggestions,
    )

    if not is_valid:
        logger.warning(f"Anti-fabrication violations detected: {violations}")
        raise HTTPException(
            status_code=422,
            detail=f"Anti-fabrication safeguard violation: {'; '.join(violations)}",
        )

    # 4. Determine deterministic output path and file format
    # Filename MUST be based on the original uploaded resume filename: {original_stem}_ATS_Optimized.pdf
    file_type = "pdf"
    original_stem = Path(app.resume.filename).stem if app.resume and app.resume.filename else "Resume"
    output_filename = f"{original_stem}_ATS_Optimized.pdf"
    output_path = (STORAGE_DIR / f"{original_stem}_ATS_Optimized_{app.id}.pdf").resolve()

    # Clean up any stale previous optimized resume for this job application
    if app.optimized_resume_path:
        resume_svc.delete_resume_file(app.optimized_resume_path)

    # 5. Render document from modified structured data
    try:
        resume_svc.render_resume_pdf(modified_data, str(output_path))
    except Exception as exc:
        logger.error(f"Failed to render optimized resume PDF: {exc}")
        raise HTTPException(status_code=500, detail=f"Failed to generate optimized resume document: {exc}")

    # 6. Anti-Data-Loss Validation Step (Zero Original Sections Dropped Guarantee)
    is_complete, missing_entities = resume_svc.validate_no_data_loss(
        source_raw_text=raw_resume,
        structured_data=modified_data,
        generated_pdf_path=str(output_path),
        approved_suggestions=req.approved_suggestions,
    )
    if not is_complete:
        resume_svc.delete_resume_file(str(output_path))
        logger.error(f"Anti-data-loss validation failed for app {app.id}: {missing_entities}")
        raise HTTPException(
            status_code=422,
            detail=f"Anti-data-loss validation failed: The following original sections/entities were missing in the generated PDF: {'; '.join(missing_entities)}",
        )

    # 7. Programmatic Verification Step: Assert approved ATS changes are actually present
    has_approved = any(s.get("approved_by_user") for s in req.approved_suggestions)
    if has_approved:
        is_verified, verify_err = resume_svc.verify_optimized_document(
            file_path=str(output_path),
            file_type=file_type,
            approved_suggestions=req.approved_suggestions,
        )
        if not is_verified:
            # Delete invalid document immediately
            resume_svc.delete_resume_file(str(output_path))
            logger.error(f"Optimization verification failed: {verify_err}")
            raise HTTPException(status_code=422, detail=verify_err)

    # 8. Extract the verified text for frontend preview
    try:
        verified_extracted_text = resume_svc.extract_text(str(output_path), file_type)
    except Exception:
        verified_extracted_text = preview_text

    # 9. Save verified path and suggestions in database
    app.optimized_resume_path = str(output_path)
    app.ats_suggestions = req.approved_suggestions
    db.commit()

    return {
        "job_application_id": str(app.id),
        "optimized_resume_path": str(output_path),
        "optimized_resume_filename": output_filename,
        "optimized_resume_text": verified_extracted_text,
        "anti_fabrication_valid": is_valid,
        "anti_fabrication_violations": violations,
        "applied_count": len(applied_suggestions),
    }


# ── Resume Download Endpoint ──────────────────────────────────────────────────
@router.get("/{application_id}/resume/download")
def download_application_resume(application_id: str, db: Session = Depends(get_db)):
    """
    Downloads or previews the resume file for a job application.
    Serves the verified optimized resume if available, otherwise the original uploaded resume.
    """
    import os
    import re
    from fastapi.responses import FileResponse
    from app.services.resume_service import STORAGE_DIR

    try:
        app_uuid = UUID(application_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid application ID format.")

    app = db.query(JobApplication).filter(JobApplication.id == app_uuid).first()
    if not app:
        raise HTTPException(status_code=404, detail="Job application not found.")

    file_path = None
    if app.optimized_resume_path and os.path.exists(app.optimized_resume_path):
        file_path = app.optimized_resume_path
    elif app.resume and os.path.exists(app.resume.file_path):
        file_path = app.resume.file_path

    if not file_path:
        raise HTTPException(status_code=404, detail="Resume file not found.")

    real_storage = os.path.realpath(STORAGE_DIR)
    real_file = os.path.realpath(file_path)
    if not real_file.startswith(real_storage):
        raise HTTPException(status_code=403, detail="Unauthorized resume file path access.")

    ext = os.path.splitext(file_path)[1].lower()
    if app.optimized_resume_path and os.path.exists(app.optimized_resume_path) and file_path == app.optimized_resume_path:
        original_stem = Path(app.resume.filename).stem if app.resume and app.resume.filename else "Resume"
        download_filename = f"{original_stem}_ATS_Optimized.pdf"
    elif app.resume and app.resume.filename:
        download_filename = app.resume.filename
    else:
        clean_company = re.sub(r'[^a-zA-Z0-9_-]', '_', (app.company_name or 'Application').strip())
        download_filename = f"Resume_{clean_company}{ext}"
    media_type = "application/pdf" if ext == ".pdf" else "application/octet-stream"

    return FileResponse(
        file_path,
        media_type=media_type,
        filename=download_filename,
        headers={"Content-Disposition": f"inline; filename=\"{download_filename}\""}
    )



# ── 5. Generate Application Email ─────────────────────────────────────────────
@router.post("/generate-email")
def generate_application_email(req: GenerateEmailRequest, db: Session = Depends(get_db)):
    """
    Uses Ollama LLM to draft a recruiter cover email referencing match strengths.
    Does NOT send anything — Phase 8 prepares draft & attachment association.
    """
    user_uuid = _get_or_create_user(req.user_id, db)

    ai = get_ai_service()
    result = ai.generate_application_email(
        job_description=req.job_description,
        recipient_email=req.recipient_email,
        company_name=req.company_name,
        job_title=req.job_title,
        additional_instructions=req.additional_instructions,
        user_profile=req.user_profile,
    )

    # Persist or update job application record
    import uuid
    app = None
    if req.job_application_id:
        try:
            app = db.query(JobApplication).filter(JobApplication.id == uuid.UUID(req.job_application_id)).first()
        except Exception:
            pass

    if not app:
        app = JobApplication(
            user_id=user_uuid,
            company_name=req.company_name,
            job_title=req.job_title,
            job_description=req.job_description,
            recipient_email=req.recipient_email,
            status="draft",
        )
        db.add(app)
        db.flush()

    from app.core.config import get_settings
    gen = GeneratedEmail(
        user_id=user_uuid,
        job_application_id=app.id,
        subject=result.get("subject"),
        body=result.get("body"),
        recipient=req.recipient_email,
        model_used=get_settings().llm_model,
        was_sent=False,
    )
    db.add(gen)
    db.commit()
    db.refresh(app)
    db.refresh(gen)

    return {
        "job_application_id": str(app.id),
        "generated_email_id": str(gen.id),
        "subject": gen.subject,
        "body": gen.body,
        "recipient": gen.recipient,
        "status": "preview",
        "resume_attached": True if app.resume_id else False,
        "note": "Phase 8 draft prepared with resume attachment. Ready for Phase 9 Gmail send.",
    }


# ── 6. List Job Applications ──────────────────────────────────────────────────
@router.get("/")
def list_applications(user_id: str, db: Session = Depends(get_db)):
    user_uuid = _get_or_create_user(user_id, db)
    apps = db.query(JobApplication).filter(JobApplication.user_id == user_uuid).order_by(JobApplication.created_at.desc()).all()
    return [
        {
            "id": str(a.id),
            "company_name": a.company_name,
            "job_title": a.job_title,
            "recipient_email": a.recipient_email,
            "match_score": a.match_score,
            "status": a.status,
            "applied_at": a.applied_at.isoformat() if a.applied_at else None,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in apps
    ]


# ── 7. Update Application Status ──────────────────────────────────────────────
@router.patch("/{application_id}/status")
def update_status(
    application_id: UUID,
    payload: UpdateApplicationStatus,
    db: Session = Depends(get_db),
):
    app = db.query(JobApplication).filter(JobApplication.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")
    app.status = payload.status
    db.commit()
    return {"status": app.status}


# ── 8. Send Application Email via Gmail API (Phase 9) ─────────────────────────
class SendApplicationRequest(BaseModel):
    user_id: str
    recipient_email: Optional[str] = None
    subject: Optional[str] = None
    body: Optional[str] = None


@router.post("/{application_id}/send")
def send_application_email(
    application_id: str,
    payload: Optional[SendApplicationRequest] = None,
    db: Session = Depends(get_db),
):
    """
    Phase 9: Sends recruiter email with attached ATS resume via Gmail API.
    Validates connected OAuth Gmail account, double-send protection, MIME construction,
    and updates DB status upon confirmed Gmail 200 OK.
    """
    import os
    from datetime import datetime
    from app.services.gmail_service import get_gmail_service
    from app.models.email_account import EmailAccount

    try:
        app_uuid = UUID(application_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid application ID format.")

    app = db.query(JobApplication).filter(JobApplication.id == app_uuid).first()
    if not app:
        raise HTTPException(status_code=404, detail="Job application not found.")

    user_id_str = payload.user_id if payload else str(app.user_id)
    try:
        user_uuid = UUID(user_id_str)
    except Exception:
        user_uuid = app.user_id

    # 1. Double-send Protection
    if app.status == "sent":
        raise HTTPException(status_code=400, detail="Application has already been sent.")

    # 2. Check for latest GeneratedEmail draft
    gen = (
        db.query(GeneratedEmail)
        .filter(GeneratedEmail.job_application_id == app.id)
        .order_by(GeneratedEmail.created_at.desc())
        .first()
    )

    recipient = (payload.recipient_email if payload and payload.recipient_email else None) or (gen.recipient if gen else None) or app.recipient_email
    subject = (payload.subject if payload and payload.subject else None) or (gen.subject if gen else None) or f"Application for {app.job_title or 'Position'}"
    body = (payload.body if payload and payload.body else None) or (gen.body if gen else None)

    if not recipient:
        raise HTTPException(status_code=400, detail="Recipient email address is required.")
    if not body:
        raise HTTPException(status_code=400, detail="Email body is required.")

    # 3. Verify connected Gmail OAuth Account (Must be active with non-empty refresh_token)
    account = (
        db.query(EmailAccount)
        .filter(
            EmailAccount.user_id == user_uuid,
            EmailAccount.is_active == True,
            EmailAccount.refresh_token.isnot(None),
            EmailAccount.refresh_token != "",
        )
        .order_by(EmailAccount.created_at.desc())
        .first()
    )
    if not account:
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
            detail="No active connected Gmail account found. Please connect your Gmail account via OAuth first.",
        )

    logger.info(f"[OAuth Diagnostic] Selected Gmail Account for send: ID={account.id}, Email={account.gmail_address}, UserID={account.user_id}")

    # 4. Verify Attachment & Path Ownership
    attachment_path = None
    attachment_filename = None

    # Priority 1: Use the verified optimized resume path for this application
    if app.optimized_resume_path and os.path.exists(app.optimized_resume_path):
        attachment_path = app.optimized_resume_path
        original_stem = Path(app.resume.filename).stem if app.resume and app.resume.filename else "Resume"
        attachment_filename = f"{original_stem}_ATS_Optimized.pdf"
    elif app.resume and os.path.exists(app.resume.file_path):
        # Fallback only if optimization was never generated
        attachment_path = app.resume.file_path
        attachment_filename = app.resume.filename

    if attachment_path:
        # Path ownership validation
        from app.services.resume_service import STORAGE_DIR
        real_storage = os.path.realpath(STORAGE_DIR)
        real_file = os.path.realpath(attachment_path)

        if not real_file.startswith(real_storage):
            raise HTTPException(status_code=403, detail="Unauthorized resume file path access.")
        if not os.path.exists(attachment_path):
            raise HTTPException(status_code=404, detail=f"Resume attachment file not found: {attachment_filename}")

    # 5. Pre-flight Token Validation (Requirement 8)
    gmail_svc = get_gmail_service()
    try:
        token = gmail_svc.get_valid_access_token(db, account)
    except Exception as exc:
        logger.error(f"[OAuth Diagnostic] Pre-flight token validation failed for account {account.gmail_address}: {exc}")
        raise HTTPException(
            status_code=401,
            detail=f"Gmail authentication error: {str(exc)}. Please re-authenticate your Gmail account.",
        )

    # 6. Execute Gmail API Send
    try:
        send_result = gmail_svc.send_mime_message(
            db=db,
            account=account,
            recipient=recipient,
            subject=subject,
            body_text=body,
            attachment_path=attachment_path,
            attachment_filename=attachment_filename,
        )
    except Exception as exc:
        logger.error(f"[OAuth Diagnostic] Gmail send failed for application {app.id}: {exc}")
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Gmail API transmission failed: {str(exc)}",
        )

    # 6. Database updates ONLY after confirmed successful send
    gmail_message_id = send_result.get("id")
    now = datetime.utcnow()

    app.status = "sent"
    app.applied_at = now
    app.recipient_email = recipient

    if not gen:
        gen = GeneratedEmail(
            user_id=user_uuid,
            job_application_id=app.id,
            subject=subject,
            body=body,
            recipient=recipient,
            was_sent=True,
            sent_at=now,
            gmail_message_id=gmail_message_id,
        )
        db.add(gen)
    else:
        gen.subject = subject
        gen.body = body
        gen.recipient = recipient
        gen.was_sent = True
        gen.sent_at = now
        gen.gmail_message_id = gmail_message_id

    db.commit()

    return {
        "status": "sent",
        "job_application_id": str(app.id),
        "recipient": recipient,
        "subject": subject,
        "gmail_account": account.gmail_address,
        "gmail_message_id": gmail_message_id,
        "sent_at": now.isoformat(),
        "attachment_name": attachment_filename,
    }
