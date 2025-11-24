import re
from decimal import Decimal

from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing, Group, Rect, String
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import Table, TableStyle

from django.db import transaction
from django.utils import timezone

from main.models import (
    ZERO,
    AccountEntry,
    BillingAccount,
    CompanySettings,
    ConsolidatedInvoice,
    Invoice,
    InvoiceLine,
    InvoiceOrder,
    Order,
    OrderLine,
    _qmoney,
)


def _safe(x) -> str:
    return str(x).strip() if x not in (None, "") else "—"


def _money(x) -> str:
    try:
        return f"${Decimal(x or 0):,.2f}"
    except Exception:
        return "$0.00"


# Center any flowable with a specific (narrower) width
def center_flow(flowable, width):
    t = Table([[flowable]], colWidths=[width], hAlign="CENTER")
    t.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return t


def make_qr_card(
    data: str, size_mm: float = 44.0, caption: str | None = "Scan to view invoice"
):
    """
    Returns a Drawing containing:
      - rounded light background
      - centered QR code
      - optional centered caption
    """
    size = size_mm * mm
    padding = 4 * mm  # inner padding around the QR
    cap_height = (6 * mm) if caption else 0

    # Base drawing height includes QR “card” plus small extra to breathe
    d = Drawing(width=size, height=size + cap_height)

    # Background card (rounded rectangle)
    d.add(
        Rect(
            0,
            cap_height,  # start at caption height so card sits above caption
            size,
            size,
            rx=4,
            ry=4,
            fillColor=colors.whitesmoke,
            strokeColor=colors.lightgrey,
            strokeWidth=0.6,
        )
    )

    # Create QR widget
    qr_widget = qr.QrCodeWidget(data)  # you can pass a URL here instead of inv_no
    x0, y0, x1, y1 = qr_widget.getBounds()
    qr_w, qr_h = (x1 - x0), (y1 - y0)

    # Scale QR so it fits inside the card with padding
    scale = (size - 2 * padding) / max(qr_w, qr_h)

    # Position (translate) so it’s centered inside the card
    tx = (size - qr_w * scale) / 2
    ty = cap_height + (size - qr_h * scale) / 2

    g = Group(qr_widget)
    g.transform = [scale, 0, 0, scale, tx, ty]
    d.add(g)

    # Optional caption under the card
    if caption:
        d.add(
            String(
                size / 2,  # centered
                (cap_height - 2 * mm),  # a touch above the very bottom
                caption,
                textAnchor="middle",
                fontName="Helvetica",
                fontSize=8,
                fillColor=colors.gray,
            )
        )

    return d


