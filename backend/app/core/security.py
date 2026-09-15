"""
Security & Token Encryption Utilities
──────────────────────────────────────
Provides Fernet encryption for OAuth access & refresh tokens stored at rest,
and cryptographically signed state token generation/verification for CSRF protection.
"""

import base64
import hashlib
import logging
import secrets
import time
from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def _get_fernet_key() -> bytes:
    """Generate a valid 32-byte url-safe base64 key from settings."""
    raw_key = settings.secret_key
    if hasattr(settings, "fernet_secret_key") and settings.fernet_secret_key:
        raw_key = settings.fernet_secret_key
    # Hash raw_key with SHA-256 to ensure exact 32 bytes, then base64 encode
    hashed = hashlib.sha256(raw_key.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(hashed)


def encrypt_token(token: Optional[str]) -> Optional[str]:
    """Encrypt plain text token using Fernet symmetric encryption."""
    if not token:
        return None
    try:
        f = Fernet(_get_fernet_key())
        return f.encrypt(token.encode("utf-8")).decode("utf-8")
    except Exception as exc:
        logger.error(f"Failed to encrypt token: {exc}")
        return token


def decrypt_token(token_encrypted: Optional[str]) -> Optional[str]:
    """Decrypt Fernet encrypted token string. Fall back to raw string if unencrypted."""
    if not token_encrypted:
        return None
    try:
        f = Fernet(_get_fernet_key())
        return f.decrypt(token_encrypted.encode("utf-8")).decode("utf-8")
    except Exception:
        # Fallback in case token was saved unencrypted during dev testing
        return token_encrypted


def generate_oauth_state() -> str:
    """
    Generate a cryptographically secure, timestamped state string for OAuth CSRF protection.
    Format: {random_bytes}.{timestamp}.{signature}
    """
    rand = secrets.token_urlsafe(24)
    ts = str(int(time.time()))
    payload = f"{rand}:{ts}"
    sig = hashlib.sha256(f"{payload}:{settings.secret_key}".encode("utf-8")).hexdigest()[:16]
    return f"{payload}:{sig}"


def verify_oauth_state(state: str, max_age_seconds: int = 900) -> bool:
    """
    Verify OAuth state parameter signature and expiration (default 15 mins).
    """
    if not state or ":" not in state:
        return False
    parts = state.split(":")
    if len(parts) != 3:
        return False
    rand, ts_str, sig = parts
    try:
        ts = int(ts_str)
        if time.time() - ts > max_age_seconds:
            logger.warning("OAuth state expired")
            return False
        expected_sig = hashlib.sha256(f"{rand}:{ts_str}:{settings.secret_key}".encode("utf-8")).hexdigest()[:16]
        return secrets.compare_digest(sig, expected_sig)
    except Exception as exc:
        logger.warning(f"OAuth state verification failed: {exc}")
        return False
