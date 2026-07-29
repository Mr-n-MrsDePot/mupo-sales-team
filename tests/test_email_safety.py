"""Email safety gate tests (no network)."""

from mupo_sales.config import get_settings
from mupo_sales.tools.email_tool import EmailService


def test_live_modes_forced_dry_when_gate_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_MODE", "gmail")
    monkeypatch.setenv("EMAIL_ALLOW_LIVE", "false")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    svc = EmailService()
    assert svc._effective_mode() == "dry_run"


def test_live_mode_only_when_both_gates_open(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_MODE", "instantly")
    monkeypatch.setenv("EMAIL_ALLOW_LIVE", "true")
    monkeypatch.setenv("DRY_RUN", "false")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    svc = EmailService()
    assert svc._effective_mode() == "instantly"


def test_dry_run_send_never_marks_sent(monkeypatch, tmp_path):
    monkeypatch.setenv("EMAIL_MODE", "gmail")
    monkeypatch.setenv("EMAIL_ALLOW_LIVE", "false")
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    get_settings.cache_clear()

    svc = EmailService()
    result = svc.send(
        to_email="prospect@example.com",
        subject="Hello from MUPO",
        body=(
            "Hi there,\n\nWe share detailed audience and placement data with qualified "
            "partners on a discovery call. Packages start after fit is confirmed.\n\n"
            "Best,\nMUPO TV\nUnsubscribe: reply STOP\n"
        ),
        lead_id="lead_test",
        force=True,
    )
    assert result["ok"] is True
    assert result["status"] == "dry_run"
