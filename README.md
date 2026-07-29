# MUPO Sales Team — Multi-Agent AI Sales System

> **Portfolio project** · Python · CrewAI · xAI Grok · human-in-the-loop sales ops  
> Production-oriented multi-agent pipeline for **MUPO Entertainment (MUPO TV)** sales.

[![CI](https://github.com/Mr-n-MrsDePot/mupo-sales-team/actions/workflows/ci.yml/badge.svg)](https://github.com/Mr-n-MrsDePot/mupo-sales-team/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Repo:** https://github.com/Mr-n-MrsDePot/mupo-sales-team

### Why this project matters
- **Multi-agent orchestration** (scout → outreach → qualify → proposal → follow-up → CRM)
- **Guardrails**: no invented metrics; auto human handoff on high-ticket deals
- **Audit trail** for commission attribution (JSONL action log)
- **xAI Grok** via OpenAI-compatible API

| Product | Range | Human close |
|---------|-------|-------------|
| TV Advertising & Sponsorship | $10k–$80k | Yes |
| 30-Second Commercial Spots | $2.5k–$15k | Yes |
| TV Membership (own show) | $1k–$5k | Soft |
| Magazine Advertising | $500–$8k | Soft |
| Artist Development | $2k–$25k | Yes |

---

## Quick start (offline demo — no API key)

Works with core deps only (including Python 3.14 for demo/tests):

```powershell
cd mupo-sales-team
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev,ui]"
python -m mupo_sales.main demo
python -m mupo_sales.main dashboard
python -m mupo_sales.main ui          # Streamlit ops UI → http://localhost:8501
```

This exercises CRM, dry-run email, proposal generation, and human handoff — without calling an LLM.

### Live multi-agent runs (CrewAI + Grok)

Requires **Python 3.11–3.13** (CrewAI does not support 3.14 yet) and an [xAI API key](https://console.x.ai):

```powershell
py -3.12 -m venv .venv-llm
.\.venv-llm\Scripts\Activate.ps1
pip install -e ".[llm,dev,ui]"
copy .env.example .env
# set XAI_API_KEY=...
python -m mupo_sales.main demo --llm
.\scripts\run_llm_demo.ps1
```

### Email modes (safe by default)

| Mode | Behavior |
|------|----------|
| `dry_run` (default) | Log only — never sends |
| `gmail` | Gmail API send when live gate open |
| `instantly` / `smartlead` | Push lead into campaign when live gate open |

**Live send requires all three:** `EMAIL_MODE` = provider, `EMAIL_ALLOW_LIVE=true`, and `DRY_RUN=false`.  
Anything else is forced dry-run.

Gmail OAuth extras: `pip install -e ".[gmail]"` and set `GMAIL_CREDENTIALS_PATH`.
---

## Architecture

```
                    Orchestrator
         (routing · handoffs · run summaries)
    Scout → Outreach → Closer → Proposal → Follow-up
              CRM Keeper · Content · Guardrails
         JSON CRM · Action JSONL · Proposal drafts
```

| Agent | Responsibility |
|-------|----------------|
| **Scout** | ICP research, lead gen, fit scoring |
| **Outreach** | Personalized cold email + LinkedIn drafts |
| **Closer Assist** | BANT qualification, objections |
| **Proposal** | Rate-card proposals (markdown) |
| **Follow-up** | Nurture / re-engage sequences |
| **CRM Keeper** | Stages, attribution, pipeline reports |
| **Content** | One-pagers, scripts, social posts |
| **Orchestrator** | Next-agent decisions + handoffs |

### Guardrails (hard rules)

- Never invent viewership / ROI / fake case studies  
- Auto **human handoff** when deal ≥ **$5,000**, strong buying signal, or product requires human close  
- Email footer + unsubscribe language  
- LinkedIn = **draft only** by default  
- Full action log for commission attribution  

---

## CLI

| Command | Purpose |
|---------|---------|
| `demo` | Offline pipeline (`--llm` for CrewAI) |
| `run -w <workflow>` | Named workflow |
| `dashboard` | Rich pipeline monitor |
| `deals` | List deals + attribution |
| `handoffs` | Open human tickets |
| `actions` | Action log tail |
| `packages` | Rate-card summary |
| `ui` | Streamlit ops UI (CRM / handoffs / proposals) |

Workflows: `full_pipeline` · `outreach_only` · `proposal_only` · `followup` · `content` · `qualify`

---

## Configuration

- **`.env`** — secrets (see `.env.example`); never commit real keys  
- **`config/settings.yaml`** — products, stages, rate limits, handoff rules  
- **`knowledge/`** — packages, compliance, outreach sequences  

---

## Tests

```powershell
pytest -q
```

CI runs tests + offline demo on Python 3.11 and 3.12.

---

## Project layout

```
mupo-sales-team/
├── config/settings.yaml
├── knowledge/                 # rate cards, compliance, sequences
├── src/mupo_sales/
│   ├── agents/                # prompts + CrewAI factory
│   ├── crew/sales_crew.py     # workflows + deterministic demo
│   ├── crm/                   # models + JSON store
│   ├── tools/                 # email, CRM, proposal, handoff
│   ├── guardrails/
│   └── dashboard/
├── data/                      # runtime (gitignored)
├── tests/
└── .github/workflows/ci.yml
```

---

## Extending

1. Swap JSON CRM for Supabase/HubSpot (keep the store interface)  
2. Wire `EMAIL_MODE=gmail|instantly|smartlead` in `tools/email_tool.py`  
3. Add Streamlit/FastAPI UI over the same CRM + logs  
4. Enable vector memory: `pip install -e ".[vector]"`  

---

## License

MIT — see [LICENSE](LICENSE).
