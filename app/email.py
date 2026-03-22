"""Async SMTP email utility."""

import logging
from email.message import EmailMessage

import aiosmtplib

from app.config import (
    ALERT_EMAIL_FROM,
    ALERT_EMAIL_TO,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USER,
    email_enabled,
)

logger = logging.getLogger(__name__)


async def send_email(subject: str, body: str) -> bool:
    """Send a plain-text email. Returns True on success, False on failure."""
    if not email_enabled():
        logger.info("Email not configured, skipping: %s", subject)
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = ALERT_EMAIL_FROM
    msg["To"] = ALERT_EMAIL_TO
    msg.set_content(body)

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        logger.info("Email sent: %s", subject)
        return True
    except Exception as exc:
        logger.error("Failed to send email '%s': %s", subject, exc)
        return False
