import random
import string
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from time import localtime
from typing import Optional, Tuple

from dateutil.relativedelta import relativedelta

from django.contrib.gis.geos import Point
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from geo_regions.models import Region
from main.models import InstallationFee, Order, Subscription

ZERO = Decimal("0.00")


def _qm(x: Decimal) -> Decimal:
    return (x or Decimal("0.00")).quantize(ZERO, rounding=ROUND_HALF_UP)


def determine_region_from_location(lat, lng):
    """
    Return the *name* of the Region whose polygon contains/covers the given point.
    Falls back to your previous bounding-box heuristics, then 'Other Regions'.
    """
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return "Other Regions"

    # Try GeoDjango polygon lookup first (SRID 4326: lon, lat order!)
    try:
        pt = Point(lng_f, lat_f, srid=4326)
        # Prefer covers (handles boundary points better), then contains
        region = (
            Region.objects.filter(fence__covers=pt).first()
            or Region.objects.filter(fence__contains=pt).first()
        )
        if region:
            return region.name
    except Exception:
        # If GIS lookup fails (e.g., DB without PostGIS), continue with heuristic
        pass

    # --- Heuristic fallbacks (your original bounding boxes) ---
    try:
        # Approximate bounding box for Lubumbashi (Haut-Katanga)
        if -11.8 <= lat_f <= -11.5 and 27.3 <= lng_f <= 27.6:
            return "Haut-Katanga / Lubumbashi"
        # Approximate bounding box for Kinshasa
        elif -4.5 <= lat_f <= -4.2 and 15.2 <= lng_f <= 15.5:
            return "Kinshasa"
    except Exception:
        pass

    return "Other Regions"


def get_installation_fee_by_region(region_name: str) -> Decimal:
    """
    Get installation fee based on a region *name*.
    Tries exact match first, then partial matches.
    Returns Decimal('100.00') as a safe default if not found.
    """
    try:
        if not region_name:
            return Decimal("100.00")

        # 1) Exact (case-insensitive)
        fee = (
            InstallationFee.objects.select_related("region")
            .filter(region__name__iexact=region_name)
            .first()
        )
        if fee:
            return fee.amount_usd

        # 2) Friendly keyword aliases for common cases
        rn = region_name.lower()
        aliases = []
        if "lubumbashi" in rn or "haut-katanga" in rn:
            aliases.append("Lubumbashi")
            aliases.append("Haut-Katanga")
        if "kinshasa" in rn:
            aliases.append("Kinshasa")
        if "kolwezi" in rn:
            aliases.append("Kolwezi")

        if aliases:
            fee = (
                InstallationFee.objects.select_related("region")
                .filter(
                    Q(region__name__iexact=region_name)
                    | Q(region__name__in=aliases)
                    | Q(region__name__icontains=region_name)
                )
                .first()
            )
            if fee:
                return fee.amount_usd

        # 3) Generic partial match as a last try
        fee = (
            InstallationFee.objects.select_related("region")
            .filter(region__name__icontains=region_name)
            .first()
        )
        if fee:
            return fee.amount_usd

        # Default if nothing matched
        return Decimal("100.00")
    except Exception:
        return Decimal("100.00")


# Optional: one-shot helper if you want to go directly from (lat, lng) to fee
def get_installation_fee_by_point(lat, lng) -> Decimal:
    """
    Resolve region via polygons, then return its installation fee (or default).
    """
    region_name = determine_region_from_location(lat, lng)
    return get_installation_fee_by_region(region_name)


# Password Generator
def generate_random_password(length=10):
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=length))


def _to_float(v):
    if v is None:
        return None
    if isinstance(v, Decimal):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fmt_date(d):
    """
    Accepts date or datetime (or None) and returns 'YYYY-MM-DD' or None.
    """
    if not d:
        return None
    try:
        # If it's a datetime, localize; if it's already a date it won't hurt
        return localtime(d).strftime("%Y-%m-%d")
    except Exception:
        try:
            return d.strftime("%Y-%m-%d")
        except Exception:
            return None


#
# def _desc_from_order(o):
#     if o.kit_price_usd and o.plan_price_usd:
#         return "Hardware + Subscription"
#     if o.kit_price_usd:
#         return "Hardware"
#     if o.plan_price_usd:
#         return "Subscription"
#     return "Order"


UNPAID_FLAGS = ["unpaid", "awaiting_confirmation"]


