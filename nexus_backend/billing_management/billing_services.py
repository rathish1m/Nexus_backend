# your_app/helpers.py
from calendar import monthrange
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable, Optional, Tuple

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from main.models import (
    AccountEntry,
    BillingConfig,
    Order,
    OrderLine,
    OrderTax,
    Subscription,
    TaxRate,
    Wallet,
)
from main.services.posting import create_entry

ZERO = Decimal("0.00")


# ---------- Money ----------
def q(x: Decimal) -> Decimal:
    """Quantize to 2dp with HALF_UP (invoice-friendly)."""
    return (x or ZERO).quantize(ZERO, rounding=ROUND_HALF_UP)


# ---------- Cycles & Anchors ----------
def months_for_cycle(cycle: str) -> int:
    cycle = (cycle or "monthly").lower()
    return {"monthly": 1, "quarterly": 3, "yearly": 12}.get(cycle, 1)


def add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    day = min(d.day, monthrange(y, m)[1])
    return date(y, m, day)


def _anchor_for(d: date, anchor_day: int) -> date:
    last = monthrange(d.year, d.month)[1]
    return date(d.year, d.month, min(anchor_day, last))


def next_anchor(d: date, anchor_day: int) -> date:
    a = _anchor_for(d, anchor_day)
    if d <= a:
        return a
    y = d.year + (1 if d.month == 12 else 0)
    m = 1 if d.month == 12 else d.month + 1
    return _anchor_for(date(y, m, 1), anchor_day)


def anchor_window(d: date, anchor_day: int):
    """Return (prev_anchor, next_anchor) surrounding date d."""
    this_anchor = _anchor_for(d, anchor_day)
    if d > this_anchor:
        prev_anchor = this_anchor
        y = d.year + (1 if d.month == 12 else 0)
        m = 1 if d.month == 12 else d.month + 1
        nxt = _anchor_for(date(y, m, 1), anchor_day)
        return prev_anchor, nxt
    else:
        nxt = this_anchor
        y = d.year - (1 if d.month == 1 else 0)
        m = 12 if d.month == 1 else d.month - 1
        prev_anchor = _anchor_for(date(y, m, 1), anchor_day)
        return prev_anchor, nxt


# ---------- Taxes ----------


# ---------- Taxes ----------
# NOTE: No whitelist anymore — tax-exempt means exempt from ALL taxes.
def is_tax_applicable(user, tax_code: str) -> bool:
    """
    Return False for all taxes if user.is_tax_exempt is True.
    """
    return not bool(getattr(user, "is_tax_exempt", False))


def tax_rate(code: str, *, user=None) -> Decimal:
    """
    Returns a decimal fraction (e.g. 0.1600 for 16%). If the user is tax-exempt,
    returns 0 for any tax code.
    """
    if not is_tax_applicable(user, code):
        return ZERO
    try:
        r = TaxRate.objects.filter(description=code).latest("id")
        pct = r.percentage or ZERO
    except TaxRate.DoesNotExist:
        pct = ZERO
    return (pct / Decimal("100.00")).quantize(Decimal("0.0001"))


def _tax_config():
    """
    Central place to derive tax configuration from DB (or settings).
    - vat_on_excise: True => VAT is applied on (base + excise); False => VAT on base only.
    """
    try:
        cfg = BillingConfig.get()
        # Example: reuse an existing boolean or add one: vat_on_excise = models.BooleanField(default=True)
        vat_on_excise = getattr(cfg, "vat_on_excise", True)  # default to compound VAT
    except Exception:
        vat_on_excise = True
    return {"vat_on_excise": vat_on_excise}


def split_amounts_for_base(base: Decimal, *, user):
    """
    Returns (base, excise, vat, total).

    Definitions:
      - excise is applied ON BASE.
      - VAT can be configured:
          * vat_on_excise=True  -> VAT on (base + excise)  [compound VAT]
          * vat_on_excise=False -> VAT on base only        [simple VAT]
    """
    cfg = _tax_config()

    base = q(base)
    exc_rate = tax_rate("EXCISE", user=user)
    vat_rate = tax_rate("VAT", user=user)

    exc = q(base * exc_rate)

    vat_base = (base + exc) if cfg["vat_on_excise"] else base
    vat = q(vat_base * vat_rate)

    total = q(base + exc + vat)
    return base, exc, vat, total


# ---------- Ledger / Wallet ----------
def order_external_ref(order: Order) -> str:
    return f"order:{order.pk}"


def due_for_ref(user, extref: str) -> Decimal:
    acc = user.billing_account
    s = (
        acc.entries.filter(external_ref=extref).aggregate(s=Sum("amount_usd"))["s"]
        or ZERO
    )
    return s if s > 0 else ZERO


