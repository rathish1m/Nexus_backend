import base64
import json
import os
from datetime import datetime, timedelta
from decimal import Decimal
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.gis.geos import Point
from django.core.paginator import Paginator
from django.db import models as dj_models
from django.db import transaction
from django.db.models import Avg, Count, Exists, ExpressionWrapper, F, OuterRef, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone as dj_timezone
from django.utils.timezone import localtime, now
from django.views.decorators.http import require_POST

from billing_management.billing_services import (
    anchor_window,
    apply_wallet_to_order,
    due_for_ref,
    ensure_first_order_invoice_entry,
    order_external_ref,
    q,
    split_amounts_for_base,
)
from feedbacks.models import Feedback
from feedbacks.permissions import user_is_feedback_staff
from geo_regions.models import Region
from main.models import (
    BillingConfig,
    CompanyKYC,
    InstallationActivity,
    Order,
    OrderLine,
    PersonalKYC,
    StarlinkKitInventory,
    Subscription,
    TechnicianAssignment,
    User,
)
from user.permissions import require_staff_role

# Create your views here.
FINANCE_ALLOWED_ROLES = {"finance", "manager", "admin"}


def user_is_finance_staff(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_superuser", False):
        return True
    for role in FINANCE_ALLOWED_ROLES:
        try:
            if user.has_role(role):
                return True
        except Exception:
            roles = getattr(user, "roles", []) or []
            if isinstance(roles, str):
                roles = [r.strip() for r in roles.split(",") if r.strip()]
            if role in {str(r).strip().lower() for r in roles}:
                return True
    return False


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def backoffice_main(request):
    # user = request.user  # Unused variable - kept for potential future use
    personnal_kyc = PersonalKYC.objects.filter(status="pending").count()
    company_kyc = CompanyKYC.objects.filter(status="pending").count()
    kyc_count = personnal_kyc + company_kyc
    template = "backoffice_main.html"

    context = {
        "kyc_count": kyc_count,
    }

    return render(request, template, context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def order_management(request):
    template = "order_management_main.html"
    orders = Order.objects.select_related("user").order_by("-created_at")

    paid_count = orders.filter(payment_status__iexact="paid").count()
    unpaid_count = orders.filter(payment_status__iexact="unpaid").count()
    failed_count = orders.filter(payment_status__iexact="failed").count()

    context = {
        "orders": orders,
        "paid_count": paid_count,
        "unpaid_count": unpaid_count,
        "failed_count": failed_count,
    }
    return render(request, template, context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def admin_view_orders(request):
    orders = Order.objects.select_related("user").order_by("-created_at")
    page_number = request.GET.get("page", 1)  # Default to page 1
    paginator = Paginator(orders, 20)  # Show 10 orders per page

    try:
        page_obj = paginator.page(page_number)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid page number"})

    order_data = []

    for order in page_obj.object_list:
        has_kit = order.lines.filter(kind=OrderLine.Kind.KIT).exists()
        has_plan = order.lines.filter(kind=OrderLine.Kind.PLAN).exists()

        if has_kit and has_plan:
            description = "Kit & Subscription"
        elif has_kit:
            description = "Kit Purchase"
        elif has_plan:
            description = "Subscription"
        else:
            description = "N/A"

        order_data.append(
            {
                "id": order.id,
                "reference": order.order_reference,
                "customer": order.user.get_full_name() or order.user.username,
                "status": order.payment_status,
                "date": order.created_at.strftime("%Y-%m-%d %H:%M"),
                "vat": 0.0,
                "exc": 0.0,
                "total": float(order.total_price),
                "description": description,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "orders": order_data,
            "page": page_obj.number,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        }
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def admin_view_orders_details(request, order_id):
    order = get_object_or_404(Order.objects.select_related("user"), id=order_id)

    has_kit = order.lines.filter(kind=OrderLine.Kind.KIT).exists()
    has_plan = order.lines.filter(kind=OrderLine.Kind.PLAN).exists()

    if has_kit and has_plan:
        description = "Kit & Subscription"
    elif has_kit:
        description = "Kit Purchase"
    elif has_plan:
        description = "Subscription"
    else:
        description = "N/A"

    order_data = {
        "id": order.id,
        "reference": order.order_reference,
        "customer": order.user.get_full_name() or order.user.username,
        "email": order.user.email,
        "phone": getattr(order, "phone", ""),  # Ensure 'phone' exists in model
        "delivery_address": getattr(order, "delivery_address", ""),
        "status": order.payment_status,
        "date": order.created_at.strftime("%Y-%m-%d %H:%M"),
        "vat": 0.0,
        "exc": 0.0,
        "total": float(order.total_price),
        "description": description,
        "items": [],
    }

    # Optional: Add items if you store them separately
    if has_kit:
        kit_total = (
            order.lines.filter(kind=OrderLine.Kind.KIT).aggregate(
                s=dj_models.Sum("line_total")
            )["s"]
            or 0
        )
        order_data["items"].append(
            {
                "name": (
                    order.kit_name if hasattr(order, "kit_name") else "Starlink Kit"
                ),
                "type": "Hardware",
                "price": float(kit_total),
            }
        )

    if has_plan:
        plan_total = (
            order.lines.filter(kind=OrderLine.Kind.PLAN).aggregate(
                s=dj_models.Sum("line_total")
            )["s"]
            or 0
        )
        order_data["items"].append(
            {
                "name": (
                    order.plan_name
                    if hasattr(order, "plan_name")
                    else "Subscription Plan"
                ),
                "type": "Subscription",
                "price": float(plan_total),
            }
        )

    return JsonResponse({"success": True, "order": order_data})


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "dispatcher"])
def dispatch_dashboard(request):
    template = "dispatch_console.html"

    # Count of orders that have been assigned to an inventory
    assigned_order_count = Order.objects.filter(
        kit_inventory__isnull=False, payment_status="paid", delivery_date__isnull=True
    ).count()
    dispatched_order = Order.objects.filter(
        kit_inventory__isnull=True, delivery_date=now().date()
    ).count()
    total_dispatched = (
        Order.objects.filter(delivery_date__isnull=False)
        .exclude(status="cancelled")
        .count()
    )

    context = {
        "assigned_order_count": assigned_order_count,
        "dispatched_order": dispatched_order,
        "total_dispatched": total_dispatched,
    }
    return render(request, template, context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "finance", "manager"])
def revenue_summary(request):
    today = dj_timezone.now().date()
    default_from = today.replace(day=1).strftime("%Y-%m")
    default_to = today.strftime("%Y-%m")
    context = {
        "default_from": default_from,
        "default_to": default_to,
        "api_endpoint": reverse("revenue-summary"),
        "page_title": "Revenue reporting",
        "default_group": "region",
    }
    return render(request, "revenue/summary.html", context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "finance", "dispatcher"])
