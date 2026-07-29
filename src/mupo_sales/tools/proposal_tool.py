"""Dynamic proposal generation from MUPO rate cards + prospect context."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Type

from jinja2 import Template
from pydantic import BaseModel, Field

from mupo_sales.config import get_settings
from mupo_sales.crm.models import Activity, PipelineStage
from mupo_sales.crm.store import get_crm
from mupo_sales.guardrails.compliance import product_requires_human, requires_human_handoff, scan_text
from mupo_sales.logging_setup import action_logger
from mupo_sales.memory.knowledge import get_kb
from mupo_sales.tools.handoff_tool import create_human_handoff

PROPOSAL_TEMPLATE = """# MUPO TV Partnership Proposal
**Status:** DRAFT — Not a binding contract  
**Date:** {{ date }}  
**Prepared for:** {{ contact_name }} — {{ company }}  
**Prepared by:** MUPO TV Partnerships (AI-assisted draft)  
**Founder:** Michele Mupo  

---

## Executive summary

{{ executive_summary }}

## Understanding your goals

{{ goals_section }}

## Recommended package

**Product:** {{ package_name }} (`{{ product_id }}`)  
**Suggested tier:** {{ tier_name }}  
**Investment range:** ${{ price_from }} – ${{ price_to }} USD  
**Indicative proposal value:** ${{ proposed_value }} USD  

### What's included
{% for item in includes %}
- {{ item }}
{% endfor %}

## Why this fit

{{ fit_rationale }}

## Process & next steps

1. Review this draft with your team.
2. A MUPO human partnership lead confirms inventory, timing, and final pricing.
3. Discovery call (if not already completed).
4. Final proposal / insertion order prepared by a human — **this document is not binding**.

{% if human_required %}
> **Human handoff required:** Deals at this value or product type are closed by a MUPO team member.
{% endif %}

## Important disclaimers

- MUPO does **not** guarantee ROI, sales lift, or specific viewership outcomes.
- Audience and placement details are shared with qualified partners; cold proposals do not invent metrics.
- Inventory and air dates are subject to availability and human confirmation.
- {{ disclaimer }}

## Rate card reference (selected)

| Tier | From | To |
|------|------|-----|
{% for t in all_tiers %}| {{ t.name }} | ${{ t.price_from }} | ${{ t.price_to }} |
{% endfor %}

## Contact

Reply to this proposal thread or email partnerships@mupotv.example.  
High-ticket and contract discussions will include a human MUPO representative.