def ensure_first_order_invoice_entry(order: Order) -> None:
    """
    Ensure exactly one invoice-style AccountEntry for the original order.
    (No new document is created; the ledger mirrors the order totals.)
    """
    extref = order_external_ref(order)
    if AccountEntry.objects.filter(external_ref=extref, entry_type="invoice").exists():
        return

    lines_total = order.lines.aggregate(s=Sum("line_total"))["s"] or ZERO
    taxes_total = order.taxes.aggregate(s=Sum("amount"))["s"] or ZERO
    grand_total = q(lines_total + taxes_total)

    create_entry(
        account=order.user.billing_account,
        entry_type="invoice",
        amount_usd=grand_total,
        description=f"Order {order.order_reference or order.id}",
        order=order,
        external_ref=extref,
    )


def apply_wallet_to_order(user, order: Order, *, max_amount=None) -> Decimal:
    """
    Apply up to max_amount (or remaining due) from wallet to the order’s ledger.
    Returns the applied amount.
    """
    extref = order_external_ref(order)
    due = due_for_ref(user, extref)
    if due <= 0:
        return ZERO

    wallet: Wallet = user.wallet
    wallet.refresh_from_db(fields=["balance"])
    if wallet.balance <= 0:
        return ZERO

    to_apply = min(wallet.balance, due, (max_amount or due))
    if to_apply <= 0:
        return ZERO

    wallet.charge(to_apply, note=f"Applied to {extref}", order=order)
    create_entry(
        account=user.billing_account,
        entry_type="payment",
        amount_usd=q(-to_apply),
        description=f"Wallet applied to {extref}",
        order=order,
        external_ref=extref,
    )
    return q(to_apply)


__all__ = [
    "ZERO",
    "q",
    "months_for_cycle",
    "add_months",
    "next_anchor",
    "anchor_window",
    "is_tax_applicable",
    "tax_rate",
    "split_amounts_for_base",
    "order_external_ref",
    "due_for_ref",
    "ensure_first_order_invoice_entry",
    "apply_wallet_to_order",
]


def _renewal_description(sub: Subscription, start: date, end: date) -> str:
    return f"Subscription renewal: {sub.plan.name} ({start:%Y-%m-%d} → {end:%Y-%m-%d})"


@transaction.atomic
def create_or_get_subscription_renewal_invoice(sub: Subscription):
    """
    Idempotently create the renewal Order + Invoice (AccountEntry) for the next period
    and apply wallet immediately. Returns (order, created: bool, applied: Decimal, total: Decimal).
    """
    if sub.status not in {"active", "suspended"}:
        return None, False, ZERO, ZERO
    if not sub.next_billing_date:
        return None, False, ZERO, ZERO

    period_start = sub.next_billing_date
    months = months_for_cycle(sub.billing_cycle)
    period_end = add_months(period_start, months)

    # If an invoice for this subscription+period already exists, reuse it
    existing = (
        AccountEntry.objects.filter(
            subscription=sub,
            entry_type="invoice",
            period_start=period_start,
            period_end=period_end,
        )
        .select_related("order")
        .first()
    )
    if existing:
        order = existing.order
        total = q(existing.amount_usd)
        applied_now = ZERO
        if order:
            applied_now = apply_wallet_to_order(sub.user, order, max_amount=total)
            _ensure_adjust_line_for_wallet(order, applied_now)
            _maybe_close_order_if_fully_paid(order)
        if not sub.last_billed_at:
            sub.last_billed_at = period_start
            sub.save(update_fields=["last_billed_at"])
        return order, False, applied_now, total

    # ---------- Create Order ----------
    order = Order.objects.create(
        user=sub.user,
        plan=sub.plan,
        status="pending_payment",
        payment_status="unpaid",
        is_subscription_renewal=True,
        created_by=None,
        total_price=ZERO,
    )

    # ---------- Price & Taxes ----------
    monthly = Decimal(str(sub.plan.monthly_price_usd or 0))
    base_amount = q(monthly * Decimal(months))
    base, excise, vat, total = split_amounts_for_base(base_amount, user=sub.user)

    # Lines
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.PLAN,
        description=_renewal_description(sub, period_start, period_end),
        quantity=1,
        unit_price=base,
    )
    if excise > 0:
        OrderTax.objects.create(
            order=order, kind=OrderTax.Kind.EXCISE, rate=Decimal("0.00"), amount=excise
        )
    if vat > 0:
        OrderTax.objects.create(
            order=order, kind=OrderTax.Kind.VAT, rate=Decimal("0.00"), amount=vat
        )

    order.total_price = q(base + excise + vat)
    order.save(update_fields=["total_price"])

    # ---------- Ledger ----------
    create_entry(
        account=sub.user.billing_account,
        entry_type="invoice",
        amount_usd=total,
        description=_renewal_description(sub, period_start, period_end),
        order=order,
        subscription=sub,
        period_start=period_start,
        period_end=period_end,
        external_ref=order_external_ref(order),
    )

    if sub.last_billed_at != period_start:
        sub.last_billed_at = period_start
        sub.save(update_fields=["last_billed_at"])

    # ---------- Wallet auto-application ----------
    applied = apply_wallet_to_order(sub.user, order, max_amount=total)
    _ensure_adjust_line_for_wallet(order, applied)
    _maybe_close_order_if_fully_paid(order)

    return order, True, applied, total


