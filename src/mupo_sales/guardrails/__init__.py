from mupo_sales.guardrails.compliance import (
    GuardrailResult,
    detect_strong_buying_signals,
    email_footer,
    enforce_email_compliance,
    product_requires_human,
    requires_human_handoff,
    scan_text,
)

__all__ = [
    "GuardrailResult",
    "detect_strong_buying_signals",
    "email_footer",
    "enforce_email_compliance",
    "product_requires_human",
    "requires_human_handoff",
    "scan_text",
]
