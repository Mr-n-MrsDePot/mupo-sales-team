"""Guardrail unit tests (no LLM required)."""

from mupo_sales.guardrails.compliance import (
    detect_strong_buying_signals,
    requires_human_handoff,
    scan_text,
)


def test_blocks_invented_viewership():
    r = scan_text("We reach 12 million viewers every night on MUPO TV.")
    assert not r.ok
    assert "invented_viewership" in r.violations


def test_blocks_guaranteed_roi():
    r = scan_text("We guarantee ROI within 30 days for sponsors.")
    assert not r.ok


def test_allows_safe_language():
    r = scan_text(
        "We share detailed audience and placement data with qualified partners on a discovery call. "
        "Packages start at $10,000 and are customized after fit is confirmed."
    )
    assert r.ok


def test_allows_disclaimer_not_guarantee_roi():
    r = scan_text(
        "MUPO does not guarantee ROI, sales lift, or specific viewership outcomes. "
        "Final inventory requires human confirmation."
    )
    assert r.ok, r.violations


def test_strong_signals():
    hits = detect_strong_buying_signals("Please send proposal — budget approved for Q3.")
    assert any("proposal" in h or "budget" in h for h in hits)


def test_handoff_threshold():
    needed, reasons = requires_human_handoff(estimated_value_usd=12000)
    assert needed
    assert any("deal_value" in r for r in reasons)


def test_no_handoff_low_ticket():
    needed, reasons = requires_human_handoff(estimated_value_usd=1500, product_requires_human=False)
    assert not needed
