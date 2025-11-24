import base64
import json
from datetime import datetime
from datetime import timezone as dt_tz
from decimal import ROUND_HALF_UP, Decimal

from django.utils.dateparse import parse_datetime

MONEY_QUANT = Decimal("0.01")


def quantize_money(x: Decimal | float | int | str) -> Decimal:
    """Always quantize using bankers-safe rounding."""
    return Decimal(x).quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def calculate_excise_selective(order, rate_percent: Decimal) -> Decimal:
    """
    Calculate excise tax ONLY on subscription line items (OrderLine.kind='plan').

    Per DRC telecom tax regulations, excise (10%) applies exclusively to
    recurring subscription services, NOT to hardware (kits) or installation fees.

    Args:
        order: Order instance with related OrderLine queryset
        rate_percent: Excise tax rate as percentage (e.g., Decimal("10.00") for 10%)

    Returns:
        Decimal: Total excise amount rounded to 2 decimals

    Example:
        order with:
        - Kit: $400 (kind='kit') → NO excise
        - Subscription: $80 (kind='plan') → excise = $8.00
        - Installation: $120 (kind='install') → NO excise

        Total excise = $8.00 (NOT $60 which would be 10% of $600)

    Reference: Nexus — Manual Billing.pdf
    """
    from main.models import OrderLine  # Avoid circular import

    subscription_total = Decimal("0.00")

    # Sum only subscription line items
    for line in order.lines.filter(kind=OrderLine.Kind.PLAN):
        subscription_total += line.line_total or Decimal("0.00")

    # Calculate excise on subscription total only
    excise_amount = (subscription_total * rate_percent / Decimal("100.00")).quantize(
        MONEY_QUANT, rounding=ROUND_HALF_UP
    )

    return excise_amount


def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii")


def _unb64(s: str) -> str:
    return base64.urlsafe_b64decode(s.encode("ascii")).decode("utf-8")


def _encode_cursor(created_at: datetime, pk: int) -> str:
    # serialize as {"t": "<iso>", "id": <int>}
    payload = {"t": created_at.replace(tzinfo=dt_tz.utc).isoformat(), "id": pk}
    return _b64(json.dumps(payload, separators=(",", ":")))


def _decode_cursor(cursor: str):
    """
    Returns (created_at, id) from cursor or (None, None) if invalid.
    """
    try:
        raw = _unb64(cursor)
        obj = json.loads(raw)
        t = parse_datetime(obj.get("t", ""))
        i = int(obj.get("id"))
        if t is None:
            return None, None
        # force UTC awareness
        if t.tzinfo is None:
            t = t.replace(tzinfo=dt_tz.utc)
        return t, i
    except Exception:
        return None, None
