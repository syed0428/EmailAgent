"""
Google OAuth 2.0 Auth Router
─────────────────────────────
Endpoints:
  GET /api/auth/google/login        -> Generates auth URL & CSRF state
  GET /api/auth/google/callback     -> Handles OAuth callback, exchanges code, saves encrypted tokens
  GET /api/auth/google/status       -> Checks current Gmail connection status
"""

import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import generate_oauth_state, verify_oauth_state
from app.db.database import get_db
from app.models.email_account import EmailAccount
from app.services.gmail_service import get_gmail_service

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter(prefix="/auth/google", tags=["Google OAuth"])


@router.get("/login")
def google_login():
    """
    Generate Google OAuth 2.0 login URL with signed state token.
    """
    gmail_svc = get_gmail_service()
    state = generate_oauth_state()
    try:
        auth_url = gmail_svc.get_authorization_url(state=state)
        return {"auth_url": auth_url, "state": state}
    except Exception as exc:
        logger.error(f"Google login generation error: {exc}")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/callback")
def google_callback(
    code: Optional[str] = Query(None),
    state: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """
    Handle Google OAuth 2.0 callback from Google consent screen.
    Validates state CSRF signature, exchanges code for tokens, enriches identity, and persists encrypted tokens.
    """
    if error:
        logger.warning(f"Google OAuth error received: {error}")
        return RedirectResponse(url=f"{settings.frontend_url}/?oauth_error={error}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing required code or state parameter")

    # Cryptographic state verification for CSRF protection
    if not verify_oauth_state(state):
        logger.error("OAuth callback failed state verification (CSRF signature mismatch or expired)")
        return RedirectResponse(url=f"{settings.frontend_url}/?oauth_error=invalid_state")

    gmail_svc = get_gmail_service()
    try:
        # Exchange authorization code for tokens
        tokens = gmail_svc.exchange_code_for_tokens(code)
        access_token = tokens.get("access_token")

        # Enrich user identity via Google userinfo endpoint
        user_info = gmail_svc.get_user_info(access_token)

        # Save/update EmailAccount with encrypted tokens
        account = gmail_svc.save_or_update_account(
            db=db,
            user_id_raw="demo-user-001",
            user_info=user_info,
            token_payload=tokens,
        )

        logger.info(f"Successfully connected Gmail account: {account.gmail_address}")
        return RedirectResponse(
            url=f"{settings.frontend_url}/?gmail_connected=true&email={account.gmail_address}"
        )
    except Exception as exc:
        logger.error(f"Failed to process Google callback: {exc}")
        return RedirectResponse(url=f"{settings.frontend_url}/?oauth_error=token_exchange_failed")


@router.get("/status")
def get_connection_status(db: Session = Depends(get_db)):
    """
    Return current status of active Gmail OAuth accounts.
    """
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
        return {
            "connected": False,
            "gmail_address": None,
            "token_expiry": None,
            "is_active": False,
        }

    return {
        "connected": True,
        "gmail_address": account.gmail_address,
        "token_expiry": account.token_expiry.isoformat() if account.token_expiry else None,
        "is_active": account.is_active,
        "account_id": str(account.id),
    }
