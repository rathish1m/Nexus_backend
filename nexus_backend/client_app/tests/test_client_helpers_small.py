import pytest
from decimal import Decimal
from datetime import timedelta

from django.utils import timezone

from main.factories import OrderFactory, UserFactory
from main.models import AccountEntry, OrderLine, OrderTax, TaxRate

from client_app.client_helpers import (
    ZERO,
    compute_local_expiry_from_coords,
    get_or_create_account,
    order_amount_components,
    post_account_entry_once,
    price_order_from_lines,
)


@pytest.mark.django_db
def test_order_amount_components_aggregates_lines_and_taxes():
    user = UserFactory()
    order = OrderFactory(user=user)

    # Create line items
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.KIT,
        description="Kit",
        quantity=1,
        unit_price=Decimal("100.00"),
    )
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.PLAN,
        description="Plan",
        quantity=2,
        unit_price=Decimal("25.00"),
    )
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.INSTALL,
        description="Install",
        quantity=1,
        unit_price=Decimal("10.00"),
    )

    # Create tax snapshot rows
    OrderTax.objects.create(
        order=order,
        kind=OrderTax.Kind.VAT,
        rate=Decimal("16.00"),
        amount=Decimal("8.00"),
    )
    OrderTax.objects.create(
        order=order,
        kind=OrderTax.Kind.EXCISE,
        rate=Decimal("10.00"),
        amount=Decimal("5.00"),
    )

    components = order_amount_components(order)

    assert components["kit"] == Decimal("100.00")
    assert components["plan"] == Decimal("50.00")  # 2 * 25
    assert components["install"] == Decimal("10.00")
    assert components["vat"] == Decimal("8.00")
    assert components["exc"] == Decimal("5.00")


@pytest.mark.django_db
def test_post_account_entry_once_is_idempotent_for_same_natural_key():
    user = UserFactory()
    # Use the same helper as production code to avoid OneToOne collisions
    acct = get_or_create_account(user)

    amount = Decimal("100.00")
    desc = "Initial invoice"

    e1 = post_account_entry_once(
        account=acct,
        entry_type="invoice",
        amount=amount,
        description=desc,
        order=None,
    )
    # Second call with exactly same tuple should not create a new row
    e2 = post_account_entry_once(
        account=acct,
        entry_type="invoice",
        amount=amount,
        description=desc,
        order=None,
    )

    assert e1 is not None
    assert e2 is None
    assert (
        AccountEntry.objects.filter(
            account=acct, entry_type="invoice", amount_usd=amount, description=desc
        ).count()
        == 1
    )

    # Changing description should create a distinct entry
    e3 = post_account_entry_once(
        account=acct,
        entry_type="invoice",
        amount=amount,
        description="Different",
        order=None,
    )
    assert e3 is not None
    assert (
        AccountEntry.objects.filter(
            account=acct, entry_type="invoice", amount_usd=amount
        ).count()
        == 2
    )


@pytest.mark.django_db
def test_price_order_from_lines_without_tax_rates_uses_subtotal_only():
    user = UserFactory()
    order = OrderFactory(user=user)

    # Ensure no TaxRate rows so only subtotal is used
    TaxRate.objects.all().delete()

    # Create a single line of 3 * 20 = 60
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.PLAN,
        description="Plan",
        quantity=3,
        unit_price=Decimal("20.00"),
    )

    result = price_order_from_lines(order)

    assert result["subtotal"] == Decimal("60.00")
    assert result["tax_total"] == ZERO
    assert result["total"] == Decimal("60.00")
    order.refresh_from_db()
    assert order.total_price == Decimal("60.00")


@pytest.mark.django_db
def test_compute_local_expiry_from_coords_falls_back_to_utc(monkeypatch):
    # Force TimezoneFinder to fail resolving a timezone so we hit the UTC fallback path
    from client_app import client_helpers as ch
    from timezonefinder import TimezoneFinder

    original_tf = ch.tf
    ch.tf = TimezoneFinder()
    monkeypatch.setattr(TimezoneFinder, "timezone_at", lambda self, lng, lat: None)

    fixed_now = timezone.now()
    monkeypatch.setattr("client_app.client_helpers.timezone.now", lambda: fixed_now)

    try:
        expires_at = compute_local_expiry_from_coords(lat=0.0, lng=0.0, hours=2)
    finally:
        ch.tf = original_tf

    assert expires_at.tzinfo is not None
    assert expires_at == fixed_now + timedelta(hours=2)