def items_list(request):
    # ---------- Query params ----------
    search_query = (request.GET.get("search") or "").strip()
    region_filter = (request.GET.get("region") or "").strip()
    start_date = (request.GET.get("startDate") or "").strip()
    end_date = (request.GET.get("endDate") or "").strip()
    page = int(request.GET.get("page", 1))
    per_page = int(request.GET.get("per_page", 20))  # UI drives the page size

    # ---------- Base queryset ----------
    orders = (
        Order.objects.select_related(
            "user",
            "kit_inventory",
            "kit_inventory__kit",
            "subscription",
            "installation_activity__technician",
        )
        .filter(
            subscription__isnull=False,
            is_installed=False,
            payment_status="paid",
            delivery_date__isnull=True,
            delivered_by__isnull=True,
        )
        .order_by("-created_at")
    )

    # ---------- Search (match your User fields) ----------
    if search_query:
        orders = orders.filter(
            Q(order_reference__icontains=search_query)
            | Q(user__full_name__icontains=search_query)
            | Q(user__email__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(user__phone__icontains=search_query)
        )

    # ---------- Date range ----------
    if start_date and end_date:
        orders = orders.filter(created_at__date__range=(start_date, end_date))
    elif start_date:
        orders = orders.filter(created_at__date__gte=start_date)
    elif end_date:
        orders = orders.filter(created_at__date__lte=end_date)

    # ---------- Pagination ----------
    paginator = Paginator(orders, per_page)
    page_obj = paginator.get_page(page)

    # ---------- Serialize ----------
    order_data = []
    # Preload region names (for "other" comparison) once
    db_region_names = set(Region.objects.values_list("name", flat=True))

    for order in page_obj:
        inv = order.kit_inventory
        user = order.user

        # Resolve region via GeoDjango polygons, if coordinates exist
        region_name = "—"
        if order.latitude is not None and order.longitude is not None:
            try:
                # GeoJSON/GeoDjango convention: Point(lon, lat)
                pt = Point(float(order.longitude), float(order.latitude), srid=4326)
                match = (
                    Region.objects.filter(fence__contains=pt)
                    .values_list("name", flat=True)
                    .first()
                )
                if match:
                    region_name = match
            except Exception:
                # leave region_name as "—" if anything goes wrong
                pass

        technician_name = (
            order.installation_activity.technician.full_name
            if getattr(order, "installation_activity", None)
            and order.installation_activity.technician
            else "Not Assigned"
        )

        kit_name = inv.kit.name if inv and inv.kit else "—"

        order_data.append(
            {
                "order_id": order.order_reference or f"#{order.id}",
                "customer": getattr(user, "full_name", "—") if user else "—",
                "phone": getattr(user, "phone", "—") if user else "—",
                "kit_type": kit_name,
                "region": region_name,
                "address": (
                    f"{order.latitude}, {order.longitude}"
                    if (order.latitude is not None and order.longitude is not None)
                    else "—"
                ),
                "order_date": localtime(order.created_at).strftime("%Y-%m-%d"),
                "stock": "Assigned" if inv else "—",
                "serial_number": getattr(inv, "serial_number", "—") if inv else "—",
                "technician": technician_name,
            }
        )

    # ---------- Region filter (post-resolve) ----------
    if region_filter:
        if region_filter.lower() == "other":
            # Keep only orders whose detected region is not in DB polygons (or not detected)
            order_data = [o for o in order_data if o["region"] not in db_region_names]
        else:
            order_data = [
                o for o in order_data if o["region"].lower() == region_filter.lower()
            ]

    # ---------- Response ----------
    return JsonResponse(
        {
            "success": True,
            "orders": order_data,
            "page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
        }
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def get_regions(request):
    regions = Region.objects.all().order_by("name")
    data = [{"name": r.name} for r in regions]
    return JsonResponse({"regions": data})


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "dispatcher"])
@require_POST
def save_serial_number(request):
    try:
        data = json.loads(request.body)
        order_id = data.get("order_id")
        serial_number = data.get("serial_number")

        if not order_id or not serial_number:
            return JsonResponse(
                {"success": False, "message": "Missing data."}, status=400
            )

        # Find the order
        order = (
            Order.objects.select_related("kit_inventory")
            .filter(order_reference=order_id)
            .first()
        )

        if not order:
            return JsonResponse(
                {"success": False, "message": "Order not found."}, status=404
            )

        inventory = order.kit_inventory
        if not inventory:
            return JsonResponse(
                {"success": False, "message": "No inventory assigned to this order."},
                status=400,
            )

        # Save the serial number
        inventory.serial_number = serial_number
        inventory.save()

        return JsonResponse({"success": True, "message": "Serial number saved."})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Server error: {str(e)}"}, status=500
        )


