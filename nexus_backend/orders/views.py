import datetime as dt
import math
import os
from decimal import Decimal, InvalidOperation
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.timezone import localtime
from django.views.decorators.http import require_POST

from api.views import _apply_taxes, _detect_order_contents
from client_app.client_helpers import _qmoney
from main.models import (
    ZERO,
    AccountEntry,
    BillingAccount,
    ConsolidatedInvoice,
    Invoice,
    InvoiceOrder,
    InvoicePayment,
    Order,
    OrderLine,
    OrderTax,
    PaymentAttempt,
    Wallet,
)
from nexus_backend import settings
from user.permissions import require_staff_role


# Create your views here.
@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "sales"])
def order_management(request):
    template = "order_management_main.html"

    # Base queryset
    orders = Order.objects.select_related("user").order_by("-created_at")

    # Status counts
    paid_count = orders.filter(payment_status__iexact="paid").count()
    unpaid_count = orders.filter(payment_status__iexact="unpaid").count()
    failed_count = orders.filter(payment_status__iexact="failed").count()

    # ===== Totals for paid invoices =====
    paid_qs = orders.filter(payment_status__iexact="paid")

    # Today (local timezone)
    today = timezone.localdate()
    start_today = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    end_today = timezone.make_aware(dt.datetime.combine(today, dt.time.max))

    sales_today_usd = paid_qs.filter(
        created_at__range=(start_today, end_today)
    ).aggregate(total=Coalesce(Sum("total_price"), Decimal("0.00")))["total"]

    # This month (from 1st day of current month to now)
    first_of_month = today.replace(day=1)
    start_month = timezone.make_aware(dt.datetime.combine(first_of_month, dt.time.min))
    now = timezone.now()

    sales_month_usd = paid_qs.filter(created_at__range=(start_month, now)).aggregate(
        total=Coalesce(Sum("total_price"), Decimal("0.00"))
    )["total"]

    context = {
        "orders": orders,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "failed_count": failed_count,
        "sales_today_usd": sales_today_usd,
        "sales_month_usd": sales_month_usd,
    }
    return render(request, template, context)


def _tax_totals(order: Order):
    """Return (vat, exc) as floats from related OrderTax rows."""
    agg = order.taxes.aggregate(
        vat=Sum("amount", filter=Q(kind="VAT")),
        exc=Sum("amount", filter=Q(kind="EXCISE")),
    )
    vat = float(agg.get("vat") or 0)
    exc = float(agg.get("exc") or 0)
    return vat, exc


def _has_kit(order: Order) -> bool:
    return order.lines.filter(kind=OrderLine.Kind.KIT).exists()


def _has_plan(order: Order) -> bool:
    return order.lines.filter(kind=OrderLine.Kind.PLAN).exists()


def _designation(order: Order) -> str:
    has_kit = _has_kit(order)
    has_plan = _has_plan(order)
    if has_kit and has_plan:
        return "Kit & Subscription"
    if has_kit:
        return "Kit Purchase"
    if has_plan:
        return "Subscription"
    return "N/A"


# ---- Payment state groupings (mapped to your model choices) ----
# Order.payment_status uses: unpaid, awaiting_confirmation, paid, cancelled
PAID_STATUSES = {"paid", "settled", "completed", "succeeded", "paid_in_full"}
UNPAID_STATUSES = {"unpaid"}
PENDING_STATUSES = {"pending", "awaiting_confirmation", "in_progress"}
FAILED_STATUSES = {"failed", "declined", "error"}
CANCELLED_STATUSES = {"cancelled", "canceled"}


