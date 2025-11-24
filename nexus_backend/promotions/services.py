import logging
from decimal import Decimal

from django.db.models import Sum

from main.models import SubscriptionPlan  # adjust path
from main.models import (
    Coupon,
    CouponRedemption,
    DiscountType,
    OrderLine,
    Promotion,
    StackPolicy,
)

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")


def _matches_target(obj, plan: SubscriptionPlan):
    ok_plan = not obj.target_plan_ids or plan.id in obj.target_plan_ids
    ok_type = not obj.target_plan_types or (
        plan.plan_type and plan.plan_type in obj.target_plan_types
    )
    ok_site = not obj.target_site_types or (
        plan.site_type and plan.site_type in obj.target_site_types
    )
    return ok_plan and ok_type and ok_site


def _apply_discount(
    amount: Decimal, discount_type: str, value: Decimal
) -> tuple[Decimal, Decimal]:
    """
    Returns (new_amount, applied_amount)
    """
    amount = amount or Decimal("0")
    value = value or Decimal("0")
    if discount_type == DiscountType.PERCENT:
        applied = (amount * (value / Decimal("100"))).quantize(Decimal("0.01"))
    else:
        applied = min(amount, value).quantize(Decimal("0.01"))
    return (amount - applied), applied


def find_live_promotions_for(plan: SubscriptionPlan):
    qs = Promotion.objects.filter(active=True)
    promos = [p for p in qs if p.is_live() and _matches_target(p, plan)]
    # Sort by ‘value’ descending so the strongest promo hits first (optional)
    promos.sort(key=lambda p: (p.discount_type, p.value), reverse=True)
    return promos


def validate_coupon_for_user(code: str, user, plan):
    """
    Returns (coupon, error_message). On success: (Coupon, None). On failure: (None, "reason").
    """
    code = (code or "").strip()
    if not code:
        return None, "Invalid code."

    try:
        coupon = Coupon.objects.get(code__iexact=code)
    except Coupon.DoesNotExist:
        return None, "Invalid code."

    # Active + date window
    if not coupon.is_live():
        return None, "Coupon is not active."

    # Targeting
    if not _matches_target(coupon, plan):
        return None, "Coupon not applicable to this plan."

    # Usage caps (match new names!)
    total_used = coupon.redemptions.count()
    if coupon.max_redemptions is not None and total_used >= coupon.max_redemptions:
        return None, "Coupon already fully used."

    user_used = coupon.redemptions.filter(user=user).count()
    if coupon.per_user_limit is not None and user_used >= coupon.per_user_limit:
        return None, "You have already used this coupon."

    return coupon, None


def price_with_discounts(
    *,
    user,
    plan,
    base_amount: Decimal,
    coupon_code: str | None = None,
    stack_policy: str | None = None,
):
    original = base_amount or Decimal("0")
    amount = original
    lines = []

    promos = find_live_promotions_for(plan)  # expects .discount_type and .value
    coupon = None
    coupon_err = None
    if coupon_code:
        coupon, coupon_err = validate_coupon_for_user(coupon_code, user, plan)

    # stacking policy
    if stack_policy:
        policy = stack_policy
    elif coupon and coupon.stack_policy:
        policy = coupon.stack_policy
    elif promos and promos[0].stack_policy:
        policy = promos[0].stack_policy
    else:
        policy = StackPolicy.PROMO_THEN_COUPON

    def apply_promos(a):
        for p in promos:
            a2, applied = _apply_discount(a, p.discount_type, p.value)
            if applied > 0:
                lines.append((f"Promotion: {p.name}", -applied))
                a = a2
        return a

    def apply_coupon(a):
        if not coupon:
            return a
        # Derive value from coupon’s fields
        if coupon.discount_type == DiscountType.PERCENT:
            value = coupon.percent_off or Decimal("0")
        else:
            value = coupon.amount_off or Decimal("0")

        a2, applied = _apply_discount(a, coupon.discount_type, value)
        if applied > 0:
            lines.append((f"Coupon: {coupon.code}", -applied))
        return a2

    if policy == StackPolicy.COUPON_THEN_PROMO:
        amount = apply_coupon(amount)
        amount = apply_promos(amount)
    else:
        amount = apply_promos(amount)
        amount = apply_coupon(amount)

    amount = max(Decimal("0"), amount)
    total_discount = original - amount
    return {
        "original": original,
        "discounted": amount,
        "discount_total": total_discount,
        "lines": lines,
        "coupon": coupon,
        "coupon_error": coupon_err,
        "promotions": promos,
        "stack_policy": policy,
    }