@login_required
@require_staff_role(["admin", "manager"])
@require_POST
def assign_kit_to_technician(request):
    try:
        kit_inventory_id = request.POST.get("kit_inventory_id")
        technician_id = request.POST.get("technician_id")

        if not kit_inventory_id or not technician_id:
            return JsonResponse(
                {"success": False, "message": "Kit and Technician are required."},
                status=400,
            )

        kit_inventory = get_object_or_404(StarlinkKitInventory, id=kit_inventory_id)
        technician = get_object_or_404(User, id=technician_id)

        # Optional: check if technician already has an active assignment of this kit
        existing_assignment = TechnicianAssignment.objects.filter(
            technician=technician, inventory_item=kit_inventory, is_active=True
        ).first()
        if existing_assignment:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"This kit is already assigned to {technician.full_name}.",
                },
                status=400,
            )

        # Mark any previous assignments for the same kit as inactive
        TechnicianAssignment.objects.filter(
            inventory_item=kit_inventory, is_active=True
        ).update(is_active=False)

        # Create the assignment
        TechnicianAssignment.objects.create(
            technician=technician,
            inventory_item=kit_inventory,
            assigned_by=request.user,
        )

        # Optionally mark the kit as assigned
        kit_inventory.is_assigned = True
        kit_inventory.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Kit {kit_inventory.kit_number} successfully assigned to {technician.full_name}.",
            }
        )

    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"An error occurred: {str(e)}"}, status=500
        )


