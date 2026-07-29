# MUPO Sales Team - Multi-Agent AI Sales System

> **Portfolio project** | Python | CrewAI | xAI Grok | human-in-the-loop sales ops  
> Production-oriented multi-agent pipeline for **MUPO Entertainment (MUPO TV)** sales.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

### Why this project matters
- **Multi-agent orchestration** (scout → outreach → qualify → proposal → follow-up → CRM)
- **Guardrails**: no invented metrics; auto human handoff on high-ticket deals
- **Audit trail** for commission attribution (JSONL action log)
- **xAI Grok** via OpenAI-compatible API (SpaceXAI / xAI)

### Quick demo (offline, no API key)
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
python -m mupo_sales.main demo
python -m mupo_sales.main dashboard
```

---
Commission-style pipeline: agents research, outreach, qualify, propose, follow up, and log everything - humans close high-ticket deals.

| Product | Range | Human close |
|---------|-------|-------------|
| TV Advertising & Sponsorship | $10k-$80k | Yes |
| 30-Second Commercial Spots | $2.5k-$15k | Yes |
| TV Membership (own show) | $1k-$5k | Soft (handoff on signals) |
| Magazine Advertising | $500-$8k | Soft |
| Artist Development | $2k-$25k | Yes |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Orchestrator                             │
│         (routing | handoffs | run summaries)                 │
└────────┬──────────┬──────────┬──────────┬──────────┬────────┘
         │          │          │          │          │
    ┌────▼───┐ ┌────▼────┐ ┌───▼────┐ ┌──▼───┐ ┌───▼────┐
    │ Scout  │ │Outreach │ │Closer  │ │Propos│ │Follow- │
    │ leads  │ │ email/LI│ │ BANT   │ │ al   │ │  up    │
    └────┬───┘ └────┬────┘ └───┬────┘ └──┬───┘ └───┬────┘
         │          │          │         │         │
    ┌────▼──────────▼──────────▼─────────▼─────────▼────┐
    │  CRM Keeper | Content | Shared Memory | Guardrails │
    └───────────────────────┬───────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
   JSON CRM (v1)      Action JSONL log    Proposals/Email drafts
   data/crm/          data/logs/          data/proposals/
```

### Agents

| Agent | Responsibility |
|-------|----------------|
| **Scout** | ICP research, lead gen, fit scoring, personalization facts |
| **Outreach** | Personalized cold email + LinkedIn drafts |
| **Closer Assist** | BANT qualification, objections, discovery |
| **Proposal** | Rate-card proposals (markdown drafts) |
| **Follow-up** | Nurture sequences, re-engagement, breakup emails |
| **CRM Keeper** | Stages, attribution, pipeline reports |
| **Content** | One-pagers, scripts, social posts |
| **Orchestrator** | Next-agent decisions, human handoffs, summaries |

### LLM

- **Primary:** xAI Grok via OpenAI-compatible API (`XAI_API_KEY`, `https://api.x.ai/v1`, model `grok-4.5`)
- **Fallback:** optional OpenAI / Anthropic keys in `.env`

### Guardrails (hard rules)

- Never invent viewership / ROI / fake case studies  
- Auto **human handoff** when estimated deal ≥ **$5,000**, strong buying signal, contract language, or product `requires_human_close`  
- Email footer + unsubscribe language  
- LinkedIn = **draft only** by default  
- Full action log for commission attribution  

---

## Project structure

```
mupo-sales-team/
├── config/settings.yaml          # Business rules, products, rate limits
├── knowledge/
│   ├── company.md
│   ├── compliance.md
│   ├── packages.json             # Rate cards & tiers
│   └── outreach_sequences/       # Per-product email sequences
├── src/mupo_sales/
│   ├── main.py                   # CLI
│   ├── config.py / llm.py
│   ├── agents/                   # Prompts + CrewAI agent factory
│   ├── crew/sales_crew.py        # Workflows
│   ├── crm/                      # Models + JSON store
│   ├── tools/                    # Email, CRM, proposal, handoff, knowledge
│   ├── guardrails/
│   ├── memory/
│   └── dashboard/                # Rich CLI monitor
├── data/                         # Runtime CRM, logs, proposals (gitignored)
├── tests/
├── requirements.txt
├── pyproject.toml
└── .env.example
```

---

## Quick start (local)

### 1. Prerequisites

