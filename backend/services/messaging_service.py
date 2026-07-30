"""WhatsApp messaging — provider-based so a future WhatsApp Business API
integration (delivery tracking, read receipts, templates, scheduled sends)
can replace `WhatsAppDeepLinkProvider` without touching any caller.
Phase 1 (current): deep link only — the salesperson reviews and sends the
pre-filled message manually, nothing is auto-sent.

Do NOT special-case WhatsApp elsewhere in the codebase — everything that
needs an outbound message goes through `build_message()` below so a future
SMS/other channel provider is a one-file change.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import quote_plus

# {placeholder} keys are filled from the `context` dict passed to
# build_message() — missing keys are rendered as an empty string rather than
# raising, so a template never crashes a follow-up action over a missing
# optional field (e.g. no quotation_number yet).
TEMPLATES: dict[str, str] = {
    "walk_in": (
        "Hello {customer_name}, thank you for visiting BuildCon House. We wanted to follow up "
        "regarding your visit. Please let us know if you'd like to schedule your tile selection."
    ),
    "selection": (
        "Hello {customer_name}, your tile selection has been completed. We'd be happy to prepare "
        "your quotation. Please let us know a convenient time to discuss it."
    ),
    "quotation": (
        "Hello {customer_name}, we hope you've had a chance to review Quotation {quotation_number}. "
        "Please let us know if you have any questions or would like any revisions."
    ),
    "payment": (
        "Hello {customer_name}, this is a friendly reminder regarding the pending payment of "
        "₹{outstanding_amount} for your order. Please contact us if you need any assistance."
    ),
    "general": "Hi {customer_name}, {reason}",
}


class _SafeDict(dict):
    def __missing__(self, key):  # noqa: D105
        return ""


def render_template(category: str, context: dict) -> str:
    tpl = TEMPLATES.get(category, TEMPLATES["general"])
    return tpl.format_map(_SafeDict(context))


class MessagingProvider(ABC):
    @abstractmethod
    def build_link(self, phone: Optional[str], message: str) -> str: ...


class WhatsAppDeepLinkProvider(MessagingProvider):
    """Phase 1 provider — opens wa.me with the message pre-filled. No send,
    no delivery tracking, no credentials required."""

    def build_link(self, phone: Optional[str], message: str) -> str:
        digits = "".join(c for c in (phone or "") if c.isdigit())
        return f"https://wa.me/{digits}?text={quote_plus(message)}" if digits else f"https://wa.me/?text={quote_plus(message)}"


_provider: MessagingProvider = WhatsAppDeepLinkProvider()


def build_message(category: str, phone: Optional[str], context: dict) -> dict:
    message = render_template(category, context)
    return {"message": message, "url": _provider.build_link(phone, message)}
