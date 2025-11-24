# helpers_discounts.py

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Dict, Iterable, List, Optional, Set, Tuple

from django.utils import timezone

from main.models import ZERO, Coupon, DiscountType, ExtraCharge, Promotion, _qmoney

# ====================== DraftLine used pre-DB ======================


@dataclass
class DraftLine:
    kind: str  # "kit" | "plan" | "install" | "extra" | "adjust"
    description: str
    quantity: int
    unit_price: Decimal
    kit_inventory_id: Optional[int] = None
    plan_id: Optional[int] = None
    extra_charge_id: Optional[int] = None
    # NEW: scoped discounts support
    scopes: Optional[Set[str]] = field(
        default=None
    )  # {"plan"} | {"kit"} | {"install"} | {"extra"} | {"any"} | combos
    meta: Optional[Dict] = field(default=None)


LINE_KINDS_ALLOWED: Set[str] = {"kit", "plan", "install", "extra", "any"}


# ====================== scope helpers ======================


def _coerce_to_set(val) -> Set[str]:
    """
    Accept string / list / tuple / set / dict -> return lowercased set of kinds.
    Supports comma-separated strings like "plan,kit".
    If dict has {'all': True}, it becomes {'any'} (basket-wide).
    """
    if not val:
        return set()

    # Dict from UI: {"all":bool, "plan":bool, "kit":bool, ...}
    if isinstance(val, dict):
        if val.get("all"):
            return {"any"}
        out = {k.strip().lower() for k, v in val.items() if v and k and str(k).strip()}
        return out

    # String: allow comma/space separated
    if isinstance(val, str):
        raw = val.strip()
        if not raw:
            return set()
        # split on comma or whitespace
        parts = [
            p.strip().lower()
            for chunk in raw.split(",")
            for p in chunk.split()
            if p.strip()
        ]
        return set(parts) if parts else {raw.lower()}

    # Iterable
    try:
        return {str(x).strip().lower() for x in val if str(x).strip()}
    except TypeError:
        return set()


def _rule_scopes(rule) -> Set[str]:
    """
    Determine line-kind scopes for the rule. Multiple scopes (plan+kit, etc.) are allowed.
    Priority:
      1) limit_to_kinds
      2) applies_to / applies_to_kind
      3) effective_line_scopes
      4) fallback: {'any'}
    """
    scopes = _coerce_to_set(getattr(rule, "limit_to_kinds", None)) & LINE_KINDS_ALLOWED
    if scopes:
        return scopes

    applies_to = getattr(rule, "applies_to", None)
    if not applies_to:
        applies_to = getattr(rule, "applies_to_kind", None)
    scopes = _coerce_to_set(applies_to) & LINE_KINDS_ALLOWED
    if scopes:
        return scopes

    scopes = (
        _coerce_to_set(getattr(rule, "effective_line_scopes", None))
        & LINE_KINDS_ALLOWED
    )
    if scopes:
        return scopes

    return {"any"}


def _rule_targets(rule) -> Dict[str, Iterable]:
    """
    Optional fine-grained targeting lists (extend to your schema as needed).
    """
    return {
        "target_plan_ids": getattr(rule, "target_plan_ids", None) or [],
        "target_extra_charge_types": getattr(rule, "target_extra_charge_types", None)
        or [],
    }


def _is_rule_live(rule, now) -> bool:
    """Honor active/status and validity windows if present."""
    if hasattr(rule, "active") and not bool(getattr(rule, "active")):
        return False
    if hasattr(rule, "status"):
        st = str(getattr(rule, "status") or "").lower()
        if st and st not in {"active", "enabled"}:
            # allow unspecified statuses to pass
            pass
    vf = getattr(rule, "valid_from", None)
    vt = getattr(rule, "valid_to", None)
    if vf and now < vf:
        return False
    if vt and now > vt:
        return False
    if hasattr(rule, "is_live") and callable(getattr(rule, "is_live")):
        return bool(rule.is_live())
    return True


# ====================== eligibility & math ======================


def _eligible_draft_lines(lines: List[DraftLine], *, rule) -> List[DraftLine]:
    """
    Return only the lines the rule may touch, honoring explicit scopes and
    targets (plan IDs, extra types). Supports combinations like plan+kit, plan+install, etc.
    """
    scopes = _rule_scopes(rule) & LINE_KINDS_ALLOWED
    want_any = "any" in scopes
    targets = _rule_targets(rule)

    extra_type_filter = {
        str(x).lower() for x in (targets.get("target_extra_charge_types") or [])
    }
    extra_id_to_type: Dict[int, str] = {}
    if ("extra" in scopes or want_any) and extra_type_filter:
        extra_ids = [
            dl.extra_charge_id
            for dl in lines
            if dl.kind == "extra" and dl.extra_charge_id
        ]
        if extra_ids:
            for ex in ExtraCharge.objects.filter(id__in=set(extra_ids)).only(
                "id", "charge_type"
            ):
                t = getattr(ex, "charge_type", None)
                if t is not None:
                    extra_id_to_type[ex.id] = str(t).lower()

    target_plan_ids = {
        int(x) for x in (targets.get("target_plan_ids") or []) if str(x).isdigit()
    }

    out: List[DraftLine] = []
    for ln in lines:
        if ln.kind == "adjust":
            continue
        if not (want_any or ln.kind in scopes):
            continue
        if ln.kind == "plan" and target_plan_ids:
            if not ln.plan_id or int(ln.plan_id) not in target_plan_ids:
                continue
        if ln.kind == "extra" and extra_type_filter:
            et = extra_id_to_type.get(ln.extra_charge_id)
            if not et or et not in extra_type_filter:
                continue
        out.append(ln)

    return out


