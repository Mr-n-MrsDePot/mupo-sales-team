"""Collect all CrewAI tools for the sales crew."""

from __future__ import annotations

from typing import Any


def all_tools() -> list[Any]:
    from mupo_sales.tools import crm_tools, handoff_tool, knowledge_tools, outreach_tools, proposal_tool

    tools: list[Any] = []
    tools.extend(crm_tools.get_crewai_tools())
    tools.extend(knowledge_tools.get_crewai_tools())
    tools.extend(outreach_tools.get_crewai_tools())
    tools.extend(proposal_tool.get_crewai_tools())
    tools.extend(handoff_tool.get_crewai_tools())
    return tools
