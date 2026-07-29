"""CRM + deterministic demo tests."""

import json
from pathlib import Path

import pytest

from mupo_sales.config import get_settings
from mupo_sales.crm.store import CRMStore
from mupo_sales.memory.knowledge import get_kb
from mupo_sales.tools.crm_tools import create_lead_record
from mupo_sales.tools.proposal_tool import generate_proposal


@pytest.fixture()
def isolated_crm(tmp_path, monkeypatch):
    """Point data_dir at temp so tests don't pollute project data."""
    data = tmp_path / "data"
    (data / "crm").mkdir(parents=True)
    (data / "logs").mkdir(parents=True)
    (data / "proposals").mkdir(parents=True)
    (data / "memory").mkdir(parents=True)

    # Clear settings cache and set env
    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(data))
    get_settings.cache_clear()

    # Reset CRM singleton
    import mupo_sales.crm.store as store_mod

    store_mod._store = None
    yield CRMStore(root=data / "crm")
    store_mod._store = None
    get_settings.cache_clear()


def test_packages_load():
    pkgs = get_kb().load_packages()
    ids = {p["id"] for p in pkgs["packages"]}
    assert "tv_sponsorship" in ids
    assert "tv_membership" in ids


def test_create_lead_and_proposal(isolated_crm, monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(isolated_crm.root.parent))
    get_settings.cache_clear()

    import mupo_sales.crm.store as store_mod

    store_mod._store = isolated_crm

    created = create_lead_record(
        company="Test Co",
        contact_name="Pat Test",
        email="pat@example.com",
        product_interest="tv_sponsorship",
        icp_fit_score=70,
        personalization_facts=["Fact one", "Fact two"],
    )
    deal_id = created["deal"]["id"]
    result = generate_proposal(
        deal_id=deal_id,
        product_id="tv_sponsorship",
        proposed_value=30000,
        executive_summary="Draft summary for Test Co sponsorship.",
        goals_section="Brand awareness via entertainment.",
        fit_rationale="Lifestyle adjacency without invented metrics.",
    )
    assert result["ok"] is True
    assert Path(result["path"]).exists()
    # High ticket should handoff
    assert result.get("human_handoff") is not None
    assert result["human_handoff"]["ok"] is True


def test_deterministic_demo_runs(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for sub in ("crm", "logs", "proposals", "memory"):
        (data / sub).mkdir(parents=True)
    get_settings.cache_clear()
    monkeypatch.setenv("DATA_DIR", str(data))
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("EMAIL_MODE", "dry_run")
    get_settings.cache_clear()

    import mupo_sales.crm.store as store_mod

    store_mod._store = None

    from mupo_sales.crew.sales_crew import run_deterministic_demo

    result = run_deterministic_demo()
    assert result["mode"] == "deterministic_demo"
    assert len(result["leads"]) == 2
    assert result["proposal"]["ok"] is True
    pipeline = json.loads(result["pipeline"])
    assert pipeline["lead_count"] >= 2