# @login_required
# @require_staff_role(["admin", "manager"])
# @require_GET
# def get_technicians(request):
#     technicians = User.objects.filter(roles__contains=["technician"])
#     data = [{"id": tech.id_user, "full_name": tech.full_name} for tech in technicians]
#     print(data)
#     return JsonResponse({"technicians": data})


# @login_required(login_url='login_page')
# @require_staff_role(["admin", "manager"])
# @require_POST
# def assign_to_technician(request):
#     if request.method != "POST":
#         return JsonResponse({"success": False, "error": "Invalid request method."}, status=405)
#     try:
#         data = json.loads(request.body)
#         technician_id = data.get("technician_id")
#         order_id = data.get("order_id")  # adjust if it's a task/job instead
#
#         print('TEST ASSIGNEMENT')
#         print(technician_id, order_id)
#
#         if not technician_id or not order_id:
#             return JsonResponse({"success": False, "error": "Technician and Order ID are required."}, status=400)
#
#         technician = get_object_or_404(User, id=technician_id)
#         order = get_object_or_404(Order, id=order_id)
#
#         order.technician = technician
#         order.save()
#
#         # return JsonResponse({"success": True, "message": "Technician assigned successfully."})
#
#     except json.JSONDecodeError:
#         return JsonResponse({"success": False, "error": "Invalid JSON data."}, status=400)
#     except Exception as e:
#         return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "dispatcher"])
def deliver_order_dispatch(request):
    user = request.user
    try:
        data = json.loads(request.body)
        order_id = data.get("order_id")

        if not order_id:
            return JsonResponse(
                {"success": False, "message": "Missing order_id."}, status=400
            )

        order = get_object_or_404(Order, order_reference=order_id)

        if order.delivery_date:
            return JsonResponse(
                {"success": False, "message": "Order has already been delivered."},
                status=400,
            )

        order.delivered_by_id = user
        order.delivery_date = now()
        order.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Order {order.order_reference} marked as delivered.",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


def _minutes(td):
    if not td:
        return 0
    return int(round(td.total_seconds() / 60.0))


def _median_minutes(durations):
    vals = [d.total_seconds() for d in durations if d is not None]
    n = len(vals)
    if n == 0:
        return 0
    vals.sort()
    mid = n // 2
    if n % 2:
        return int(round(vals[mid] / 60.0))
    return int(round(((vals[mid - 1] + vals[mid]) / 2.0) / 60.0))


