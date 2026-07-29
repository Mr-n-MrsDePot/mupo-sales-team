"""
MUPO TV Sales Ops UI (Streamlit).

Run:
  streamlit run src/mupo_sales/ui/app.py
  # or: python -m mupo_sales.main ui
"""

from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from mupo_sales.config import get_settings
from mupo_sales.crm.models import PipelineStage
from mupo_sales.crm.store import get_crm
from mupo_sales.logging_setup import action_logger


st.set_page_config(
    page_title="MUPO Sales Ops",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded",
)


def _money(v: float) -> str:
    return f"${v:,.0f}"


def page_overview() -> None:
    crm = get_crm()
    summary = crm.pipeline_summary()
    settings = get_settings()

    st.title("MUPO TV · Sales Command Center")
    st.caption(
        f"{settings.brand_name} · Founded by {settings.founder_name} · "
        f"email_mode={settings.email_mode} · dry_run={settings.dry_run}"
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Leads", summary.get("lead_count", 0))
    c2.metric("Deals", summary.get("deal_count", 0))
    c3.metric("Open handoffs", summary.get("open_handoffs", 0))
    c4.metric("Outbound today", summary.get("outbound_today", 0))

    stages = summary.get("by_stage", {})
    values = summary.get("value_by_stage", {})
    if stages:
        rows = [
            {"stage": s, "deals": stages[s], "est_value_usd": values.get(s, 0)}
            for s in sorted(stages.keys())
        ]
        st.subheader("Pipeline by stage")
        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("Pipeline empty — run `python -m mupo_sales.main demo` first.")

    st.subheader("Recent actions (commission audit)")
    actions = list(reversed(action_logger.read_all(40)))
    if actions:
        st.dataframe(
            [
                {
                    "ts": a.get("ts", "")[:19],
                    "agent": a.get("agent"),
                    "action": a.get("action"),
                    "deal_id": a.get("deal_id"),
                    "lead_id": a.get("lead_id"),
                }
                for a in actions
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.write("No actions logged yet.")


def page_leads() -> None:
    st.title("Leads")
    leads = list(reversed(get_crm().list_leads()))
    q = st.text_input("Filter company / contact / email", "")
    rows = []
    for lead in leads:
        blob = f"{lead.company} {lead.contact_name} {lead.email or ''}".lower()
        if q and q.lower() not in blob:
            continue
        rows.append(
            {
                "id": lead.id,
                "company": lead.company,
                "contact": lead.contact_name,
                "email": lead.email or "",
                "title": lead.title or "",
                "product": lead.product_interest or "",
                "fit": lead.icp_fit_score,
                "industry": lead.industry or "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)
    if rows:
        pick = st.selectbox("Lead detail", [r["id"] for r in rows])
        lead = get_crm().get_lead(pick)
        if lead:
            st.json(lead.model_dump())


def page_deals() -> None:
    st.title("Deals")
    crm = get_crm()
    stage_filter = st.selectbox(
        "Stage filter",
        ["(all)"] + [s.value for s in PipelineStage],
    )
    deals = crm.list_deals(None if stage_filter == "(all)" else stage_filter)
    leads = {l.id: l for l in crm.list_leads()}
    rows = []
    for d in reversed(deals):
        lead = leads.get(d.lead_id)
        rows.append(
            {
                "id": d.id,
                "company": lead.company if lead else "?",
                "stage": d.stage.value,
                "product": d.product_id or "",
                "value": d.estimated_value_usd,
                "human_required": d.human_required,
                "proposal": Path(d.proposal_path).name if d.proposal_path else "",
            }
        )
    st.dataframe(rows, use_container_width=True, hide_index=True)

    if deals:
        pick = st.selectbox("Deal detail", [d.id for d in reversed(deals)])
        deal = crm.get_deal(pick)
        if deal:
            st.json(deal.model_dump(mode="json"))
            if deal.proposal_path and Path(deal.proposal_path).exists():
                st.subheader("Linked proposal")
                st.markdown(Path(deal.proposal_path).read_text(encoding="utf-8"))

            st.subheader("Update stage")
            new_stage = st.selectbox("New stage", [s.value for s in PipelineStage], key="stage_upd")
            note = st.text_input("Note", "")
            if st.button("Save stage"):
                crm.update_stage(deal.id, PipelineStage(new_stage), note or None)
                st.success(f"Updated {deal.id} → {new_stage}")
                st.rerun()


def page_handoffs() -> None:
    st.title("Human handoffs")
    crm = get_crm()
    status = st.radio("Status", ["open", "all"], horizontal=True)
    handoffs = crm.list_handoffs(None if status == "all" else "open")
    if not handoffs:
        st.info("No handoffs.")
        return

    for h in reversed(handoffs):
        with st.expander(
            f"{h.id} · {_money(h.estimated_value_usd)} · {h.priority} · {h.status}",
            expanded=h.status == "open",
        ):
            st.write(f"**Deal:** `{h.deal_id}`  ·  **Lead:** `{h.lead_id}`")
            st.write(f"**Reason:** {h.reason}")
            st.write(h.summary)
            if h.recommended_next_steps:
                st.markdown("**Next steps**")
                for s in h.recommended_next_steps:
                    st.markdown(f"- {s}")
            if h.status == "open" and st.button("Mark resolved", key=f"res_{h.id}"):
                crm.resolve_handoff(h.id)
                st.success("Resolved")
                st.rerun()


def page_proposals() -> None:
    st.title("Proposals")
    prop_dir = get_settings().data_dir / "proposals"
    files = sorted(prop_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        st.info("No proposals yet.")
        return
    names = [f.name for f in files]
    pick = st.selectbox("Proposal file", names)
    path = prop_dir / pick
    st.caption(str(path))
    st.markdown(path.read_text(encoding="utf-8"))
    st.download_button("Download markdown", path.read_bytes(), file_name=pick)


def page_messages() -> None:
    st.title("Outbound messages")
    crm = get_crm()
    msgs = list(reversed(crm.list_messages() if hasattr(crm, "list_messages") else []))
    if not msgs:
        # fallback read file
        path = get_settings().data_dir / "crm" / "messages.json"
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            st.dataframe(raw[::-1], use_container_width=True, hide_index=True)
        else:
            st.info("No messages.")
        # also show dry-run email files
        email_dir = get_settings().data_dir / "logs" / "emails"
        files = sorted(email_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
        if files:
            st.subheader("Email draft files")
            pick = st.selectbox("Email file", [f.name for f in files])
            st.json(json.loads((email_dir / pick).read_text(encoding="utf-8")))
        return

    st.dataframe(
        [
            {
                "id": m.id,
                "channel": m.channel,
                "status": m.status,
                "subject": m.subject or "",
                "lead_id": m.lead_id,
                "deal_id": m.deal_id or "",
            }
            for m in msgs
        ],
        use_container_width=True,
        hide_index=True,
    )


def page_settings() -> None:
    st.title("Runtime settings (read-only)")
    s = get_settings()
    st.json(
        {
            "company": s.company_name,
            "brand": s.brand_name,
            "email_mode": s.email_mode,
            "dry_run": s.dry_run,
            "email_allow_live": getattr(s, "email_allow_live", False),
            "deal_handoff_threshold_usd": s.deal_handoff_threshold_usd,
            "max_outreach_per_day": s.max_outreach_per_day,
            "xai_model": s.xai_model,
            "xai_base_url": s.xai_base_url,
            "xai_key_set": bool(s.xai_api_key),
            "data_dir": str(s.data_dir),
        }
    )
    st.caption("Edit `.env` / `config/settings.yaml` and restart the UI to apply changes.")


def main() -> None:
    get_settings().ensure_dirs()
    with st.sidebar:
        st.header("MUPO Ops")
        page = st.radio(
            "Page",
            [
                "Overview",
                "Leads",
                "Deals",
                "Handoffs",
                "Proposals",
                "Messages",
                "Settings",
            ],
        )
        st.markdown("---")
        st.caption("Offline demo: `python -m mupo_sales.main demo`")
        st.caption("Live agents: `python -m mupo_sales.main demo --llm`")

    pages = {
        "Overview": page_overview,
        "Leads": page_leads,
        "Deals": page_deals,
        "Handoffs": page_handoffs,
        "Proposals": page_proposals,
        "Messages": page_messages,
        "Settings": page_settings,
    }
    pages[page]()


if __name__ == "__main__":
    main()
