"""
Gmail Service (OAuth & Token Management)
────────────────────────────────────────
Handles Google OAuth 2.0 URL generation, token exchange, Google UserInfo identity
enrichment, token refresh using encrypted Fernet storage, and token validation.
Derived from verified AIDATACOPILITE reference architecture.
"""

import time
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import encrypt_token, decrypt_token
from app.models.email_account import EmailAccount
from app.models.user import User

logger = logging.getLogger(__name__)
settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "openid",
]


class GmailService:
    def __init__(self):
        self.client_id = settings.google_client_id
        self.client_secret = settings.google_client_secret
        self.redirect_uri = settings.google_redirect_uri

    def get_authorization_url(self, state: str) -> str:
        """Construct the Google OAuth 2.0 consent screen URL."""
        if not self.client_id:
            raise ValueError("GOOGLE_CLIENT_ID is not configured in environment settings.")
        
        scope_str = " ".join(GMAIL_SCOPES)
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": scope_str,
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
        req = httpx.Request("GET", GOOGLE_AUTH_URL, params=params)
        return str(req.url)

    def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """Exchange authorization code for access and refresh tokens."""
        if not self.client_id or not self.client_secret:
            raise ValueError("Google OAuth Client ID and Client Secret must be configured.")

        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(GOOGLE_TOKEN_URL, data=data)
            if resp.status_code != 200:
                logger.error(f"Google token exchange failed: {resp.status_code} {resp.text}")
                raise ValueError(f"OAuth token exchange failed: {resp.text}")
            return resp.json()

    def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Fetch user identity (email, name, sub) from Google userinfo endpoint."""
        headers = {"Authorization": f"Bearer {access_token}"}
        with httpx.Client(timeout=15) as client:
            resp = client.get(GOOGLE_USERINFO_URL, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(f"Google userinfo endpoint returned {resp.status_code}: {resp.text}")
            return {}

    def save_or_update_account(
        self,
        db: Session,
        user_id_raw: str,
        user_info: Dict[str, Any],
        token_payload: Dict[str, Any],
    ) -> EmailAccount:
        """
        Persist or update EmailAccount with Fernet-encrypted access and refresh tokens.
        """
        import uuid
        try:
            user_uuid = uuid.UUID(user_id_raw)
        except Exception:
            user_uuid = uuid.UUID("00000000-0000-0000-0000-000000000001")

        # Ensure User exists
        user = db.query(User).filter(User.id == user_uuid).first()
        if not user:
            user = User(
                id=user_uuid,
                email=user_info.get("email", "demo@example.com"),
                name=user_info.get("name", "Demo User"),
            )
            db.add(user)
            db.commit()

        gmail_address = user_info.get("email") or "unknown@gmail.com"
        access_token_raw = token_payload.get("access_token")
        refresh_token_raw = token_payload.get("refresh_token")
        expires_in = token_payload.get("expires_in", 3600)
        token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)

        # Encrypt tokens for database storage
        access_encrypted = encrypt_token(access_token_raw)
        refresh_encrypted = encrypt_token(refresh_token_raw)

        acc = db.query(EmailAccount).filter(EmailAccount.gmail_address == gmail_address).first()
        if acc:
            acc.access_token = access_encrypted
            if refresh_encrypted:
                acc.refresh_token = refresh_encrypted
            acc.token_expiry = token_expiry
            acc.is_active = True
        else:
            acc = EmailAccount(
                user_id=user.id,
                gmail_address=gmail_address,
                access_token=access_encrypted,
                refresh_token=refresh_encrypted,
                token_expiry=token_expiry,
                is_active=True,
            )
            db.add(acc)

        db.commit()
        db.refresh(acc)
        logger.info(f"Successfully saved EmailAccount for {gmail_address}")
        return acc

    def refresh_access_token(self, db: Session, account: EmailAccount) -> str:
        """
        Use stored encrypted refresh token to fetch a new access token from Google.
        Updates DB with new encrypted access_token and expiry.
        """
        logger.info(f"[OAuth Diagnostic] Attempting token refresh for account ID: {account.id}, email: {account.gmail_address}")
        raw_refresh_token = decrypt_token(account.refresh_token)
        if not raw_refresh_token:
            logger.error(f"[OAuth Diagnostic] Refresh token missing or failed decryption for {account.gmail_address}")
            raise ValueError("No refresh token available for this account. Re-authentication required.")

        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": raw_refresh_token,
            "grant_type": "refresh_token",
        }
        with httpx.Client(timeout=15) as client:
            resp = client.post(GOOGLE_TOKEN_URL, data=data)
            if resp.status_code != 200:
                logger.error(f"[OAuth Diagnostic] Token refresh failed for {account.gmail_address}. HTTP {resp.status_code}: {resp.text}")
                account.is_active = False
                db.commit()
                raise ValueError("Refresh token expired or revoked. Re-authentication required.")

            token_data = resp.json()
            new_access_raw = token_data.get("access_token")
            expires_in = token_data.get("expires_in", 3600)
            token_expiry = datetime.utcnow() + timedelta(seconds=expires_in)

            account.access_token = encrypt_token(new_access_raw)
            account.token_expiry = token_expiry
            account.is_active = True
            db.commit()
            logger.info(f"[OAuth Diagnostic] Token refresh SUCCEEDED for {account.gmail_address}. New expiry: {token_expiry.isoformat()}")
            return new_access_raw

    def get_valid_access_token(self, db: Session, account: EmailAccount) -> str:
        """
        Return a valid access token for the given account.
        Automatically refreshes token if expired or expiring within 5 minutes.
        """
        now = datetime.utcnow()
        buffer = timedelta(minutes=5)
        
        is_expired = not (account.token_expiry and (account.token_expiry - buffer > now))
        logger.info(f"[OAuth Diagnostic] get_valid_access_token check for account ID: {account.id}, email: {account.gmail_address}. Expiry: {account.token_expiry}. Refresh required: {is_expired}")

        # Check if current access token is unexpired
        if account.access_token and not is_expired:
            decrypted = decrypt_token(account.access_token)
            if decrypted:
                logger.info(f"[OAuth Diagnostic] Using cached unexpired access token for {account.gmail_address}")
                return decrypted

        # Token is expired or missing — refresh it
        logger.info(f"[OAuth Diagnostic] Access token expired/missing for {account.gmail_address}. Triggering refresh.")
        return self.refresh_access_token(db, account)

    def fetch_inbox_messages(
        self,
        db: Session,
        account: EmailAccount,
        max_results: int = 20,
        query: str = "",
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Fetch list of message references from user's Gmail mailbox."""
        access_token = self.get_valid_access_token(db, account)
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {"maxResults": min(max_results, 50)}
        if query:
            params["q"] = query
        if page_token:
            params["pageToken"] = page_token

        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, headers=headers, params=params)
            if resp.status_code != 200:
                logger.error(f"Gmail list messages failed: {resp.status_code} {resp.text}")
                raise ValueError(f"Failed to fetch Gmail messages: {resp.text}")
            return resp.json()

    def fetch_message_detail(self, access_token: str, message_id: str) -> Dict[str, Any]:
        """
        Fetch full Gmail message detail and parse headers & base64url body parts.
        """
        import base64
        url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"
        headers = {"Authorization": f"Bearer {access_token}"}
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch message detail for {message_id}: {resp.status_code}")
                return {}
            msg = resp.json()

        payload = msg.get("payload", {})
        headers_list = payload.get("headers", [])
        hdr_map = {h["name"].lower(): h["value"] for h in headers_list}

        def decode_base64_data(data_str: str) -> str:
            if not data_str:
                return ""
            try:
                pad = len(data_str) % 4
                if pad:
                    data_str += "=" * (4 - pad)
                return base64.urlsafe_b64decode(data_str.encode("utf-8")).decode("utf-8", errors="ignore")
            except Exception as err:
                logger.warning(f"Failed to decode base64 MIME part: {err}")
                return ""

        body_parts = {"text": "", "html": ""}

        def extract_parts(parts):
            for part in parts:
                mime_type = part.get("mimeType", "")
                data = part.get("body", {}).get("data", "")
                if mime_type == "text/plain" and data:
                    body_parts["text"] += decode_base64_data(data)
                elif mime_type == "text/html" and data:
                    body_parts["html"] += decode_base64_data(data)
                if "parts" in part:
                    extract_parts(part["parts"])

        # Root body
        root_mime = payload.get("mimeType", "")
        root_data = payload.get("body", {}).get("data", "")
        if root_mime == "text/plain" and root_data:
            body_parts["text"] += decode_base64_data(root_data)
        elif root_mime == "text/html" and root_data:
            body_parts["html"] += decode_base64_data(root_data)

        if "parts" in payload:
            extract_parts(payload["parts"])

        body_text = body_parts["text"].strip()
        body_html = body_parts["html"].strip()
        snippet = msg.get("snippet", "")

        if not body_text and not body_html:
            body_text = snippet

        # Parse received_at date
        date_str = hdr_map.get("date")
        received_at = None
        if date_str:
            try:
                from email.utils import parsedate_to_datetime
                received_at = parsedate_to_datetime(date_str).isoformat()
            except Exception:
                received_at = None

        return {
            "gmail_id": msg.get("id"),
            "thread_id": msg.get("threadId"),
            "subject": hdr_map.get("subject", "(no subject)"),
            "sender": hdr_map.get("from", "Unknown Sender"),
            "recipients": hdr_map.get("to", ""),
            "body_text": body_text,
            "body_html": body_html,
            "snippet": snippet,
            "labels": ", ".join(msg.get("labelIds", [])),
            "received_at": received_at,
            "size_bytes": msg.get("sizeEstimate", 0),
        }

    def send_mime_message(
        self,
        db: Session,
        account: EmailAccount,
        recipient: str,
        subject: str,
        body_text: str,
        attachment_path: Optional[str] = None,
        attachment_filename: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Constructs a multipart MIME message with optional base64-encoded PDF/DOCX attachment,
        base64url encodes it, and sends it via Gmail API: POST users/me/messages/send.
        Returns {"id": gmail_message_id, "threadId": gmail_thread_id}.
        """
        import os
        import base64
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        from email.mime.application import MIMEApplication

        if not recipient:
            raise ValueError("Recipient email address is required.")

        msg = MIMEMultipart("mixed")
        msg["To"] = recipient
        msg["From"] = account.gmail_address
        msg["Subject"] = subject or "(No Subject)"

        # RFC 2046: Use multipart/alternative so email clients display either HTML or plain text, NEVER both in series
        body_part = MIMEMultipart("alternative")
        body_part.attach(MIMEText(body_text or "", "plain", "utf-8"))

        html_body = f"<div style='font-family: Arial, sans-serif; font-size: 14px; line-height: 1.6;'>{(body_text or '').replace(chr(10), '<br>')}</div>"
        body_part.attach(MIMEText(html_body, "html", "utf-8"))

        msg.attach(body_part)

        # Attach file if path exists (exactly one attachment)
        if attachment_path and os.path.exists(attachment_path):
            filename = attachment_filename or os.path.basename(attachment_path)
            file_ext = os.path.splitext(filename)[1].lower()

            with open(attachment_path, "rb") as f:
                file_data = f.read()

            if file_ext == ".pdf":
                part = MIMEApplication(file_data, _subtype="pdf")
            elif file_ext == ".docx":
                part = MIMEApplication(
                    file_data,
                    _subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            else:
                part = MIMEApplication(file_data, _subtype="octet-stream")

            part.add_header("Content-Disposition", "attachment", filename=filename)
            msg.attach(part)

        # Base64url encode full MIME message
        raw_bytes = msg.as_bytes()
        raw_b64url = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

        # Get valid OAuth access token (auto-refreshed via Fernet key)
        logger.info(f"[OAuth Diagnostic] Obtaining valid access token for send to {recipient} via account {account.gmail_address}")
        access_token = self.get_valid_access_token(db, account)

        url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {"raw": raw_b64url}

        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=headers, json=payload)
            logger.info(f"[OAuth Diagnostic] Gmail API POST messages/send HTTP Status: {resp.status_code}")
            if resp.status_code != 200:
                logger.error(f"[OAuth Diagnostic] Gmail send API error ({resp.status_code}): {resp.text}")
                raise ValueError(f"Gmail API error ({resp.status_code}): {resp.text}")
            
            result = resp.json()
            logger.info(f"[OAuth Diagnostic] Successfully sent email via Gmail API to {recipient}. Message ID: {result.get('id')}")
            return result


def get_gmail_service() -> GmailService:
    return GmailService()