# ---------------- Coupon helpers ----------------


def _extract_coupon_from_order(order):
    """
    Try multiple places to find the coupon code tied to this order.
    Returns (coupon_code: str|None, discounted_amount: Decimal|None).
    discounted_amount is the ABS sum of negative coupon ADJUST lines if available.
    """
    # 1) If you stored it directly on Order (recommended simplest approach)
    code = getattr(order, "coupon_code", None)
    if code:
        neg_total = order.lines.filter(
            kind=OrderLine.Kind.ADJUST, description__icontains=code
        ).aggregate(s=Sum("line_total")).get("s") or Decimal("0.00")
        discounted_amount = abs(neg_total) if neg_total < 0 else None
        return code, discounted_amount

    # 2) If you stashed it in JSON meta (if you have an order.meta JSONField)
    meta = getattr(order, "meta", None)
    if isinstance(meta, dict):
        meta_code = meta.get("coupon") or meta.get("coupon_code")
        if meta_code:
            neg_total = order.lines.filter(
                kind=OrderLine.Kind.ADJUST, description__icontains=meta_code
            ).aggregate(s=Sum("line_total")).get("s") or Decimal("0.00")
            discounted_amount = abs(neg_total) if neg_total < 0 else None
            return meta_code, discounted_amount

    # 3) Parse ADJUST lines like "Coupon: SAVE10" or "Promo: LAUNCH"
    adjust = (
        order.lines.filter(kind=OrderLine.Kind.ADJUST)
        .order_by("-id")
        .values("description", "line_total")
        .first()
    )
    if adjust:
        desc = (adjust["description"] or "").strip()
        amt = Decimal(adjust["line_total"] or "0.00")
        if desc.lower().startswith("coupon:"):
            code = desc.split(":", 1)[-1].strip()
            discounted_amount = abs(amt) if amt < 0 else None
            return code, discounted_amount
        if desc.lower().startswith("promo:"):
            code = desc.split(":", 1)[-1].strip()
            discounted_amount = abs(amt) if amt < 0 else None
            return code, discounted_amount

    return None, None


def record_coupon_redemption_if_any(order):
    """
    Idempotently record a coupon redemption when an order is PAID.
    Never raises: logs error and returns if anything is wrong.
    """
    try:
        # Already recorded for this order?
        if CouponRedemption.objects.filter(order=order).exists():
            return

        code, discounted_amount = _extract_coupon_from_order(order)
        if not code:
            return  # nothing to record

        # Confirm coupon exists and is active
        try:
            coupon = Coupon.objects.get(code__iexact=code, is_active=True)
        except Coupon.DoesNotExist:
            return  # ignore unknown/inactive codes silently

        # Idempotency again: (coupon, order) unique in spirit
        if CouponRedemption.objects.filter(coupon=coupon, order=order).exists():
            return

        CouponRedemption.objects.create(
            coupon=coupon,
            user=order.user if order.user_id else None,
            order=order,
            subscription=getattr(order, "subscription", None),
            discount_type=coupon.discount_type,  # e.g. "percent" | "fixed"
            value=coupon.value,  # the configured value
            discounted_amount=discounted_amount or Decimal("0.00"),
        )

        # Optional: if you track usage caps, increment here
        # if coupon.max_uses:
        #     Coupon.objects.filter(pk=coupon.pk).update(uses=F("uses") + 1)

    except Exception:
        logger.exception("Failed to record coupon redemption for order %s", order.id)