@login_required(login_url="login_page")
@require_staff_role(["admin", "leadtechnician"])
def completed_installations(request):
    technician_id = request.GET.get("technician")
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")

    # ---- Date validation (server-side) ----
    today = dj_timezone.now().date()
    date_errors, df_obj, dt_obj = [], None, None

    if date_from:
        try:
            df_obj = datetime.strptime(date_from, "%Y-%m-%d").date()
            if df_obj > today:
                date_errors.append("La date de début ne peut pas être dans le futur.")
                df_obj = None
                date_from = None
        except ValueError:
            date_errors.append("Format de date de début invalide.")
            date_from = None

    if date_to:
        try:
            dt_obj = datetime.strptime(date_to, "%Y-%m-%d").date()
            if dt_obj > today:
                date_errors.append("La date de fin ne peut pas être dans le futur.")
                dt_obj = None
                date_to = None
        except ValueError:
            date_errors.append("Format de date de fin invalide.")
            date_to = None

    if df_obj and dt_obj and dt_obj < df_obj:
        date_errors.append("La date de fin doit être postérieure à la date de début.")
        dt_obj = None
        date_to = None

    for err in date_errors:
        messages.error(request, err)

    # ---- Base queryset ----
    qs = (
        InstallationActivity.objects.select_related(
            "order", "order__user", "technician", "order__subscription"
        )
        .filter(submitted_at__isnull=False)
        .order_by("-submitted_at")
    )
    if technician_id:
        qs = qs.filter(technician_id=technician_id)
    if df_obj:
        qs = qs.filter(submitted_at__date__gte=df_obj)
    if dt_obj:
        qs = qs.filter(submitted_at__date__lte=dt_obj)

    # ---- Pagination ----
    paginator = Paginator(qs, 20)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    # ---- Technicians for filter ----
    technicians = (
        User.objects.filter(
            Q(roles__icontains='"technician"') | Q(roles__icontains='"installer"'),
            is_active=True,
        )
        .order_by("first_name", "last_name")
        .distinct()
    )

    # ---- KPIs (use explicit Django DurationField instance) ----
    duration_expr = ExpressionWrapper(
        F("completed_at") - F("started_at"),
        output_field=dj_models.DurationField(),
    )
    kpi_qs = qs.filter(completed_at__isnull=False, started_at__isnull=False)

    completed_today = kpi_qs.filter(completed_at__date=today).count()
    avg_td = kpi_qs.aggregate(avg_dur=Avg(duration_expr))["avg_dur"]
    avg_completion_minutes = _minutes(avg_td) if avg_td else 0

    all_rows = list(
        kpi_qs.annotate(dur=duration_expr).values_list(
            "technician_id", "dur", "customer_rating"
        )
    )
    all_durations = [r[1] for r in all_rows if r[1] is not None]
    median_completion_minutes = _median_minutes(all_durations)

    per_tech_durs, per_tech_ratings = {}, {}
    for tech_id, dur, rating in all_rows:
        if tech_id and dur:
            per_tech_durs.setdefault(tech_id, []).append(dur)
        if tech_id and rating is not None:
            per_tech_ratings.setdefault(tech_id, []).append(rating)

    agg_by_tech = kpi_qs.values("technician_id").annotate(
        cnt=Count("id"), avg_dur=Avg(duration_expr), avg_rating=Avg("customer_rating")
    )
    tech_map = {
        u.pk: u
        for u in User.objects.filter(
            pk__in=[row["technician_id"] for row in agg_by_tech]
        )
    }
    tech_kpis = []
    for row in agg_by_tech:
        tid = row["technician_id"]
        tech_kpis.append(
            {
                "technician": tech_map.get(tid),
                "count": row["cnt"] or 0,
                "avg_minutes": _minutes(row["avg_dur"]) if row["avg_dur"] else 0,
                "median_minutes": _median_minutes(per_tech_durs.get(tid, [])),
                "avg_rating": row["avg_rating"],
            }
        )

    # ---- Unbilled today (no active subscription yet) ----
    active_sub_qs = Subscription.objects.filter(
        order_id=OuterRef("order_id"), status="active"
    )
    unbilled_today = (
        InstallationActivity.objects.select_related(
            "order", "order__user", "technician"
        )
        .annotate(has_active_sub=Exists(active_sub_qs))
        .filter(submitted_at__date=today, has_active_sub=False)
        .order_by("-submitted_at")
    )
    unbilled_today_count = unbilled_today.count()

    return render(
        request,
        "completed_installations.html",
        {
            "installations": page_obj,
            "page_obj": page_obj,
            "total_completed": paginator.count,
            "technicians": technicians,
            "selected_technician": technician_id,
            "date_from": date_from,
            "date_to": date_to,
            "completed_today": completed_today,
            "avg_completion_minutes": avg_completion_minutes,
            "median_completion_minutes": median_completion_minutes,
            "tech_kpis": tech_kpis,
            "unbilled_today": unbilled_today,
            "unbilled_today_count": unbilled_today_count,
        },
    )


def _can_start_billing(user) -> bool:
    roles = set(getattr(user, "roles", []) or [])
    return bool(
        user.is_staff
        or {"finance", "manager", "admin", "dispatcher", "leadtechnician"} & roles
    )


