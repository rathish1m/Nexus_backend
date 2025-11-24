from datetime import timedelta
from decimal import Decimal

import pytest

from django.utils import timezone

from billing_management.billing_services import (
    ZERO,
    add_months,
    apply_wallet_to_order,
    create_or_get_subscription_renewal_invoice,
    due_for_ref,
    enforce_cutoff,
    ensure_first_order_invoice_entry,
    months_for_cycle,
    order_external_ref,
    run_prebill,
)
from main.factories import (
    OrderFactory,
    SubscriptionFactory,
    SubscriptionPlanFactory,
    UserFactory,
)
from main.models import AccountEntry, BillingConfig


@pytest.mark.django_db
def test_apply_wallet_to_order_partially_pays_invoice():
    user = UserFactory()
    order = OrderFactory(user=user, total_price=Decimal("100.00"))
    extref = order_external_ref(order)

    # Seed ledger with a single invoice entry for this order.
    AccountEntry.objects.create(
        account=user.billing_account,
        entry_type="invoice",
        amount_usd=Decimal("100.00"),
        description="Test invoice",
        order=order,
        external_ref=extref,
    )

    # Top up wallet with less than the amount due.
    wallet = user.wallet
    wallet.add_funds(Decimal("40.00"), note="Test top-up", order=order)

    applied = apply_wallet_to_order(user, order)

    assert applied == Decimal("40.00")
    wallet.refresh_from_db()
    assert wallet.balance == ZERO

    # Ledger should now show only 60 USD due for this order.
    remaining_due = due_for_ref(user, extref)
    assert remaining_due == Decimal("60.00")


@pytest.mark.django_db
def test_ensure_first_order_invoice_entry_idempotent():
    user = UserFactory()
    order = OrderFactory(user=user, total_price=Decimal("100.00"))

    # Create a simple line and tax snapshot to give a non-zero total.
    ensure_first_order_invoice_entry(order)

    extref = order_external_ref(order)
    qs = AccountEntry.objects.filter(
        account=user.billing_account,
        entry_type="invoice",
        external_ref=extref,
    )
    assert qs.count() == 1

    # Calling again must not create a duplicate invoice entry.
    ensure_first_order_invoice_entry(order)
    assert qs.count() == 1


@pytest.mark.django_db
def test_create_or_get_subscription_renewal_invoice_creates_and_applies_wallet():
    # Fixed, predictable plan price for assertions.
    plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("100.00"))
    sub = SubscriptionFactory(plan=plan, billing_cycle="monthly")
    sub.user.is_tax_exempt = True
    sub.user.save()

    today = timezone.now().date()
    sub.next_billing_date = today
    sub.save()

    # Seed wallet with 40 USD and let tax logic return zero (tax-exempt).
    wallet = sub.user.wallet
    wallet.add_funds(Decimal("40.00"), note="Top-up")

    order, created, applied, total = create_or_get_subscription_renewal_invoice(sub)

    assert created is True
    assert total == Decimal("100.00")
    assert applied == Decimal("40.00")
    assert order.user == sub.user

    # Ledger should now have one invoice and one payment for this subscription period.
    period_start = sub.next_billing_date
    period_end = add_months(period_start, months_for_cycle(sub.billing_cycle))
    invoice_qs = AccountEntry.objects.filter(
        subscription=sub,
        entry_type="invoice",
        period_start=period_start,
        period_end=period_end,
    )
    extref = order_external_ref(order)
    payment_qs = AccountEntry.objects.filter(
        account=sub.user.billing_account,
        entry_type="payment",
        order=order,
        external_ref=extref,
    )
    assert invoice_qs.count() == 1
    assert payment_qs.count() == 1


@pytest.mark.django_db
def test_create_or_get_subscription_renewal_invoice_idempotent():
    plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("50.00"))
    sub = SubscriptionFactory(plan=plan, billing_cycle="monthly")
    sub.user.is_tax_exempt = True
    sub.user.save()
    sub.next_billing_date = timezone.now().date()
    sub.save()

    # First call creates the invoice.
    order_1, created_1, applied_1, total_1 = create_or_get_subscription_renewal_invoice(
        sub
    )
    # Second call should reuse the existing invoice and not create a new one.
    order_2, created_2, applied_2, total_2 = create_or_get_subscription_renewal_invoice(
        sub
    )

    assert order_1 == order_2
    assert created_1 is True
    assert created_2 is False
    assert total_1 == total_2
    # No additional wallet application on the reused path.
    assert applied_2 == ZERO