def issue_invoice(inv) -> "Invoice":
    """
    Issue a draft Invoice:
      - Assign a unique number via next_invoice_number()
      - Set issued_at / due_at (CompanySettings.payment_terms_days)
      - Compute subtotal from invoice lines (includes discounts/ADJUST)
      - Prefer taxes from linked Order snapshot (OrderTax) if available
      - Otherwise compute VAT/Excise from TaxRate, honoring user tax-exempt flag
      - Set status=issued and create a ledger AccountEntry (+ charge)
    """
    from main.models import CompanySettings, Invoice, TaxRate  # adjust imports

    if not inv or inv.status != Invoice.Status.DRAFT:
        return inv

    with transaction.atomic():
        cs = CompanySettings.objects.select_for_update().get(pk=1)

        # 1) Number + timestamps
        # Determine customer type for numbering based on APPROVED KYC:
        #   - COR if CompanyKYC.status == 'approved'
        #   - IND if PersonalKYC.status == 'approved'
        #   - Fallback: IND
        type_code = "IND"
        try:
            u = inv.user
            ckyc = getattr(u, "company_kyc", None)
            pkyc = getattr(u, "personnal_kyc", None)
            if ckyc and getattr(ckyc, "status", "") == "approved":
                type_code = "COR"
            elif pkyc and getattr(pkyc, "status", "") == "approved":
                type_code = "IND"
        except Exception:
            pass

        inv.number = next_invoice_number(
            type_code=type_code
        )  # uses annual reset & uniqueness
        inv.issued_at = timezone.now()

        try:
            terms_days = int(cs.payment_terms_days or 0)
        except Exception:
            terms_days = 0
        inv.due_at = (
            (inv.issued_at + timezone.timedelta(days=terms_days))
            if terms_days > 0
            else None
        )

        # 2) Subtotal from lines (include discounts; exclude any explicit tax-adjust lines)
        lines = list(inv.lines.all())
        subtotal = ZERO
        for l in lines:
            line_total = (
                l.line_total
                if l.line_total is not None
                else _qmoney((l.unit_price or ZERO) * Decimal(l.quantity or 0))
            )
            if (getattr(l, "kind", "") or "").lower() not in {"tax_adjust", "tax"}:
                subtotal += line_total
        inv.subtotal = _qmoney(subtotal)

        # 3) Resolve tax regime and rates from DB (TaxRate), honoring tax-exempt flag
        is_exempt = bool(getattr(getattr(inv, "user", None), "is_tax_exempt", False))
        vat_rate_pct = Decimal("0.00")
        excise_rate_pct = Decimal("0.00")
        try:
            vat_rec = (
                TaxRate.objects.filter(description="VAT").only("percentage").first()
            )
            if vat_rec and vat_rec.percentage is not None:
                vat_rate_pct = Decimal(vat_rec.percentage)
        except Exception:
            pass
        try:
            excise_rec = (
                TaxRate.objects.filter(description="EXCISE").only("percentage").first()
            )
            if excise_rec and excise_rec.percentage is not None:
                excise_rate_pct = Decimal(excise_rec.percentage)
        except Exception:
            pass
        if is_exempt:
            vat_rate_pct = Decimal("0.00")
            excise_rate_pct = Decimal("0.00")

        # Snapshot the chosen rates on the invoice
        inv.vat_rate_percent = _qmoney(vat_rate_pct)
        inv.excise_rate_percent = (
            _qmoney(excise_rate_pct) if excise_rate_pct is not None else None
        )

        # 4) Compute taxes strictly from OrderTax when possible and create consolidated tax lines
        vat_amount = Decimal("0.00")
        excise_amount = Decimal("0.00")
        orders = []
        try:
            # Prefer explicit InvoiceOrder links
            orders = [ol.order for ol in inv.order_links.select_related("order")]
            if not orders:
                # Fallback: infer orders from invoice lines
                ords = []
                for l in lines:
                    if getattr(l, "order", None) and l.order not in ords:
                        ords.append(l.order)
                orders = ords
        except Exception:
            orders = []

        if orders:
            # Sum OrderTax by kind across all linked orders (consolidated or single)
            for o in orders:
                taxes_qs = o.taxes.all()
                vat_amount += sum(
                    (
                        Decimal(t.amount)
                        for t in taxes_qs
                        if getattr(t, "kind", "").upper() == "VAT"
                    ),
                    Decimal("0.00"),
                )
                excise_amount += sum(
                    (
                        Decimal(t.amount)
                        for t in taxes_qs
                        if getattr(t, "kind", "").upper() in ("EXCISE", "EXC")
                    ),
                    Decimal("0.00"),
                )
        else:
            # No orders linked; fallback to rate-based computation on subtotal
            vat_amount = (
                (subtotal * vat_rate_pct) / Decimal("100")
                if vat_rate_pct
                else Decimal("0.00")
            )
            excise_amount = (
                (subtotal * excise_rate_pct) / Decimal("100")
                if excise_rate_pct
                else Decimal("0.00")
            )

        # Normalize to money
        vat_amount = _qmoney(vat_amount)
        excise_amount = _qmoney(excise_amount)

        # Snapshot separated tax amounts on the invoice record
        try:
            inv.vat_amount = vat_amount
            inv.excise_amount = excise_amount
        except Exception:
            # Older schemas might not have fields yet; ignore assignment
            pass

        # Remove any pre-existing tax lines (to avoid duplicates on re-issue) and recreate
        inv.lines.filter(kind__iexact="tax").delete()

        # Create exactly one line per tax kind if amount > 0
        if excise_amount and Decimal(excise_amount) != Decimal("0.00"):
            InvoiceLine.objects.create(
                invoice=inv,
                description="Excise",
                quantity=Decimal("1"),
                unit_price=excise_amount,
                kind="tax",
            )
        if vat_amount and Decimal(vat_amount) != Decimal("0.00"):
            InvoiceLine.objects.create(
                invoice=inv,
                description="VAT",
                quantity=Decimal("1"),
                unit_price=vat_amount,
                kind="tax",
            )

        tax_total = _qmoney((excise_amount or ZERO) + (vat_amount or ZERO))
        inv.tax_total = tax_total
        inv.grand_total = _qmoney(inv.subtotal + inv.tax_total)
        inv.status = Invoice.Status.ISSUED

        inv.save(
            update_fields=[
                "number",
                "issued_at",
                "due_at",
                "subtotal",
                "tax_total",
                "grand_total",
                "status",
                "vat_rate_percent",
                "excise_rate_percent",
                "vat_amount",
                "excise_amount",
            ]
        )

        # 6) Ledger entry
        acct, _ = BillingAccount.objects.get_or_create(user=inv.user)
        AccountEntry.objects.create(
            account=acct,
            entry_type="invoice",
            amount_usd=inv.grand_total,
            description=f"Invoice {inv.number}",
        )

    return inv


