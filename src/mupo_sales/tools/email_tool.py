"""
Email sending with pluggable backends.

Modes:
  - dry_run / log_only: never send (default)
  - gmail: Gmail API (OAuth desktop credentials)
  - instantly: Instantly.ai lead API
  - smartlead: Smartlead lead API

Safety:
  Live send requires ALL of:
    EMAIL_ALLOW_LIVE=true
    DRY_RUN=false
    EMAIL_MODE in (gmail, instantly, smartlead)
  Otherwise messages are always dry-run / queued for review.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

import httpx

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

    def _effective_mode(self) -> str:
        mode = (self.settings.email_mode or "dry_run").lower().strip()
        allow_live = bool(self.settings.email_allow_live) and not bool(self.settings.dry_run)
        if mode in ("gmail", "instantly", "smartlead") and not allow_live:
            logger.warning(
                "EMAIL_MODE=%s but live send blocked "
                "(need EMAIL_ALLOW_LIVE=true AND DRY_RUN=false). Using dry_run.",
                mode,
            )
            return "dry_run"
        if mode not in ("dry_run", "log_only", "gmail", "instantly", "smartlead"):
            return "dry_run"
        return mode

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
        mode = self._effective_mode()
        status = "dry_run"
        provider_response: dict[str, Any] = {"mode": mode}

        if mode in ("dry_run", "log_only"):
            logger.info("[DRY RUN EMAIL] to=%s subject=%s", to_email, subject)
            provider_response["note"] = "Email not sent — dry_run/log_only (or live gate closed)"
            status = "dry_run"
        elif mode == "gmail":
            provider_response = self._send_gmail(to_email, subject, body)
            status = provider_response.get("status", "failed")
        elif mode == "instantly":
            provider_response = self._send_instantly(to_email, subject, body, lead_id=lead_id)
            status = provider_response.get("status", "failed")
        elif mode == "smartlead":
            provider_response = self._send_smartlead(to_email, subject, body, lead_id=lead_id)
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
            sent_at=datetime.now(timezone.utc).isoformat()
            if status in ("sent", "dry_run", "queued")
            else None,
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
                "mode": mode,
                "warnings": guard.warnings,
            },
            attribution="outreach",
        )

        out_dir = self.settings.data_dir / "logs" / "emails"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / f"{msg.id}.json").write_text(
            json.dumps(
                {
                    "to": to_email,
                    "subject": subject,
                    "body": body,
                    "status": status,
                    "mode": mode,
                    "provider": provider_response,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        return {
            "ok": status not in ("failed",),
            "message_id": msg.id,
            "status": status,
            "provider": provider_response,
            "warnings": guard.warnings,
        }

    # --- Gmail ---
    def _send_gmail(self, to: str, subject: str, body: str) -> dict[str, Any]:
        creds_path = self.settings.gmail_credentials_path
        token_path = self.settings.gmail_token_path or str(
            self.settings.data_dir / "gmail_token.json"
        )
        if not creds_path or not Path(creds_path).exists():
            logger.warning("Gmail credentials missing — queueing draft")
            return {
                "status": "queued",
                "provider": "gmail",
                "error": "GMAIL_CREDENTIALS_PATH missing or file not found",
                "to": to,
                "subject": subject,
                "note": "Place OAuth client secrets JSON and set GMAIL_CREDENTIALS_PATH.",
            }
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
        except ImportError:
            return {
                "status": "failed",
                "provider": "gmail",
                "error": "Install gmail extras: pip install -e \".[gmail]\"",
            }

        scopes = ["https://www.googleapis.com/auth/gmail.send"]
        creds = None
        token_file = Path(token_path)
        if token_file.exists():
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
                creds = flow.run_local_server(port=0)
            token_file.parent.mkdir(parents=True, exist_ok=True)
            token_file.write_text(creds.to_json(), encoding="utf-8")

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        message = MIMEText(body)
        message["to"] = to
        message["from"] = self.settings.gmail_user or self.settings.sales_from_email
        message["subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
        sent = (
            service.users()
            .messages()
            .send(userId="me", body={"raw": raw})
            .execute()
        )
        return {
            "status": "sent",
            "provider": "gmail",
            "gmail_id": sent.get("id"),
            "to": to,
        }

    # --- Instantly ---
    def _send_instantly(
        self, to: str, subject: str, body: str, *, lead_id: str
    ) -> dict[str, Any]:
        api_key = self.settings.instantly_api_key
        if not api_key:
            return {"status": "failed", "provider": "instantly", "error": "INSTANTLY_API_KEY missing"}

        campaign = self.settings.instantly_campaign_id
        base = self.settings.instantly_api_base.rstrip("/")
        # Instantly API v2 style lead upsert into campaign (common pattern)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "email": to,
            "first_name": "",
            "last_name": "",
            "custom_variables": {
                "mupo_lead_id": lead_id,
                "subject_hint": subject,
                "body_preview": body[:500],
            },
        }
        if campaign:
            payload["campaign"] = campaign
            payload["campaign_id"] = campaign

        url = f"{base}/api/v2/leads"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                # Some accounts still use v1
                if resp.status_code in (404, 405):
                    resp = client.post(
                        f"{base}/api/v1/lead/add",
                        headers={"Content-Type": "application/json"},
                        json={
                            "api_key": api_key,
                            "campaign_id": campaign,
                            "email": to,
                            "skip_if_in_workspace": True,
                        },
                    )
                data: Any
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:500]}
                if resp.is_success:
                    return {
                        "status": "queued",
                        "provider": "instantly",
                        "http_status": resp.status_code,
                        "response": data,
                        "note": "Lead pushed to Instantly; campaign sequencing handled by Instantly.",
                    }
                return {
                    "status": "failed",
                    "provider": "instantly",
                    "http_status": resp.status_code,
                    "error": data,
                }
        except Exception as e:
            logger.exception("Instantly send failed")
            return {"status": "failed", "provider": "instantly", "error": str(e)}

    # --- Smartlead ---
    def _send_smartlead(
        self, to: str, subject: str, body: str, *, lead_id: str
    ) -> dict[str, Any]:
        api_key = self.settings.smartlead_api_key
        campaign = self.settings.smartlead_campaign_id
        if not api_key:
            return {"status": "failed", "provider": "smartlead", "error": "SMARTLEAD_API_KEY missing"}
        if not campaign:
            return {
                "status": "failed",
                "provider": "smartlead",
                "error": "SMARTLEAD_CAMPAIGN_ID missing",
            }

        url = f"https://server.smartlead.ai/api/v1/campaigns/{campaign}/leads"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    url,
                    params={"api_key": api_key},
                    json={
                        "lead_list": [
                            {
                                "email": to,
                                "custom_fields": {
                                    "mupo_lead_id": lead_id,
                                    "subject_hint": subject,
                                },
                            }
                        ]
                    },
                )
                try:
                    data = resp.json()
                except Exception:
                    data = {"raw": resp.text[:500]}
                if resp.is_success:
                    return {
                        "status": "queued",
                        "provider": "smartlead",
                        "http_status": resp.status_code,
                        "response": data,
                        "note": "Lead added to Smartlead campaign.",
                    }
                return {
                    "status": "failed",
                    "provider": "smartlead",
                    "http_status": resp.status_code,
                    "error": data,
                }
        except Exception as e:
            logger.exception("Smartlead send failed")
            return {"status": "failed", "provider": "smartlead", "error": str(e)}


_email: EmailService | None = None


def get_email_service() -> EmailService:
    global _email
    if _email is None:
        _email = EmailService()
    return _email