@pytest.mark.django_db
def test_run_prebill_creates_invoice_for_subscription_in_window():
    # Configure billing so that a subscription with next_billing_date = today + 1
    # is inside the prebill window.
    cfg = BillingConfig.get()
    cfg.prebill_lead_days = 5
    cfg.invoice_start_date = None
    cfg.save()

    plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("80.00"))
    sub = SubscriptionFactory(plan=plan, billing_cycle="monthly")
    sub.user.is_tax_exempt = True
    sub.user.save()
    today = timezone.now().date()
    sub.next_billing_date = today + timedelta(days=1)
    sub.save()

    processed, created = run_prebill([sub])
    assert processed == 1
    assert created == 1


@pytest.mark.django_db
def test_run_prebill_dry_run_does_not_create_invoices():
    cfg = BillingConfig.get()
    cfg.prebill_lead_days = 5
    cfg.invoice_start_date = None
    cfg.save()

    plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("80.00"))
    sub = SubscriptionFactory(plan=plan, billing_cycle="monthly")
    sub.user.is_tax_exempt = True
    sub.user.save()
    today = timezone.now().date()
    sub.next_billing_date = today + timedelta(days=1)
    sub.save()

    processed, created = run_prebill([sub], dry_run=True)
    assert processed == 1
    assert created == 0

    # No billing entries should have been created.
    assert not AccountEntry.objects.filter(subscription=sub).exists()


@pytest.mark.django_db
def test_enforce_cutoff_suspends_unpaid_subscription():
    cfg = BillingConfig.get()
    cfg.cutoff_days_before_anchor = 1
    cfg.auto_suspend_on_cutoff = True
    cfg.save()

    plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("100.00"))
    sub = SubscriptionFactory(plan=plan, billing_cycle="monthly")
    sub.user.is_tax_exempt = True
    sub.user.save()

    today = timezone.now().date()
    # Set next_billing_date so that cutoff date == today.
    sub.next_billing_date = today + timedelta(days=1)
    sub.save()

    # Create an unpaid invoice for the current period.
    period_start = sub.next_billing_date
    period_end = add_months(period_start, months_for_cycle(sub.billing_cycle))
    order = OrderFactory(user=sub.user, total_price=Decimal("100.00"))
    extref = order_external_ref(order)

    AccountEntry.objects.create(
        account=sub.user.billing_account,
        entry_type="invoice",
        amount_usd=Decimal("100.00"),
        description="Renewal invoice",
        order=order,
        subscription=sub,
        period_start=period_start,
        period_end=period_end,
        external_ref=extref,
    )

    checked, suspended = enforce_cutoff(
        type(sub).objects.filter(pk=sub.pk), dry_run=False
    )

    sub.refresh_from_db()
    assert checked == 1
    assert suspended == 1
    assert sub.status == "suspended"


@pytest.mark.django_db
def test_enforce_cutoff_skips_paid_subscription():
    cfg = BillingConfig.get()
    cfg.cutoff_days_before_anchor = 1
    cfg.auto_suspend_on_cutoff = True
    cfg.save()

    plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("60.00"))
    sub = SubscriptionFactory(plan=plan, billing_cycle="monthly")
    sub.user.is_tax_exempt = True
    sub.user.save()

    today = timezone.now().date()
    sub.next_billing_date = today + timedelta(days=1)
    sub.save()

    period_start = sub.next_billing_date
    period_end = add_months(period_start, months_for_cycle(sub.billing_cycle))
    order = OrderFactory(user=sub.user, total_price=Decimal("60.00"))
    extref = order_external_ref(order)

    # Create a fully paid invoice for the current period.
    AccountEntry.objects.create(
        account=sub.user.billing_account,
        entry_type="invoice",
        amount_usd=Decimal("60.00"),
        description="Renewal invoice",
        order=order,
        subscription=sub,
        period_start=period_start,
        period_end=period_end,
        external_ref=extref,
    )
    AccountEntry.objects.create(
        account=sub.user.billing_account,
        entry_type="payment",
        amount_usd=Decimal("-60.00"),
        description="Payment for renewal",
        order=order,
        subscription=sub,
        period_start=period_start,
        period_end=period_end,
        external_ref=extref,
    )

    checked, suspended = enforce_cutoff(
        type(sub).objects.filter(pk=sub.pk), dry_run=False
    )

    sub.refresh_from_db()
    assert checked == 1
    assert suspended == 0
    assert sub.status == "active"