INVOICE_PAD_WIDTH = 6  # 000001 … 999999


def _format_number(year: int, seq: int, type_code: str) -> str:
    """
    New canonical format (requested):
      YYYY-TYPE-######
    where TYPE ∈ {IND, COR}
    """
    tc = (type_code or "IND").strip().upper()
    if tc not in {"IND", "COR"}:
        tc = "IND"
    return f"{year}-{tc}-{seq:0{INVOICE_PAD_WIDTH}d}"


@transaction.atomic
def next_invoice_number(*, type_code: str = "IND", force_date=None) -> str:
    """
    Allocate the next unique invoice number in the format `YYYY-TYPE-######` and advance the counter.
    - TYPE is "IND" for individuals and "COR" for corporate customers.
    - Concurrency-safe with SELECT FOR UPDATE on CompanySettings.
    - Respects CompanySettings.reset_number_annually (annual counter reset).
    - Ensures uniqueness across Invoice and ConsolidatedInvoice tables.
    """
    today = force_date or timezone.localdate()

    # Lock settings row
    cs = CompanySettings.objects.select_for_update().get(pk=1)
    year = cs.current_invoice_year()
    annual = bool(cs.reset_number_annually)

    # Start from stored next value
    seq = int(cs.next_invoice_number or 1)

    # Helper to compute the maximum existing sequence for the current year
    def _max_seq_for_year() -> int:
        max_seq = 0
        year_prefix = f"{year}-"
        # Scan invoice numbers that start with "YYYY-" to extract numeric tail
        # Include both Invoice and ConsolidatedInvoice for safety. If consolidated numbers
        # don't match the pattern, they will be skipped.
        pattern = re.compile(rf"^{year}-(IND|COR)-(\d{{{INVOICE_PAD_WIDTH}}})$")
        for model in (Invoice, ConsolidatedInvoice):
            for row in model.objects.filter(number__startswith=year_prefix).only(
                "number"
            ):
                try:
                    m = pattern.match(row.number or "")
                    if not m:
                        continue
                    num = int(m.group(2))
                    if num > max_seq:
                        max_seq = num
                except Exception:
                    continue
        return max_seq

    # If we reset annually, ensure seq is at least max(yearly)+1
    if annual:
        max_existing = _max_seq_for_year()
        if seq <= max_existing:
            seq = max_existing + 1

    # Find first non-colliding number
    while True:
        candidate = _format_number(year, seq, type_code)
        if not (
            Invoice.objects.filter(number=candidate).exists()
            or ConsolidatedInvoice.objects.filter(number=candidate).exists()
        ):
            break
        seq += 1

    # Persist next for the following call
    cs.next_invoice_number = seq + 1
    cs.save(update_fields=["next_invoice_number"])

    return candidate