@login_required
@user_passes_test(_can_start_billing, login_url="login_page")
@transaction.atomic
def start_billing(request, installation_id: int):
    """
    First activation flow:

    - If cfg.first_cycle_included_in_order is True (default), DO NOT create a new invoice.
      The first month lives on the original order; we only mirror that order into the ledger
      (ensure_first_order_invoice_entry) and apply a prorated activation→anchor charge
      against that same order using the wallet.
    - Align subscription to the global anchor day immediately when cfg.align_first_cycle_to_anchor is True.
    - Taxes follow split_amounts_for_base() which already respects user.is_tax_exempt == True (all taxes = 0).
    """
    if request.method != "POST":
        messages.error(request, "Invalid method. Please use the Start Billing button.")
        return redirect(reverse("backoffice:completed_installations"))

    installation = get_object_or_404(
        InstallationActivity.objects.select_related(
            "order", "order__user", "order__plan"
        ),
        pk=installation_id,
    )
    order: Order = installation.order
    user = order.user

    if not order or not order.plan:
        messages.error(
            request, "Order/Plan missing on this installation; cannot start billing."
        )
        return redirect(reverse("backoffice:completed_installations"))

    # Ensure subscription exists (created in suspended state until we activate)
    sub = getattr(order, "subscription", None)
    if not sub:
        billing_cycle = (request.POST.get("billing_cycle") or "monthly").lower()
        if billing_cycle not in {"monthly", "quarterly", "yearly"}:
            billing_cycle = "monthly"
        sub = Subscription.objects.create(
            user=user,
            plan=order.plan,
            status="suspended",
            billing_cycle=billing_cycle,
            order=order,
        )

    # Idempotent early-exit
    if sub.status == "active" and sub.started_at:
        messages.info(
            request,
            f"Billing already active since {sub.started_at:%Y-%m-%d}. "
            f"Next bill on {sub.next_billing_date or '—'}.",
        )
        return redirect(reverse("backoffice:completed_installations"))

    # Pick start date (install completion or today)
    start_localdate = (
        dj_timezone.localtime(installation.completed_at).date()
        if installation.completed_at
        else dj_timezone.now().date()
    )

    # Mark order operationally installed if not already
    if not order.is_installed:
        order.is_installed = True
        order.installation_date = installation.completed_at or dj_timezone.now()
        order.save(update_fields=["is_installed", "installation_date"])

    cfg = BillingConfig.get()
    # Set subscription start; align immediately to the global anchor if configured
    sub.started_at = sub.started_at or start_localdate
    if cfg.align_first_cycle_to_anchor:
        prev_a, next_a = anchor_window(sub.started_at, cfg.anchor_day)
        sub.next_billing_date = next_a
    else:
        # If not aligning, first full cycle starts right away
        # (still safe with the rest of the flow)
        prev_a, next_a = anchor_window(sub.started_at, cfg.anchor_day)
        sub.next_billing_date = next_a  # keeping this consistent for simplicity

    sub.status = "active"
    sub.save(update_fields=["status", "started_at", "next_billing_date"])

    # Ensure original order is represented in the ledger (single invoice-style entry).
    # This does NOT create a new document; it mirrors the original order totals.
    ensure_first_order_invoice_entry(order)

    # --- Proration from activation → anchor (only if we align) ---
    # If the start date is exactly the anchor, proration multiplier is 0.
    period_days = max(1, (next_a - prev_a).days)
    used_days = max(0, (next_a - sub.started_at).days)
    mult = (used_days / period_days) if period_days else 0.0

    monthly_base = Decimal(str(order.plan.monthly_price_usd or 0))
    # For quarterly/yearly cycles you can keep monthly proration on initial activation
    # and let renewals handle full cycle amounts.
    prorated_base = q(monthly_base * Decimal(str(mult)))

    # Split taxes (respects user.is_tax_exempt → both taxes become 0)
    base, excise, vat, prorated_total = split_amounts_for_base(prorated_base, user=user)

    # Apply wallet up to the prorated amount against the existing order ledger
    applied = Decimal("0.00")
    if cfg.first_cycle_included_in_order:
        applied = apply_wallet_to_order(user, order, max_amount=prorated_total)
        # If fully covered, mark as paid/fulfilled
        if (
            due_for_ref(user, order_external_ref(order)) == 0
            and order.payment_status != "paid"
        ):
            order.payment_status = "paid"
            order.status = "fulfilled"
            order.save(update_fields=["payment_status", "status"])
    else:
        # Edge case: if your policy excludes first cycle from the original order
        # you could create a one-off AccountEntry (invoice) here instead and apply wallet.
        # Keeping current behavior simple: apply against original order as above.
        applied = apply_wallet_to_order(user, order, max_amount=prorated_total)

    # Configurable cutoff date (e.g., D-1)
    cutoff_days = getattr(cfg, "cutoff_days_before_anchor", 1)
    try:
        cutoff_days = int(cutoff_days)
    except Exception:
        cutoff_days = 1
    cutoff_days = max(0, cutoff_days)
    cutoff_date = sub.next_billing_date - timedelta(days=cutoff_days)

    if applied > 0:
        messages.success(
            request,
            (
                f"Activated billing. Applied ${applied} "
                f"(prorated: base ${base}, excise ${excise}, VAT ${vat}). "
                f"Anchor day={cfg.anchor_day}, next bill={sub.next_billing_date:%Y-%m-%d}, "
                f"cut-off={cutoff_date:%Y-%m-%d}."
            ),
        )
    else:
        messages.warning(
            request,
            (
                "Activated billing with zero wallet application (no funds). "
                f"Anchor day={cfg.anchor_day}, next bill={sub.next_billing_date:%Y-%m-%d}, "
                f"cut-off={cutoff_date:%Y-%m-%d}."
            ),
        )

    return redirect("completed_installations")


