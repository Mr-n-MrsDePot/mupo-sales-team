"""CRM domain models for the MUPO sales pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class PipelineStage(str, Enum):
    NEW = "new"
    RESEARCHED = "researched"
    OUTREACH_SENT = "outreach_sent"
    REPLIED = "replied"
    QUALIFIED = "qualified"
    DISCOVERY = "discovery"
    PROPOSAL_SENT = "proposal_sent"
    NEGOTIATION = "negotiation"
    HUMAN_HANDOFF = "human_handoff"
    WON = "won"
    LOST = "lost"
    NURTURE = "nurture"


class Lead(BaseModel):
    id: str = Field(default_factory=lambda: _id("lead"))
    company: str
    contact_name: str
    email: str | None = None
    linkedin_url: str | None = None
    title: str | None = None
    industry: str | None = None
    website: str | None = None
    icp_fit_score: float = 0.0  # 0–100
    product_interest: str | None = None  # package id
    research_notes: str = ""
    personalization_facts: list[str] = Field(default_factory=list)
    source: str = "scout"
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class Deal(BaseModel):
    id: str = Field(default_factory=lambda: _id("deal"))
    lead_id: str
    stage: PipelineStage = PipelineStage.NEW
    product_id: str | None = None
    estimated_value_usd: float = 0.0
    currency: str = "USD"
    owner_agent: str = "orchestrator"
    human_required: bool = False
    handoff_reason: str | None = None
    handoff_at: str | None = None
    proposal_path: str | None = None
    next_followup_at: str | None = None
    followup_count: int = 0
    bant: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    attribution_chain: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=_now)
    updated_at: str = Field(default_factory=_now)


class Activity(BaseModel):
    id: str = Field(default_factory=lambda: _id("act"))
    deal_id: str | None = None
    lead_id: str | None = None
    agent: str
    activity_type: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_now)


class OutreachMessage(BaseModel):
    id: str = Field(default_factory=lambda: _id("msg"))
    lead_id: str
    deal_id: str | None = None
    channel: str  # email | linkedin
    direction: str = "outbound"
    subject: str | None = None
    body: str
    status: str = "draft"  # draft | queued | sent | failed | dry_run
    sequence_id: str | None = None
    touch_number: int = 1
    created_at: str = Field(default_factory=_now)
    sent_at: str | None = None


class HandoffTicket(BaseModel):
    id: str = Field(default_factory=lambda: _id("handoff"))
    deal_id: str
    lead_id: str
    reason: str
    estimated_value_usd: float = 0.0
    priority: str = "normal"  # normal | high | urgent
    summary: str
    recommended_next_steps: list[str] = Field(default_factory=list)
    status: str = "open"  # open | acknowledged | closed
    created_at: str = Field(default_factory=_now)
    notified_channels: list[str] = Field(default_factory=list)
