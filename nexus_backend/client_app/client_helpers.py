import hashlib
import logging
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Optional
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

from django.contrib.gis.geos import Point
from django.db import connection, models, transaction
from django.db.models import Sum
from django.utils import timezone

from billing_management.billing_helpers import quantize_money
from geo_regions.models import Region
from main.models import (
    AccountEntry,
    BillingAccount,
    InstallationFee,
    Order,
    OrderLine,
    OrderTax,
    TaxRate,
    User,
)
from main.services.posting import create_entry

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

tf = TimezoneFinder()


def _qmoney(x: Decimal) -> Decimal:
    return (x or Decimal("0.00")).quantize(ZERO, rounding=ROUND_HALF_UP)


def _money_or_zero(v):
    try:
        return Decimal(v or "0.00")
    except Exception:
        return Decimal("0.00")


def _to_float(val) -> float:
    try:
        if val is None:
            return 0.0
        if isinstance(val, Decimal):
            return float(val)
        return float(val)
    except Exception:
        return 0.0


def _fmt_date(dt):
    if not dt:
        return None
    # Always return ISO date (YYYY-MM-DD) for the UI
    if isinstance(dt, datetime):
        return (
            timezone.localtime(dt).date().isoformat()
            if timezone.is_aware(dt)
            else dt.date().isoformat()
        )
    # date instance
    try:
        return dt.isoformat()
    except Exception:
        return None


def _is_success_status(s: str) -> bool:
    s = (s or "").lower()
    return s in ("succeeded", "success", "paid", "completed")


def _desc_from_order(order) -> str:
    # Feel free to elaborate; kept short and safe
    plan_name = getattr(order.plan, "name", None)
    if plan_name:
        return f"Order for {plan_name}"
    return f"Order {order.order_reference or '#'+str(order.pk)}"


def _order_totals_from_lines_and_taxes(order) -> tuple[Decimal, Decimal, Decimal]:
    """
    Return (subtotal, tax_total, total) using the current snapshot rows.
    Does NOT re-price or mutate; just reads Order.lines and Order.taxes.
    """
    subtotal = order.lines.aggregate(s=Sum("line_total"))["s"] or Decimal("0.00")
    tax_total = order.taxes.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    total = subtotal + tax_total
    return subtotal, tax_total, total


def order_amount_components(order) -> dict:
    """
    Return a breakdown of monetary components for an order using OrderLine and OrderTax:
      - kit: sum of KIT line totals
      - plan: sum of PLAN line totals
      - install: sum of INSTALL line totals
      - vat: sum of VAT OrderTax amounts
      - exc: sum of EXCISE OrderTax amounts
    """
    lines = order.lines.all()

    kit_total = (
        lines.filter(kind=OrderLine.Kind.KIT).aggregate(s=Sum("line_total"))["s"]
        or ZERO
    )
    plan_total = (
        lines.filter(kind=OrderLine.Kind.PLAN).aggregate(s=Sum("line_total"))["s"]
        or ZERO
    )
    install_total = (
        lines.filter(kind=OrderLine.Kind.INSTALL).aggregate(s=Sum("line_total"))["s"]
        or ZERO
    )

    vat_total = order.taxes.filter(kind="VAT").aggregate(s=Sum("amount"))["s"] or ZERO
    exc_total = (
        order.taxes.filter(kind="EXCISE").aggregate(s=Sum("amount"))["s"] or ZERO
    )

    return {
        "kit": kit_total,
        "plan": plan_total,
        "install": install_total,
        "vat": vat_total,
        "exc": exc_total,
    }


def installation_fee_for_coords(lat: float, lng: float) -> Decimal:
    """
    If 'assisted' install is requested, find the Region containing the point
    and return its InstallationFee.amount_usd. Otherwise return 0.00.

    Requires:
      - geo_regions.Region with a geometry field (e.g., MultiPolygon 'geom')
      - InstallationFee(region=FK to Region, amount_usd=Decimal)
    """

    try:
        # GeoDjango uses (x=lng, y=lat); SRID 4326 is WGS84
        pt = Point(float(lng), float(lat), srid=4326)
    except Exception:
        return Decimal("0.00")

    region = (
        Region.objects.filter(fence__contains=pt)  # adjust field name if not 'geom'
        .only("id")  # keep query lean
        .first()
    )
    if not region:
        return Decimal("0.00")

    fee = InstallationFee.objects.filter(region=region).only("amount_usd").first()
    return _qmoney(getattr(fee, "amount_usd", Decimal("0.00")))