@login_required(login_url="login_page")
@user_passes_test(user_is_feedback_staff, login_url="login_page")
def feedback_list(request):
    queryset = (
        Feedback.objects.select_related(
            "installation",
            "installation__order",
            "customer",
        )
        .prefetch_related("attachments")
        .order_by("-created_at")
    )

    status_filter = request.GET.get("status") or ""
    rating_filter = request.GET.get("rating") or ""
    flagged = request.GET.get("flagged") or ""
    pinned = request.GET.get("pinned") or ""
    search = request.GET.get("q") or ""

    if status_filter:
        queryset = queryset.filter(status=status_filter)
    if rating_filter.isdigit():
        queryset = queryset.filter(rating=int(rating_filter))
    if flagged in {"true", "1"}:
        queryset = queryset.filter(internal_flag=True)
    if pinned in {"true", "1"}:
        queryset = queryset.filter(pinned=True)
    if search:
        queryset = queryset.filter(
            Q(installation__order__order_reference__icontains=search)
            | Q(customer__full_name__icontains=search)
            | Q(customer__email__icontains=search)
        )

    if request.GET.get("export") == "csv":
        return _export_feedbacks_csv(queryset)

    paginator = Paginator(queryset, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "feedback_page": page_obj,
        "filters": {
            "status": status_filter,
            "rating": rating_filter,
            "flagged": flagged,
            "pinned": pinned,
            "q": search,
        },
    }
    return render(request, "feedbacks/list.html", context)