def _safe_customer_label(u):
    if not u:
        return "—"
    full = ""
    if hasattr(u, "get_full_name"):
        full = (u.get_full_name() or "").strip()
    full = full or getattr(u, "full_name", "") or ""
    return full or getattr(u, "email", "") or getattr(u, "username", "") or "—"


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "sales"])
def admin_view_orders(request):
    """
    JSON endpoint consumed by the Order Management page.
    It merges single orders and consolidated invoices into one list,
    exposes `invoice_line` so the UI can show a single-line designation.
    Adds tax totals: `tax_total` (singles) and `sum_tax_total` (consolidated).
    """
    try:
        page = max(int(request.GET.get("page", 1)), 1)
        per_page = max(min(int(request.GET.get("per_page", 20)), 200), 1)
    except Exception:
        page, per_page = 1, 20

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip().lower()

    # ---------------------
    # Singles (Order rows)
    # ---------------------
    oqs = (
        Order.objects.select_related("user", "plan")
        .prefetch_related("taxes", "lines")
        .all()
    )

    if q:
        oqs = oqs.filter(
            Q(order_reference__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )

    # Allow filtering by either order.status or payment_status (common admin need)
    if status:
        if status in {
            "pending_payment",
            "fulfilled",
            "cancelled",
            "awaiting_confirmation",
        }:
            oqs = oqs.filter(status__iexact=status)
        elif status in {"paid", "unpaid", "partially_paid", "awaiting_confirmation"}:
            oqs = oqs.filter(payment_status__iexact=status)

    singles = []
    # Order by most recent first
    for o in oqs.order_by("-created_at"):
        # Latest invoice for this order (if any)
        inv = (
            Invoice.objects.filter(order_links__order=o)
            .order_by("-issued_at", "-id")
            .first()
        )

        invoice_line = None
        invoice_number = None
        if inv:
            invoice_line = (
                inv.lines.order_by("id").values_list("description", flat=True).first()
            )
            invoice_number = inv.number

        vat_amt = (
            o.taxes.filter(kind__iexact="VAT").aggregate(s=Sum("amount"))["s"] or ZERO
        )
        exc_amt = (
            o.taxes.filter(kind__iexact="EXC").aggregate(s=Sum("amount"))["s"] or ZERO
        )
        tax_total = (vat_amt or ZERO) + (exc_amt or ZERO)

        # Fallback description if there’s no invoice yet
        fallback_desc = invoice_line or (
            o.plan.name if getattr(o, "plan_id", None) else "Order"
        )

        singles.append(
            {
                "id": o.id,
                "reference": o.order_reference,
                "reference_label": f"#{o.order_reference}",
                "customer": (o.user.get_full_name() or o.user.email or "—"),
                "status": o.status,
                "payment_status": o.payment_status,
                "date": timezone.localtime(o.created_at).strftime("%Y-%m-%d %H:%M"),
                "total": str(o.total_price or ZERO),
                "vat": str(vat_amt),
                "exc": str(exc_amt),
                "tax_total": str(tax_total),  # <<< NEW
                # NEW: single-line text the UI will show in the “Designation” column
                "invoice_line": invoice_line,
                "invoice_number": invoice_number,
                # Keep legacy key as fallback to avoid breaking older UI
                "description": fallback_desc,
                "is_consolidated": False,
            }
        )

    # ------------------------------------
    # Consolidated (Invoice covering >1 order)
    # ------------------------------------
    ivqs = (
        Invoice.objects.annotate(n_orders=Count("order_links"))
        .filter(n_orders__gt=1)
        .select_related("user")
        .prefetch_related("lines", "order_links__order")
    )

    if q:
        ivqs = ivqs.filter(
            Q(number__icontains=q)
            | Q(user__email__icontains=q)
            | Q(user__first_name__icontains=q)
            | Q(user__last_name__icontains=q)
        )

    # Typical invoice statuses: draft / issued / paid / overdue / cancelled
    if status in {"draft", "issued", "paid", "overdue", "cancelled"}:
        ivqs = ivqs.filter(status__iexact=status)

    consolidated = []
    for inv in ivqs.order_by("-issued_at", "-id"):
        refs = list(
            InvoiceOrder.objects.filter(invoice=inv).values_list(
                "order__order_reference", flat=True
            )
        )
        summary_line = (
            inv.lines.order_by("id").values_list("description", flat=True).first()
        )

        # Compute taxes by summing OrderTax entries across all orders linked to this invoice
        order_ids = list(
            InvoiceOrder.objects.filter(invoice=inv).values_list("order_id", flat=True)
        )
        if order_ids:
            vat_amt = (
                OrderTax.objects.filter(order_id__in=order_ids, kind__iexact="VAT")
                .aggregate(s=Sum("amount"))
                .get("s")
                or ZERO
            )
            exc_amt = (
                OrderTax.objects.filter(order_id__in=order_ids, kind__iexact="EXC")
                .aggregate(s=Sum("amount"))
                .get("s")
                or ZERO
            )
        else:
            vat_amt = ZERO
            exc_amt = ZERO
        sum_tax_total = (vat_amt or ZERO) + (exc_amt or ZERO)

        # Normalize consolidated invoice status to order-like status for UI consistency
        inv_status = (inv.status or "").lower()
        if inv_status == "paid":
            order_like_status = "fulfilled"
            order_like_payment_status = "paid"
        elif inv_status in {"issued", "overdue"}:
            order_like_status = "pending_payment"
            order_like_payment_status = "unpaid"
        elif inv_status in {"cancelled", "canceled"}:
            order_like_status = "cancelled"
            order_like_payment_status = "cancelled"
        else:
            order_like_status = inv_status or "issued"
            order_like_payment_status = "unpaid"

        consolidated.append(
            {
                "is_consolidated": True,
                "consolidated_number": inv.number,
                "reference": inv.number,
                "customer": (inv.user.get_full_name() or inv.user.email or "—"),
                "status": order_like_status,
                "payment_status": order_like_payment_status,
                "date": timezone.localtime(inv.issued_at).strftime("%Y-%m-%d %H:%M")
                if inv.issued_at
                else "",
                "total": str(inv.grand_total or ZERO),
                "sum_vat": str(vat_amt),
                "sum_exc": str(exc_amt),
                "sum_tax_total": str(sum_tax_total),  # <<< NEW
                "order_refs": refs,
                # NEW: the single summary line text from the consolidated invoice
                "invoice_line": summary_line,
                # Provide invoice_number so UI displays it like single invoices
                "invoice_number": inv.number,
                "description": summary_line
                or f"Consolidated invoice for {len(refs)} orders",
            }
        )

    # --------------------------
    # Merge, sort, paginate
    # --------------------------
    rows = [*singles, *consolidated]

    # Sort by datetime desc (singles have 'date' as string; we already formatted uniformly)
    def _key(x):
        return x.get("date", "")

    rows.sort(key=_key, reverse=True)

    total_count = len(rows)
    total_pages = max(1, math.ceil(total_count / per_page))
    start = (page - 1) * per_page
    end = start + per_page
    page_rows = rows[start:end]

    return JsonResponse(
        {
            "success": True,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_count": total_count,
            "orders": page_rows,
        }
    )


def _as_float(x):
    try:
        return float(x or 0)
    except Exception:
        return 0.0


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "sales"])
def admin_view_orders_details(request, order_id):
    """
    Detail endpoint:
      - If order_id is numeric  -> returns a SINGLE order details (existing behaviour)
      - If order_id is non-numeric -> treated as CONSOLIDATED reference (ConsolidatedInvoice.number)
    The JSON schema is unified via `is_consolidated` flag so the same modal can render both.
    """
    # Utility map for readable line kinds
    kind_label = {
        OrderLine.Kind.KIT: "Hardware",
        OrderLine.Kind.PLAN: "Subscription",
        OrderLine.Kind.EXTRA: "Extra",
        OrderLine.Kind.INSTALL: "Installation",
        OrderLine.Kind.ADJUST: "Adjustment",
    }

    # ---------- Branch 1: SINGLE ORDER ----------
    if str(order_id).isdigit():
        order = get_object_or_404(
            Order.objects.select_related("user").prefetch_related("lines", "taxes"),
            id=int(order_id),
        )

        # Lines -> items
        items = []
        for ln in order.lines.all().order_by("id"):
            items.append(
                {
                    "name": ln.description or kind_label.get(ln.kind, "Item"),
                    "type": kind_label.get(ln.kind, "Item"),
                    "quantity": ln.quantity or 1,
                    "unit_price": _as_float(ln.unit_price),
                    "price": _as_float(ln.line_total),  # qty * unit
                    "kind": ln.kind,
                }
            )

        # Taxes list
        taxes_list = []
        for tx in order.taxes.all().order_by("id"):
            taxes_list.append(
                {
                    "kind": tx.kind,
                    "rate": _as_float(tx.rate),
                    "amount": _as_float(tx.amount),
                }
            )

        vat, exc = _tax_totals(order)
        total = _as_float(getattr(order, "total_price", None))

        # Customer display
        customer = "—"
        email = ""
        phone = ""
        if order.user:
            full_name = ""
            try:
                full_name = (order.user.get_full_name() or "").strip()
            except Exception:
                full_name = ""
            customer = (
                full_name
                or getattr(order.user, "full_name", "")
                or ""
                or getattr(order.user, "email", "")
                or ""
                or getattr(order.user, "username", "")
                or "—"
            )
            email = getattr(order.user, "email", "") or ""
            phone = getattr(order.user, "phone", "") or ""

        order_data = {
            "is_consolidated": False,
            "id": order.id,
            "reference": order.order_reference or "—",
            "customer": customer,
            "email": email,
            "phone": phone,
            "delivery_address": getattr(order, "delivery_address", "") or "",
            "status": order.status or "unknown",
            "payment_status": order.payment_status or "unknown",
            "date": (
                localtime(order.created_at).strftime("%Y-%m-%d %H:%M")
                if getattr(order, "created_at", None)
                else "—"
            ),
            "vat": vat,
            "exc": exc,
            "taxes": taxes_list,
            "total": round(total, 2),
            "description": _designation(order),
            "items": items,
            "expires_at": getattr(order, "expires_at_iso", None),
            # For convenience in frontend (PDF, process, etc.)
            "invoice_id": getattr(order, "invoice_id", None)
            or getattr(order, "invoice_pk", None),
        }
        return JsonResponse({"success": True, "order": order_data})

    # ---------- Branch 2: CONSOLIDATED (non-numeric reference) ----------
    cons_ref = str(order_id).strip()
    # We match by ConsolidatedInvoice.number; adjust if your field name differs.
    cons = get_object_or_404(
        ConsolidatedInvoice.objects.select_related("user"), number=cons_ref
    )

    # Gather child invoices linked to this consolidated invoice
    child_invoices = list(
        Invoice.objects.filter(consolidated_of=cons).prefetch_related("lines")
    )

    # Aggregate items (flattened, tagged with invoice number)
    items = []
    sum_subtotal = 0.0
    sum_vat = 0.0
    sum_exc = 0.0
    sum_tax_total = 0.0
    sum_grand_total = 0.0

    # Track orders behind those invoices (via InvoiceOrder join)
    order_ids = set()
    order_refs = set()

    # Build a compact invoices list for the UI
    invoices_payload = []

    for inv in child_invoices:
        inv_number = getattr(inv, "number", None) or getattr(inv, "id", None)
        inv_currency = getattr(inv, "currency", "USD")
        inv_subtotal = _as_float(getattr(inv, "subtotal", None))
        inv_tax_total = _as_float(getattr(inv, "tax_total", None))
        # Some schemas store split VAT/Excise; fall back to tax_total when not available
        inv_vat = _as_float(getattr(inv, "vat", None))
        inv_exc = _as_float(getattr(inv, "excise", None) or getattr(inv, "exc", None))
        if not inv_vat and not inv_exc and inv_tax_total:
            # If split not stored, don't double-count; keep both 0 and use tax_total only
            pass

        inv_grand = _as_float(
            getattr(inv, "grand_total", None) or getattr(inv, "total", None)
        )

        sum_subtotal += inv_subtotal
        sum_tax_total += inv_tax_total
        sum_vat += inv_vat
        sum_exc += inv_exc
        sum_grand_total += inv_grand

        # Lines if you want to display them at consolidated detail level
        # (optional; can be heavy—include if useful in your modal)
        try:
            inv_lines = inv.lines.all().order_by("id")
        except Exception:
            inv_lines = []

        for ln in inv_lines:
            items.append(
                {
                    "invoice_number": inv_number,
                    "name": getattr(ln, "description", "") or "Item",
                    "type": getattr(ln, "kind", "") or "Item",
                    "quantity": _as_float(getattr(ln, "quantity", 1)),
                    "unit_price": _as_float(getattr(ln, "unit_price", 0)),
                    "price": _as_float(getattr(ln, "line_total", 0)),
                    "kind": getattr(ln, "kind", ""),
                }
            )

        # Map to orders via InvoiceOrder join table
        # InvoiceOrder has fields: invoice (FK to Invoice), order (FK to Order), amount_excl_tax
        for io in InvoiceOrder.objects.filter(invoice=inv).select_related("order"):
            if io.order_id:
                order_ids.add(io.order_id)
            if getattr(io.order, "order_reference", None):
                order_refs.add(io.order.order_reference)

        invoices_payload.append(
            {
                "number": inv_number,
                "currency": inv_currency,
                "subtotal": round(inv_subtotal, 2),
                "vat": round(inv_vat, 2),
                "exc": round(inv_exc, 2),
                "tax_total": round(inv_tax_total, 2),
                "grand_total": round(inv_grand, 2),
            }
        )

    # If consolidated itself stores totals, prefer them, otherwise keep sums
    cons_currency = getattr(cons, "currency", "USD")
    cons_total = _as_float(getattr(cons, "total", None))
    if cons_total:
        sum_grand_total = (
            cons_total  # trust the authoritative total on the consolidated
        )

    customer = "—"
    email = ""
    phone = ""
    if cons.user:
        full_name = ""
        try:
            full_name = (cons.user.get_full_name() or "").strip()
        except Exception:
            full_name = ""
        customer = (
            full_name
            or getattr(cons.user, "full_name", "")
            or ""
            or getattr(cons.user, "email", "")
            or ""
            or getattr(cons.user, "username", "")
            or "—"
        )
        email = getattr(cons.user, "email", "") or ""
        phone = getattr(cons.user, "phone", "") or ""

    cons_data = {
        "is_consolidated": True,
        "consolidated_number": cons.number,
        "customer": customer,
        "email": email,
        "phone": phone,
        "status": getattr(cons, "status", "issued") or "issued",
        "payment_status": getattr(cons, "payment_status", "unpaid") or "unpaid",
        "date": (
            localtime(
                getattr(cons, "issued_at", None) or getattr(cons, "created_at", None)
            ).strftime("%Y-%m-%d %H:%M")
            if (getattr(cons, "issued_at", None) or getattr(cons, "created_at", None))
            else "—"
        ),
        "currency": cons_currency,
        "subtotal": round(sum_subtotal, 2),
        "vat": round(sum_vat, 2),
        "exc": round(sum_exc, 2),
        "tax_total": round(sum_tax_total, 2),
        "total": round(sum_grand_total, 2),
        "items": items,  # flattened invoice lines across all child invoices
        "order_ids": sorted(list(order_ids)),
        "order_refs": sorted(list(order_refs)),
        "invoices": invoices_payload,  # compact per-invoice summary for sidebar
        # Optional friendly description
        "description": f"Consolidated invoice #{cons.number} ({len(invoices_payload)} invoices)",
    }

    return JsonResponse({"success": True, "order": cons_data})


