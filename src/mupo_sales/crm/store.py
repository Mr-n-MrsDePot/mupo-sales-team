"""
JSON-file CRM store (v1).

Production path: swap this class for Airtable/Supabase while keeping the same interface.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, TypeVar

from mupo_sales.config import get_settings
from mupo_sales.crm.models import (
    Activity,
    Deal,
    HandoffTicket,
    Lead,
    OutreachMessage,
    PipelineStage,
    _now,
)

T = TypeVar("T")


class CRMStore:
    """Thread-safe JSON document store for leads, deals, activities, messages, handoffs."""

    def __init__(self, root: Path | None = None) -> None:
        s = get_settings()
        self.root = root or (s.data_dir / "crm")
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._files = {
            "leads": self.root / "leads.json",
            "deals": self.root / "deals.json",
            "activities": self.root / "activities.json",
            "messages": self.root / "messages.json",
            "handoffs": self.root / "handoffs.json",
        }
        for path in self._files.values():
            if not path.exists():
                self._write(path, [])

    def _read(self, path: Path) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _write(self, path: Path, data: list[dict[str, Any]]) -> None:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        tmp.replace(path)

    # --- Leads ---
    def upsert_lead(self, lead: Lead) -> Lead:
        with self._lock:
            rows = self._read(self._files["leads"])
            lead.updated_at = _now()
            found = False
            for i, r in enumerate(rows):
                if r.get("id") == lead.id:
                    rows[i] = lead.model_dump()
                    found = True
                    break
            if not found:
                rows.append(lead.model_dump())
            self._write(self._files["leads"], rows)
            return lead

    def get_lead(self, lead_id: str) -> Lead | None:
        with self._lock:
            for r in self._read(self._files["leads"]):
                if r.get("id") == lead_id:
                    return Lead.model_validate(r)
        return None

    def list_leads(self) -> list[Lead]:
        with self._lock:
            return [Lead.model_validate(r) for r in self._read(self._files["leads"])]

    def find_leads_by_company(self, company: str) -> list[Lead]:
        company_l = company.lower()
        return [l for l in self.list_leads() if company_l in l.company.lower()]

    # --- Deals ---
    def upsert_deal(self, deal: Deal) -> Deal:
        with self._lock:
            rows = self._read(self._files["deals"])
            deal.updated_at = _now()
            found = False
            for i, r in enumerate(rows):
                if r.get("id") == deal.id:
                    rows[i] = deal.model_dump(mode="json")
                    found = True
                    break
            if not found:
                rows.append(deal.model_dump(mode="json"))
            self._write(self._files["deals"], rows)
            return deal

    def get_deal(self, deal_id: str) -> Deal | None:
        with self._lock:
            for r in self._read(self._files["deals"]):
                if r.get("id") == deal_id:
                    return Deal.model_validate(r)
        return None

    def list_deals(self, stage: PipelineStage | str | None = None) -> list[Deal]:
        with self._lock:
            deals = [Deal.model_validate(r) for r in self._read(self._files["deals"])]
        if stage is None:
            return deals
        stage_s = stage.value if isinstance(stage, PipelineStage) else stage
        return [d for d in deals if d.stage.value == stage_s]

    def update_stage(self, deal_id: str, stage: PipelineStage, note: str | None = None) -> Deal:
        deal = self.get_deal(deal_id)
        if not deal:
            raise KeyError(f"Deal not found: {deal_id}")
        deal.stage = stage
        if note:
            deal.notes.append(f"[{_now()}] stage→{stage.value}: {note}")
        return self.upsert_deal(deal)

    # --- Activities ---
    def add_activity(self, activity: Activity) -> Activity:
        with self._lock:
            rows = self._read(self._files["activities"])
            rows.append(activity.model_dump())
            self._write(self._files["activities"], rows)
            return activity

    def list_activities(self, deal_id: str | None = None, limit: int = 100) -> list[Activity]:
        with self._lock:
            rows = self._read(self._files["activities"])
        acts = [Activity.model_validate(r) for r in rows]
        if deal_id:
            acts = [a for a in acts if a.deal_id == deal_id]
        return acts[-limit:]

    # --- Messages ---
    def add_message(self, msg: OutreachMessage) -> OutreachMessage:
        with self._lock:
            rows = self._read(self._files["messages"])
            rows.append(msg.model_dump())
            self._write(self._files["messages"], rows)
            return msg

    def list_messages(self, lead_id: str | None = None) -> list[OutreachMessage]:
        with self._lock:
            rows = self._read(self._files["messages"])
        msgs = [OutreachMessage.model_validate(r) for r in rows]
        if lead_id:
            msgs = [m for m in msgs if m.lead_id == lead_id]
        return msgs

    def count_outbound_today(self) -> int:
        """Rough daily outreach count for rate limiting."""
        today = _now()[:10]
        count = 0
        for m in self.list_messages():
            if m.direction == "outbound" and m.status in ("sent", "dry_run", "queued"):
                if (m.sent_at or m.created_at or "").startswith(today):
                    count += 1
        return count

    # --- Handoffs ---
    def add_handoff(self, ticket: HandoffTicket) -> HandoffTicket:
        with self._lock:
            rows = self._read(self._files["handoffs"])
            rows.append(ticket.model_dump())
            self._write(self._files["handoffs"], rows)
            return ticket

    def list_handoffs(self, status: str | None = "open") -> list[HandoffTicket]:
        with self._lock:
            rows = self._read(self._files["handoffs"])
        tickets = [HandoffTicket.model_validate(r) for r in rows]
        if status:
            tickets = [t for t in tickets if t.status == status]
        return tickets

    # --- Reporting ---
    def pipeline_summary(self) -> dict[str, Any]:
        deals = self.list_deals()
        by_stage: dict[str, int] = {}
        value_by_stage: dict[str, float] = {}
        for d in deals:
            by_stage[d.stage.value] = by_stage.get(d.stage.value, 0) + 1
            value_by_stage[d.stage.value] = value_by_stage.get(d.stage.value, 0.0) + d.estimated_value_usd
        return {
            "lead_count": len(self.list_leads()),
            "deal_count": len(deals),
            "by_stage": by_stage,
            "value_by_stage": value_by_stage,
            "open_handoffs": len(self.list_handoffs("open")),
            "outbound_today": self.count_outbound_today(),
        }


# Singleton
_store: CRMStore | None = None


def get_crm() -> CRMStore:
    global _store
    if _store is None:
        _store = CRMStore()
    return _store