def _export_feedbacks_csv(queryset):
    rows = [
        [
            "ID",
            "Job",
            "Client",
            "Note",
            "Statut",
            "Créé le",
            "Modifié le",
            "Pinned",
            "Flag",
        ],
    ]
    for feedback in queryset:
        order = getattr(feedback.installation, "order", None)
        rows.append(
            [
                feedback.id,
                order.order_reference if order else feedback.installation_id,
                feedback.customer.email or feedback.customer.full_name,
                feedback.rating,
                feedback.status,
                feedback.created_at.isoformat(),
                feedback.updated_at.isoformat(),
                "yes" if feedback.pinned else "no",
                "yes" if feedback.internal_flag else "no",
            ]
        )

    content = "\n".join(",".join(str(cell) for cell in row) for row in rows)
    response = HttpResponse(content, content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="feedbacks.csv"'
    return response


@login_required(login_url="login_page")
@user_passes_test(user_is_feedback_staff, login_url="login_page")
def feedback_detail(request, pk: int):
    feedback = get_object_or_404(
        Feedback.objects.select_related(
            "installation",
            "installation__order",
            "customer",
        ).prefetch_related("attachments", "audit_logs__actor"),
        pk=pk,
    )

    api_root = "/api/feedbacks/"
    detail_endpoint = f"{api_root}{feedback.pk}/"
    attachment_delete_base = "/api/feedbacks/attachments/"

    context = {
        "feedback": feedback,
        "order": getattr(feedback.installation, "order", None),
        "detail_endpoint": detail_endpoint,
        "pin_endpoint": f"{detail_endpoint}pin/",
        "lock_endpoint": f"{detail_endpoint}lock/",
        "reply_endpoint": f"{detail_endpoint}reply/",
        "attachment_endpoint": f"{detail_endpoint}attachments/",
        "attachment_delete_base": attachment_delete_base,
    }
    return render(request, "feedbacks/detail.html", context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def installation_report_detail(request, installation_id):
    """
    Page dédiée pour afficher les détails complets d'un rapport d'installation.
    Plus maintenable et UX-friendly qu'une modal pour des données complexes.
    """
    installation = get_object_or_404(
        InstallationActivity.objects.select_related(
            "order", "order__user", "technician"
        ),
        id=installation_id,
        submitted_at__isnull=False,  # Only submitted reports
    )

    context = {
        "installation": installation,
        "page_title": f"Rapport d'installation - {installation.order.order_reference}",
    }

    return render(request, "installation_report_detail.html", context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager"])
def installation_report_pdf(request, installation_id):
    """Generate a PDF for the Installation Report, including signature if present."""
    installation = get_object_or_404(
        InstallationActivity.objects.select_related(
            "order", "order__user", "technician"
        ),
        id=installation_id,
        submitted_at__isnull=False,
    )

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=(210 * mm, 297 * mm),
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"Installation Report – {getattr(installation.order, 'order_reference', '')}",
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TITLE", fontName="Helvetica-Bold", fontSize=14))
    styles.add(
        ParagraphStyle(
            name="SUB",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#4b5563"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="LBL",
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#6b7280"),
        )
    )
    styles.add(ParagraphStyle(name="VAL", fontName="Helvetica-Bold", fontSize=10))

    elems = []

    # Header with logo + title
    logo_path = os.path.join(
        django_settings.BASE_DIR, "static", "images", "logo", "logo.png"
    )
    left = []
    if os.path.exists(logo_path):
        left.append(Image(logo_path, width=40 * mm, height=12 * mm))
    left.append(Paragraph("Installation Report", styles["TITLE"]))
    left.append(
        Paragraph(getattr(installation.order, "order_reference", ""), styles["SUB"])
    )
    header = Table([[left]], colWidths=[174 * mm])
    header.setStyle(TableStyle([("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    elems += [header, Spacer(1, 6)]

    # Parties/info table
    cust = installation.order.user if installation.order else None
    info = [
        [
            Paragraph("Order", styles["LBL"]),
            Paragraph(
                getattr(installation.order, "order_reference", ""), styles["VAL"]
            ),
        ],
        [
            Paragraph("Customer", styles["LBL"]),
            Paragraph(
                (getattr(cust, "full_name", "") or getattr(cust, "username", "")) or "",
                styles["VAL"],
            ),
        ],
        [
            Paragraph("Email", styles["LBL"]),
            Paragraph(getattr(cust, "email", "") or "", styles["VAL"]),
        ],
        [
            Paragraph("Technician", styles["LBL"]),
            Paragraph(
                getattr(getattr(installation, "technician", None), "full_name", "")
                or "",
                styles["VAL"],
            ),
        ],
        [
            Paragraph("Submitted", styles["LBL"]),
            Paragraph(
                (
                    installation.submitted_at.strftime("%Y-%m-%d %H:%M")
                    if installation.submitted_at
                    else ""
                ),
                styles["VAL"],
            ),
        ],
    ]
    tbl = Table(info, colWidths=[28 * mm, 146 * mm], hAlign="LEFT")
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elems += [tbl, Spacer(1, 10)]

    # Signature (if available)
    sig_dataurl = getattr(installation, "customer_signature", "") or ""
    if sig_dataurl.startswith("data:image") and "," in sig_dataurl:
        try:
            b64 = sig_dataurl.split(",", 1)[1]
            raw = base64.b64decode(b64)
            sig_img = Image(BytesIO(raw), width=60 * mm, height=24 * mm)
            sig_box = Table(
                [[Paragraph("Customer signature", styles["LBL"])], [sig_img]],
                colWidths=[174 * mm],
            )
            sig_box.setStyle(
                TableStyle(
                    [
                        ("BOX", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            elems += [sig_box, Spacer(1, 8)]
        except Exception:
            pass

    doc.build(elems)
    pdf = buffer.getvalue()
    buffer.close()

    filename = f"installation_report_{getattr(installation.order, 'order_reference', installation.id)}.pdf"
    resp = HttpResponse(pdf, content_type="application/pdf")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
