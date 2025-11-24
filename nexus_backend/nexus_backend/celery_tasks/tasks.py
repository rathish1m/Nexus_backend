import logging
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from celery import shared_task

from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from billing_management.billing_services import enforce_cutoff, run_prebill
from main.models import (
    ZERO,
    AccountEntry,
    BillingConfig,
    Order,
    OrderLine,
    OrderTax,
    Subscription,
    TaxRate,
    User,
    _qmoney,
)
from main.services.posting import create_entry
from stock.inventory import release_expired_reservations

logger = logging.getLogger(__name__)


# ---------- scheduled job ----------
@shared_task(name="nexus_backend.celery_tasks.tasks.cancel_expired_orders")
def cancel_expired_orders():
    """
    Cancel all orders that have reached their expiry time.
    - Locks only Order rows (no joins) to avoid Postgres FOR UPDATE restrictions on outer joins.
    - Uses skip_locked to allow concurrent workers without blocking.
    - Keeps per-order cancellation idempotent via Order.cancel().
    """
    now = timezone.now()

    # Build a base queryset WITHOUT select_related to avoid outer joins on the locking query
    base_qs = Order.objects.filter(
        payment_status__in=["unpaid", "pending", "awaiting_confirmation"],
        status__in=["awaiting_confirmation", "pending_payment", "pending"],
        expires_at__isnull=False,
        expires_at__lte=now,
    ).order_by("pk")

    summary = {
        "cancelled": 0,
        "freed": 0,
        "movements_deleted": 0,
        "subscriptions_deleted": 0,
    }

    with transaction.atomic():
        # Lock only the Order rows. Use skip_locked where supported.
        try:
            lock_qs = base_qs.select_for_update(of=("self",), skip_locked=True)
        except TypeError:
            # Fallback if 'of' or 'skip_locked' not supported in the current backend/version
            lock_qs = base_qs.select_for_update()

        for order in lock_qs.iterator(chunk_size=200):
            res = order.cancel(reason="expired (1h hold)")
            if res.get("changed"):
                summary["cancelled"] += 1
                if res.get("freed_inventory"):
                    summary["freed"] += 1
                summary["movements_deleted"] += int(res.get("movements_deleted") or 0)
                summary["subscriptions_deleted"] += int(
                    res.get("subscriptions_deleted") or 0
                )
    return summary