def _ensure_adjust_line_for_wallet(order: Order, applied: Decimal):
    """
    Create/merge a negative ADJUST line so the invoice document shows wallet application.
    """
    applied = q(applied)
    if applied <= 0:
        return
    desc = "Wallet credit applied"
    line = order.lines.filter(kind=OrderLine.Kind.ADJUST, description=desc).first()
    if line:
        new_unit = q(line.unit_price - applied)
        line.unit_price = new_unit
        line.save(update_fields=["unit_price", "line_total"])
    else:
        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.ADJUST,
            description=desc,
            quantity=1,
            unit_price=q(-applied),
        )
    order.refresh_from_db(fields=["total_price"])
    order.total_price = q(order.total_price - applied)
    order.save(update_fields=["total_price"])


def _maybe_close_order_if_fully_paid(order: Order):
    # reuse helper
    if due_for_ref(order.user, order_external_ref(order)) == 0:
        if order.payment_status != "paid":
            order.payment_status = "paid"
            order.status = "fulfilled"
            order.save(update_fields=["payment_status", "status"])


def _today() -> date:
    return timezone.now().date()


def _in_prebill_window(
    next_billing_date: date, cfg: BillingConfig, *, today: Optional[date] = None
) -> bool:
    """
    Prebill window: [next_billing_date - prebill_lead_days, next_billing_date)
    Include the start day, exclude the billing day (prepaid).
    """
    if not next_billing_date:
        return False
    today = today or _today()
    start = next_billing_date - timedelta(days=cfg.prebill_lead_days)
    return start <= today < next_billing_date


@transaction.atomic
def run_prebill(
    subs: Iterable[Subscription], *, dry_run: bool = False
) -> Tuple[int, int]:
    """
    Create renewal order+invoice for subscriptions in the prebill window and auto-apply wallet.
    Returns (processed_count, created_count).
    """
    cfg = BillingConfig.get()
    processed = 0
    created = 0

    for sub in subs:
        if sub.status not in {"active", "suspended"}:
            continue
        if not sub.next_billing_date:
            continue
        if cfg.invoice_start_date and _today() < cfg.invoice_start_date:
            continue
        if not _in_prebill_window(sub.next_billing_date, cfg):
            continue

        processed += 1
        if dry_run:
            continue

        # This helper:
        # - creates a renewal Order
        # - creates the invoice AccountEntry (idempotent by unique constraint)
        # - applies wallet immediately and adds an ADJUST line "Wallet credit applied"
        # - closes the order if fully paid (paid/fulfilled)
        _order, was_created, _applied, _total = (
            create_or_get_subscription_renewal_invoice(sub)
        )
        if was_created:
            created += 1

    return processed, created


def _cutoff_date_for(sub: Subscription, cfg: BillingConfig) -> Optional[date]:
    """
    cutoff date = next_billing_date - cutoff_days_before_anchor
    (e.g., if anchor=20 and cutoff_days_before_anchor=1 => cutoff is 19)
    """
    if not sub.next_billing_date:
        return None
    return sub.next_billing_date - timedelta(days=cfg.cutoff_days_before_anchor or 0)


def _has_unpaid_current_invoice(sub: Subscription) -> bool:
    """
    We consider the *current* renewal invoice (period starting at next_billing_date).
    If the order tied to that invoice has any remaining due, return True.
    """
    if not sub.next_billing_date:
        return False
    period_start = sub.next_billing_date
    period_end = add_months(period_start, months_for_cycle(sub.billing_cycle))

    inv = (
        sub.billing_entries.filter(
            entry_type="invoice", period_start=period_start, period_end=period_end
        )
        .select_related("order")
        .first()
    )
    if not inv:
        # No invoice yet — treat as unpaid to be conservative (or return False if you prefer)
        return True

    order: Order | None = inv.order
    if not order:
        return True  # invoice exists but no order link; safest is to treat as unpaid

    extref = order_external_ref(order)
    due = due_for_ref(sub.user, extref)
    return due > 0


@transaction.atomic
def enforce_cutoff(
    subs: Iterable[Subscription], *, dry_run: bool = False
) -> Tuple[int, int]:
    """
    Suspend subscriptions on their cutoff day if their renewal invoice is still unpaid.
    Returns (checked_count, suspended_count).
    """
    cfg = BillingConfig.get()
    if not cfg.auto_suspend_on_cutoff:
        return 0, 0

    today = _today()
    checked = 0
    suspended = 0

    for sub in subs.select_related("user", "plan"):
        if sub.status not in {"active", "suspended"}:
            continue
        co = _cutoff_date_for(sub, cfg)
        if not co or co != today:
            continue

        checked += 1
        # If unpaid at cutoff => suspend (prepaid rule)
        if _has_unpaid_current_invoice(sub):
            if not dry_run and sub.status != "suspended":
                sub.status = "suspended"
                sub.save(update_fields=["status"])
            suspended += 1

    return checked, suspended
