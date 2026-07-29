"""
Email sending with pluggable backends.

Modes:
  - dry_run: log only, never send (default for local MVP)
  - log_only: same as dry_run but explicit
  - gmail / instantly / smartlead: placeholders for production wiring
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from mupo_sales.config import get_settings
from mupo_sales.crm.models import OutreachMessage
from mupo_sales.crm.store import get_crm
from mupo_sales.guardrails.compliance import enforce_email_compliance
from mupo_sales.logging_setup import action_logger

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.crm = get_crm()

    def send(
        self,
        *,
        to_email: str,
        subject: str,
        body: str,
        lead_id: str,
        deal_id: str | None = None,
        sequence_id: str | None = None,
        touch_number: int = 1,
        force: bool = False,
    ) -> dict[str, Any]:
        # Rate limit
        if not force and self.crm.count_outbound_today() >= self.settings.max_outreach_per_day:
            return {
                "ok": False,
                "error": "daily_outreach_limit_reached",
                "limit": self.settings.max_outreach_per_day,
            }

        guard = enforce_email_compliance(body, subject)
        if not guard.ok:
            action_logger.log(
                agent="email_service",
                action="email_blocked_compliance",
                lead_id=lead_id,
                deal_id=deal_id,
                details={"violations": guard.violations, "subject": subject},
            )
            return {
                "ok": False,
                "error": "compliance_violation",
                "violations": guard.violations,
            }

        body = guard.sanitized_text or body
        mode = self.settings.email_mode
        if self.settings.dry_run and mode not in ("gmail", "instantly", "smartlead"):
            mode = "dry_run"

        status = "dry_run"
        provider_response: dict[str, Any] = {"mode": mode}

        if mode in ("dry_run", "log_only"):
            logger.info("[DRY RUN EMAIL] to=%s subject=%s", to_email, subject)
            provider_response["note"] = "Email not sent — dry_run/log_only mode"
            status = "dry_run"
        elif mode == "gmail":
            provider_response = self._send_gmail_placeholder(to_email, subject, body)
            status = provider_response.get("status", "failed")
        elif mode == "instantly":
            provider_response = self._send_instantly_placeholder(to_email, subject, body)
            status = provider_response.get("status", "failed")
        elif mode == "smartlead":
            provider_response = self._send_smartlead_placeholder(to_email, subject, body)
            status = provider_response.get("status", "failed")
        else:
            return {"ok": False, "error": f"unknown_email_mode:{mode}"}

        msg = OutreachMessage(
            lead_id=lead_id,
            deal_id=deal_id,
            channel="email",
            subject=subject,
            body=body,
            status=status,
            sequence_id=sequence_id,
            touch_number=touch_number,
            sent_at=datetime.now(timezone.utc).isoformat() if status in ("sent", "dry_run") else None,
        )
        self.crm.add_message(msg)

        action_logger.log(
            agent="email_service",
            action="email_dispatched",
            lead_id=lead_id,
            deal_id=deal_id,
            details={
                "to": to_email,
                "subject": subject,
                "status": status,
                "message_id": msg.id,
                "warnings": guard.warnings,
            },
            attribution="outreach",
        )

        # Persist draft copy for review
        out_dir = self.settings.data_dir / "logs" / "emails"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{msg.id}.json").write_text(
            json.dumps(
                {
                    "to": to_email,
                    "subject": subject,
                    "body": body,
                    "status": status,
                    "provider": provider_response,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "ok": True,
            "message_id": msg.id,
            "status": status,
            "provider": provider_response,
            "warnings": guard.warnings,
        }

    def _send_gmail_placeholder(self, to: str, subject: str, body: str) -> dict[str, Any]:
        # Wire Gmail API here using GMAIL_CREDENTIALS_PATH
        logger.warning("Gmail mode selected but not fully configured — saving as queued draft")
        return {
            "status": "queued",
            "provider": "gmail",
            "note": "Implement Gmail API send using credentials path; message queued for human approval.",
            "to": to,
            "subject": subject,
        }

    def _send_instantly_placeholder(self, to: str, subject: str, body: str) -> dict[str, Any]:
        if not self.settings.instantly_api_key:
            return {"status": "failed", "error": "INSTANTLY_API_KEY missing"}
        return {
            "status": "queued",
            "provider": "instantly",
            "note": "POST to Instantly API /api/v2/emails/campaigns — implement with campaign id mapping.",
            "to": to,
        }

    def _send_smartlead_placeholder(self, to: str, subject: str, body: str) -> dict[str, Any]:
        if not self.settings.smartlead_api_key:
            return {"status": "failed", "error": "SMARTLEAD_API_KEY missing"}
        return {
            "status": "queued",
            "provider": "smartlead",
            "note": "POST to Smartlead lead/email endpoints — implement campaign mapping.",
            "to": to,
        }


_email: EmailService | None = None


def get_email_service() -> EmailService:
    global _email
    if _email is None:
        _email = EmailService()
    return _email