@transaction.atomic
def create_consolidated_invoice(
    *, user, orders, using: str = "default"
) -> tuple[Invoice, ConsolidatedInvoice]:
    """
    Create a consolidated invoice for the given user and list of orders.
    Rules:
    - Build a single DRAFT Invoice with sections per order: a header line with the order_ref,
      followed by all detailed order lines for that order.
    - Create `InvoiceOrder` join rows for each order, with `amount_excl_tax` equal to the order's pre-tax subtotal
      (excludes ADJUST/discount lines to avoid double-taxing).
    - Finalize by calling `issue_invoice()` which assigns a unique number, computes taxes, totals,
      and creates the ledger entry.
    - Create a `ConsolidatedInvoice` record and assign it the same number and totals as the issued Invoice.
    Returns (invoice, consolidated_invoice).
    """
    from django.db import connections

    # Ensure we operate on desired DB alias
    conn = connections[using]

    if not orders:
        raise ValueError("orders must be a non-empty list")

    # Normalize to concrete Order objects and ensure same user
    orders = [o for o in orders if o is not None]
    if not orders:
        raise ValueError("orders list contains no valid items")

    # Refresh orders from database to ensure we have the latest user_id values
    order_ids = [o.pk for o in orders]
    orders = list(
        Order.objects.using(using).filter(pk__in=order_ids).select_related("user")
    )

    # Get the expected user ID
    expected_user_id = user.pk if user else None

    # Enforce same user for all orders with better error messaging
    for o in orders:
        order_user_id = o.user_id if o.user else None
        if order_user_id != expected_user_id:
            raise ValueError(
                f"All orders in a consolidated invoice must belong to the same user. "
                f"Expected user_id={expected_user_id}, but order {o.order_reference or o.pk} has user_id={order_user_id}"
            )

    # Create a DRAFT invoice which will hold all lines
    cs = CompanySettings.get()
    inv = Invoice.objects.using(using).create(
        user=user,
        currency=cs.default_currency or "USD",
        tax_regime=cs.tax_regime,
        vat_rate_percent=cs.vat_rate_percent,
        status=Invoice.Status.DRAFT,
        bill_to_name=(getattr(user, "full_name", None) or getattr(user, "email", "")),
        bill_to_address="",
    )

    # Add per-order section header and detailed lines
    sum_subtotals = ZERO
    for o in orders:
        # Header/section line with the order reference at the beginning
        order_ref = o.order_reference or str(o.pk)
        InvoiceLine.objects.using(using).create(
            invoice=inv,
            description=f"Order {order_ref}",  # section header
            quantity=Decimal("0"),  # informational header, no amount
            unit_price=ZERO,
            kind="section",
            order=o,
            order_line=None,
        )
        # Detailed lines copied from the order
        for ol in o.lines.all().order_by("id"):
            InvoiceLine.objects.using(using).create(
                invoice=inv,
                description=ol.description,
                quantity=Decimal(ol.quantity or 1),
                unit_price=ol.unit_price or ZERO,
                kind=ol.kind,
                order=o,
                order_line=ol,
            )
        # Link join table with pre-tax subtotal (exclude ADJUST lines)
        order_subtotal = sum(
            (
                l.line_total
                for l in o.lines.all()
                if (l.kind or "") != OrderLine.Kind.ADJUST
            ),
            ZERO,
        )
        InvoiceOrder.objects.using(using).create(
            invoice=inv,
            order=o,
            amount_excl_tax=_qmoney(order_subtotal),
        )
        sum_subtotals += _qmoney(order_subtotal)

    # Issue the invoice (assign number, compute tax/totals, ledger entry)
    inv = issue_invoice(inv)

    # Create the consolidated envelope and point the invoice to it
    cons = ConsolidatedInvoice.objects.using(using).create(
        number=inv.number,  # share same number for traceability
        user=user,
        total=inv.grand_total,
        currency=inv.currency,
        due_date=inv.due_at,
        status="issued",
    )
    # Link back
    inv.consolidated_of = cons
    inv.save(update_fields=["consolidated_of"])

    return inv, cons