# @shared_task(bind=True, autoretry_for=(requests.Timeout, requests.ConnectionError),
#              retry_backoff=10, retry_kwargs={"max_retries": 3})
# @shared_task(name="nexus_backend.celery_tasks.tasks.check_flexpay_transactions")
# def check_flexpay_transactions():
#     """
#     Poll FlexPay for PaymentAttempts that are not completed.
#     Mark ONLY the order linked to the current PaymentAttempt (same order_number) as paid
#     when BOTH: response code == "0" AND transaction.status == "0".
#     Also record coupon redemption (if any) once the order is paid.
#     """
#     attempts = (
#         PaymentAttempt.objects.select_related("order")
#         .exclude(status__in=["completed", "succeeded", "paid"])
#         .order_by("-created_at")
#     )
#
#     checked = 0
#     updated_attempts = 0
#     updated_orders = 0
#
#     for pa in attempts:
#         order_number = pa.order_number
#         if not order_number:
#             logger.warning("PaymentAttempt %s has no order_number. Skipping.", pa.id)
#             continue
#
#         try:
#             headers = {
#                 "Authorization": f"Bearer {nexus_backend.settings.FLEXPAY_API_KEY}",
#                 "Content-Type": "application/json",
#             }
#
#             resp = requests.get(
#                 f"{FLEXPAY_CHECK_URL.rstrip('/')}/{order_number}",
#                 headers=headers,
#                 timeout=15,
#             )
#             checked += 1
#
#             if resp.status_code != 200:
#                 logger.error(
#                     "FlexPay check HTTP %s for orderNumber=%s",
#                     resp.status_code,
#                     order_number,
#                 )
#                 continue
#
#             data = resp.json() if resp.content else {}
#             code = str(data.get("code", "")).strip()
#
#             if code == "0":
#                 tx = data.get("transaction") or {}
#                 tx_status = str(tx.get("status", "")).strip()
#                 tx_reference = (tx.get("reference") or "").strip()
#
#                 # Optional: ensure the transaction refers to THIS attempt/order
#                 expected_refs = set()
#                 if pa.reference:
#                     expected_refs.add(str(pa.reference).strip())
#                 if pa.order and getattr(pa.order, "order_reference", None):
#                     expected_refs.add(str(pa.order.order_reference).strip())
#
#                 if tx_reference and expected_refs and tx_reference not in expected_refs:
#                     logger.warning(
#                         "FlexPay reference mismatch for attempt %s: got '%s', expected one of %s. Skipping.",
#                         pa.id, tx_reference, list(expected_refs),
#                     )
#                     continue
#
#                 # Prepare values (convert string amounts to Decimal)
#                 amount = pa.amount
#                 amount_customer = pa.amount_customer
#                 try:
#                     if tx.get("amount") is not None:
#                         amount = Decimal(str(tx.get("amount")))
#                 except (InvalidOperation, TypeError):
#                     logger.warning("Invalid amount in FlexPay tx for attempt %s: %s", pa.id, tx.get("amount"))
#
#                 try:
#                     if tx.get("amountCustomer") is not None:
#                         amount_customer = Decimal(str(tx.get("amountCustomer")))
#                 except (InvalidOperation, TypeError):
#                     logger.warning("Invalid amountCustomer in FlexPay tx for attempt %s: %s", pa.id, tx.get("amountCustomer"))
#
#                 # Status mapping (only 'completed' when BOTH are "0")
#                 new_status = "completed" if tx_status == "0" else ("pending" if tx_status in ("1", "") else tx_status)
#
#                 with transaction.atomic():
#                     # Update PaymentAttempt
#                     pa.code = code
#                     if tx_reference:
#                         pa.reference = tx_reference
#                     pa.amount = amount
#                     pa.amount_customer = amount_customer
#                     if tx.get("currency"):
#                         pa.currency = tx.get("currency")
#                     pa.transaction_time = _parse_flexpay_datetime(tx.get("createdAt"))
#                     pa.raw_payload = data
#                     pa.status = new_status
#                     pa.save(
#                         update_fields=[
#                             "code", "reference", "amount", "amount_customer",
#                             "currency", "transaction_time", "raw_payload", "status",
#                         ]
#                     )
#                     updated_attempts += 1
#
#                     # Mark ONLY this attempt's order as paid/fulfilled when BOTH are 0
#                     if code == "0" and tx_status == "0" and pa.order:
#                         order = pa.order
#                         if order.payment_status != "paid":
#                             order.payment_status = "paid"
#                             order.status = "fulfilled"
#                             order.save(update_fields=["payment_status", "status"])
#                             updated_orders += 1
#
#                             # ✅ Record coupon redemption now that it's paid
#                             record_coupon_redemption_if_any(order)
#
#                 logger.info(
#                     "FlexPay OK -> Completed orderNumber=%s (attempt %s)",
#                     order_number, pa.id,
#                 )
#
#             elif code == "1":
#                 logger.info(
#                     "FlexPay: no transaction yet for orderNumber=%s (attempt %s)",
#                     order_number, pa.id,
#                 )
#             else:
#                 logger.warning(
#                     "FlexPay unexpected response for %s: %s", order_number, data
#                 )
#
#         except requests.Timeout:
#             logger.exception("FlexPay timeout for orderNumber=%s", order_number)
#         except Exception as e:
#             logger.exception("FlexPay check error for orderNumber=%s: %s", order_number, e)
#
#     logger.info(
#         "FlexPay checks done. checked=%s, attempts_updated=%s, orders_updated=%s",
#         checked, updated_attempts, updated_orders,
#     )
#     return {
#         "checked": checked,
#         "attempts_updated": updated_attempts,
#         "orders_updated": updated_orders,
#     }


# -------------------- core: build renewal --------------------

# -------------------- helpers --------------------


def _months_for_cycle(cycle: str) -> int:
    cycle = (cycle or "monthly").lower()
    return {"monthly": 1, "quarterly": 3, "yearly": 12}.get(cycle, 1)


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    # keep day in [1..28] “anchor-safe”
    day = min(d.day, 28)
    # final clamp to month length
    from calendar import monthrange

    day = min(day, monthrange(y, m)[1])
    return date(y, m, day)


