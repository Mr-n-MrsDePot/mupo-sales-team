"""CRM operations exposed as CrewAI tools and plain Python helpers."""

from __future__ import annotations

import json
from typing import Any, Type

from pydantic import BaseModel, Field

from mupo_sales.crm.models import Activity, Deal, Lead, PipelineStage
from mupo_sales.crm.store import get_crm
from mupo_sales.logging_setup import action_logger


def create_lead_record(
    company: str,
    contact_name: str,
    email: str | None = None,
    title: str | None = None,
    industry: str | None = None,
    website: str | None = None,
    product_interest: str | None = None,
    icp_fit_score: float = 50.0,
    research_notes: str = "",
    personalization_facts: list[str] | None = None,
    linkedin_url: str | None = None,
) -> dict[str, Any]:
    crm = get_crm()
    lead = Lead(
        company=company,
        contact_name=contact_name,
        email=email,
        title=title,
        industry=industry,
        website=website,
        product_interest=product_interest,
        icp_fit_score=icp_fit_score,
        research_notes=research_notes,
        personalization_facts=personalization_facts or [],
        linkedin_url=linkedin_url,
    )
    crm.upsert_lead(lead)
    deal = Deal(
        lead_id=lead.id,
        stage=PipelineStage.RESEARCHED,
        product_id=product_interest,
        owner_agent="scout",
        attribution_chain=["scout"],
    )
    crm.upsert_deal(deal)
    crm.add_activity(
        Activity(
            deal_id=deal.id,
            lead_id=lead.id,
            agent="scout",
            activity_type="lead_created",
            summary=f"Scout created lead {contact_name} @ {company}",
            payload={"icp_fit_score": icp_fit_score},
        )
    )
    action_logger.log(
        agent="scout",
        action="lead_created",
        lead_id=lead.id,
        deal_id=deal.id,
        details={"company": company, "contact": contact_name, "score": icp_fit_score},
    )
    return {"lead": lead.model_dump(), "deal": deal.model_dump(mode="json")}


def update_deal_stage(deal_id: str, stage: str, note: str = "", agent: str = "crm_keeper") -> dict[str, Any]:
    crm = get_crm()
    try:
        stage_enum = PipelineStage(stage)
    except ValueError:
        return {"ok": False, "error": f"invalid_stage:{stage}", "valid": [s.value for s in PipelineStage]}
    deal = crm.update_stage(deal_id, stage_enum, note=note or None)
    if agent not in deal.attribution_chain:
        deal.attribution_chain.append(agent)
        crm.upsert_deal(deal)
    crm.add_activity(
        Activity(
            deal_id=deal_id,
            lead_id=deal.lead_id,
            agent=agent,
            activity_type="stage_change",
            summary=f"Stage → {stage}: {note}",
        )
    )
    action_logger.log(agent=agent, action="stage_change", deal_id=deal_id, lead_id=deal.lead_id, details={"stage": stage, "note": note})
    return {"ok": True, "deal": deal.model_dump(mode="json")}


def set_deal_value(deal_id: str, value_usd: float, product_id: str | None = None, agent: str = "closer") -> dict[str, Any]:
    crm = get_crm()
    deal = crm.get_deal(deal_id)
    if not deal:
        return {"ok": False, "error": "deal_not_found"}
    deal.estimated_value_usd = float(value_usd)
    if product_id:
        deal.product_id = product_id
    if agent not in deal.attribution_chain:
        deal.attribution_chain.append(agent)
    crm.upsert_deal(deal)
    action_logger.log(
        agent=agent,
        action="deal_value_set",
        deal_id=deal_id,
        details={"value_usd": value_usd, "product_id": product_id},
    )
    return {"ok": True, "deal": deal.model_dump(mode="json")}


def log_activity(agent: str, activity_type: str, summary: str, deal_id: str | None = None, lead_id: str | None = None, payload: dict | None = None) -> dict[str, Any]:
    crm = get_crm()
    act = Activity(
        deal_id=deal_id,
        lead_id=lead_id,
        agent=agent,
        activity_type=activity_type,
        summary=summary,
        payload=payload or {},
    )
    crm.add_activity(act)
    action_logger.log(agent=agent, action=activity_type, deal_id=deal_id, lead_id=lead_id, details={"summary": summary})
    return act.model_dump()