def get_current_balance(user) -> Decimal:
    """
    Sum total_price for the user's orders that are not cancelled and not paid.
    Returns a Decimal rounded to 2 decimal places.
    """
    qs = Order.objects.filter(user=user, payment_status__in=UNPAID_FLAGS).exclude(
        status__iexact="cancelled"
    )

    total = qs.aggregate(total=Coalesce(Sum("total_price"), Decimal("0.00")))["total"]
    # Ensure a Decimal and normalize to 2 places
    total = (total or Decimal("0.00")).quantize(Decimal("0.01"))
    return total


def _parse_flexpay_datetime(dt_str: str):
    """
    FlexPay example: "06-02-2021 17:32:46"
    Format appears to be DD-MM-YYYY HH:MM:SS.
    """
    if not dt_str:
        return None
    for fmt in ("%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return timezone.make_aware(datetime.strptime(dt_str, fmt))
        except Exception:
            continue
    return None


# ---------- Utilities ----------


def _add_cycle(d, cycle: str):
    if cycle == "monthly":
        return d + relativedelta(months=1)
    if cycle == "quarterly":
        return d + relativedelta(months=3)
    if cycle == "yearly":
        return d + relativedelta(years=1)
    return d + relativedelta(months=1)


def _existing_open_order(sub: Subscription) -> Optional[Order]:
    """Find latest open (unpaid & not cancelled/failed) order for same user+plan."""
    return (
        Order.objects.filter(user=sub.user, plan=sub.plan)
        .exclude(status__in=["cancelled", "failed"])
        .exclude(payment_status="paid")
        .order_by("-created_at")
        .first()
    )


# ---------- core API ----------
def create_subscription_renewal_order(
    sub: Subscription, created_by=None
) -> Tuple[Optional[Order], bool]:
    """
    Create a renewal Order exactly 7 days before the subscription's next_billing_date.
    Returns (order, created_flag). No payment attempt is created.
    """
    # Preconditions
    if (
        sub.status != "active"
        or not sub.user
        or not sub.plan
        or not sub.next_billing_date
    ):
        return None, False

    today = timezone.now().date()
    # 1) Normalize the "upcoming due date": roll forward if next_billing_date is in the past
    upcoming_due = sub.next_billing_date
    safety = 0

    while upcoming_due < today and safety < 24:  # safety guard for runaway loops
        upcoming_due = _add_cycle(upcoming_due, sub.billing_cycle)
        safety += 1

    # 2) Compute days until the upcoming due date
    days_until_due = (upcoming_due - today).days

    # Create ONLY when we are exactly 7 days before the due date
    if days_until_due != 7:
        return None, False

    with transaction.atomic():
        order = Order.objects.create(
            user=sub.user,
            plan=sub.plan,
            payment_method="",  # or your preferred default
            payment_status="unpaid",
            status="pending_payment",
            created_by=created_by,
            is_subscription_renewal=True,  # explicit flag
        )

        # Hold should expire on the due date (i.e., in exactly 'days_until_due' days = 7 here)
        order.start_subscription_payment_hold(days=days_until_due)

    return order, True


def advance_subscription_cycle_if_needed(order):
    """
    Advance cycle ONLY when:
      - the order is paid,
      - it's a subscription renewal,
      - and today is on/after the current next_billing_date.
    Idempotent via date checks.
    """
    if order.payment_status != "paid":
        return
    if not getattr(order, "is_subscription_renewal", False):
        return
    if not order.plan or not order.user:
        return

    sub = (
        Subscription.objects.filter(user=order.user, plan=order.plan, status="active")
        .order_by("-started_at")
        .first()
    )
    if not sub or not sub.next_billing_date:
        return

    today = timezone.now().date()
    if today < sub.next_billing_date:
        # Paid early; don't move the cycle yet
        return

    # Move forward exactly one cycle from the *current* next_billing_date
    sub.last_billed_at = today
    sub.next_billing_date = _add_cycle(sub.next_billing_date, sub.billing_cycle)
    sub.save(update_fields=["last_billed_at", "next_billing_date"])


def _month_bounds(dt):
    """Return timezone-aware start and end (exclusive) of the month containing dt."""
    # Start of month (local time)
    start = dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    # Compute next month
    if start.month == 12:
        next_month = start.replace(year=start.year + 1, month=1)
    else:
        next_month = start.replace(month=start.month + 1)
    return start, next_month
