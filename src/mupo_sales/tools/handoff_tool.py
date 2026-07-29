"""Human-in-the-loop handoff notifications."""

from __future__ import annotations

import json
import logging
from typing import Any, Type

from pydantic import BaseModel, Field

from mupo_sales.config import get_settings
from mupo_sales.crm.models import Activity, HandoffTicket, PipelineStage
from mupo_sales.crm.store import get_crm
from mupo_sales.logging_setup import action_logger

logger = logging.getLogger(__name__)


def create_human_handoff(
    *,
    deal_id: str,
    reason: str,
    summary: str,
    estimated_value_usd: float | None = None,
    priority: str = "high",
    recommended_next_steps: list[str] | None = None,
    agent: str = "orchestrator",
) -> dict[str, Any]:
    crm = get_crm()
    deal = crm.get_deal(deal_id)
    if not deal:
        return {"ok": False, "error": "deal_not_found", "deal_id": deal_id}

    lead = crm.get_lead(deal.lead_id)
    value = estimated_value_usd if estimated_value_usd is not None else deal.estimated_value_usd

    ticket = HandoffTicket(
        deal_id=deal_id,
        lead_id=deal.lead_id,
        reason=reason,
        estimated_value_usd=value,
        priority=priority,
        summary=summary,
        recommended_next_steps=recommended_next_steps
        or [
            "Review deal notes and last outreach",
            "Confirm inventory / package availability",
            "Contact prospect personally for discovery or close",
        ],
    )

    channels = ["log"]
    settings = get_settings()

    # Email placeholder notification
    notify_payload = {
        "to": settings.human_handoff_email,
        "subject": f"[MUPO HANDOFF] {priority.upper()} — {lead.company if lead else deal_id}",
        "body": (
            f"Human handoff required\n\n"
            f"Deal: {deal_id}\nLead: {deal.lead_id}\n"
            f"Company: {lead.company if lead else 'n/a'}\n"
            f"Contact: {lead.contact_name if lead else 'n/a'} <{lead.email if lead else ''}>\n"
            f"Value est.: ${value:,.0f}\n"
            f"Reason: {reason}\n\n"
            f"Summary:\n{summary}\n\n"
            f"Next steps:\n- " + "\n- ".join(ticket.recommended_next_steps)
        ),
    }
    # Always write notification file
    out = settings.data_dir / "logs" / "handoffs"
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{ticket.id}.json"
    path.write_text(json.dumps({"ticket": ticket.model_dump(), "notify": notify_payload}, indent=2), encoding="utf-8")
    channels.append("file")

    if settings.human_handoff_slack_webhook:
        channels.append("slack_webhook_configured_not_sent_in_mvp")

    ticket.notified_channels = channels
    crm.add_handoff(ticket)

    deal.human_required = True
    deal.handoff_reason = reason
    deal.stage = PipelineStage.HUMAN_HANDOFF
    from mupo_sales.crm.models import _now

    deal.handoff_at = _now()
    if agent not in deal.attribution_chain:
        deal.attribution_chain.append(agent)
    crm.upsert_deal(deal)

    crm.add_activity(
        Activity(
            deal_id=deal_id,
            lead_id=deal.lead_id,
            agent=agent,
            activity_type="human_handoff",
            summary=f"Handoff: {reason}",
            payload={"ticket_id": ticket.id, "priority": priority},
        )
    )
    action_logger.log(
        agent=agent,
        action="human_handoff",
        deal_id=deal_id,
        lead_id=deal.lead_id,
        details={"ticket_id": ticket.id, "reason": reason, "value": value, "path": str(path)},
    )
    logger.info("HUMAN HANDOFF created %s for deal %s — %s", ticket.id, deal_id, reason)
    return {"ok": True, "ticket": ticket.model_dump(), "notify_path": str(path)}


def get_crewai_tools() -> list[Any]:
    try:
        from crewai.tools import BaseTool
    except ImportError:
        return []

    class HandoffInput(BaseModel):
        deal_id: str
        reason: str
        summary: str
        estimated_value_usd: float = 0.0
        priority: str = "high"
        recommended_next_steps: str = Field(default="", description="Semicolon-separated steps")
        agent: str = "orchestrator"

    class HumanHandoffTool(BaseTool):
        name: str = "create_human_handoff"
        description: str = (
            "Escalate a deal to a human sales lead. REQUIRED when estimated value >= $5000, "
            "strong buying signal, contract/legal request, or product requires human close. "
            "Provide deal_id, reason, summary, estimated_value_usd."
        )
        args_schema: Type[BaseModel] = HandoffInput

        def _run(
            self,
            deal_id: str,
            reason: str,
            summary: str,
            estimated_value_usd: float = 0.0,
            priority: str = "high",
            recommended_next_steps: str = "",
            agent: str = "orchestrator",
        ) -> str:
            steps = [s.strip() for s in recommended_next_steps.split(";") if s.strip()] or None
            return json.dumps(
                create_human_handoff(
                    deal_id=deal_id,
                    reason=reason,
                    summary=summary,
                    estimated_value_usd=estimated_value_usd or None,
                    priority=priority,
                    recommended_next_steps=steps,
                    agent=agent,
                ),
                default=str,
            )

    return [HumanHandoffTool()]
