"""Email delivery for notifications (optional channel).

Disabled by default ("Email, if approved").
When enabled, sends via SMTP; failures raise EmailError so the outbox worker
can classify and retry them. The sandbox/dev default logs the message instead
of sending, so nothing leaves the machine unconfigured.
"""

import logging
import smtplib
from email.message import EmailMessage

from app.core.config import get_settings

logger = logging.getLogger("decops.email")


class EmailError(Exception):
    """Transient or configuration email failure (retryable by the worker)."""


def send_email(*, to_email: str, subject: str, body: str) -> None:
    cfg = get_settings()
    if not cfg.email_notifications_enabled:
        logger.info(
            "email_suppressed",
            extra={"context": {"to": to_email, "subject": subject,
                               "reason": "email_notifications_enabled=False"}},
        )
        return
    message = EmailMessage()
    message["From"] = cfg.email_from
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as smtp:
            if cfg.smtp_username:
                smtp.starttls()
                smtp.login(cfg.smtp_username, cfg.smtp_password)
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailError(f"SMTP delivery failed: {exc}") from exc
