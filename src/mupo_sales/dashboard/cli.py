"""Rich CLI dashboard to monitor MUPO sales activity."""

from __future__ import annotations

import json
from typing import Optional

from mupo_sales.crm.store import get_crm
from mupo_sales.logging_setup import action_logger


def render_dashboard() -> str:
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich import box

        console = Console(record=True)
        crm = get_crm()
        summary = crm.pipeline_summary()

        console.print(Panel.fit("[bold magenta]MUPO TV Sales Command Center[/bold magenta]\nMichele Mupo · Multi-Agent Pipeline", border_style="magenta"))

        # Pipeline table
        t = Table(title="Pipeline by Stage", box=box.SIMPLE_HEAVY)
        t.add_column("Stage")
        t.add_column("Deals", justify="right")
        t.add_column("Est. Value (USD)", justify="right")
        stages = summary.get("by_stage", {})
        values = summary.get("value_by_stage", {})
        for stage, count in sorted(stages.items(), key=lambda x: x[0]):
            t.add_row(stage, str(count), f"${values.get(stage, 0):,.0f}")
        if not stages:
            t.add_row("(empty)", "0", "$0")
        console.print(t)

        # KPI panel
        console.print(
            Panel(
                f"Leads: [cyan]{summary['lead_count']}[/cyan]  |  "
                f"Deals: [cyan]{summary['deal_count']}[/cyan]  |  "
                f"Open handoffs: [yellow]{summary['open_handoffs']}[/yellow]  |  "
                f"Outbound today: [green]{summary['outbound_today']}[/green]",
                title="KPIs",
            )
        )

        # Recent leads
        leads = crm.list_leads()[-8:]
        lt = Table(title="Recent Leads", box=box.MINIMAL)
        lt.add_column("ID", max_width=18)
        lt.add_column("Company")
        lt.add_column("Contact")
        lt.add_column("Product")
        lt.add_column("Fit")
        for lead in leads:
            lt.add_row(lead.id, lead.company, lead.contact_name, lead.product_interest or "-", f"{lead.icp_fit_score:.0f}")
        console.print(lt)

        # Open handoffs
        handoffs = crm.list_handoffs("open")
        ht = Table(title="Open Human Handoffs", box=box.MINIMAL, style="yellow")
        ht.add_column("Ticket")
        ht.add_column("Deal")
        ht.add_column("Value")
        ht.add_column("Reason", max_width=40)
        for h in handoffs[-10:]:
            ht.add_row(h.id, h.deal_id, f"${h.estimated_value_usd:,.0f}", h.reason[:40])
        if not handoffs:
            ht.add_row("—", "—", "—", "None open")
        console.print(ht)

        # Recent actions
        actions = action_logger.read_all(15)
        at = Table(title="Recent Actions (commission audit)", box=box.MINIMAL)
        at.add_column("Time", max_width=20)
        at.add_column("Agent")
        at.add_column("Action")
        at.add_column("Deal", max_width=16)
        for a in actions:
            at.add_row(
                str(a.get("ts", ""))[:19],
                str(a.get("agent", "")),
                str(a.get("action", "")),
                str(a.get("deal_id") or "")[:16],
            )
        if not actions:
            at.add_row("—", "—", "No actions yet", "—")
        console.print(at)

        return console.export_text()
    except ImportError:
        # Fallback plain text
        crm = get_crm()
        summary = crm.pipeline_summary()
        lines = [
            "=== MUPO TV Sales Command Center ===",
            json.dumps(summary, indent=2),
            f"Open handoffs: {len(crm.list_handoffs('open'))}",
            f"Recent actions: {len(action_logger.read_all(20))}",
        ]
        text = "\n".join(lines)
        print(text)
        return text


def list_deals_table() -> None:
    crm = get_crm()
    deals = crm.list_deals()
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        t = Table(title="All Deals")
        t.add_column("Deal ID")
        t.add_column("Lead")
        t.add_column("Stage")
        t.add_column("Product")
        t.add_column("Value")
        t.add_column("Human?")
        t.add_column("Attribution")
        for d in deals:
            lead = crm.get_lead(d.lead_id)
            t.add_row(
                d.id,
                lead.company if lead else d.lead_id,
                d.stage.value,
                d.product_id or "-",
                f"${d.estimated_value_usd:,.0f}",
                "yes" if d.human_required else "no",
                "→".join(d.attribution_chain) or "-",
            )
        console.print(t)
    except ImportError:
        for d in deals:
            print(d.model_dump_json())