def _next_anchor(today: date, anchor_day: int) -> date:
    """Return the upcoming anchor date (this month or next) on [1..28]."""
    anchor_day = max(1, min(28, int(anchor_day or 20)))
    if today.day <= anchor_day:
        return date(today.year, today.month, anchor_day)
    # next month
    m = today.month + 1
    y = today.year + (1 if m > 12 else 0)
    m = 1 if m > 12 else m
    return date(y, m, anchor_day)


def _gross_taxes(user, base: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """
    Calculate (excise, vat, total_with_tax).
    VAT is applied on (base + excise). Respect user's tax exemption.
    """
    base = _qmoney(base)
    if getattr(user, "is_tax_exempt", False):
        return ZERO, ZERO, base

    excise_rate = TaxRate.objects.filter(description="EXCISE").values_list(
        "percentage", flat=True
    ).first() or Decimal("0.00")
    vat_rate = TaxRate.objects.filter(description="VAT").values_list(
        "percentage", flat=True
    ).first() or Decimal("0.00")

    excise = _qmoney(base * excise_rate / Decimal("100"))
    vat = _qmoney((base + excise) * vat_rate / Decimal("100"))
    total = _qmoney(base + excise + vat)
    return excise, vat, total


def _acquire_lock(key: str, ttl: int = 1800) -> bool:
    # Prevent duplicate runs across workers
    return cache.add(key, "1", ttl)


def _release_lock(key: str):
    cache.delete(key)


@transaction.atomic
def _create_renewal_order_and_invoice(
    sub: Subscription, period_start: date, period_end: date, *, auto_apply_wallet: bool
) -> Order:
    """
    Idempotent via AccountEntry unique constraint (invoice per sub/period).
    Creates Order (+lines, +tax rows), AccountEntry(invoice), applies wallet payment.
    """
    user = sub.user
    plan = sub.plan
    months = _months_for_cycle(sub.billing_cycle)

    # Amount base (assumes plan.monthly_price_usd is monthly)
    base = _qmoney((plan.monthly_price_usd or ZERO) * months)
    excise, vat, total = _gross_taxes(user, base)

    # 1) Create an Order for the renewal
    order = Order.objects.create(
        user=user,
        plan=plan,
        total_price=total,
        payment_status="unpaid",
        status="pending_payment",
        is_subscription_renewal=True,
        created_by=None,
    )

    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.PLAN,
        description=f"{plan.name} – {sub.billing_cycle.capitalize()} ({period_start:%Y-%m-%d} → {period_end:%Y-%m-%d})",
        quantity=1,
        unit_price=base,
    )

    if excise > 0:
        OrderTax.objects.create(
            order=order,
            kind=OrderTax.Kind.EXCISE,
            rate=TaxRate.objects.get(description="EXCISE").percentage,
            amount=excise,
        )
    if vat > 0:
        OrderTax.objects.create(
            order=order,
            kind=OrderTax.Kind.VAT,
            rate=TaxRate.objects.get(description="VAT").percentage,
            amount=vat,
        )

    # 2) Create the invoice ledger entry (idempotent by constraint)
    create_entry(
        account=user.billing_account,
        entry_type="invoice",
        amount_usd=total,  # +ve = charge
        description=f"Subscription invoice {plan.name} ({period_start:%Y-%m-%d} → {period_end:%Y-%m-%d})",
        order=order,
        subscription=sub,
        period_start=period_start,
        period_end=period_end,
        external_ref=f"SUB#{sub.id}:{period_start.isoformat()}",
    )

    # 3) Optionally auto-apply wallet (partially or fully)
    if auto_apply_wallet and hasattr(user, "wallet") and user.wallet.is_active:
        wallet = user.wallet
        wallet.refresh_from_db()
        to_apply = min(wallet.balance, total)
        to_apply = _qmoney(to_apply)

        if to_apply > 0:
            # Wallet DEBIT (transaction ledger) + negative AccountEntry (payment)
            wallet.charge(
                to_apply, note="Auto-applied to subscription invoice", order=order
            )
            create_entry(
                account=user.billing_account,
                entry_type="payment",
                amount_usd=-to_apply,  # -ve = payment/credit
                description="Wallet applied to invoice",
                order=order,
                subscription=sub,
            )
            # Visual on Order: an adjust line (optional)
            OrderLine.objects.create(
                order=order,
                kind=OrderLine.Kind.ADJUST,
                description="Wallet credit applied",
                quantity=1,
                unit_price=-to_apply,
            )

    # 4) Payment status after wallet
    #   due = sum(AccountEntry) for the user’s account; but here compute per order total - wallet applied
    #   Simpler: recompute due = invoice total + sum(payments linked to this order only
    total_invoiced = total
    total_paid = (
        -sum(
            AccountEntry.objects.filter(order=order, entry_type="payment").values_list(
                "amount_usd", flat=True
            )
        )
        or ZERO
    )
    remaining = _qmoney(total_invoiced - total_paid)

    if remaining <= ZERO:
        order.payment_status = "paid"
        order.status = "fulfilled"
        order.save(update_fields=["payment_status", "status"])
    else:
        order.payment_status = "unpaid"
        order.status = "pending_payment"
        order.save(update_fields=["payment_status", "status"])

    # 5) Touch subscription pointers (billed for this period)
    sub.last_billed_at = period_start
    sub.next_billing_date = period_end
    sub.save(update_fields=["last_billed_at", "next_billing_date"])

    return order


