"""
MUPO Entertainment Multi-Agent Sales Team — CLI entrypoint.

Examples:
  python -m mupo_sales.main demo
  python -m mupo_sales.main dashboard
  python -m mupo_sales.main run --workflow full_pipeline
  python -m mupo_sales.main run --workflow proposal_only --deal-id deal_xxx --product-id tv_sponsorship
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure src/ is on path when run as script
_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

import typer
from rich.console import Console

from mupo_sales.config import get_settings
from mupo_sales.logging_setup import setup_logging

app = typer.Typer(
    name="mupo-sales",
    help="MUPO TV multi-agent sales team (CrewAI + xAI Grok)",
    add_completion=False,
)
console = Console()


@app.callback()
def _init() -> None:
    setup_logging()
    get_settings().ensure_dirs()


@app.command("demo")
def demo_cmd(
    deterministic: bool = typer.Option(
        True,
        "--deterministic/--llm",
        help="Deterministic path (no API key) or full LLM crew",
    ),
) -> None:
    """
    Run an end-to-end demo of the sales pipeline.

    Default is deterministic (CRM + dry-run email + proposal + handoff) without LLM.
    Use --llm to run CrewAI with XAI_API_KEY.
    """
    if deterministic:
        console.print("[bold green]Running deterministic MVP demo (no LLM required)…[/bold green]")
        from mupo_sales.crew.sales_crew import run_deterministic_demo

        result = run_deterministic_demo()
        console.print_json(json.dumps(result, default=str))
        console.print("\n[bold]Open the dashboard:[/bold] python -m mupo_sales.main dashboard")
        console.print(f"Proposals dir: {get_settings().data_dir / 'proposals'}")
        console.print(f"Handoffs dir: {get_settings().data_dir / 'logs' / 'handoffs'}")
    else:
        console.print("[bold cyan]Running full CrewAI pipeline (requires XAI_API_KEY)…[/bold cyan]")
        settings = get_settings()
        if not settings.xai_api_key:
            console.print("[red]XAI_API_KEY missing. Copy .env.example → .env and set your key.[/red]")
            raise typer.Exit(1)
        try:
            from mupo_sales.crew.sales_crew import run_workflow
        except ImportError as e:
            console.print(f"[red]LLM stack missing: {e}[/red]")
            console.print("Install with Python 3.11–3.13: [bold]pip install -e \".[llm]\"[/bold]")
            raise typer.Exit(1) from e

        out = run_workflow(
            "full_pipeline",
            target_segment="Beauty/CPG brands for sponsorship + one coach for TV membership",
            seed_companies="Prefer realistic EXAMPLE companies with example.com emails",
        )
        console.print(out)


@app.command("run")
def run_cmd(
    workflow: str = typer.Option(
        "full_pipeline",
        "--workflow",
        "-w",
        help="full_pipeline | outreach_only | proposal_only | followup | content | qualify",
    ),
    deal_id: Optional[str] = typer.Option(None, "--deal-id"),
    lead_id: Optional[str] = typer.Option(None, "--lead-id"),
    product_id: Optional[str] = typer.Option(None, "--product-id"),
    proposed_value: Optional[float] = typer.Option(None, "--value"),
    target_segment: Optional[str] = typer.Option(None, "--segment"),
    asset_type: Optional[str] = typer.Option(None, "--asset-type"),
    prospect_message: Optional[str] = typer.Option(None, "--message"),
) -> None:
    """Run a CrewAI workflow with xAI Grok."""
    settings = get_settings()
    if not settings.xai_api_key:
        console.print("[red]XAI_API_KEY required for LLM workflows. Use `demo` for offline path.[/red]")
        raise typer.Exit(1)

    inputs = {k: v for k, v in {
        "deal_id": deal_id,
        "lead_id": lead_id,
        "product_id": product_id,
        "proposed_value": proposed_value,
        "target_segment": target_segment,
        "asset_type": asset_type,
        "prospect_message": prospect_message,
    }.items() if v is not None}

    try:
        from mupo_sales.crew.sales_crew import run_workflow
    except ImportError as e:
        console.print(f"[red]LLM stack missing: {e}[/red]")
        console.print("Install with Python 3.11–3.13: [bold]pip install -e \".[llm]\"[/bold]")
        raise typer.Exit(1) from e

    console.print(f"[bold]Workflow:[/bold] {workflow}  inputs={inputs}")
    result = run_workflow(workflow, **inputs)
    console.print(result)


@app.command("dashboard")
def dashboard_cmd() -> None:
    """Show pipeline KPIs, handoffs, and recent actions."""
    from mupo_sales.dashboard.cli import render_dashboard

    render_dashboard()


@app.command("deals")
def deals_cmd() -> None:
    """List all deals."""
    from mupo_sales.dashboard.cli import list_deals_table

    list_deals_table()


@app.command("handoffs")
def handoffs_cmd() -> None:
    """List open human handoff tickets."""
    from mupo_sales.crm.store import get_crm

    tickets = get_crm().list_handoffs("open")
    if not tickets:
        console.print("[green]No open handoffs.[/green]")
        return
    for t in tickets:
        console.print(t.model_dump_json(indent=2))


@app.command("actions")
def actions_cmd(limit: int = typer.Option(30, "--limit", "-n")) -> None:
    """Show action log (commission attribution trail)."""
    from mupo_sales.logging_setup import action_logger

    for row in action_logger.read_all(limit):
        console.print(
            f"{row.get('ts', '')[:19]} | {row.get('agent')} | {row.get('action')} | "
            f"deal={row.get('deal_id')} lead={row.get('lead_id')}"
        )


@app.command("packages")
def packages_cmd() -> None:
    """Print MUPO package summary from knowledge base."""
    from mupo_sales.memory.knowledge import get_kb

    console.print(get_kb().list_package_summaries())


def main() -> None:
    app()


if __name__ == "__main__":
    main()