def _subtotal(lines: List[DraftLine]) -> Decimal:
    total = Decimal("0.00")
    for ln in lines:
        total += (ln.unit_price or ZERO) * Decimal(ln.quantity or 0)
    return _qmoney(total)


def _compute_rule_discount(eligible: List[DraftLine], *, rule) -> Decimal:
    base = _subtotal(eligible)
    if base <= 0:
        return ZERO

    dtype = getattr(rule, "discount_type", None)
    if dtype == DiscountType.PERCENT or str(dtype).lower() in {
        "percent",
        "percentage",
        "pct",
    }:
        raw = getattr(rule, "value", None) or getattr(rule, "percent_off", "0")
        value = Decimal(str(raw))
        amt = (base * (value / Decimal("100"))).quantize(Decimal("0.01"))
    else:
        raw = getattr(rule, "value", None) or getattr(rule, "amount_off", "0")
        value = Decimal(str(raw))
        amt = min(_qmoney(value), base)

    return _qmoney(amt) if amt > 0 else ZERO


def _adjust_label_for_rule(rule) -> str:
    if isinstance(rule, Coupon):
        return f"Coupon {rule.code}"
    return f"Promotion: {rule.name}"


def _scopes_for_rule(rule) -> Set[str]:
    scopes = _rule_scopes(rule) & LINE_KINDS_ALLOWED
    return scopes or {"any"}


def _make_scoped_adjust_line(
    *, label: str, amount: Decimal, scopes: Set[str]
) -> DraftLine:
    """
    Create an ADJUST line with explicit scope metadata and a [scopes=...] tag
    in the description so downstream code (e.g., taxes) can reason about it.
    `amount` is positive magnitude; unit_price stored negative.
    """
    scopes_csv = ",".join(sorted(scopes))
    desc = f"{label} [scopes={scopes_csv}]"
    return DraftLine(
        kind="adjust",
        description=desc,
        quantity=1,
        unit_price=_qmoney(-amount),
        scopes=set(scopes),
        meta={"scopes": list(scopes)},
    )


def apply_promotions_and_coupon_to_draft_lines(
    *, user, draft_lines: List[DraftLine], coupon_code: Optional[str] = None
) -> Dict:
    """
    Returns:
      {
        "lines": [DraftLine ... plus DraftLine(kind='adjust', unit_price=-X, scopes=...) ...],
        "applied": [(label, negative_amount), ...],
        "coupon": Coupon|None,
        "coupon_error": str|None,
      }
    """
    results: List[Tuple[str, Decimal]] = []
    out_lines = list(draft_lines)
    now = timezone.now()

    # -------- 1) Auto promotions (can have multi-scope) --------
    for promo in Promotion.objects.all():
        if not _is_rule_live(promo, now):
            continue
        elig = _eligible_draft_lines(out_lines, rule=promo)
        disc = _compute_rule_discount(elig, rule=promo)
        if disc > 0:
            lbl = _adjust_label_for_rule(promo)
            scopes = _scopes_for_rule(promo)  # e.g., {"plan","kit"}
            out_lines.append(
                _make_scoped_adjust_line(label=lbl, amount=disc, scopes=scopes)
            )
            results.append((lbl, Decimal(-_qmoney(disc))))

    # -------- 2) Optional coupon (can have multi-scope) --------
    coupon_obj = None
    coupon_error = None
    if coupon_code:
        code = coupon_code.strip().upper()
        coupon_obj = Coupon.objects.filter(code=code).first()
        if not coupon_obj:
            coupon_error = "Invalid coupon."
        elif not _is_rule_live(coupon_obj, now):
            coupon_error = "Coupon not currently valid."
        else:
            ok, msg = (True, None)
            if hasattr(coupon_obj, "can_redeem"):
                ok, msg = coupon_obj.can_redeem(user=user)
            if not ok:
                coupon_error = msg or "Coupon cannot be redeemed."
            else:
                elig = _eligible_draft_lines(out_lines, rule=coupon_obj)
                disc = _compute_rule_discount(elig, rule=coupon_obj)
                if disc > 0:
                    lbl = _adjust_label_for_rule(coupon_obj)
                    scopes = _scopes_for_rule(coupon_obj)  # e.g., {"plan","extra"}
                    out_lines.append(
                        _make_scoped_adjust_line(label=lbl, amount=disc, scopes=scopes)
                    )
                    results.append((lbl, Decimal(-_qmoney(disc))))
                else:
                    coupon_error = "No eligible items to discount."

    return {
        "lines": out_lines,
        "applied": results,
        "coupon": coupon_obj,
        "coupon_error": coupon_error,
    }
