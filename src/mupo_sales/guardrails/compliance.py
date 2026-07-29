"""
Compliance guardrails for MUPO sales content.

Scans agent outputs for forbidden claims and enforces human-handoff rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from mupo_sales.config import get_business_rules, get_handoff_threshold, get_settings

# Patterns that often indicate invented metrics / overclaims
_FORBIDDEN_PATTERNS: list[tuple[str, str]] = [
    (r"\b\d+(\.\d+)?\s*(million|m)\s+(viewers|impressions|households)\b", "invented_viewership"),
    (r"\bguaranteed?\s+(roi|return|sales|results)\b", "guaranteed_roi"),
    (r"\b\d+x\s+(roi|return|revenue)\b", "multiplier_roi"),
    (r"\bnielsen\s+rating\b", "nielsen_claim"),
    (r"\b#1\s+(network|channel|show)\b", "ranking_claim"),
    (r"\bguaranteed\s+placement\b", "guaranteed_placement"),
    (r"\bwe\s+have\s+\d+\s*(million|k|m)\b", "audience_size_claim"),
]

_STRONG_SIGNAL_DEFAULTS = [
    "send proposal",
    "ready to buy",
    "budget approved",
    "decision maker available",
    "want to schedule call",
    "send contract",
    "invoice",
    "purchase order",
    "let's move forward",
    "we're interested in buying",
    "can you draft an agreement",
]


@dataclass
class GuardrailResult:
    ok: bool
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    sanitized_text: str | None = None
    requires_human: bool = False
    human_reasons: list[str] = field(default_factory=list)


def _is_negated_claim(text: str, match_start: int) -> bool:
    """True if match is inside a disclaimer / negation window (e.g. 'does not guarantee ROI')."""
    window = text[max(0, match_start - 48) : match_start].lower()
    neg_markers = (
        "not ",
        "no ",
        "never ",
        "don't ",
        "does not ",
        "do not ",
        "without ",
        "cannot ",
        "can't ",
        "≠",
        "disclaim",
    )
    return any(m in window for m in neg_markers)


def scan_text(text: str) -> GuardrailResult:
    """Scan marketing/sales text for compliance issues."""
    violations: list[str] = []
    warnings: list[str] = []
    lower = text.lower()

    for pattern, code in _FORBIDDEN_PATTERNS:
        for m in re.finditer(pattern, lower, flags=re.IGNORECASE):
            if _is_negated_claim(lower, m.start()):
                continue
            violations.append(code)
            break

    # Soft checks — affirmative ROI promises only
    if "roi" in lower:
        for m in re.finditer(r"\b(will|guarantee|ensure|promise).{0,40}roi\b", lower):
            if _is_negated_claim(lower, m.start()):
                continue
            violations.append("roi_promise")
            break

    if re.search(r"\b(closing tonight|only \d+ spots left today)\b", lower):
        warnings.append("possible_false_scarcity")

    # Dedupe while preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for v in violations:
        if v not in seen:
            seen.add(v)
            uniq.append(v)
    violations = uniq

    ok = len(violations) == 0
    return GuardrailResult(ok=ok, violations=violations, warnings=warnings, sanitized_text=text if ok else None)


def detect_strong_buying_signals(text: str) -> list[str]:
    rules = get_business_rules()
    signals = [s.lower() for s in rules.get("strong_buying_signals", _STRONG_SIGNAL_DEFAULTS)]
    lower = text.lower()
    hit = [s for s in signals if s in lower]
    return hit


def requires_human_handoff(
    *,
    estimated_value_usd: float = 0.0,
    product_requires_human: bool = False,
    prospect_message: str | None = None,
    agent_uncertainty: bool = False,
    legal_or_contract: bool = False,
) -> tuple[bool, list[str]]:
    """Return (required, reasons)."""
    reasons: list[str] = []
    threshold = get_handoff_threshold()
    settings = get_settings()

    if estimated_value_usd >= threshold:
        reasons.append(f"deal_value_ge_{threshold:g}")

    if product_requires_human:
        reasons.append("product_requires_human_close")

    if prospect_message:
        signals = detect_strong_buying_signals(prospect_message)
        if signals and settings.strong_signal_notify:
            reasons.append(f"strong_signals:{','.join(signals)}")
        if re.search(r"\b(contract|msa|insertion order|io\b|legal|nda)\b", prospect_message, re.I):
            legal_or_contract = True

    if legal_or_contract:
        reasons.append("legal_or_contract_request")

    if agent_uncertainty:
        reasons.append("agent_uncertainty")

    return (len(reasons) > 0, reasons)


def email_footer() -> str:
    s = get_settings()
    return (
        f"\n\n--\n"
        f"{s.sales_from_name}\n"
        f"{s.brand_name} | {s.company_name}\n"
        f"Founded by {s.founder_name}\n"
        f"123 Entertainment Way, Suite 100, [City, ST ZIP]  # replace with real address\n"
        f"Unsubscribe: reply STOP or email unsubscribe@mupotv.example\n"
        f"This message may be AI-assisted; a human partnership lead handles contracts and high-ticket closes.\n"
    )


def enforce_email_compliance(body: str, subject: str) -> GuardrailResult:
    """Scan email and append footer if missing unsubscribe language."""
    result = scan_text(f"{subject}\n{body}")
    if "unsubscribe" not in body.lower() and "stop" not in body.lower():
        body = body.rstrip() + email_footer()
        result.warnings.append("footer_appended")
    result.sanitized_text = body if result.ok else None
    if result.ok:
        result.sanitized_text = body
    return result


def product_requires_human(product_id: str | None, packages: dict[str, Any] | None = None) -> bool:
    if not product_id:
        return False
    # From packages knowledge
    if packages:
        for p in packages.get("packages", []):
            if p.get("id") == product_id:
                return bool(p.get("requires_human_close", False))
    # Fallback thresholds by known high-ticket ids
    return product_id in {"tv_sponsorship", "commercial_30s", "artist_dev"}
