from decimal import Decimal

from django.conf import settings

from client_app.client_helpers import installation_fee_for_coords
from main.calculations import determine_region_from_location
from main.models import InstallationFee, Order, OrderLine


def _dt(v):
    """Safe ISO8601 formatter for datetimes/dates."""
    if not v:
        return None
    try:
        return v.isoformat()
    except Exception:
        return str(v)


def _qmoney(x):
    x = Decimal(str(x or "0"))
    return x.quantize(Decimal("0.01"))


def _supports_skip_locked(qs):
    try:
        qs.select_for_update(skip_locked=True)  # type: ignore
        return True
    except Exception:
        return False


def _safe_installation_fee_from_coords(lat: float, lng: float) -> Decimal:
    """
    Primary path: use the same helper as submit_order (installation_fee_for_coords).
    Fallback: resolve a Region in multiple safe ways and fetch InstallationFee.
    """
    # 1) Same logic as submit_order
    if installation_fee_for_coords:
        try:
            return _qmoney(installation_fee_for_coords(lat, lng))
        except Exception:
            pass  # fall through to region-based lookup

    # 2) Region-based fallback (robust to str/int/Region instance)
    region_obj = None
    region_name = None
    region_id = None

    if determine_region_from_location:
        try:
            region = determine_region_from_location(lat, lng)
        except Exception:
            region = None
    else:
        region = None

    # Region may be an instance, an id, or a string like "Haut-Katanga / Lubumbashi"
    try:
        from geo_regions.models import Region  # type: ignore
    except Exception:
        Region = None  # noqa

    if Region and region is not None and isinstance(region, Region):
        region_obj = region
    elif isinstance(region, int):
        region_id = region
    elif isinstance(region, str) and region.strip():
        region_name = region.strip()

    fee_q = InstallationFee.objects.all()

    if region_obj is not None:
        fee_q = fee_q.filter(region=region_obj)
    elif region_id is not None:
        fee_q = fee_q.filter(region_id=region_id)
    elif region_name:
        # Try name / slug / alt fields defensively; keep this flexible
        fee_q = fee_q.filter(
            Q(region__name__iexact=region_name)
            | Q(region__slug__iexact=region_name)
            | Q(region__full_name__iexact=region_name)
        )

    fee = fee_q.order_by("-id").first()
    return _qmoney(getattr(fee, "amount_usd", Decimal("0.00")) or Decimal("0.00"))


def _price_order_from_lines(order: Order) -> dict:
    """
    Compute taxes/total from the order's lines (same structure as submit_order).
    - Excise applies to PLAN only
    - VAT applies to (subtotal + excise)
    Persists OrderTax rows with kinds 'EXCISE' and 'VAT'.
    Returns str-ified numbers for JSON response consistency.
    """
    lines = list(order.lines.all())
    base_subtotal = _qmoney(sum((l.line_total or Decimal("0.00")) for l in lines))
    plan_base = _qmoney(
        sum(
            (l.line_total or Decimal("0.00"))
            for l in lines
            if l.kind == OrderLine.Kind.PLAN
        )
    )

    taxable = not getattr(getattr(order, "user", None), "is_tax_exempt", False)
    VAT_RATE = Decimal(str(getattr(settings, "VAT_RATE", "0.16")))
    EXCISE_RATE = Decimal(str(getattr(settings, "EXCISE_RATE", "0.10")))

    if taxable:
        excise = _qmoney(plan_base * EXCISE_RATE)  # on PLAN only
        vat = _qmoney((base_subtotal + excise) * VAT_RATE)  # on (subtotal + excise)
    else:
        excise = Decimal("0.00")
        vat = Decimal("0.00")

    # Persist taxes (uppercase kinds to match OrderTax.Kind)
    order.taxes.filter(kind__in=["EXCISE", "VAT"]).delete()
    if taxable:
        order.taxes.create(kind="EXCISE", rate=EXCISE_RATE, amount=excise)
        order.taxes.create(kind="VAT", rate=VAT_RATE, amount=vat)

    tax_total = _qmoney(excise + vat)
    grand_total = _qmoney(base_subtotal + tax_total)

    # Reflect totals on order if fields exist; always set total_price
    fields_to_update = []
    if hasattr(order, "subtotal_price"):
        order.subtotal_price = base_subtotal
        fields_to_update.append("subtotal_price")
    if hasattr(order, "tax_total"):
        order.tax_total = tax_total
        fields_to_update.append("tax_total")

    order.total_price = grand_total
    fields_to_update.append("total_price")
    order.save(update_fields=fields_to_update)

    return {
        "subtotal": str(base_subtotal),
        "tax_total": str(tax_total),
        "total": str(grand_total),
    }