— MUPO Entertainment / MUPO TV  
"""


def _pick_tier(package: dict[str, Any], proposed_value: float) -> dict[str, Any]:
    tiers = package.get("tiers") or []
    if not tiers:
        return {
            "name": "Custom",
            "price_from": package.get("price_min", 0),
            "price_to": package.get("price_max", 0),
            "includes": ["Custom package — details TBD with human lead"],
        }
    # Choose closest tier by midpoint
    best = tiers[0]
    best_dist = float("inf")
    for t in tiers:
        mid = (float(t["price_from"]) + float(t["price_to"])) / 2
        dist = abs(mid - proposed_value)
        if dist < best_dist:
            best_dist = dist
            best = t
    return best


def generate_proposal(
    *,
    deal_id: str,
    product_id: str,
    proposed_value: float,
    executive_summary: str,
    goals_section: str,
    fit_rationale: str,
    tier_name: str | None = None,
    agent: str = "proposal",
) -> dict[str, Any]:
    crm = get_crm()
    kb = get_kb()
    settings = get_settings()

    deal = crm.get_deal(deal_id)
    if not deal:
        return {"ok": False, "error": "deal_not_found"}

    lead = crm.get_lead(deal.lead_id)
    if not lead:
        return {"ok": False, "error": "lead_not_found"}

    package = kb.get_package(product_id)
    if not package:
        return {"ok": False, "error": "unknown_product", "product_id": product_id}

    # Clamp value into package range for honesty
    pmin, pmax = float(package["price_min"]), float(package["price_max"])
    value = max(pmin, min(pmax, float(proposed_value)))

    tier = _pick_tier(package, value)
    if tier_name:
        for t in package.get("tiers") or []:
            if t["name"].lower() == tier_name.lower():
                tier = t
                break

    human_req = bool(package.get("requires_human_close")) or value >= settings.deal_handoff_threshold_usd
    need_handoff, handoff_reasons = requires_human_handoff(
        estimated_value_usd=value,
        product_requires_human=bool(package.get("requires_human_close")),
    )

    md = Template(PROPOSAL_TEMPLATE).render(
        date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        contact_name=lead.contact_name,
        company=lead.company,
        executive_summary=executive_summary.strip(),
        goals_section=goals_section.strip(),
        fit_rationale=fit_rationale.strip(),
        package_name=package["name"],
        product_id=product_id,
        tier_name=tier.get("name", "Custom"),
        price_from=tier.get("price_from", pmin),
        price_to=tier.get("price_to", pmax),
        proposed_value=value,
        includes=tier.get("includes") or [],
        human_required=human_req,
        disclaimer=kb.load_packages().get("disclaimer", ""),
        all_tiers=package.get("tiers") or [],
    )

    # Guardrail scan (strip template artifacts for check)
    plain = re.sub(r"[|#>*_`]", " ", md)
    guard = scan_text(plain)
    if not guard.ok:
        return {"ok": False, "error": "compliance_violation", "violations": guard.violations}

    out_dir = settings.data_dir / "proposals"
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"proposal_{deal_id}_{product_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.md"
    path = out_dir / fname
    path.write_text(md, encoding="utf-8")

    deal.product_id = product_id
    deal.estimated_value_usd = value
    deal.proposal_path = str(path)
    deal.stage = PipelineStage.PROPOSAL_SENT
    deal.human_required = human_req
    if agent not in deal.attribution_chain:
        deal.attribution_chain.append(agent)
    crm.upsert_deal(deal)

    crm.add_activity(
        Activity(
            deal_id=deal_id,
            lead_id=lead.id,
            agent=agent,
            activity_type="proposal_generated",
            summary=f"Proposal draft for {package['name']} @ ${value:,.0f}",
            payload={"path": str(path), "tier": tier.get("name")},
        )
    )
    action_logger.log(
        agent=agent,
        action="proposal_generated",
        deal_id=deal_id,
        lead_id=lead.id,
        details={"path": str(path), "value": value, "product_id": product_id},
    )

    handoff_result = None
    if need_handoff:
        handoff_result = create_human_handoff(
            deal_id=deal_id,
            reason=";".join(handoff_reasons),
            summary=f"Proposal generated at ${value:,.0f} for {lead.company}. Path: {path}",
            estimated_value_usd=value,
            priority="high" if value >= 10000 else "normal",
            agent=agent,
        )

    return {
        "ok": True,
        "path": str(path),
        "proposed_value": value,
        "tier": tier.get("name"),
        "human_handoff": handoff_result,
        "markdown_preview": md[:1500],
    }


def get_crewai_tools() -> list[Any]:
    try:
        from crewai.tools import BaseTool
    except ImportError:
        return []

    class ProposalInput(BaseModel):
        deal_id: str
        product_id: str
        proposed_value: float
        executive_summary: str
        goals_section: str
        fit_rationale: str
        tier_name: str | None = None

    class GenerateProposalTool(BaseTool):
        name: str = "generate_proposal"
        description: str = (
            "Generate a DRAFT markdown proposal for a deal from the MUPO rate card. "
            "Never invent viewership metrics. Auto-handoffs to human when value >= $5k or product requires it."
        )
        args_schema: Type[BaseModel] = ProposalInput

        def _run(
            self,
            deal_id: str,
            product_id: str,
            proposed_value: float,
            executive_summary: str,
            goals_section: str,
            fit_rationale: str,
            tier_name: str | None = None,
        ) -> str:
            return json.dumps(
                generate_proposal(
                    deal_id=deal_id,
                    product_id=product_id,
                    proposed_value=proposed_value,
                    executive_summary=executive_summary,
                    goals_section=goals_section,
                    fit_rationale=fit_rationale,
                    tier_name=tier_name,
                ),
                default=str,
            )

    return [GenerateProposalTool()]
