import re
from decimal import Decimal

from main.models import ZERO, OrderLine, TaxRate, _qmoney


def compute_totals_from_lines(order):
    """
    Discounts are materialized as ADJUST (negative) lines.

    Pipeline:
      1) Build positive bases per kind (KIT/PLAN/INSTALL/EXTRA) and collect ADJUST
         totals per-target: PLAN / KIT / INSTALL / EXTRA / ANY (fallback).
      2) Subtotal_after_discounts = positives + all_adjusts (adjusts are negative).
      3) If user tax-exempt -> taxes = 0 (persist zero rows for consistency).
      4) Excise base = PLAN
         + ADJUSTs that explicitly target PLAN
         + proportional share of site-wide ("ANY") ADJUSTs allocated to PLAN.
         (ADJUSTs that target KIT/INSTALL/EXTRA do NOT change excise base.)
      5) Excise = EXCISE% * excise_base (floored at zero).
      6) VAT = VAT% * (Subtotal_after_discounts + Excise).
      7) Persist OrderTax rows and return amounts as strings.
    """

    # ---- Helpers -------------------------------------------------------------

    def _normalize_scopes(raw):
        """
        Normalize scopes to a lowercase set within {'plan','kit','install','extra','any'}.
        Empty/unknown -> {'any'}.
        """
        allowed = {"plan", "kit", "install", "extra", "any"}
        if not raw:
            return {"any"}
        if isinstance(raw, str):
            parts = [p.strip().lower() for p in raw.split(",") if p.strip()]
        else:
            parts = [str(p).strip().lower() for p in (raw or []) if str(p).strip()]
        scopes = set(p for p in parts if p in allowed)
        return scopes or {"any"}

    def _extract_scopes_from_adjust_line(ln):
        """
        Try several places to find scopes for an ADJUST line.
        Order of precedence:
          - ln.scopes / ln.target_scopes / ln.effective_line_scopes (attributes)
          - ln.meta / ln.metadata JSON: keys 'scopes' / 'target_scopes' / 'effective_line_scopes'
          - Bracket tag in description: '...[scopes=plan,kit]...'
          - Fallback: {'any'}
        """
        # direct attributes
        for attr in ("scopes", "target_scopes", "effective_line_scopes"):
            if hasattr(ln, attr):
                val = getattr(ln, attr)
                if val:
                    return _normalize_scopes(val)

        # metadata JSON-ish attributes
        for attr in ("meta", "metadata"):
            meta = getattr(ln, attr, None)
            if isinstance(meta, dict):
                for k in ("scopes", "target_scopes", "effective_line_scopes"):
                    if k in meta and meta[k]:
                        return _normalize_scopes(meta[k])

        # parse description marker if present
        desc = getattr(ln, "description", "") or ""
        m = re.search(r"\[scopes?=([^\]]+)\]", desc, flags=re.I)
        if m:
            csv = m.group(1)
            return _normalize_scopes(csv)

        # fallback
        return {"any"}

    # ---- Collect bases -------------------------------------------------------

    base_kit = Decimal("0.00")
    base_plan = Decimal("0.00")
    base_install = Decimal("0.00")
    base_extra = Decimal("0.00")

    # Adjust totals per scope bucket (negative numbers)
    adj_plan = Decimal("0.00")
    adj_kit = Decimal("0.00")
    adj_install = Decimal("0.00")
    adj_extra = Decimal("0.00")
    adj_any = Decimal("0.00")

    for ln in order.lines.all():
        line_amt = (ln.unit_price or ZERO) * Decimal(ln.quantity or 0)

        if ln.kind == OrderLine.Kind.KIT:
            base_kit += line_amt
        elif ln.kind == OrderLine.Kind.PLAN:
            base_plan += line_amt
        elif ln.kind == OrderLine.Kind.INSTALL:
            base_install += line_amt
        elif ln.kind == OrderLine.Kind.EXTRA:
            base_extra += line_amt
        elif ln.kind == OrderLine.Kind.ADJUST:
            # allocate this adjust amount to buckets by scope
            scopes = _extract_scopes_from_adjust_line(ln)
            # If multiple scopes are present, split evenly across listed scopes.
            # (This is conservative; you can change to proportional split if you store more detail.)
            listed = sorted(scopes)
            share = (line_amt / Decimal(len(listed))) if listed else line_amt
            for sc in listed or ["any"]:
                if sc == "plan":
                    adj_plan += share
                elif sc == "kit":
                    adj_kit += share
                elif sc == "install":
                    adj_install += share
                elif sc == "extra":
                    adj_extra += share
                else:
                    adj_any += share

    # Positive basket before discounts (for any proportional allocation)
    positive_basket = base_kit + base_plan + base_install + base_extra
    positive_basket = _qmoney(positive_basket if positive_basket > 0 else ZERO)

    # Grand total of all adjustments
    total_adjust = _qmoney(adj_plan + adj_kit + adj_install + adj_extra + adj_any)

    # Subtotal AFTER discounts (non-negative)
    subtotal = _qmoney(
        (positive_basket + total_adjust)
        if (positive_basket + total_adjust) > 0
        else ZERO
    )

    # ---- Fetch configured rates (defaults if missing) ------------------------

    vat_rate_pct = Decimal("0.00")
    excise_rate_pct = Decimal("10.00")  # default per business rule

    try:
        vat_rec = TaxRate.objects.filter(description="VAT").first()
        if vat_rec and vat_rec.percentage is not None:
            vat_rate_pct = Decimal(vat_rec.percentage)
    except Exception:
        pass

    try:
        excise_rec = TaxRate.objects.filter(description="EXCISE").first()
        if excise_rec and excise_rec.percentage is not None:
            excise_rate_pct = Decimal(excise_rec.percentage)
    except Exception:
        pass

    # ---- Tax-exempt: persist zero rows and return ----------------------------

    is_tax_exempt = bool(getattr(getattr(order, "user", None), "is_tax_exempt", False))

    # Rebuild taxes snapshot idempotently
    order.taxes.all().delete()

    if is_tax_exempt or subtotal <= 0:
        if excise_rate_pct > 0:
            order.taxes.create(
                kind="EXCISE", rate=_qmoney(excise_rate_pct), amount=_qmoney(ZERO)
            )
        if vat_rate_pct > 0:
            order.taxes.create(
                kind="VAT", rate=_qmoney(vat_rate_pct), amount=_qmoney(ZERO)
            )
        return {
            "subtotal": str(subtotal),
            "tax_total": str(_qmoney(ZERO)),
            "total": str(subtotal),
        }

    # ---- Excise: apply ONLY on PLAN after relevant discounts -----------------
    # 1) Start with base_plan
    # 2) Add ADJUSTs that explicitly target PLAN (adj_plan is negative -> reduces base)
    # 3) Add PLAN's proportional share of site-wide ("any") adjustments
    #    (but DO NOT include kit/install/extra-only ADJUSTs)
    plan_share = (base_plan / positive_basket) if positive_basket > 0 else Decimal("0")
    allocated_any_to_plan = _qmoney(adj_any * plan_share)  # adj_any is negative

    excise_base = _qmoney(base_plan + adj_plan + allocated_any_to_plan)
    if excise_base < 0:
        excise_base = _qmoney(ZERO)

    excise_amount = _qmoney(excise_base * (excise_rate_pct / Decimal("100")))

    # ---- VAT on (discounted subtotal + excise) -------------------------------

    vat_base = _qmoney(subtotal + excise_amount)
    vat_amount = _qmoney(vat_base * (vat_rate_pct / Decimal("100")))

    tax_total = _qmoney(excise_amount + vat_amount)
    total = _qmoney(subtotal + tax_total)

    # ---- Persist snapshot rows ------------------------------------------------
    if excise_rate_pct > 0:
        order.taxes.create(
            kind="EXCISE", rate=_qmoney(excise_rate_pct), amount=excise_amount
        )
    if vat_rate_pct > 0:
        order.taxes.create(kind="VAT", rate=_qmoney(vat_rate_pct), amount=vat_amount)

    return {
        "subtotal": str(subtotal),
        "tax_total": str(tax_total),
        "total": str(total),
    }
