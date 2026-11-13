"""Transactional email via Resend. Without RESEND_API_KEY, emails are logged instead."""

import logging

import httpx

from app.config import get_settings

log = logging.getLogger("courtiq.email")


def send_email(to: str, subject: str, text: str) -> bool:
    settings = get_settings()
    if not settings.resend_api_key:
        log.info("Email (not sent, no RESEND_API_KEY) to=%s subject=%r", to, subject)
        return False
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
            json={"from": settings.email_from, "to": [to], "subject": subject, "text": text},
            timeout=10,
        )
        r.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        log.warning("Email to %s failed: %s", to, exc)
        return False