# -------------------- periodic runners --------------------


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_jitter=True,
    max_retries=3,
    queue="billing",
)
def run_prebill_and_collect(self):
    """
    Daily task. When today reaches the "lead window" (anchor - prebill_lead_days),
    generate renewal orders/invoices for the *next* period and auto-apply wallets.
    Idempotent (UniqueConstraint on AccountEntry).
    """
    cfg = BillingConfig.get()
    today = timezone.localdate()
    next_anchor = _next_anchor(today, cfg.anchor_day)
    lead_open = next_anchor - timedelta(days=cfg.prebill_lead_days)

    # run once per day (simple lock)
    lock_key = f"billing:prebill:{today.isoformat()}"
    if not _acquire_lock(lock_key, ttl=60 * 20):
        return "Skip: lock held"

    try:
        # Only act inside the lead window up to anchor day (inclusive safeguard)
        if not (lead_open <= today <= next_anchor):
            return f"No-op (today={today}, lead_open={lead_open}, anchor={next_anchor})"

        # Eligible subs: active, started, not ended, not first cycle if already included in first order
        q = (
            Subscription.objects.select_related("user", "plan")
            .filter(
                status="active",
                user__isnull=False,
                plan__isnull=False,
            )
            .filter(
                Q(started_at__isnull=False),
                Q(ended_at__isnull=True) | Q(ended_at__gt=today),
            )
        )

        created = 0
        months = None  # per sub

        for sub in q.iterator(chunk_size=500):
            # Determine period boundaries aligned to anchor and cycle
            months = _months_for_cycle(sub.billing_cycle)
            period_start = next_anchor
            period_end = _add_months(period_start, months)

            # Skip first cycle if your config says it's already on the first hardware order invoice
            if (
                getattr(cfg, "first_cycle_included_in_order", False)
                and not sub.last_billed_at
            ):
                # Initialize pointers only, without invoicing
                sub.last_billed_at = period_start
                sub.next_billing_date = period_end
                sub.save(update_fields=["last_billed_at", "next_billing_date"])
                continue

            try:
                _create_renewal_order_and_invoice(
                    sub,
                    period_start,
                    period_end,
                    auto_apply_wallet=getattr(cfg, "auto_apply_wallet", True),
                )
                created += 1
            except IntegrityError:
                # already invoiced for that period — safe to skip
                continue

        return f"prebilled={created} (window {lead_open}→{next_anchor})"
    finally:
        _release_lock(lock_key)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_jitter=True,
    max_retries=3,
    queue="billing",
)
def run_cutoff_enforcement(self):
    """
    Daily task. If today == (anchor - cutoff_days_before_anchor) and a renewal invoice remains unpaid,
    auto-suspend subscription (optional via config).
    """
    cfg = BillingConfig.get()
    today = timezone.localdate()
    next_anchor = _next_anchor(today, cfg.anchor_day)
    cutoff_days = getattr(cfg, "cutoff_days_before_anchor", 1)
    cutoff_date = next_anchor - timedelta(days=cutoff_days)

    if not getattr(cfg, "auto_suspend_on_cutoff", True):
        return "auto_suspend_on_cutoff disabled"

    if today != cutoff_date:
        return f"No-op (today={today}, cutoff={cutoff_date})"

    # Find invoices for this upcoming period that remain due, and suspend the sub
    months_map = {"monthly": 1, "quarterly": 3, "yearly": 12}

    suspended = 0
    subs = Subscription.objects.select_related("user", "plan").filter(status="active")
    for sub in subs.iterator(chunk_size=500):
        months = months_map.get(sub.billing_cycle or "monthly", 1)
        period_start = next_anchor
        period_end = _add_months(period_start, months)

        # Does an invoice exist for this sub/period?
        inv = AccountEntry.objects.filter(
            entry_type="invoice",
            subscription=sub,
            period_start=period_start,
            period_end=period_end,
        ).first()
        if not inv:
            continue

        # How much is still due for this order (look at payments against this order)
        order = inv.order
        if not order:
            continue
        paid = (
            -sum(
                AccountEntry.objects.filter(
                    order=order, entry_type="payment"
                ).values_list("amount_usd", flat=True)
            )
            or ZERO
        )
        remaining = _qmoney(inv.amount_usd - paid)

        if remaining > ZERO:
            sub.status = "suspended"
            sub.ended_at = None  # just suspended
            sub.save(update_fields=["status"])
            suspended += 1
    return f"suspended={suspended}"


