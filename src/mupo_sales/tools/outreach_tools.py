"""Outreach tools: send email drafts / dry-run and LinkedIn draft-only messages."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Type

from pydantic import BaseModel, Field

from mupo_sales.config import get_settings
from mupo_sales.crm.models import Activity, OutreachMessage, PipelineStage
from mupo_sales.crm.store import get_crm
from mupo_sales.logging_setup import action_logger
from mupo_sales.tools.email_tool import get_email_service


def send_outreach_email(
    *,
    lead_id: str,
    subject: str,
    body: str,
    deal_id: str | None = None,
    sequence_id: str | None = None,
    touch_number: int = 1,
) -> dict[str, Any]:
    crm = get_crm()
    lead = crm.get_lead(lead_id)
    if not lead:
        return {"ok": False, "error": "lead_not_found"}
    if not lead.email:
        return {"ok": False, "error": "lead_missing_email"}

    result = get_email_service().send(
        to_email=lead.email,
        subject=subject,
        body=body,
        lead_id=lead_id,
        deal_id=deal_id,
        sequence_id=sequence_id,
        touch_number=touch_number,
    )

    if result.get("ok") and deal_id:
        deal = crm.get_deal(deal_id)
        if deal and deal.stage in (PipelineStage.NEW, PipelineStage.RESEARCHED):
            deal.stage = PipelineStage.OUTREACH_SENT
            if "outreach" not in deal.attribution_chain:
                deal.attribution_chain.append("outreach")
            crm.upsert_deal(deal)
        crm.add_activity(
            Activity(
                deal_id=deal_id,
                lead_id=lead_id,
                agent="outreach",
                activity_type="email_outreach",
                summary=f"Email touch {touch_number}: {subject}",
                payload={"status": result.get("status"), "message_id": result.get("message_id")},
            )
        )
    return result


def draft_linkedin_message(
    *,
    lead_id: str,
    message: str,
    deal_id: str | None = None,
    is_connection_note: bool = False,
) -> dict[str, Any]:
    """LinkedIn is draft-only by default — never auto-send."""
    settings = get_settings()
    crm = get_crm()
    lead = crm.get_lead(lead_id)
    if not lead:
        return {"ok": False, "error": "lead_not_found"}

    if settings.linkedin_mode != "draft_only":
        # Still force draft in MVP for safety
        pass

    msg = OutreachMessage(
        lead_id=lead_id,
        deal_id=deal_id,
        channel="linkedin",
        subject="connection_note" if is_connection_note else "message",
        body=message,
        status="draft",
    )
    crm.add_message(msg)

    out = settings.data_dir / "logs" / "linkedin"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{msg.id}.json"
    path.write_text(
        json.dumps(
            {
                "lead_id": lead_id,
                "linkedin_url": lead.linkedin_url,
                "contact": lead.contact_name,
                "message": message,
                "mode": "draft_only",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    action_logger.log(
        agent="outreach",
        action="linkedin_draft",
        lead_id=lead_id,
        deal_id=deal_id,
        details={"message_id": msg.id, "path": str(path)},
    )
    return {"ok": True, "message_id": msg.id, "status": "draft", "path": str(path)}


def get_crewai_tools() -> list[Any]:
    try:
        from crewai.tools import BaseTool
    except ImportError:
        return []

    class EmailInput(BaseModel):
        lead_id: str
        subject: str
        body: str
        deal_id: str | None = None
        sequence_id: str | None = None
        touch_number: int = 1

    class SendEmailTool(BaseTool):
        name: str = "send_outreach_email"
        description: str = (
            "Send (or dry-run) a personalized outreach email for a lead. "
            "Body must comply with MUPO rules: no invented metrics, include value, clear CTA. "
            "Footer/unsubscribe is auto-appended if missing."
        )
        args_schema: Type[BaseModel] = EmailInput

        def _run(
            self,
            lead_id: str,
            subject: str,
            body: str,
            deal_id: str | None = None,
            sequence_id: str | None = None,
            touch_number: int = 1,
        ) -> str:
            return json.dumps(
                send_outreach_email(
                    lead_id=lead_id,
                    subject=subject,
                    body=body,
                    deal_id=deal_id,
                    sequence_id=sequence_id,
                    touch_number=touch_number,
                ),
                default=str,
            )

    class LinkedInInput(BaseModel):
        lead_id: str
        message: str
        deal_id: str | None = None
        is_connection_note: bool = False

    class LinkedInDraftTool(BaseTool):
        name: str = "draft_linkedin_message"
        description: str = "Create a LinkedIn message or connection note DRAFT only — never auto-sends."
        args_schema: Type[BaseModel] = LinkedInInput

        def _run(
            self,
            lead_id: str,
            message: str,
            deal_id: str | None = None,
            is_connection_note: bool = False,
        ) -> str:
            return json.dumps(
                draft_linkedin_message(
                    lead_id=lead_id,
                    message=message,
                    deal_id=deal_id,
                    is_connection_note=is_connection_note,
                ),
                default=str,
            )

    return [SendEmailTool(), LinkedInDraftTool()]