def _get_invoice_for_order(order):
    """
    Prefer a direct Invoice(order=order), otherwise take the first via InvoiceOrder.
    Returns (invoice or None, invoice_number or "").
    """
    # The Invoice model does not have a direct FK to Order; instead,
    # invoices are linked via the InvoiceOrder join table.
    inv = (
        Invoice.objects.filter(order_links__order=order)
        .order_by("-issued_at", "-id")
        .first()
    )
    if inv:
        return inv, (inv.number or "")
    return None, ""


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "sales"])
@require_POST
def process_order_payment(request, order_id=None, consolidated_number=None):
    """
    Processes a payment for either:
      A) Single Order  -> identified by URL kwarg `order_id` (int)
      B) Consolidated  -> if POST includes `consolidated_number` (string)

    POST fields (common):
      - paymentMethod: "cash" | "terminal"
      - currency:      optional (defaults USD; terminal forces USD)
      - amount:        required for cash (must equal DUE total)
      - terminal_reference: required for terminal
      - consolidated_number: if present -> bulk payment for that consolidated invoice

    All created PaymentAttempt.reference and ledger descriptions use the
    corresponding **invoice number** (not the order reference).
    """
    print("TEST")
    payment_method = (request.POST.get("paymentMethod") or "").strip().lower()
    currency = (request.POST.get("currency") or "USD").strip().upper()
    amount_raw = (request.POST.get("amount") or "").strip()
    terminal_reference = (request.POST.get("terminal_reference") or "").strip()
    # Prefer consolidated_number from URL kwarg when provided, fallback to POST field for backward compatibility
    consolidated_num = (
        consolidated_number or request.POST.get("consolidated_number") or ""
    ).strip()

    if not payment_method:
        return JsonResponse(
            {"success": False, "message": "Payment method is required."}, status=400
        )

    # =====================================================================
    # ===============  BRANCH 1: CONSOLIDATED (BULK)  =====================
    # =====================================================================
    if consolidated_num:
        try:
            cons = ConsolidatedInvoice.objects.prefetch_related("child_invoices").get(
                number=consolidated_num
            )
        except ConsolidatedInvoice.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Consolidated invoice not found."},
                status=404,
            )

        # consolidated due = total - payments on all child invoices
        cons_total = _qmoney(Decimal(cons.total or "0.00"))
        child_invoices = list(
            Invoice.objects.filter(consolidated_of=cons).prefetch_related("payments")
        )
        already_paid = Decimal("0.00")
        for inv in child_invoices:
            inv_paid = sum((ip.amount or Decimal("0.00")) for ip in inv.payments.all())
            already_paid += _qmoney(Decimal(inv_paid or 0))
        cons_due = _qmoney(cons_total - _qmoney(already_paid))
        if cons_due < Decimal("0.00"):
            cons_due = Decimal("0.00")

        # Validate method/amount
        if payment_method == "cash":
            if not amount_raw:
                return JsonResponse(
                    {"success": False, "message": "Cash payment requires an amount."},
                    status=400,
                )
            try:
                amount = _qmoney(Decimal(amount_raw))
            except (InvalidOperation, ValueError):
                return JsonResponse(
                    {"success": False, "message": "Invalid amount."}, status=400
                )
            if amount != cons_due:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Amount must equal the consolidated total due.",
                    },
                    status=400,
                )
            currency = currency or "USD"
        elif payment_method == "terminal":
            if not terminal_reference:
                return JsonResponse(
                    {"success": False, "message": "Terminal reference is required."},
                    status=400,
                )
            amount = cons_due
            currency = "USD"
        else:
            return JsonResponse(
                {"success": False, "message": "Unsupported payment method."}, status=400
            )

        if cons_due <= 0:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Consolidated invoice is already fully paid.",
                },
                status=400,
            )

        try:
            with transaction.atomic():
                for inv in child_invoices:
                    # pay each child invoice to zero
                    inv_paid = sum(
                        (ip.amount or Decimal("0.00")) for ip in inv.payments.all()
                    )
                    inv_total = _qmoney(Decimal(inv.grand_total or inv.total or "0.00"))
                    inv_due = _qmoney(inv_total - _qmoney(Decimal(inv_paid or 0)))
                    if inv_due <= 0:
                        continue

                    # record payment on the invoice
                    ip = InvoicePayment.objects.create(
                        invoice=inv,
                        amount=_qmoney(inv_due),
                        created_at=timezone.now(),
                        payment_attempt=None,  # will link to per-order attempt below
                    )
                    inv.status = "paid"
                    inv.save(update_fields=["status"])

                    # mark all related orders as paid + create attempts that reference the invoice number
                    related_orders = list(
                        Order.objects.filter(
                            pk__in=InvoiceOrder.objects.filter(invoice=inv).values_list(
                                "order_id", flat=True
                            )
                        ).select_related("user")
                    )
                    for ord_obj in related_orders:
                        already_paid_order = (
                            ord_obj.payment_status or ""
                        ).lower() == "paid"

                        pa = PaymentAttempt.objects.create(
                            order=ord_obj,
                            payment_type=payment_method,
                            payment_for=(
                                "hardware"
                                if not hasattr(ord_obj, "subscription")
                                else "subscription"
                            ),
                            currency=currency or "USD",
                            amount=_qmoney(Decimal(ord_obj.total_price or "0.00")),
                            amount_customer=_qmoney(
                                Decimal(ord_obj.total_price or "0.00")
                            ),
                            provider_reference=terminal_reference or "",
                            processed_by=request.user
                            if request.user.is_authenticated
                            else None,
                            status="completed",
                            transaction_time=timezone.now(),
                            reference=(inv.number or ""),  # ← use invoice number
                        )
                        # link the per-invoice InvoicePayment to the attempt (optional)
                        try:
                            ip.payment_attempt = pa
                            ip.save(update_fields=["payment_attempt"])
                        except Exception:
                            pass

                        if not already_paid_order:
                            ord_obj.payment_status = "paid"
                            ord_obj.status = "fulfilled"
                            ord_obj.payment_method = payment_method
                            ord_obj.expires_at = None
                            ord_obj.payment_hold_until = None
                            ord_obj.cancelled_reason = ""
                            ord_obj.save(
                                update_fields=[
                                    "payment_status",
                                    "status",
                                    "payment_method",
                                    "expires_at",
                                    "payment_hold_until",
                                    "cancelled_reason",
                                ]
                            )

                        # ledger entry mentions invoice number
                        if ord_obj.user_id:
                            acct, _ = BillingAccount.objects.get_or_create(
                                user=ord_obj.user
                            )
                            AccountEntry.objects.create(
                                account=acct,
                                entry_type="payment",
                                amount_usd=_qmoney(
                                    Decimal("-1")
                                    * _qmoney(Decimal(ord_obj.total_price or "0.00"))
                                ),
                                description=f"{payment_method.capitalize()} payment for Invoice {inv.number or '—'} (consolidated)",
                                order=ord_obj,
                                payment=pa,
                            )

                # re-check consolidated status
                cons.refresh_from_db()
                child_invoices = list(
                    Invoice.objects.filter(consolidated_of=cons).prefetch_related(
                        "payments"
                    )
                )
                re_due = Decimal("0.00")
                for inv in child_invoices:
                    inv_total = _qmoney(Decimal(inv.grand_total or inv.total or "0.00"))
                    inv_paid = _qmoney(
                        sum((ip.amount or Decimal("0.00")) for ip in inv.payments.all())
                    )
                    re_due += _qmoney(inv_total - inv_paid)
                if _qmoney(re_due) <= 0:
                    cons.status = "paid"
                    cons.save(update_fields=["status"])

            return JsonResponse(
                {
                    "success": True,
                    "message": "Consolidated payment recorded successfully.",
                    "consolidated": {
                        "number": cons.number,
                        "status": cons.status,
                        "paid_amount": str(amount),
                        "currency": currency,
                    },
                }
            )
        except Exception as e:
            return JsonResponse(
                {"success": False, "message": f"Server error: {str(e)}"}, status=500
            )

    # =====================================================================
    # ===============  BRANCH 2: SINGLE ORDER (DEFAULT)  ==================
    # =====================================================================
    try:
        order = Order.objects.select_related("user").get(pk=order_id)
    except Order.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Order not found."}, status=404
        )

    if (order.payment_status or "").lower() == "paid":
        # still return invoice number for UI convenience
        _, inv_no = _get_invoice_for_order(order)
        return JsonResponse(
            {
                "success": False,
                "message": "Order already marked as paid.",
                "invoice_number": inv_no,
            },
            status=400,
        )

    # Prefer validating against INVOICE DUE (if invoice exists), else fall back to order total.
    inv_for_ref, inv_no = _get_invoice_for_order(order)
    order_total = _qmoney(Decimal(order.total_price or "0.00"))
    if inv_for_ref:
        inv_total = _qmoney(
            Decimal(inv_for_ref.grand_total or inv_for_ref.total or "0.00")
        )
        inv_paid = _qmoney(
            sum((ip.amount or Decimal("0.00")) for ip in inv_for_ref.payments.all())
        )
        due_total = _qmoney(inv_total - inv_paid)
    else:
        due_total = order_total

    # Validate method/amount
    if payment_method == "cash":
        if not amount_raw:
            return JsonResponse(
                {"success": False, "message": "Cash payment requires an amount."},
                status=400,
            )
        try:
            amount = _qmoney(Decimal(amount_raw))
        except (InvalidOperation, ValueError):
            return JsonResponse(
                {"success": False, "message": "Invalid amount."}, status=400
            )
        if amount != due_total:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Amount must equal the invoice total due.",
                },
                status=400,
            )
        currency = currency or "USD"
    elif payment_method == "terminal":
        if not terminal_reference:
            return JsonResponse(
                {"success": False, "message": "Terminal reference is required."},
                status=400,
            )
        amount = due_total
        currency = "USD"
    else:
        return JsonResponse(
            {"success": False, "message": "Unsupported payment method."}, status=400
        )

    try:
        with transaction.atomic():
            # order contents (for wallet credit logic)
            contents = _detect_order_contents(order)
            has_sub = contents["has_subscription"]
            has_hw = contents["has_hardware"]

            plan_lines_monthly_total = _qmoney(contents["plan_lines_total"])
            billing_cycle = (
                getattr(getattr(order, "subscription", None), "billing_cycle", None)
                or "monthly"
            ).lower()
            cycle_multiplier = {
                "monthly": Decimal("1"),
                "quarterly": Decimal("3"),
                "yearly": Decimal("12"),
            }.get(billing_cycle, Decimal("1"))
            subscription_base_for_cycle = (
                _qmoney(plan_lines_monthly_total * cycle_multiplier)
                if has_sub
                else Decimal("0.00")
            )
            inferred_payment_for = (
                "subscription"
                if has_sub and not has_hw
                else ("hardware" if not has_sub else "subscription")
            )

            # PaymentAttempt uses invoice number
            pa = PaymentAttempt.objects.create(
                order=order,
                payment_type=payment_method,
                payment_for=inferred_payment_for,
                currency=currency or "USD",
                amount=_qmoney(amount),
                amount_customer=_qmoney(amount),
                provider_reference=terminal_reference or "",
                processed_by=request.user if request.user.is_authenticated else None,
                status="completed",
                transaction_time=timezone.now(),
                reference=(inv_no or ""),  # ← use invoice number here
            )

            # mark order paid/fulfilled
            order.payment_status = "paid"
            order.status = "fulfilled"
            order.payment_method = payment_method
            order.expires_at = None
            order.payment_hold_until = None
            order.cancelled_reason = ""
            order.save(
                update_fields=[
                    "payment_status",
                    "status",
                    "payment_method",
                    "expires_at",
                    "payment_hold_until",
                    "cancelled_reason",
                ]
            )

            # write payment on the invoice (preferred), or allocate via InvoiceOrder
            if inv_for_ref:
                InvoicePayment.objects.create(
                    invoice=inv_for_ref,
                    amount=_qmoney(amount),
                    created_at=timezone.now(),
                    payment_attempt=pa,
                )
                # mark invoice paid if fully covered now
                inv_paid_new = _qmoney(
                    sum(
                        (ip.amount or Decimal("0.00"))
                        for ip in inv_for_ref.payments.all()
                    )
                )
                if inv_paid_new >= _qmoney(
                    Decimal(inv_for_ref.grand_total or inv_for_ref.total or "0.00")
                ):
                    inv_for_ref.status = "paid"
                    inv_for_ref.save(update_fields=["status"])
            else:
                # Fallback allocation across any related invoices
                for inv_id in InvoiceOrder.objects.filter(order=order).values_list(
                    "invoice_id", flat=True
                ):
                    invx = Invoice.objects.get(pk=inv_id)
                    inv_total_x = _qmoney(
                        Decimal(invx.grand_total or invx.total or "0.00")
                    )
                    inv_paid_x = _qmoney(
                        sum(
                            (ip.amount or Decimal("0.00")) for ip in invx.payments.all()
                        )
                    )
                    inv_due_x = _qmoney(inv_total_x - inv_paid_x)
                    if inv_due_x <= 0:
                        continue
                    pay_now = min(inv_due_x, _qmoney(amount))
                    if pay_now <= 0:
                        continue
                    InvoicePayment.objects.create(
                        invoice=invx,
                        amount=_qmoney(pay_now),
                        created_at=timezone.now(),
                        payment_attempt=pa,
                    )
                    if _qmoney(inv_paid_x + pay_now) >= inv_total_x:
                        invx.status = "paid"
                        invx.save(update_fields=["status"])

            # Ledger entry — mention invoice number (fallback to order ref only for display)
            if order.user_id:
                acct, _ = BillingAccount.objects.get_or_create(user=order.user)
                desc_inv = inv_no if inv_no else f"Order {order.order_reference}"
                AccountEntry.objects.create(
                    account=acct,
                    entry_type="payment",
                    amount_usd=_qmoney(Decimal("-1") * Decimal(amount)),
                    description=f"{payment_method.capitalize()} payment for Invoice {desc_inv}",
                    order=order,
                    payment=pa,
                )

                # Optional wallet top-up for the subscription cycle
                if has_sub and subscription_base_for_cycle > 0:
                    tax_exempt = bool(getattr(order.user, "is_tax_exempt", False))
                    credit_amount = _apply_taxes(
                        subscription_base_for_cycle, tax_exempt=tax_exempt
                    )
                    already = order.wallet_transactions.filter(
                        payment_attempt=pa, tx_type="credit"
                    ).exists()
                    if not already:
                        wallet, _ = Wallet.objects.get_or_create(user=order.user)
                        note = f"Subscription {billing_cycle} top-up (incl. taxes) for Invoice {desc_inv}"
                        wallet.add_funds(
                            credit_amount,
                            note=note,
                            order=order,
                            payment_attempt=pa,
                        )

        return JsonResponse(
            {
                "success": True,
                "message": "Payment recorded successfully.",
                "order": {
                    "id": order.id,
                    "reference": order.order_reference,  # kept for UI links
                    "invoice_number": inv_no or "",  # ← expose invoice number
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "payment_method": order.payment_method,
                },
            }
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"}, status=500
        )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "sales"])
