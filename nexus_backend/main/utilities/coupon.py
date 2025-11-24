# views_orders.py
import json
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_POST

from main.models import Coupon


def _qmoney(x):
    if x is None:
        x = Decimal("0")
    if not isinstance(x, Decimal):
        x = Decimal(str(x))
    return x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@require_POST
@csrf_protect
def validate_coupon(request):
    """
    Request (JSON):
    {
      "code": "WELCOME10",
      "cart": [
        {
          "kit_id": 12,
          "plan_id": 34,
          "billing_cycle": "monthly",
          "service_ids": [1,2],
          "pre_tax_subtotal": 499.99,
          "tax_total": 119.00,
          "grand_total": 618.99
        },
        ...
      ]
    }

    Response (JSON):
    { "success": true, "discount_amount": 61.90, "new_total": 557.09, "message": "Coupon applied: 10% off" }
    or
    { "success": false, "message": "Coupon expired" }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except Exception:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON payload."}, status=400
        )

    code = (payload.get("code") or "").strip()
    cart = payload.get("cart") or []

    if not code:
        return JsonResponse(
            {"success": False, "message": "Missing coupon code."}, status=400
        )
    if not isinstance(cart, list) or not cart:
        return JsonResponse({"success": False, "message": "Cart is empty."}, status=400)

    # ---------- Fetch & validate coupon ----------
    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Coupon not found or invalid."}, status=404
        )

    # Work with timezone-aware datetimes and compare on date component
    now_dt = timezone.now()

    # Common boolean flag
    if hasattr(coupon, "is_active") and not coupon.is_active:
        return JsonResponse(
            {"success": False, "message": "Coupon is not active."}, status=400
        )

    # Validity window: valid_from <= today <= valid_to|valid_until
    valid_from = getattr(coupon, "valid_from", None)
    valid_until = getattr(coupon, "valid_to", None) or getattr(
        coupon, "valid_until", None
    )

    def _to_date(value):
        if isinstance(value, datetime):
            return value.date()
        return value

    today = now_dt.date()
    vf = _to_date(valid_from)
    vu = _to_date(valid_until)

    if vf and today < vf:
        return JsonResponse(
            {"success": False, "message": "Coupon is not yet valid."}, status=400
        )
    if vu and today > vu:
        return JsonResponse(
            {"success": False, "message": "Coupon has expired."}, status=400
        )

    # Usage limits (from new Coupon model: max_redemptions + redemptions relation)
    if getattr(coupon, "max_redemptions", None) is not None:
        try:
            used = coupon.redemptions_count()
        except Exception:
            used = 0
        remaining_uses = (coupon.max_redemptions or 0) - used
        if coupon.max_redemptions and remaining_uses <= 0:
            return JsonResponse(
                {"success": False, "message": "Coupon usage limit reached."}, status=400
            )

    # Min cart total (optional)
    min_total = _qmoney(getattr(coupon, "min_cart_total", Decimal("0.00")))
    # ---------- Compute global cart total ----------
    grand_total = Decimal("0.00")
    for row in cart:
        try:
            line_total = _qmoney(row.get("grand_total", 0))
        except Exception:
            return JsonResponse(
                {"success": False, "message": "Invalid line total in cart."}, status=400
            )
        if line_total < 0:
            return JsonResponse(
                {"success": False, "message": "Negative line total not allowed."},
                status=400,
            )
        grand_total += line_total
    grand_total = _qmoney(grand_total)

    if min_total and grand_total < min_total:
        return JsonResponse(
            {
                "success": False,
                "message": f"Minimum cart total for this coupon is ${min_total:.2f}.",
            },
            status=400,
        )

    # ---------- Eligibility targeting (optional) ----------
    # If your Coupon supports plan/kit/line-scope targeting, check here.
    # Example for allowed plans M2M:
    # if hasattr(coupon, "allowed_plans") and coupon.allowed_plans.exists():
    #     plan_ids = {int(r.get("plan_id")) for r in cart if r.get("plan_id")}
    #     if not plan_ids.intersection(coupon.allowed_plans.values_list("id", flat=True)):
    #         return JsonResponse({"success": False, "message": "Coupon not applicable to selected plans."}, status=400)
    #
    # For your earlier requirement "coupon must be global", we apply to the entire cart.

    # ---------- Discount computation ----------
    # New Coupon model stores either percent_off or amount_off depending on discount_type.
    discount_type = getattr(coupon, "discount_type", "percent")

    # Normalize type to internal keywords
    normalized = str(discount_type or "").lower()
    if normalized in {"percent", "percentage", "pct", "percent_off"}:
        discount_type = "percent"
        raw_value = getattr(coupon, "percent_off", None)
    else:
        discount_type = "amount"
        raw_value = getattr(coupon, "amount_off", None)

    discount_value = _qmoney(raw_value or Decimal("0.00"))

    if discount_type == "percent":
        if discount_value <= 0 or discount_value > 100:
            return JsonResponse(
                {"success": False, "message": "Invalid percent value."}, status=400
            )
        discount_amount = (grand_total * discount_value / Decimal("100")).quantize(
            Decimal("0.01")
        )
        message = f"Coupon applied: {discount_value}% off"
    else:  # "amount"
        if discount_value <= 0:
            return JsonResponse(
                {"success": False, "message": "Invalid discount amount."}, status=400
            )
        discount_amount = discount_value
        message = f"Coupon applied: ${discount_value:.2f} off"

    # Clamp: discount cannot exceed cart total
    discount_amount = min(discount_amount, grand_total)
    new_total = _qmoney(grand_total - discount_amount)

    # ---------- (Optional) record preview usage state ----------
    # We do NOT persist here because user might cancel the checkout.
    # Persist actual redemption on order creation, referencing the coupon code.

    return JsonResponse(
        {
            "success": True,
            "discount_amount": float(discount_amount),
            "new_total": float(new_total),
            "message": message,
        },
        status=200,
    )