def _get_user_profile_dict(user: User) -> dict:
    p = getattr(user, "profile", None)
    return {
        # Base user fields
        "full_name": getattr(user, "full_name", "") or "",
        "first_name": getattr(user, "first_name", "") or "",
        "last_name": getattr(user, "last_name", "") or "",
        "email": getattr(user, "email", "") or "",
        "avatar_url": getattr(p, "avatar_url", "") or "",
        "phone": getattr(p, "phone", "") or "",
        "twofa_enabled": bool(getattr(p, "twofa_enabled", False)),
        "notify_updates": bool(getattr(p, "notify_updates", True)),
        "notify_billing": bool(getattr(p, "notify_billing", True)),
        "notify_tickets": bool(getattr(p, "notify_tickets", True)),
    }


def _get_user_kyc(
    user: User,
) -> tuple[Optional[object], str, Optional[str], Optional[str]]:
    """
    Returns (kyc_obj, status, rejection_reason, rejection_details).
    Picks company KYC first if present, else personal.
    """
    kyc = None
    if hasattr(user, "company_kyc") and user.company_kyc:
        kyc = user.company_kyc
    elif hasattr(user, "personnal_kyc") and user.personnal_kyc:
        kyc = user.personnal_kyc

    if not kyc:
        return None, "not_submitted", None, None

    status = getattr(kyc, "status", "pending") or "pending"
    reason = getattr(kyc, "rejection_reason", None)
    details = getattr(kyc, "remarks", None)
    return kyc, status, reason, details


def _get_billing_overview(user: User) -> dict:
    acct, _ = BillingAccount.objects.get_or_create(user=user)
    balance = acct.balance_usd
    due = acct.due_usd
    credit = acct.credit_usd
    last_entries = acct.entries.select_related(
        "order", "subscription", "payment"
    ).values("entry_type", "amount_usd", "description", "created_at")[:10]
    return {
        "balance_usd": f"{balance:.2f}",
        "due_usd": f"{due:.2f}",
        "credit_usd": f"{credit:.2f}",
        "last_entries": list(last_entries),
    }


def hash_order_payload(user_id, kit_id, plan_id, lat_f, lng_f):
    raw = f"{user_id}|{kit_id}|{plan_id}|{lat_f:.6f}|{lng_f:.6f}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_create_account(user) -> "BillingAccount | None":
    # If there is no user, we cannot attach a BillingAccount
    if not user:
        return None
    acct, _ = BillingAccount.objects.get_or_create(user=user)
    return acct


def post_account_entry_once(
    *,
    account: "BillingAccount",
    entry_type: str,
    amount: Decimal,
    description: str,
    order: "Order | None" = None,
    subscription: "Any | None" = None,
    payment: "Any | None" = None,
) -> "AccountEntry | None":
    """
    Idempotently create a ledger line.
    Natural-key uniqueness: account + order + entry_type + amount + description.
    Adjust the uniqueness if you want stricter/looser matching.
    """
    if amount == ZERO:
        return None

    exists = AccountEntry.objects.filter(
        account=account,
        entry_type=entry_type,
        amount_usd=amount,
        description=description,
        order=order,
        subscription=subscription,
        payment=payment,
    ).exists()
    if exists:
        return None

    return create_entry(
        account=account,
        entry_type=entry_type,
        amount_usd=amount,
        description=description,
        order=order,
        subscription=subscription,
        payment=payment,
    )