def report_invoice_pdf(request, order_id: int):
    """
    Minimalist, Starlink-like invoice:
      - Header: company logo + company meta (left)
      - Parties row: Bill To (left) + Invoice meta (right)
      - Items from Order.lines; VAT/EXCISE from OrderTax
      - Centered bottom section (divider, QR/Barcode placeholder, note)

    NOTE: This endpoint now resolves the Invoice associated with the given order
    and redirects to the unified invoice-by-number PDF under /billing/invoice/<id>/pdf/.
    If no Invoice is linked yet, it falls back to legacy rendering below.
    """

    # Try to resolve an Invoice first and redirect to the new invoice-centric route
    try:
        from django.http import HttpResponseRedirect

        from main.models import Invoice, InvoiceLine, InvoiceOrder

        link = (
            InvoiceOrder.objects.select_related("invoice")
            .filter(order_id=order_id, invoice__number__isnull=False)
            .order_by("-invoice__issued_at", "-invoice__id")
            .first()
        )
        inv = link.invoice if link else None
        if not inv:
            il = (
                InvoiceLine.objects.select_related("invoice")
                .filter(order_id=order_id, invoice__number__isnull=False)
                .order_by("-invoice__issued_at", "-invoice__id")
                .first()
            )
            inv = il.invoice if il else None
        if not inv:
            # last resort by user and date
            from main.models import Order

            ord_obj = Order.objects.filter(pk=order_id).only("user_id").first()
            if ord_obj:
                inv = (
                    Invoice.objects.filter(
                        user_id=ord_obj.user_id, number__isnull=False
                    )
                    .order_by("-issued_at", "-id")
                    .first()
                )
        if inv and inv.number:
            return HttpResponseRedirect(
                request.build_absolute_uri(f"/billing/invoice/{inv.number}/pdf/")
            )
    except Exception:
        pass

    # ---- tiny helpers -------------------------------------------------------
    def _safe(val, dash="—"):
        s = (
            (val or "").strip()
            if isinstance(val, str)
            else ("" if val is None else str(val))
        )
        return s or dash

    def _money(val: Decimal | float | int):
        try:
            return f"${Decimal(val or 0).quantize(Decimal('0.01')):,.2f}"
        except Exception:
            return "$0.00"

    def center_flow(flow, width):
        """Center any flowable by wrapping into a 1-cell table."""
        t = Table([[flow]], colWidths=[width], hAlign="CENTER")
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        return t

    # Thin horizontal rule flowable
    class HR(Flowable):
        def __init__(self, width, thickness=0.4, color=colors.black, vspace=6):
            super().__init__()
            self.width = width
            self.thickness = thickness
            self.color = color
            self.vspace = vspace

        def wrap(self, availWidth, availHeight):
            return self.width, self.vspace * 2

        def draw(self):
            self.canv.setStrokeColor(self.color)
            self.canv.setLineWidth(self.thickness)
            y = self.vspace
            self.canv.line(0, y, self.width, y)

    # ---- data ---------------------------------------------------------------
    order = get_object_or_404(Order, pk=order_id)
    created = order.created_at or timezone.now()
    inv_no = order.order_reference or f"ORD-{order.id}"

    # Resolve "Bill To" from KYC if available
    u = order.user
    company_kyc = getattr(u, "company_kyc", None) if u else None
    personal_kyc = getattr(u, "personnal_kyc", None) if u else None

    bill_to_lines: list[tuple[str, str]] = [("BILL TO", "header")]
    if company_kyc and (
        _safe(company_kyc.company_name) != "—" or _safe(company_kyc.address) != "—"
    ):
        bill_to_lines += [
            (_safe(company_kyc.company_name), "body"),
            (_safe(company_kyc.address), "small"),
        ]
        ids = []
        if _safe(company_kyc.rccm) != "—":
            ids.append(f"RCCM: {_safe(company_kyc.rccm)}")
        if _safe(company_kyc.nif) != "—":
            ids.append(f"NIF: {_safe(company_kyc.nif)}")
        if _safe(company_kyc.id_nat) != "—":
            ids.append(f"ID NAT: {_safe(company_kyc.id_nat)}")
        if ids:
            bill_to_lines.append((" • ".join(ids), "small"))
        if _safe(company_kyc.representative_name) != "—":
            bill_to_lines.append(
                (f"Rep: {_safe(company_kyc.representative_name)}", "small")
            )
        bill_to_lines.append((_safe(getattr(u, "email", "")), "small"))
        bill_to_lines.append((_safe(getattr(u, "phone", "")), "small"))

    elif personal_kyc and (
        _safe(personal_kyc.full_name) != "—" or _safe(personal_kyc.address) != "—"
    ):
        bill_to_lines += [
            (_safe(personal_kyc.full_name or getattr(u, "full_name", "")), "body"),
        ]
        if _safe(personal_kyc.address) != "—":
            bill_to_lines.append((_safe(personal_kyc.address), "small"))
        if _safe(personal_kyc.document_number) != "—":
            bill_to_lines.append(
                (f"Document: {_safe(personal_kyc.document_number)}", "small")
            )
        bill_to_lines.append((_safe(getattr(u, "email", "")), "small"))
        bill_to_lines.append((_safe(getattr(u, "phone", "")), "small"))
    else:
        customer_name = (
            (getattr(u, "full_name", None) or getattr(u, "username", None) or "")
            if u
            else ""
        )
        bill_to_lines += [
            (_safe(customer_name), "body"),
            (_safe(getattr(u, "email", "") if u else ""), "small"),
            (_safe(getattr(u, "phone", "") if u else ""), "small"),
        ]

    # Line items from Order.lines (fallback if none)
    line_items = []
    for ln in order.lines.all().order_by("id"):
        label = ln.description or ln.get_kind_display() or "Item"
        detail = f"Qty {ln.quantity}"
        line_items.append([label.upper(), _safe(detail), _money(ln.line_total)])

    # Taxes from OrderTax (by kind)
    taxes_qs = order.taxes.all()
    exc = sum(
        (t.amount for t in taxes_qs if t.kind == OrderTax.Kind.EXCISE), Decimal("0.00")
    )

    vat = sum(
        (t.amount for t in taxes_qs if t.kind == OrderTax.Kind.VAT), Decimal("0.00")
    )

    # Subtotal / Total
    subtotal = sum((ln.line_total for ln in order.lines.all()), Decimal("0.00"))
    total = (
        order.total_price
        if order.total_price not in (None, Decimal("0.00"))
        else (subtotal + vat + exc)
    )

    # ---- PDF ----------------------------------------------------------------
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {inv_no}",
        author="Nexus Telecoms SA",
    )
    W = doc.width

    # Palette
    BLACK = colors.black
    GRAY_900 = colors.HexColor("#0B0B0C")
    GRAY_700 = colors.HexColor("#5A5A5F")
    GRAY_300 = colors.HexColor("#D1D5DB")
    GRAY_200 = colors.HexColor("#E5E7EB")
    GRAY_100 = colors.HexColor("#F5F5F5")

    # Styles
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="H_BIG",
            fontName="Helvetica-Bold",
            fontSize=18,
            leading=22,
            textColor=BLACK,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="H_META",
            fontName="Helvetica",
            fontSize=9,
            leading=12,
            textColor=GRAY_700,
            spaceAfter=0,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LBL_UP",
            fontName="Helvetica",
            fontSize=7.5,
            leading=10,
            textColor=GRAY_700,
            spaceAfter=1,
        )
    )
    styles.add(
        ParagraphStyle(
            name="BODY",
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=GRAY_900,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SMALL",
            fontName="Helvetica",
            fontSize=8.5,
            leading=12,
            textColor=GRAY_700,
        )
    )
    styles.add(ParagraphStyle(name="SMALL_CENTER", parent=styles["SMALL"], alignment=1))
    styles.add(
        ParagraphStyle(
            name="TOTALS_LABEL",
            fontName="Helvetica",
            fontSize=9,
            alignment=2,
            textColor=GRAY_700,
        )
    )
    styles.add(
        ParagraphStyle(
            name="TOTALS_VAL",
            fontName="Helvetica-Bold",
            fontSize=10.5,
            alignment=2,
            textColor=BLACK,
        )
    )

    elems = []

    # Thin top band
    band = Table(
        [[Paragraph("&nbsp;", styles["H_META"])]], colWidths=[W], rowHeights=[6]
    )
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    elems.append(band)
    elems.append(Spacer(1, 10))

    # Header — LEFT ONLY
    left_block = []
    logo_path = os.path.join(settings.BASE_DIR, "static", "images", "logo", "logo.png")
    if os.path.exists(logo_path):
        left_block.append(Image(logo_path, width=42 * mm, height=12 * mm))
    else:
        left_block.append(Paragraph("<b>NEXUS TELECOMS SA</b>", styles["H_BIG"]))
    left_block.append(Spacer(1, 2))
    left_block.append(Paragraph("RCCM: CD/LSH/RCCM/25-B-00807", styles["SMALL"]))
    left_block.append(Paragraph("ID.NAT: 05-S9502-N80001D", styles["SMALL"]))
    left_block.append(Paragraph("NIF: 05-S9502-N80001D", styles["SMALL"]))
    left_block.append(
        Paragraph("Addr: 8273, AV Lukonzolwa, Lubumbashi", styles["SMALL"])
    )
    left_block.append(Paragraph("billing@nexustelecoms.cd", styles["SMALL"]))

    header = Table([[left_block]], colWidths=[W], hAlign="LEFT")
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elems.append(header)
    elems.append(Spacer(1, 12))

    # Divider
    elems.append(HR(W, thickness=0.6, color=BLACK, vspace=4))
    elems.append(Spacer(1, 6))

    # Bill To (left)
    bill_to_paras = [Paragraph("<b>BILL TO</b>", styles["LBL_UP"])]
    for txt, kind in bill_to_lines[1:]:  # skip header
        bill_to_paras.append(
            Paragraph(_safe(txt), styles["BODY" if kind == "body" else "SMALL"])
        )

    # Invoice meta (right)
    invoice_meta_right = [
        Paragraph("<b>INVOICE</b>", styles["LBL_UP"]),
        Spacer(1, 4),
    ]
    meta_rows = [
        [
            Paragraph("INVOICE NO:", styles["LBL_UP"]),
            Paragraph(_safe(inv_no), styles["SMALL"]),
        ],
        [
            Paragraph("DATE:", styles["LBL_UP"]),
            Paragraph(
                timezone.localtime(created).strftime("%Y-%m-%d %H:%M"), styles["SMALL"]
            ),
        ],
        [
            Paragraph("STATUS:", styles["LBL_UP"]),
            Paragraph(_safe(order.payment_status).upper(), styles["SMALL"]),
        ],
    ]
    meta_tbl = Table(
        meta_rows, colWidths=[30 * mm, (W * 0.5) - (30 * mm)], hAlign="RIGHT"
    )
    meta_tbl.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
            ]
        )
    )
    invoice_meta_right.append(meta_tbl)

    parties = Table([[bill_to_paras, invoice_meta_right]], colWidths=[W * 0.5, W * 0.5])
    parties.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elems.append(parties)
    elems.append(Spacer(1, 14))

    # Items
    items_data = [["ITEM", "DETAILS", "AMOUNT"]]
    items_data += line_items or [["—", "—", _money(0)]]
    items_tbl = Table(
        items_data, colWidths=[W * 0.42, W * 0.40, W * 0.18], hAlign="LEFT"
    )
    items_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), GRAY_100),
                ("TEXTCOLOR", (0, 0), (-1, 0), BLACK),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 9),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, GRAY_300),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("LEADING", (0, 1), (-1, -1), 12),
                ("VALIGN", (0, 1), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 1), (2, -1), "RIGHT"),
                ("BOX", (0, 0), (-1, -1), 0.5, GRAY_200),
                ("LINEABOVE", (0, 1), (-1, -1), 0.3, GRAY_200),
            ]
        )
    )
    elems.append(items_tbl)
    elems.append(Spacer(1, 16))

    # Totals (span to align with items)
    totals_data = [
        [
            Paragraph("SUBTOTAL", styles["TOTALS_LABEL"]),
            Paragraph(_money(subtotal), styles["TOTALS_VAL"]),
        ],
        [
            Paragraph("EXCISE", styles["TOTALS_LABEL"]),
            Paragraph(_money(exc), styles["TOTALS_VAL"]),
        ],
        [
            Paragraph("VAT", styles["TOTALS_LABEL"]),
            Paragraph(_money(vat), styles["TOTALS_VAL"]),
        ],
        [
            Paragraph("TOTAL", styles["TOTALS_LABEL"]),
            Paragraph(_money(total), styles["TOTALS_VAL"]),
        ],
    ]
    totals_tbl = Table(totals_data, colWidths=[W * 0.82, W * 0.18], hAlign="LEFT")
    totals_tbl.setStyle(
        TableStyle(
            [
                ("ALIGN", (0, 0), (0, -1), "RIGHT"),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, BLACK),
                ("LINEBELOW", (0, -1), (-1, -1), 0.8, BLACK),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    elems.append(totals_tbl)
    elems.append(Spacer(1, 14))

    # Centered bottom section
    elems.append(
        center_flow(HR(W * 0.6, thickness=0.4, color=GRAY_300, vspace=3), width=W)
    )
    elems.append(Spacer(1, 6))

    # Optional QR card – if you have a util, keep it; otherwise comment it out
    try:
        # from .pdf_utils import make_qr_card  # if you have one
        # qr_card = make_qr_card(data=inv_no, size_mm=46, caption="Scan to verify")
        # elems.append(center_flow(qr_card, width=W))
        # elems.append(Spacer(1, 8))
        pass
    except Exception:
        pass

    note = Paragraph(
        "For support, contact billing@nexus.cd. Please retain this invoice for your records.",
        styles["SMALL_CENTER"],
    )
    elems.append(center_flow(note, width=W))

    # Build & respond
    doc.build(elems)
    pdf = buf.getvalue()
    buf.close()

    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="Invoice_{inv_no}.pdf"'
    return resp


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "sales"])
@require_POST
def process_payment_unified(request, identifier):
    """
    Unified payment endpoint:
    - If `identifier` is all digits -> treat as single order id and delegate to process_order_payment(order_id=...)
    - Else if a ConsolidatedInvoice exists with number == identifier -> delegate to process_order_payment(consolidated_number=...)
    - Else -> delegate to process_invoice_payment(invoice_id=identifier) for single invoice payment

    Path examples:
      /en/orders/pay/123/process_payment/
      /en/orders/pay/INV/000002/process_payment/
      /en/orders/pay/INV-000123/process_payment/
    """
    # Make sure identifier is a clean string
    ident = (str(identifier) if identifier is not None else "").strip()

    # 1) Single order by numeric id
    if ident.isdigit():
        return process_order_payment(request, order_id=int(ident))

    # 2) Consolidated invoice by number
    try:
        cons_exists = ConsolidatedInvoice.objects.filter(number=ident).exists()
    except Exception:
        cons_exists = False
    if cons_exists:
        return process_order_payment(request, consolidated_number=ident)

    # 3) Fallback to single-invoice payment by number
    return process_invoice_payment(request, invoice_id=ident)


