# Architecture — MUPO Multi-Agent Sales Team

## Design goals

1. **Runnable MVP** without external CRM or email vendor  
2. **High-ticket honesty** — no fabricated metrics; humans close ≥ $5k  
3. **Attribution** — every action logged for commission-style ops  
4. **Swappable backends** — JSON CRM / dry-run email today → Supabase / Instantly later  

## Control flow

```
User CLI (typer)
    │
    ├─ demo (deterministic) ──► tools directly (no LLM)
    │
    └─ run / demo --llm
            │
            ▼
     CrewAI Crew (sequential Process)
            │
            ├─ Scout Task → create_lead
            ├─ Outreach Task → send_outreach_email / draft_linkedin
            ├─ Closer Task → BANT + handoff rules
            ├─ Proposal Task → generate_proposal
            ├─ CRM Keeper → pipeline_report
            └─ Orchestrator → executive summary
```

## Data plane

| Store | Path | Purpose |
|-------|------|---------|
| Leads/Deals/Messages/Handoffs | `data/crm/*.json` | Pipeline source of truth (v1) |
| Action log | `data/logs/actions.jsonl` | Audit + commission |
| Email drafts | `data/logs/emails/` | Dry-run / review |
| LinkedIn drafts | `data/logs/linkedin/` | Never auto-send |
| Proposals | `data/proposals/*.md` | Human-reviewable drafts |
| Session memory | `data/memory/session.json` | Cross-run notes |
| Optional vectors | `data/memory/chroma/` | Long-term KB retrieval |

## Agent ↔ tool matrix

| Agent | Primary tools |
|-------|----------------|
| Scout | `create_lead`, knowledge lookup |
| Outreach | `send_outreach_email`, `draft_linkedin_message`, sequences |
| Closer | `log_activity`, `update_deal_stage`, `create_human_handoff` |
| Proposal | `lookup_package`, `generate_proposal` |
| Follow-up | outreach + CRM |
| CRM Keeper | `pipeline_report`, stage fixes |
| Content | knowledge only |
| Orchestrator | all tools + delegation |

## Guardrail pipeline

```
Agent draft → scan_text / enforce_email_compliance
           → block on invented metrics / ROI promises
           → requires_human_handoff(value, product, signals)
           → create_human_handoff + stage=human_handoff
```

## LLM layer

```
CrewAI LLM ──openai-compatible──► https://api.x.ai/v1  (grok-4.5)
Direct tools may call openai.OpenAI(base_url=api.x.ai)
Optional fallback: OPENAI_API_KEY / ANTHROPIC_API_KEY
```

## Scaling map

| Layer | MVP | Production |
|-------|-----|------------|
| Framework | CrewAI sequential | CrewAI hierarchical or LangGraph state machine |
| CRM | JSON files | Supabase / Airtable / HubSpot |
| Email | dry_run | Instantly / Smartlead / Gmail API |
| Memory | session JSON | Chroma/pgvector + deal transcripts |
| UI | Rich CLI | Streamlit / internal ops dashboard |
| Auth | none | SSO + role-based handoff queue |

## Why CrewAI for MVP

- Fast agent/task wiring with tool use  
- Sequential pipeline maps cleanly to sales stages  
- xAI via OpenAI-compatible endpoint is a one-line LLM config  

LangGraph is a good next step if you need explicit state machines, cycles (reply → qualify → propose → negotiate), and interrupt/resume for human approval gates.
