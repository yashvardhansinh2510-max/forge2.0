"""Email — provider-based, same shape as services/messaging_service.py, so
Quotations, Payments, Dispatch or any future module can share one
implementation. Phase 1 (current): `mailto:` deep link only — the
salesperson reviews and sends manually via their own mail client. Swapping
to a transactional provider (e.g. Resend) later means adding one new
EmailProvider subclass, not touching any caller.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import quote

TEMPLATES: dict[str, dict[str, str]] = {
    "quotation": {
        "subject": "Your BuildCon House Quotation - {quotation_number}",
        "body": (
            "Dear {customer_name},\n\n"
            "Please find your quotation {quotation_number} for your review.\n\n"
            "Salesperson: {salesperson_name}\n\n"
            "Thank you for choosing BuildCon House.\n"
            "BuildCon House · buildconhouse.example"
        ),
    },
    "payment_reminder": {
        "subject": "Payment Reminder - {invoice_number}",
        "body": (
            "Dear {customer_name},\n\n"
            "This is a friendly reminder that ₹{outstanding_amount} is outstanding against "
            "order {order_number}.\n\n"
            "Salesperson: {salesperson_name}\n\n"
            "Kindly arrange payment at your convenience. Thank you!\n"
            "BuildCon House"
        ),
    },
    "invoice": {
        "subject": "Invoice - {invoice_number}",
        "body": (
            "Dear {customer_name},\n\n"
            "Please find attached the invoice {invoice_number} for order {order_number}.\n\n"
            "Salesperson: {salesperson_name}\n\n"
            "BuildCon House"
        ),
    },
}


class _SafeDict(dict):
    def __missing__(self, key):  # noqa: D105
        return ""


def render_template(template_key: str, context: dict) -> dict:
    tpl = TEMPLATES.get(template_key, TEMPLATES["quotation"])
    return {
        "subject": tpl["subject"].format_map(_SafeDict(context)),
        "body": tpl["body"].format_map(_SafeDict(context)),
    }


class EmailProvider(ABC):
    @abstractmethod
    def build_link(self, to: Optional[str], subject: str, body: str) -> str: ...


class MailtoProvider(EmailProvider):
    def build_link(self, to: Optional[str], subject: str, body: str) -> str:
        return f"mailto:{to or ''}?subject={quote(subject)}&body={quote(body)}"


_provider: EmailProvider = MailtoProvider()


def build_email(template_key: str, to: Optional[str], context: dict) -> dict:
    rendered = render_template(template_key, context)
    return {**rendered, "mailto_url": _provider.build_link(to, rendered["subject"], rendered["body"])}