@transaction.atomic
def post_initial_invoice_entries(order: "Order"):
    """
    Create immutable ledger lines that sum to order.total_price:
      - Kit (invoice)
      - Plan (invoice)
      - Installation fee (invoice, if any)
      - VAT (tax)
      - Excise (tax)

    Positive amounts increase what the customer owes.
    Idempotent: calling multiple times won’t double-post identical rows.
    """
    account = get_or_create_account(order.user)
    if not account:
        # No user / account -> nothing to post
        return []

    components = order_amount_components(order)

    # Always use quantified Decimals
    kit_amt = quantize_money(components["kit"])
    plan_amt = quantize_money(components["plan"])
    inst_amt = quantize_money(components["install"])
    vat_amt = quantize_money(components["vat"])
    exc_amt = quantize_money(components["exc"])

    created = []

    # Component: Kit
    if kit_amt > ZERO:
        e = post_account_entry_once(
            account=account,
            entry_type="invoice",
            amount=kit_amt,
            description=f"Kit charge – {getattr(getattr(order.kit_inventory, 'kit', None), 'name', 'Starlink Kit')}",
            order=order,
        )
        if e:
            created.append(e)

    # Component: Plan
    if plan_amt > ZERO:
        e = post_account_entry_once(
            account=account,
            entry_type="invoice",
            amount=plan_amt,
            description=f"Subscription plan – {getattr(order.plan, 'name', 'Plan')}",
            order=order,
        )
        if e:
            created.append(e)

    # Component: Installation
    if inst_amt > ZERO:
        e = post_account_entry_once(
            account=account,
            entry_type="invoice",
            amount=inst_amt,
            description="Installation fee",
            order=order,
        )
        if e:
            created.append(e)

    # Taxes (separate lines so they’re searchable/aggregable)
    if vat_amt > ZERO:
        e = post_account_entry_once(
            account=account,
            entry_type="tax",
            amount=vat_amt,
            description="VAT",
            order=order,
        )
        if e:
            created.append(e)

    if exc_amt > ZERO:
        e = post_account_entry_once(
            account=account,
            entry_type="tax",
            amount=exc_amt,
            description="Excise tax",
            order=order,
        )
        if e:
            created.append(e)

    return created


def _supports_skip_locked():
    return connection.vendor == "postgresql"


def price_order_from_lines(order):
    """
    Compute subtotal from Order.lines, create OrderTax snapshots from ALL TaxRate rows,
    and update order.total_price. Returns the computed numbers for UI.
    """
    with transaction.atomic():
        # 1) subtotal from lines
        subtotal = order.lines.aggregate(s=models.Sum("line_total"))["s"] or Decimal(
            "0.00"
        )

        # 2) recompute taxes (dynamic: whatever is in TaxRate)
        OrderTax.objects.filter(order=order).delete()
        tax_total = Decimal("0.00")

        if not order.is_tax_exempt:
            for rate in TaxRate.objects.all():
                pct = (rate.percentage or Decimal("0.00")) / Decimal("100")
                if pct > 0:
                    amt = (subtotal * pct).quantize(Decimal("0.01"))
                    OrderTax.objects.create(
                        order=order,
                        kind=rate.description,  # e.g., "VAT", "EXCISE", "SERVICE", ...
                        rate=rate.percentage,  # snapshot %
                        amount=amt,  # snapshot $
                    )
                    tax_total += amt

        # 3) update order total only (since that's the only field you have now)
        order.total_price = (subtotal + tax_total).quantize(Decimal("0.01"))
        order.save(update_fields=["total_price"])

        # Return values for response/diagnostics
        return {
            "subtotal": subtotal,
            "tax_total": tax_total,
            "total": order.total_price,
        }


def compute_local_expiry_from_coords(lat: float, lng: float, hours: int = 1):
    """
    Return an aware UTC datetime representing 'now + hours' *in the user's local time*,
    where local time is derived from the provided coordinates.

    If the timezone cannot be determined, falls back to UTC.
    """
    now_utc = timezone.now()

    try:
        tz_name = tf.timezone_at(lng=lng, lat=lat)
    except Exception:
        tz_name = None

    if not tz_name:
        # Fallback: treat 'now + hours' in UTC
        return now_utc + timedelta(hours=hours)

    try:
        local_tz = ZoneInfo(tz_name)
    except Exception:
        # Bad/unknown TZ id → fallback to UTC addition
        return now_utc + timedelta(hours=hours)

    # Convert to the user's local 'now', add hours, then convert back to UTC for storage
    now_local = now_utc.astimezone(local_tz)
    expires_local = now_local + timedelta(hours=hours)
    return expires_local.astimezone(dt_timezone.utc)
