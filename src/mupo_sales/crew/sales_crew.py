"""
MUPO Sales Crew — CrewAI orchestration.

Workflows:
  - full_pipeline: scout → outreach → closer → proposal → crm → orchestrator summary
  - outreach_only: personalize + send for existing leads
  - proposal_only: generate proposal for a deal
  - followup: nurture sequence for stale deals
  - content: sales asset generation
"""

from __future__ import annotations

import logging
from typing import Any

from mupo_sales.config import get_settings
from mupo_sales.crm.store import get_crm
from mupo_sales.memory.knowledge import SharedMemory, get_kb

logger = logging.getLogger(__name__)


def build_sales_crew(
    workflow: str = "full_pipeline",
    *,
    inputs: dict[str, Any] | None = None,
    verbose: bool = True,
):
    """Construct a CrewAI Crew for the requested workflow."""
    try:
        from crewai import Crew, Process, Task
    except ImportError as e:
        raise ImportError(
            "Install LLM stack: pip install -e \".[llm]\" (Python 3.11–3.13 recommended)"
        ) from e

    # Lazy import so offline demo/tests work without crewai/openai
    from mupo_sales.agents.factory import build_agents

    agents = build_agents(verbose=verbose)
    inputs = inputs or {}
    memory = SharedMemory()
    kb = get_kb()
    settings = get_settings()

    context_blob = (
        f"Company: {settings.company_name} / {settings.brand_name}\n"
        f"Founder: {settings.founder_name}\n"
        f"Dry run: {settings.dry_run} | Email mode: {settings.email_mode}\n"
        f"Handoff threshold: ${settings.deal_handoff_threshold_usd:,.0f}\n"
        f"Shared memory:\n{memory.as_context()}\n"
        f"User inputs:\n{inputs}\n"
        f"Packages:\n{kb.list_package_summaries()}\n"
    )

    tasks: list[Any] = []

    if workflow == "full_pipeline":
        target = inputs.get(
            "target_segment",
            "Consumer lifestyle brands and agencies open to TV sponsorships; "
            "also 1–2 creator/coach leads for TV membership.",
        )
        seed = inputs.get("seed_companies", "Use plausible example companies if none provided (label as EXAMPLE).")

        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    f"## Scout Task\n"
                    f"Research and create 2–4 high-quality EXAMPLE or provided leads for:\n{target}\n"
                    f"Seed guidance: {seed}\n"
                    f"For each lead: company, contact_name, email (use example.com if fictional), "
                    f"title, industry, product_interest, icp_fit_score, research_notes, "
                    f"personalization_facts (JSON array string).\n"
                    f"Call create_lead for each. Prefer tv_sponsorship and tv_membership mix.\n"
                    f"Return lead_ids and deal_ids created."
                ),
                expected_output="JSON-like summary of created leads and deals with ids and scores.",
                agent=agents["scout"],
            )
        )
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    "## Outreach Task\n"
                    "Using leads from the Scout, write personalized email touch #1 for each lead "
                    "with a real email. Use get_outreach_sequence and list_packages as needed.\n"
                    "Call send_outreach_email with lead_id, subject, body, deal_id, touch_number=1.\n"
                    "Also draft one LinkedIn connection note per lead via draft_linkedin_message.\n"
                    "No invented metrics. Keep emails 80–160 words."
                ),
                expected_output="Summary of emails dispatched (status) and LinkedIn drafts created.",
                agent=agents["outreach"],
            )
        )
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    "## Closer Assist Task\n"
                    "For each deal from Scout/Outreach, produce a BANT qualification plan and "
                    "likely objections. Estimate value mid-tier for the product_interest.\n"
                    "Use log_activity and update_deal_stage to `qualified` or `discovery` as appropriate.\n"
                    "If estimated value >= 5000 or product requires human close, call create_human_handoff.\n"
                    "Recommend which deal should get a proposal first."
                ),
                expected_output="BANT notes per deal, handoff tickets if any, proposal recommendation.",
                agent=agents["closer"],
            )
        )
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    "## Proposal Task\n"
                    "Generate ONE draft proposal for the highest-priority deal recommended by Closer.\n"
                    "Use generate_proposal with realistic proposed_value inside package range, "
                    "strong executive_summary, goals_section, fit_rationale — no fake metrics.\n"
                    "Return proposal path and handoff status."
                ),
                expected_output="Proposal generation result including file path and any handoff.",
                agent=agents["proposal"],
            )
        )
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    "## CRM Keeper Task\n"
                    "Reconcile pipeline: call pipeline_report, fix any inconsistent stages with update_deal_stage, "
                    "log_activity summarizing the run for commission attribution."
                ),
                expected_output="Pipeline report JSON and list of stage fixes.",
                agent=agents["crm_keeper"],
            )
        )
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    "## Orchestrator Summary\n"
                    "Review the full run. List: (1) actions completed, (2) open human handoffs, "
                    "(3) emails/drafts produced, (4) next 48h recommendations for Michele's team.\n"
                    "Call pipeline_report once."
                ),
                expected_output="Executive run summary for the human sales owner.",
                agent=agents["orchestrator"],
            )
        )

    elif workflow == "outreach_only":
        lead_id = inputs.get("lead_id", "")
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    f"Send personalized outreach for lead_id={lead_id} (or first researched lead if empty).\n"
                    f"Touch number: {inputs.get('touch_number', 1)}.\n"
                    f"Use CRM context and sequences. send_outreach_email + optional LinkedIn draft."
                ),
                expected_output="Outreach result with message ids and statuses.",
                agent=agents["outreach"],
            )
        )

    elif workflow == "proposal_only":
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    f"Generate a proposal for deal_id={inputs.get('deal_id')}, "
                    f"product_id={inputs.get('product_id', 'tv_sponsorship')}, "
                    f"proposed_value={inputs.get('proposed_value', 25000)}.\n"
                    f"Goals context: {inputs.get('goals', 'Brand awareness via entertainment media')}\n"
                    f"Use generate_proposal tool."
                ),
                expected_output="Proposal path and compliance confirmation.",
                agent=agents["proposal"],
            )
        )

    elif workflow == "followup":
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    "Identify deals in outreach_sent or nurture that need a follow-up. "
                    "Write and send (dry-run) the next touch for up to 3 deals. "
                    "Respect max 4 follow-ups. Log activities."
                ),
                expected_output="Follow-up actions taken per deal.",
                agent=agents["followup"],
            )
        )
        tasks.append(
            Task(
                description="Update CRM stages and produce pipeline_report after follow-ups.",
                expected_output="Pipeline report.",
                agent=agents["crm_keeper"],
            )
        )

    elif workflow == "content":
        asset = inputs.get("asset_type", "one-pager")
        product = inputs.get("product_id", "tv_sponsorship")
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    f"Create a {asset} for product_id={product}. "
                    f"Use lookup_package. No invented metrics. Output polished markdown."
                ),
                expected_output="Full markdown sales asset.",
                agent=agents["content"],
            )
        )

    elif workflow == "qualify":
        tasks.append(
            Task(
                description=(
                    f"{context_blob}\n\n"
                    f"Qualify deal_id={inputs.get('deal_id')} given prospect message:\n"
                    f"{inputs.get('prospect_message', '(no message — produce discovery questions)')}\n"
                    f"BANT + objections + handoff if needed."
                ),
                expected_output="Qualification report and any handoff.",
                agent=agents["closer"],
            )
        )

    else:
        raise ValueError(f"Unknown workflow: {workflow}")

    crew = Crew(
        agents=list(agents.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=verbose,
        memory=False,  # we use SharedMemory + CRM explicitly
    )
    return crew


def run_workflow(workflow: str = "full_pipeline", **inputs: Any) -> str:
    """Build and kick off a workflow; return raw result string."""
    settings = get_settings()
    logger.info("Starting workflow=%s dry_run=%s", workflow, settings.dry_run)
    crew = build_sales_crew(workflow, inputs=inputs, verbose=True)
    result = crew.kickoff(inputs=inputs)
    # Persist last result snippet
    SharedMemory().set(
        "last_run",
        {"workflow": workflow, "inputs": inputs, "result_preview": str(result)[:4000]},
    )
    return str(result)


def run_deterministic_demo() -> dict[str, Any]:
    """
    Run a full pipeline WITHOUT requiring LLM/CrewAI.

    Useful for local validation of CRM, email dry-run, proposals, and handoffs.
    """
    from mupo_sales.tools.crm_tools import create_lead_record, log_activity, pipeline_report, update_deal_stage
    from mupo_sales.tools.handoff_tool import create_human_handoff
    from mupo_sales.tools.outreach_tools import draft_linkedin_message, send_outreach_email
    from mupo_sales.tools.proposal_tool import generate_proposal

    results: dict[str, Any] = {"mode": "deterministic_demo"}

    lead_a = create_lead_record(
        company="Lumen & Oak Cosmetics",
        contact_name="Ava Chen",
        email="ava.chen@example.com",
        title="VP Brand Marketing",
        industry="Beauty / CPG",
        website="https://lumenoak.example",
        product_interest="tv_sponsorship",
        icp_fit_score=82,
        research_notes="DTC beauty brand expanding into entertainment-adjacent partnerships; recent lifestyle campaign.",
        personalization_facts=[
            "Recently launched a clean-beauty campaign targeting millennial women",
            "Hiring media roles suggests increased paid/brand budget",
        ],
        linkedin_url="https://linkedin.com/in/example-ava-chen",
    )
    lead_b = create_lead_record(
        company="Summit Path Coaching",
        contact_name="Jordan Miles",
        email="jordan@example.com",
        title="Founder",
        industry="Professional coaching",
        product_interest="tv_membership",
        icp_fit_score=74,
        research_notes="Podcast host with leadership niche; exploring video/TV extension.",
        personalization_facts=[
            "Runs a leadership podcast with interview format",
            "Announced interest in expanding into video content",
        ],
    )
    results["leads"] = [lead_a, lead_b]

    deal_a = lead_a["deal"]["id"]
    deal_b = lead_b["deal"]["id"]
    lead_a_id = lead_a["lead"]["id"]
    lead_b_id = lead_b["lead"]["id"]

    email_a = send_outreach_email(
        lead_id=lead_a_id,
        deal_id=deal_a,
        subject="Lumen & Oak × MUPO TV — partnership idea",
        body=(
            "Hi Ava,\n\n"
            "I noticed Lumen & Oak's recent clean-beauty campaign and the push into broader brand storytelling — "
            "congrats on the momentum.\n\n"
            "I'm with MUPO TV (MUPO Entertainment, founded by Michele Mupo). We partner with lifestyle brands on "
            "TV sponsorship integrations and companion magazine placements. Packages are customized after a short "
            "discovery call; we share detailed audience/placement context with qualified partners rather than "
            "throwing unverifiable numbers over email.\n\n"
            "Open to a 15-minute fit check this week?\n\n"
            "Best,\nMUPO TV Partnerships"
        ),
        sequence_id="sponsorship",
        touch_number=1,
    )
    email_b = send_outreach_email(
        lead_id=lead_b_id,
        deal_id=deal_b,
        subject="Jordan — pathway to your own show on MUPO TV",
        body=(
            "Hi Jordan,\n\n"
            "Your leadership podcast's interview format would translate cleanly to a MUPO TV show concept. "
            "Our TV Membership ($1k–$5k) is a structured pathway for hosts/experts — not a vanity primetime promise, "
            "but a real onboarding + format development track.\n\n"
            "Want the membership overview for coaches in your niche?\n\n"
            "Best,\nMUPO TV Partnerships"
        ),
        sequence_id="membership",
        touch_number=1,
    )
    li = draft_linkedin_message(
        lead_id=lead_a_id,
        deal_id=deal_a,
        is_connection_note=True,
        message=(
            "Hi Ava — I work partnerships for MUPO TV (entertainment media). "
            "Thought there might be a brand storytelling fit with Lumen & Oak. Happy to share context if useful."
        ),
    )
    results["outreach"] = {"email_a": email_a, "email_b": email_b, "linkedin": li}

    update_deal_stage(deal_a, "qualified", "BANT: budget TBD mid-tier, authority VP Brand, need brand entertainment adjacency, timeline this half", agent="closer")
    log_activity("closer", "bant_notes", "Estimated Showcase/Premier band $15k–$40k", deal_id=deal_a, lead_id=lead_a_id)

    proposal = generate_proposal(
        deal_id=deal_a,
        product_id="tv_sponsorship",
        proposed_value=28000,
        executive_summary=(
            "This draft outlines a Premier-leaning Showcase-to-Premier sponsorship path for Lumen & Oak "
            "to associate with MUPO TV entertainment properties and optional magazine companion placements. "
            "Final inventory and pricing require human confirmation."
        ),
        goals_section=(
            "Support brand storytelling and entertainment adjacency for a clean-beauty audience; "
            "explore multi-channel presence (TV integration + magazine) without over-committing inventory."
        ),
        fit_rationale=(
            "Lifestyle CPG brands often benefit from authentic entertainment environments. "
            "MUPO structures packages after discovery; this draft uses published rate-card ranges only."
        ),
        tier_name="Premier Partner",
    )
    results["proposal"] = proposal

    # Membership mid-ticket — may or may not handoff depending on value
    update_deal_stage(deal_b, "discovery", "Creator fit strong; membership Host tier likely", agent="closer")

    results["pipeline"] = pipeline_report()
    results["handoffs"] = [h.model_dump() for h in get_crm().list_handoffs("open")]
    return results
