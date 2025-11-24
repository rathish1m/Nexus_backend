import json
from decimal import Decimal

from django.db.models import Sum

from client_app.client_helpers import _qmoney


def _d(x) -> Decimal:
    try:
        if isinstance(x, Decimal):
            return x
        return Decimal(str(x))
    except Exception:
        return Decimal("0.00")


def _get_req_data(request):
    """Support DRF (request.data) and plain Django (request.body)."""
    if hasattr(request, "data"):
        return request.data
    try:
        body = (request.body or b"").decode("utf-8") or "{}"
        return json.loads(body)
    except Exception:
        return {}


def _order_gross_amount(order) -> Decimal:
    """
    Prefer the snapshot on Order.total_price (set by price_order_from_lines).
    Fallback to sum(lines) + sum(taxes).
    """
    if order.total_price is not None:
        return _qmoney(order.total_price)

    lines_total = order.lines.aggregate(s=Sum("line_total"))["s"] or Decimal("0.00")
    taxes_total = order.taxes.aggregate(s=Sum("amount"))["s"] or Decimal("0.00")
    return _qmoney(lines_total + taxes_total)


def _is_success(code) -> bool:
    try:
        c = int(code)
        return c == 0
    except Exception:
        s = str(code or "").strip().lower()
        return s in {"0", "success", "succeeded", "completed", "paid"}


def _is_failure(code) -> bool:
    try:
        c = int(code)
        return c == 1
    except Exception:
        s = str(code or "").strip().lower()
        return s in {"1", "failed", "failure", "error", "cancelled"}