- Python **3.11+** (3.12/3.13 OK; 3.14 may need latest wheels)
- An [xAI API key](https://console.x.ai) for live agent runs

### 2. Install

```powershell
cd mupo-sales-team
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
copy .env.example .env
# Edit .env → set XAI_API_KEY=...
```

Or: `pip install -r requirements.txt` then set `PYTHONPATH=src`.

### 3. Offline demo (no API key)

Validates CRM, dry-run email, proposal generation, and human handoff:

```powershell
python -m mupo_sales.main demo
python -m mupo_sales.main dashboard
python -m mupo_sales.main handoffs
python -m mupo_sales.main actions
```

Artifacts:

- `data/crm/*.json` - leads, deals, messages, handoffs  
- `data/logs/actions.jsonl` - audit / commission trail  
- `data/logs/emails/` - dry-run email bodies  
- `data/proposals/*.md` - draft proposals  
- `data/logs/handoffs/` - human notification payloads  

### 4. Live multi-agent run (requires `XAI_API_KEY`)

```powershell
python -m mupo_sales.main demo --llm
# or
python -m mupo_sales.main run -w full_pipeline
python -m mupo_sales.main run -w content --product-id tv_membership --asset-type one-pager
python -m mupo_sales.main run -w proposal_only --deal-id DEAL_ID --product-id tv_sponsorship --value 25000
python -m mupo_sales.main run -w followup
```

### 5. Tests

```powershell
pytest -q
```

---

## CLI reference

| Command | Purpose |
|---------|---------|
| `demo` | Deterministic MVP pipeline (`--llm` for CrewAI) |
| `run -w <workflow>` | Execute a named CrewAI workflow |
| `dashboard` | Rich pipeline monitor |
| `deals` | List deals + attribution |
| `handoffs` | Open human tickets |
| `actions` | Action log tail |
| `packages` | Rate-card summary |

Workflows: `full_pipeline` | `outreach_only` | `proposal_only` | `followup` | `content` | `qualify`

---

## Configuration

### `.env` (secrets & runtime)

See `.env.example`. Critical keys:

- `XAI_API_KEY` / `XAI_MODEL` / `XAI_BASE_URL`  
- `DEAL_HANDOFF_THRESHOLD_USD=5000`  
- `EMAIL_MODE=dry_run|log_only|gmail|instantly|smartlead`  
- `DRY_RUN=true`  
- `MAX_OUTREACH_PER_DAY=40`  

### `config/settings.yaml` (business)

Products, forbidden claims, pipeline stages, sequence cadence, handoff triggers.

### Knowledge base

- Edit `knowledge/packages.json` to change pricing tiers (agents read this - don't invent outside it).  
- Sequences in `knowledge/outreach_sequences/*.yaml`.  
- Compliance in `knowledge/compliance.md`.

---

## Human-in-the-loop rules

Agents **must** call `create_human_handoff` when:

1. Estimated value ≥ `$5,000` (configurable)  
2. Strong buying signals (`send proposal`, `budget approved`, `send contract`, …)  
3. Product has `requires_human_close: true`  
4. Legal / contract / IO language  
5. Agent uncertainty on claims  

Handoffs write to `data/logs/handoffs/` and set deal stage `human_handoff`. Wire `HUMAN_HANDOFF_EMAIL` / Slack webhook for production alerts.

---

## Email & LinkedIn

| Mode | Behavior |
|------|----------|
| `dry_run` (default) | Logs email JSON; never sends |
| `gmail` / `instantly` / `smartlead` | Placeholders - implement API calls in `tools/email_tool.py` |
| LinkedIn | Always `draft_only` in MVP |

Compliance scan blocks outbound with invented metrics; footer auto-appended.

---

## Extending (scale path)

1. **CRM:** Replace `crm/store.py` with Supabase/Airtable; keep the same method surface (`upsert_lead`, `list_deals`, …).  
2. **Vector memory:** `ENABLE_VECTOR_MEMORY=true` + `pip install chromadb`.  
3. **Lead sources:** Add Apollo/Clay/Clearbit tools on Scout.  
4. **Sequencer:** Map `EMAIL_MODE=instantly` to real campaign IDs.  
5. **Calendar:** Closer books via Calendly API after qualification.  
6. **Dashboard:** Promote CLI to Streamlit/FastAPI reading the same JSON/DB.  
7. **Auth & multi-tenant:** Add user roles so commission attribution maps to reps.  
8. **Eval harness:** Golden-set tests for outreach quality + compliance regression.

---

## Example outreach (sponsorship touch 1)

```
Subject: {{company}} × MUPO TV - partnership idea

Hi {{first_name}},

[1-2 real personalization facts]

I'm with MUPO TV (MUPO Entertainment, founded by Michele Mupo). We partner with brands on
TV sponsorship integrations and companion magazine placements. Packages are customized
after a short discovery; we share audience/placement detail with qualified partners rather
than unverifiable vanity numbers over email.

Open to a 15-minute fit check this week?

- MUPO TV Partnerships
```

Full sequences: `knowledge/outreach_sequences/`.

---

## Commission attribution

Every tool action hits:

1. `data/logs/actions.jsonl`  
2. CRM `activities` + deal `attribution_chain`  

Use `python -m mupo_sales.main actions` for the audit trail.

---

## Disclaimer

This system drafts sales materials. It does **not** send binding contracts, guarantee inventory, or claim metrics outside `packages.json` → `verified_metrics`. Michele’s team (or designated humans) closes deals ≥ threshold.

---

## License

Internal use for MUPO Entertainment unless otherwise specified.

