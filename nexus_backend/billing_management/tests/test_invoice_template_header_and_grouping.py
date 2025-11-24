from decimal import Decimal

import pytest

from django.template.loader import render_to_string
from django.utils import timezone

from billing_management.views import _build_invoice_context
from main.models import CompanySettings, Invoice, InvoiceLine, Order


@pytest.mark.django_db
def test_header_title_subtitle_and_no_rccm_link(user_factory):
    # Arrange company settings
    cs, _ = CompanySettings.objects.get_or_create(
        id=1,
        defaults={
            "legal_name": "Nexus Telecoms SA",
            "trade_name": "Nexus Telecoms SA",
            "street_address": "8273, Avenue Lukonzolwa",
            "city": "Lubumbashi",
            "province": "Katanga Province",
            "country": "DRC",
            "email": "billing@nexus.cd",
            "phone": "+243 900 000 000",
            "rccm": "CD/LSH/RCCM/25-B-00807",
            "default_currency": "USD",
        },
    )

    user = user_factory(username="headertest")
    inv = Invoice.objects.create(
        user=user,
        number="INV-HEAD-001",
        currency="USD",
        status=Invoice.Status.ISSUED,
        issued_at=timezone.now(),
        due_at=timezone.now(),
    )

    # Minimal one line to allow rendering paths that show items table
    order = Order.objects.create(order_reference="ORD-HT-001")
    InvoiceLine.objects.create(
        invoice=inv,
        order=order,
        description="Any",
        quantity=Decimal("1.00"),
        unit_price=Decimal("1.00"),
    )

    context = _build_invoice_context(inv, cs)
    html = render_to_string("invoices/inv_templates.html", context)

    assert "INVOICE · FACTURE" in html
    assert "Tax Invoice · Facture fiscale · Currency/Devise: USD" in html
    # Ensure the removed RCCM right-column link/class is absent
    assert "rccm-link" not in html


@pytest.mark.django_db
def test_skip_duplicate_order_header_like_zero_lines(user_factory):
    # Arrange
    cs, _ = CompanySettings.objects.get_or_create(id=1)
    user = user_factory(username="duptest")
    inv = Invoice.objects.create(
        user=user,
        number="INV-DUP-001",
        currency="USD",
        status=Invoice.Status.ISSUED,
        issued_at=timezone.now(),
    )

    # Two orders
    o1 = Order.objects.create(order_reference="ORD-001")
    o2 = Order.objects.create(order_reference="ORD-002")

    # Inject header-like zero lines (should be skipped by template)
    for o in (o1, o2):
        InvoiceLine.objects.create(
            invoice=inv,
            order=o,
            description=f"Order {o.order_reference}",
            quantity=Decimal("0"),
            unit_price=Decimal("0"),
            line_total=Decimal("0.00"),
        )

    # Real items per order (should be rendered)
    InvoiceLine.objects.create(
        invoice=inv,
        order=o1,
        description="Kit",
        quantity=Decimal("1.00"),
        unit_price=Decimal("10.00"),
        line_total=Decimal("10.00"),
    )
    InvoiceLine.objects.create(
        invoice=inv,
        order=o2,
        description="Plan",
        quantity=Decimal("1.00"),
        unit_price=Decimal("20.00"),
        line_total=Decimal("20.00"),
    )

    context = _build_invoice_context(inv, cs)
    html = render_to_string("invoices/inv_templates.html", context)

    # The group header renders one "Order ORD-XXX" line per group.
    # We must NOT render the second duplicate header-like item line.
    assert html.count("Order ORD-001") == 1
    assert html.count("Order ORD-002") == 1


def test_bank_accounts_usd_cdf_and_swift_label(user_factory):
    cs, _ = CompanySettings.objects.get_or_create(
        id=1,
        defaults={
            "legal_name": "Nexus Telecoms SA",
            "trade_name": "Nexus Telecoms SA",
            "bank_name": "Rawbank",
            "bank_account_name": "Nexus Telecoms SA",
            "bank_account_number_usd": "05100-05130-01146609001-26",
            "bank_account_number_cdf": "00000-00000-00000000000-00",
            "bank_swift": "RBCDCDKIXXX",
        },
    )

    user = user_factory(username="banktest")
    inv = Invoice.objects.create(
        user=user,
        number="INV-BNK-001",
        currency="USD",
        status=Invoice.Status.ISSUED,
    )

    # Minimal line to render the table
    o = Order.objects.create(order_reference="ORD-BNK-001")
    InvoiceLine.objects.create(
        invoice=inv,
        order=o,
        description="Any",
        quantity=Decimal("1.00"),
        unit_price=Decimal("1.00"),
    )

    ctx = _build_invoice_context(inv, cs)
    html = render_to_string("invoices/inv_templates.html", ctx)

    assert "Account Number (USD):" in html
    assert "05100-05130-01146609001-26" in html
    assert "Account Number (CDF):" in html
    assert "SWIFT/BIC:" in html