@shared_task(ignore_result=True)
def task_release_expired_reservations():
    return release_expired_reservations()


@contextmanager
def task_lock(key: str, timeout: int = 60 * 30):  # 30 min default
    """
    Simple cache-based mutex to avoid overlapping task runs.
    Returns immediately if another worker holds the lock.
    """
    acquired = cache.add(key, "1", timeout=timeout)
    try:
        yield acquired
    finally:
        if acquired:
            cache.delete(key)


def _subs_qs_for_user(user_id: Optional[int] = None, email: Optional[str] = None):
    qs = Subscription.objects.select_related("plan", "user").filter(
        status__in=["active", "suspended"]
    )
    if user_id:
        qs = qs.filter(user_id=user_id)
    elif email:
        try:
            user = User.objects.get(email=email)
            qs = qs.filter(user=user)
        except User.DoesNotExist:
            return Subscription.objects.none()
    return qs


# ----------------------
# PREBILL (create renewal invoice/order + auto-apply wallet)
# ----------------------
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,  # exponential (seconds)
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=60 * 60,  # 60 min safety cap
)
def prebill_renewals_task(
    self, *, user_id: int | None = None, email: str | None = None, dry_run: bool = False
):
    lock_key = "billing:locks:prebill_renewals"
    with task_lock(lock_key, timeout=60 * 50) as acquired:
        if not acquired:
            logger.info("[prebill] skipped: another worker holds the lock")
            return {"processed": 0, "created": 0, "locked": True}

        qs = _subs_qs_for_user(user_id, email)
        logger.info(
            "[prebill] starting | dry_run=%s | user_id=%s | email=%s | subs=%s",
            dry_run,
            user_id,
            email,
            qs.count(),
        )

        with transaction.atomic():
            processed, created = run_prebill(qs, dry_run=dry_run)

        logger.info(
            "[prebill] done | processed=%s created=%s dry_run=%s",
            processed,
            created,
            dry_run,
        )
        return {"processed": processed, "created": created, "locked": False}


# ----------------------
# CUTOFF (suspend at cutoff if unpaid)
# ----------------------
@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
    soft_time_limit=30 * 60,
)
def enforce_cutoff_task(self, *, dry_run: bool = False):
    lock_key = "billing:locks:enforce_cutoff"
    with task_lock(lock_key, timeout=60 * 20) as acquired:
        if not acquired:
            logger.info("[cutoff] skipped: another worker holds the lock")
            return {"checked": 0, "suspended": 0, "locked": True}

        qs = Subscription.objects.select_related("plan", "user").filter(
            status__in=["active", "suspended"]
        )
        logger.info("[cutoff] starting | dry_run=%s | subs=%s", dry_run, qs.count())

        with transaction.atomic():
            checked, suspended = enforce_cutoff(qs, dry_run=dry_run)

        logger.info(
            "[cutoff] done | checked=%s suspended=%s dry_run=%s",
            checked,
            suspended,
            dry_run,
        )
        return {"checked": checked, "suspended": suspended, "locked": False}
