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


def send_email(*, to_email: str, subject: str, body: str, html: str | None = None) -> None:
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
    if html:
        message.add_alternative(html, subtype="html")
    try:
        if cfg.smtp_ssl:
            with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=10) as smtp:
                if cfg.smtp_username:
                    smtp.login(cfg.smtp_username, cfg.smtp_password)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=10) as smtp:
                if cfg.smtp_username:
                    smtp.starttls()
                    smtp.login(cfg.smtp_username, cfg.smtp_password)
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        raise EmailError(f"SMTP delivery failed: {exc}") from exc


def render_html(*, heading: str, body: str, link: str | None = None, link_label: str = "Open in DecOps") -> str:
    """Small, dependency-free HTML email (all dynamic text is escaped)."""
    from html import escape

    button = (
        f'<p style="margin:24px 0"><a href="{escape(link, quote=True)}" style="background:#1d4ed8;color:#fff;'
        f'padding:10px 18px;border-radius:6px;text-decoration:none;font-weight:600">{escape(link_label)}</a></p>'
        if link else ""
    )
    return (
        '<div style="font-family:system-ui,Segoe UI,Arial,sans-serif;max-width:520px;margin:auto;color:#111827">'
        f'<h2 style="font-size:18px;margin:0 0 12px">{escape(heading)}</h2>'
        f'<p style="font-size:15px;line-height:1.5">{escape(body)}</p>{button}'
        '<p style="font-size:12px;color:#6b7280">You receive this because of your DecOps notification settings.</p></div>'
    )
