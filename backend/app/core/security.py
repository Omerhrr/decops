"""Password hashing and session token utilities.

- Passwords: Argon2id via pwdlib (spec: secure password hashing for locally managed credentials)
- Session tokens: cryptographically random opaque tokens; only the SHA-256 hash is stored,
  so a database leak does not expose usable session credentials.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from pwdlib import PasswordHash

_password_hasher = PasswordHash.recommended()  # argon2


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password, password_hash)
    except Exception:
        return False


def generate_session_token() -> str:
    """256 bits of entropy, URL-safe."""
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> str:
    """Sessions are stored as SHA-256(token); the raw token lives only in the cookie."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session_expiry(lifetime_minutes: int) -> datetime:
    return datetime.now(UTC) + timedelta(minutes=lifetime_minutes)
