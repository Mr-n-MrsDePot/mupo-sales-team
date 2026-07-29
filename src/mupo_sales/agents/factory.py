"""Build CrewAI Agent instances for the MUPO sales team."""

from __future__ import annotations

from typing import Any

from mupo_sales.agents import prompts
from mupo_sales.llm import get_crew_llm
from mupo_sales.memory.knowledge import get_kb
from mupo_sales.tools import all_tools
from mupo_sales.tools import crm_tools, handoff_tool, knowledge_tools, outreach_tools, proposal_tool


def _agent_kwargs(verbose: bool = True) -> dict[str, Any]:
    return {
        "llm": get_crew_llm(),
        "verbose": verbose,
        "allow_delegation": False,
        "max_iter": 8,
    }


def build_agents(verbose: bool = True) -> dict[str, Any]:
    """Return named CrewAI agents."""
    try:
        from crewai import Agent
    except ImportError as e:
        raise ImportError("Install crewai: pip install -r requirements.txt") from e

    kb_text = get_kb().agent_context_bundle()
    kw = _agent_kwargs(verbose=verbose)
    tools = all_tools()

    # Split tools by role for focus (all still have compliance/knowledge access)
    knowledge = knowledge_tools.get_crewai_tools()
    crm = crm_tools.get_crewai_tools()
    outreach = outreach_tools.get_crewai_tools()
    proposal = proposal_tool.get_crewai_tools()
    handoff = handoff_tool.get_crewai_tools()

    scout = Agent(
        role="Scout — Lead Research & Generation",
        goal=(
            "Find and record high-ICP leads for MUPO TV products with honest fit scores "
            "and personalization facts."
        ),
        backstory=prompts.with_knowledge_preamble(prompts.SCOUT, kb_text),
        tools=knowledge + crm,
        **kw,
    )

    outreach_agent = Agent(
        role="Outreach — Personalized Cold Email & LinkedIn",
        goal="Write compliant, personalized outreach that earns replies for MUPO packages.",
        backstory=prompts.with_knowledge_preamble(prompts.OUTREACH, kb_text),
        tools=knowledge + outreach + crm,
        **kw,
    )

    closer = Agent(
        role="Closer Assist — Qualification & Objection Handling",
        goal="Qualify with BANT, handle objections honestly, and escalate high-ticket deals.",
        backstory=prompts.with_knowledge_preamble(prompts.CLOSER, kb_text),
        tools=knowledge + crm + handoff,
        **kw,
    )

    proposal_agent = Agent(
        role="Proposal — Dynamic Custom Proposals",
        goal="Generate DRAFT proposals from the official rate card and trigger handoffs when needed.",
        backstory=prompts.with_knowledge_preamble(prompts.PROPOSAL, kb_text),
        tools=knowledge + proposal + crm + handoff,
        **kw,
    )

    followup = Agent(
        role="Follow-up — Nurture & Re-engagement",
        goal="Run respectful multi-touch follow-ups without harassment; re-engage stale leads.",
        backstory=prompts.with_knowledge_preamble(prompts.FOLLOWUP, kb_text),
        tools=knowledge + outreach + crm,
        **kw,
    )

    crm_keeper = Agent(
        role="CRM Keeper — Pipeline Tracking & Reporting",
        goal="Maintain accurate pipeline stages, attribution, and reports for commission transparency.",
        backstory=prompts.with_knowledge_preamble(prompts.CRM_KEEPER, kb_text),
        tools=crm + handoff,
        **kw,
    )

    content = Agent(
        role="Content — Sales Assets",
        goal="Create compliant one-pagers, scripts, and social posts that support the sales team.",
        backstory=prompts.with_knowledge_preamble(prompts.CONTENT, kb_text),
        tools=knowledge,
        **kw,
    )

    orchestrator = Agent(
        role="Orchestrator — Sales Floor Manager",
        goal=(
            "Coordinate the MUPO multi-agent sales team, route work, enforce human handoffs, "
            "and deliver an actionable run summary."
        ),
        backstory=prompts.with_knowledge_preamble(prompts.ORCHESTRATOR, kb_text),
        tools=tools,
        allow_delegation=True,
        llm=kw["llm"],
        verbose=verbose,
        max_iter=12,
    )

    return {
        "orchestrator": orchestrator,
        "scout": scout,
        "outreach": outreach_agent,
        "closer": closer,
        "proposal": proposal_agent,
        "followup": followup,
        "crm_keeper": crm_keeper,
        "content": content,
    }