def pipeline_report() -> str:
    crm = get_crm()
    return json.dumps(crm.pipeline_summary(), indent=2)


# --- CrewAI tool wrappers (lazy so imports work without crewai for unit tests) ---

def get_crewai_tools() -> list[Any]:
    try:
        from crewai.tools import BaseTool
    except ImportError:
        return []

    class CreateLeadInput(BaseModel):
        company: str
        contact_name: str
        email: str | None = None
        title: str | None = None
        industry: str | None = None
        website: str | None = None
        product_interest: str | None = None
        icp_fit_score: float = 50.0
        research_notes: str = ""
        personalization_facts: str = Field(default="", description="JSON array or semicolon-separated facts")
        linkedin_url: str | None = None

    class CreateLeadTool(BaseTool):
        name: str = "create_lead"
        description: str = (
            "Create a new lead and associated deal in the CRM after research. "
            "Provide company, contact_name, optional email, product_interest package id, "
            "icp_fit_score 0-100, research_notes, and personalization_facts."
        )
        args_schema: Type[BaseModel] = CreateLeadInput

        def _run(
            self,
            company: str,
            contact_name: str,
            email: str | None = None,
            title: str | None = None,
            industry: str | None = None,
            website: str | None = None,
            product_interest: str | None = None,
            icp_fit_score: float = 50.0,
            research_notes: str = "",
            personalization_facts: str = "",
            linkedin_url: str | None = None,
        ) -> str:
            facts: list[str] = []
            if personalization_facts:
                try:
                    facts = json.loads(personalization_facts)
                    if not isinstance(facts, list):
                        facts = [str(facts)]
                except json.JSONDecodeError:
                    facts = [f.strip() for f in personalization_facts.split(";") if f.strip()]
            result = create_lead_record(
                company=company,
                contact_name=contact_name,
                email=email,
                title=title,
                industry=industry,
                website=website,
                product_interest=product_interest,
                icp_fit_score=icp_fit_score,
                research_notes=research_notes,
                personalization_facts=facts,
                linkedin_url=linkedin_url,
            )
            return json.dumps(result, default=str)

    class UpdateStageInput(BaseModel):
        deal_id: str
        stage: str
        note: str = ""
        agent: str = "crm_keeper"

    class UpdateStageTool(BaseTool):
        name: str = "update_deal_stage"
        description: str = (
            "Update pipeline stage for a deal. Stages: new, researched, outreach_sent, "
            "replied, qualified, discovery, proposal_sent, negotiation, human_handoff, won, lost, nurture."
        )
        args_schema: Type[BaseModel] = UpdateStageInput

        def _run(self, deal_id: str, stage: str, note: str = "", agent: str = "crm_keeper") -> str:
            return json.dumps(update_deal_stage(deal_id, stage, note, agent), default=str)

    class PipelineReportTool(BaseTool):
        name: str = "pipeline_report"
        description: str = "Return JSON summary of leads, deals by stage, values, and open handoffs."

        def _run(self) -> str:
            return pipeline_report()

    class LogActivityInput(BaseModel):
        agent: str
        activity_type: str
        summary: str
        deal_id: str | None = None
        lead_id: str | None = None

    class LogActivityTool(BaseTool):
        name: str = "log_activity"
        description: str = "Log a free-form activity for commission attribution and audit."
        args_schema: Type[BaseModel] = LogActivityInput

        def _run(
            self,
            agent: str,
            activity_type: str,
            summary: str,
            deal_id: str | None = None,
            lead_id: str | None = None,
        ) -> str:
            return json.dumps(log_activity(agent, activity_type, summary, deal_id, lead_id), default=str)

    return [CreateLeadTool(), UpdateStageTool(), PipelineReportTool(), LogActivityTool()]
