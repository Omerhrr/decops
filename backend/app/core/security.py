"""Password hashing and session token utilities.

- Passwords: Argon2id via pwdlib
- Session tokens: cryptographically random opaque tokens; only the SHA-256 hash is stored,
  so a database leak does not expose usable session credentials.
"""

import base64
import hashlib
import re
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


# A real Argon2 hash of a random value: verifying against it costs the same as a
# genuine check, so unknown-email logins are not distinguishable by timing.
DUMMY_PASSWORD_HASH = _password_hasher.hash(secrets.token_urlsafe(24))


# ---------------------------------------------------------------------------
# Password policy
# ---------------------------------------------------------------------------
MIN_PASSWORD_LENGTH = 10
_COMMON_PASSWORDS = {
    "password", "password1", "password123", "passw0rd", "qwerty123", "letmein123",
    "welcome123", "admin123456", "changeme123", "iloveyou123", "1234567890",
    "decops!2026", "interdec!2026",
}


def password_policy_problem(password: str, *, email: str | None = None) -> str | None:
    """Return a human-readable reason the password is unacceptable, else None."""
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if len(password) > 200:
        return "Password must be 200 characters or fewer."
    if password.lower() in _COMMON_PASSWORDS:
        return "That password is too common. Choose something less guessable."
    if len(set(password)) < 5:
        return "Password is too repetitive."
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 4 and local in password.lower():
            return "Password must not contain your email name."
    if not (re.search(r"[A-Za-z]", password) and re.search(r"[0-9\W_]", password)):
        return "Use a mix of letters and numbers or symbols."
    return None


# ---------------------------------------------------------------------------
# One-time tokens (password reset)
# ---------------------------------------------------------------------------
def generate_url_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# TOTP second factor
# ---------------------------------------------------------------------------
def _fernet():  # noqa: ANN202
    from cryptography.fernet import Fernet

    from app.core.config import settings

    key = base64.urlsafe_b64encode(hashlib.sha256(settings.session_secret_key.encode()).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()


def new_totp_secret() -> str:
    import pyotp

    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    import pyotp

    code = (code or "").strip().replace(" ", "")
    if not (code.isdigit() and len(code) == 6):
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def totp_uri(secret: str, email: str, issuer: str = "DecOps") -> str:
    import pyotp

    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)


def generate_recovery_codes(count: int = 10) -> list[str]:
    return [f"{secrets.token_hex(2)}-{secrets.token_hex(2)}-{secrets.token_hex(2)}" for _ in range(count)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().lower().encode()).hexdigest()
