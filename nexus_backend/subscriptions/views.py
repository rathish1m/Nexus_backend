from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET

from main.models import Subscription
from user.permissions import require_staff_role


# Create your views here.
@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "leadtechnician", "finance"])
def subscription_dashboard(request):
    template = "subscriptions.html"
    total_subscriptions = Subscription.objects.count()
    active_subscriptions = Subscription.objects.filter(status="active").count()
    pending_activations = Subscription.objects.filter(status="pending").count()
    cancelled_activations = Subscription.objects.filter(status="cancelled").count()
    context = {
        "total_subscriptions": total_subscriptions,
        "active_subscriptions": active_subscriptions,
        "pending_activations": pending_activations,
        "cancelled_activations": cancelled_activations,
    }
    return render(request, template, context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "leadtechnician", "finance"])
def get_overdue_customers():
    today = date.today()

    # Step 1: Find subscriptions where next billing date has passed
    overdue_subs = Subscription.objects.filter(
        status="active", next_billing_date__lt=today
    ).select_related("user", "order")

    overdue_list = []

    for sub in overdue_subs:
        # Step 2: Check if any payment attempt for this subscription after last billing date
        last_payment = (
            sub.get_payment_attempts()
            .filter(
                status="completed",
                transaction_time__date__gte=sub.next_billing_date - timedelta(days=30),
            )
            .exists()
        )

        if not last_payment:
            days_overdue = (today - sub.next_billing_date).days
            overdue_list.append(
                {
                    "id": sub.id,
                    "name": sub.user.full_name if sub.user else "Unknown",
                    "email": sub.user.email if sub.user else "—",
                    "days_overdue": days_overdue,
                }
            )

    return overdue_list


ZERO = Decimal("0.00")


def _q(x):
    return (Decimal(x) if x is not None else ZERO).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def _cycle_price(monthly_price, billing_cycle: str) -> Decimal:
    """
    Return the PRICE FOR THE CYCLE shown in the table (not monthly equivalent):
    - monthly  => monthly_price * 1
    - quarterly=> monthly_price * 3
    - yearly   => monthly_price * 12
    """
    p = _q(monthly_price)
    cycle = (billing_cycle or "monthly").lower()
    if cycle == "quarterly":
        return _q(p * Decimal("3"))
    if cycle == "yearly":
        return _q(p * Decimal("12"))
    return p  # monthly / fallback


def _ui_status(model_status: str) -> str:
    """
    Map model statuses to UI statuses:
    - 'suspended' -> 'pending'
    - 'cancelled' -> 'canceled'
    - others pass through (e.g., 'active')
    """
    if not model_status:
        return ""
    s = model_status.lower()
    if s == "suspended":
        return "pending"
    if s == "cancelled":
        return "canceled"
    return s


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "leadtechnician", "finance"])
@require_GET
def getallcust_subscr(request):
    today = date.today()

    search_term = (request.GET.get("search", "") or "").strip().lower()
    status_filter = (request.GET.get("status", "") or "").strip().lower()

    # Map UI filter to model values
    status_map = {"pending": "suspended", "canceled": "cancelled"}
    model_status_filter = status_map.get(status_filter, status_filter)

    qs = Subscription.objects.select_related(
        "user", "plan", "order", "order__kit_inventory"
    ).order_by("-started_at")

    # Search filter
    if search_term:
        qs = qs.filter(
            Q(user__full_name__icontains=search_term)
            | Q(user__email__icontains=search_term)
            | Q(plan__name__icontains=search_term)
            | Q(status__icontains=search_term)
        )

    # Status filter
    if model_status_filter and model_status_filter != "all":
        qs = qs.filter(status__iexact=model_status_filter)

    data = []
    overdue_customers = []
    deactivated_customers = []

    for sub in qs:
        user = sub.user
        plan = sub.plan
        order = sub.order

        # Pricing per cycle for table display
        monthly_price = plan.monthly_price_usd if plan else None
        cycle_cost = (
            _cycle_price(monthly_price, sub.billing_cycle)
            if monthly_price is not None
            else None
        )

        # Kit ID (prefer kit_number; fall back to serial_number if you prefer)
        kit_id = None
        if order and getattr(order, "kit_inventory", None):
            kit_id = order.kit_inventory.kit_number or order.kit_inventory.serial_number

        # Location fields (address placeholder if you don't store one)
        latitude = getattr(order, "latitude", None) if order else None
        longitude = getattr(order, "longitude", None) if order else None
        address = ""  # Fill from your source if/when available

        # Build subscription row
        data.append(
            {
                "id": sub.id,
                "user_name": user.full_name if user else "Unknown",
                "user_email": user.email if user else "",
                "plan_name": plan.name if plan else "—",
                "status": _ui_status(sub.status),
                "cycle_cost": float(cycle_cost) if cycle_cost is not None else None,
                "billing_cycle": (sub.billing_cycle or "monthly").lower(),
                "started_at": (
                    sub.started_at.strftime("%Y-%m-%d") if sub.started_at else ""
                ),
                "next_billing_date": (
                    sub.next_billing_date.strftime("%Y-%m-%d")
                    if sub.next_billing_date
                    else ""
                ),
                "order_ref": order.order_reference if order else "",
                "kit_id": kit_id or "—",
                "latitude": latitude,
                "longitude": longitude,
                "address": address,
            }
        )

        # Overdue detection (only for ACTIVE subs in model terms)
        if (
            sub.status == "active"
            and sub.next_billing_date
            and sub.next_billing_date < today
        ):
            last_payment_exists = (
                sub.get_payment_attempts()
                .filter(
                    status="completed",
                    transaction_time__date__gte=sub.next_billing_date
                    - timedelta(days=30),
                )
                .exists()
            )
            if not last_payment_exists:
                overdue_customers.append(
                    {
                        "id": sub.id,
                        "name": user.full_name if user else "Unknown",
                        "email": user.email if user else "",
                        "days_overdue": (today - sub.next_billing_date).days,
                    }
                )

        # Deactivated (model 'cancelled' → UI shows in alert)
        if sub.status == "cancelled":
            deactivated_customers.append(
                {
                    "id": sub.id,
                    "name": user.full_name if user else "Unknown",
                    "email": user.email if user else "",
                    "deactivated_at": (
                        sub.ended_at.strftime("%Y-%m-%d") if sub.ended_at else None
                    ),
                }
            )

    return JsonResponse(
        {
            "success": True,
            "subscriptions": data,
            "overdue_customers": overdue_customers,
            "deactivated_customers": deactivated_customers,
        }
    )