@require_POST
def process_invoice_payment(request, invoice_id):
    """
    Process a payment by invoice number (e.g., INV/000123):
      - Accepts POST with fields:
          paymentMethod: "cash" | "terminal"
          currency: optional (defaults to USD; terminal forces USD)
          amount: required for cash, must equal invoice due
          terminal_reference: required for terminal

    Side effects:
      - Creates InvoicePayment on the invoice
      - Creates PaymentAttempt(s) on related order(s)
      - Marks invoice and orders as paid/fulfilled when applicable
    """
    payment_method = (request.POST.get("paymentMethod") or "").strip().lower()
    currency = (request.POST.get("currency") or "USD").strip().upper()
    amount_raw = (request.POST.get("amount") or "").strip()
    terminal_reference = (request.POST.get("terminal_reference") or "").strip()

    if not payment_method:
        return JsonResponse(
            {"success": False, "message": "Payment method is required."}, status=400
        )

    # Locate invoice by its human-readable number
    try:
        inv = Invoice.objects.get(number=invoice_id)
    except Invoice.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Invoice not found."}, status=404
        )

    inv_total = _qmoney(Decimal(inv.grand_total or inv.total or "0.00"))
    inv_paid = _qmoney(sum((ip.amount or Decimal("0.00")) for ip in inv.payments.all()))
    inv_due = _qmoney(inv_total - inv_paid)

    if inv_due <= 0:
        return JsonResponse(
            {"success": False, "message": "Invoice already fully paid."}, status=400
        )

    # Validate method/amount
    if payment_method == "cash":
        # No amount validation required from client; always use the current invoice due
        amount = inv_due
        currency = currency or "USD"
    elif payment_method == "terminal":
        if not terminal_reference:
            return JsonResponse(
                {"success": False, "message": "Terminal reference is required."},
                status=400,
            )
        amount = inv_due
        currency = "USD"
    else:
        return JsonResponse(
            {"success": False, "message": "Unsupported payment method."}, status=400
        )

    try:
        with transaction.atomic():
            # Record payment on invoice
            ip = InvoicePayment.objects.create(
                invoice=inv,
                amount=_qmoney(amount),
                created_at=timezone.now(),
                payment_attempt=None,
            )

            # If fully covered, switch status to paid
            new_paid = _qmoney(
                sum((x.amount or Decimal("0.00")) for x in inv.payments.all())
            )
            if new_paid >= inv_total:
                inv.status = "paid"
                inv.save(update_fields=["status"])

            # For all orders linked to this invoice, create PaymentAttempt and mark as paid
            related_orders = list(
                Order.objects.filter(
                    pk__in=InvoiceOrder.objects.filter(invoice=inv).values_list(
                        "order_id", flat=True
                    )
                ).select_related("user")
            )

            for ord_obj in related_orders:
                already_paid_order = (ord_obj.payment_status or "").lower() == "paid"

                pa = PaymentAttempt.objects.create(
                    order=ord_obj,
                    payment_type=payment_method,
                    payment_for=(
                        "hardware"
                        if not hasattr(ord_obj, "subscription")
                        else "subscription"
                    ),
                    currency=currency or "USD",
                    amount=_qmoney(Decimal(ord_obj.total_price or "0.00")),
                    amount_customer=_qmoney(Decimal(ord_obj.total_price or "0.00")),
                    provider_reference=terminal_reference or "",
                    processed_by=request.user
                    if request.user.is_authenticated
                    else None,
                    status="completed",
                    transaction_time=timezone.now(),
                    reference=(inv.number or ""),
                )

                # Optionally link the invoice payment to the last attempt (mirrors consolidated behavior)
                try:
                    ip.payment_attempt = pa
                    ip.save(update_fields=["payment_attempt"])
                except Exception:
                    pass

                if not already_paid_order:
                    ord_obj.payment_status = "paid"
                    ord_obj.status = "fulfilled"
                    ord_obj.payment_method = payment_method
                    ord_obj.expires_at = None
                    ord_obj.payment_hold_until = None
                    ord_obj.cancelled_reason = ""
                    ord_obj.save(
                        update_fields=[
                            "payment_status",
                            "status",
                            "payment_method",
                            "expires_at",
                            "payment_hold_until",
                            "cancelled_reason",
                        ]
                    )

                # Ledger entry referencing the invoice number
                if ord_obj.user_id:
                    acct, _ = BillingAccount.objects.get_or_create(user=ord_obj.user)
                    AccountEntry.objects.create(
                        account=acct,
                        entry_type="payment",
                        amount_usd=_qmoney(
                            Decimal("-1")
                            * _qmoney(Decimal(ord_obj.total_price or "0.00"))
                        ),
                        description=f"{payment_method.capitalize()} payment for Invoice {inv.number or '—'}",
                        order=ord_obj,
                        payment=pa,
                    )

        return JsonResponse(
            {
                "success": True,
                "message": "Invoice payment recorded successfully.",
                "invoice": {
                    "number": inv.number,
                    "status": inv.status,
                    "paid_amount": str(amount),
                    "currency": currency,
                },
            }
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"}, status=500
        )
