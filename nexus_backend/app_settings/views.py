import json
import logging
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from typing import Iterable, List

from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import GEOSGeometry
from django.core.files.storage import default_storage
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db import transaction
from django.db.models import Count
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from geo_regions.models import Region
from main.models import (
    BillingConfig,
    CompanySettings,
    Coupon,
    DiscountType,
    InstallationFee,
    PaymentMethod,
    Promotion,
    StackPolicy,
    StarlinkKit,
    SubscriptionPlan,
    TaxRate,
)
from promotions.coupons import bulk_generate_coupons, generate_unique_coupon
from site_survey.models import ExtraCharge, SiteSurveyChecklist

# RBAC imports - Phase 1 migration
from user.permissions import require_staff_role

# --- Extra Charge Views (fusionnés depuis extra_charge_views.py) ---


@require_staff_role(["admin", "finance", "manager"])
def get_extra_charges(request):
    """Get paginated list of extra charges"""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    extra_charges = ExtraCharge.objects.all().order_by(
        "cost_type", "display_order", "item_name"
    )
    paginator = Paginator(extra_charges, 10)  # Show 10 items per page

    page_number = request.GET.get("page", 1)
    try:
        items_page = paginator.page(page_number)
    except PageNotAnInteger:
        items_page = paginator.page(1)
    except EmptyPage:
        items_page = paginator.page(paginator.num_pages)

    data = []
    for item in items_page:
        data.append(
            {
                "id": item.id,
                "cost_type": item.cost_type,
                "cost_type_display": item.get_cost_type_display(),
                "item_name": item.item_name,
                "description": item.description,
                "brand": item.brand,
                "model": item.model,
                "unit_price": str(item.unit_price),
                "is_active": item.is_active,
                "display_order": item.display_order,
                "specifications": item.specifications,
            }
        )

    return JsonResponse(
        {
            "extra_charges": data,
            "pagination": {
                "has_next": items_page.has_next(),
                "has_previous": items_page.has_previous(),
                "page_number": items_page.number,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
            },
        }
    )


@require_staff_role(["admin", "finance"])
@require_POST
@csrf_protect
def create_extra_charge(request):
    """Create a new extra charge"""

    logger.info(
        f"create_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
    )
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request headers: {dict(request.headers)}")
    try:
        logger.info(f"Request body: {request.body.decode('utf-8')}")
    except Exception as e:
        logger.warning(f"Could not decode request body: {e}")

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "create_extra_charge: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        logger.info(f"create_extra_charge: Received data: {data}")

        # Extract data from request
        cost_type = data.get("cost_type")
        item_name = data.get("item_name")
        description = data.get("description", "")
        brand = data.get("brand", "")
        model = data.get("model", "")
        unit_price = data.get("unit_price")
        is_active = data.get("is_active", True)
        display_order = data.get("display_order", 0)
        specifications = data.get("specifications", "")

        # Validate required fields
        if not all([cost_type, item_name, unit_price]):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cost type, item name, and unit price are required.",
                },
                status=400,
            )

        # Validate unit price
        try:
            unit_price = Decimal(str(unit_price))
            if unit_price < 0:
                return JsonResponse(
                    {"success": False, "message": "Unit price must be positive."},
                    status=400,
                )
        except (ValueError, InvalidOperation):
            return JsonResponse(
                {"success": False, "message": "Invalid unit price format."}, status=400
            )

        # Check for duplicate item names
        if ExtraCharge.objects.filter(item_name=item_name).exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": "An extra charge with this item name already exists.",
                },
                status=400,
            )

        # Create the extra charge
        extra_charge = ExtraCharge.objects.create(
            cost_type=cost_type,
            item_name=item_name,
            description=description,
            brand=brand,
            model=model,
            unit_price=unit_price,
            is_active=bool(is_active),
            display_order=int(display_order),
            specifications=specifications,
        )

        logger.info(f"create_extra_charge: Created item with ID {extra_charge.id}")

        return JsonResponse(
            {
                "success": True,
                "message": f"Extra charge '{item_name}' created successfully.",
                "extra_charge": {
                    "id": extra_charge.id,
                    "cost_type": extra_charge.cost_type,
                    "cost_type_display": extra_charge.get_cost_type_display(),
                    "item_name": extra_charge.item_name,
                    "description": extra_charge.description,
                    "brand": extra_charge.brand,
                    "model": extra_charge.model,
                    "unit_price": str(extra_charge.unit_price),
                    "is_active": extra_charge.is_active,
                    "display_order": extra_charge.display_order,
                    "specifications": extra_charge.specifications,
                },
            }
        )

    except json.JSONDecodeError:
        logger.error("create_extra_charge: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"create_extra_charge: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance"])
@require_POST
@csrf_protect
def edit_extra_charge(request):
    """Update an existing extra charge"""
    logger.info(
        f"update_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "update_extra_charge: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        logger.info(f"update_extra_charge: Received data: {data}")

        # Extract data from request
        extracharge_id = data.get("extracharge_id")
        cost_type = data.get("cost_type")
        item_name = data.get("item_name")
        description = data.get("description", "")
        brand = data.get("brand", "")
        model = data.get("model", "")
        unit_price = data.get("unit_price")
        is_active = data.get("is_active", True)
        display_order = data.get("display_order", 0)
        specifications = data.get("specifications", "")

        # Validate required fields
        if not all([extracharge_id, cost_type, item_name, unit_price]):
            return JsonResponse(
                {
                    "success": False,
                    "message": "ID, cost type, item name, and unit price are required.",
                },
                status=400,
            )

        # Get the extra charge
        try:
            extra_charge = ExtraCharge.objects.get(id=extracharge_id)
        except ExtraCharge.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Extra charge not found."}, status=404
            )

        # Validate unit price
        try:
            unit_price = Decimal(str(unit_price))
            if unit_price < 0:
                return JsonResponse(
                    {"success": False, "message": "Unit price must be positive."},
                    status=400,
                )
        except (ValueError, InvalidOperation):
            return JsonResponse(
                {"success": False, "message": "Invalid unit price format."}, status=400
            )

        # Check for duplicate item names (excluding current item)
        if (
            ExtraCharge.objects.filter(item_name=item_name)
            .exclude(id=extracharge_id)
            .exists()
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": "An extra charge with this item name already exists.",
                },
                status=400,
            )

        # Update the extra charge
        extra_charge.cost_type = cost_type
        extra_charge.item_name = item_name
        extra_charge.description = description
        extra_charge.brand = brand
        extra_charge.model = model
        extra_charge.unit_price = unit_price
        extra_charge.is_active = bool(is_active)
        extra_charge.display_order = int(display_order)
        extra_charge.specifications = specifications
        extra_charge.save()

        logger.info(f"update_extra_charge: Updated item with ID {extra_charge.id}")

        return JsonResponse(
            {
                "success": True,
                "message": f"Extra charge '{item_name}' updated successfully.",
                "extra_charge": {
                    "id": extra_charge.id,
                    "cost_type": extra_charge.cost_type,
                    "cost_type_display": extra_charge.get_cost_type_display(),
                    "item_name": extra_charge.item_name,
                    "description": extra_charge.description,
                    "brand": extra_charge.brand,
                    "model": extra_charge.model,
                    "unit_price": str(extra_charge.unit_price),
                    "is_active": extra_charge.is_active,
                    "display_order": extra_charge.display_order,
                    "specifications": extra_charge.specifications,
                },
            }
        )

    except json.JSONDecodeError:
        logger.error("update_extra_charge: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"update_extra_charge: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin"])
@require_POST
@csrf_protect
def delete_extra_charge(request):
    """Delete an extra charge"""
    logger.info(
        f"delete_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "delete_extra_charge: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        extracharge_id = data.get("extracharge_id")

        if not extracharge_id:
            return JsonResponse(
                {"success": False, "message": "Extra charge ID is required."},
                status=400,
            )

        # Get and delete the extra charge
        try:
            extra_charge = ExtraCharge.objects.get(id=extracharge_id)

            # Check if this extra charge is used in any survey additional costs
            if (
                hasattr(extra_charge, "surveyadditionalcost_set")
                and extra_charge.surveyadditionalcost_set.exists()
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Cannot delete this extra charge as it is being used in existing site surveys.",
                    },
                    status=400,
                )

            item_name = extra_charge.item_name
            extra_charge.delete()

            logger.info(f"delete_extra_charge: Deleted item with ID {extracharge_id}")

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Extra charge '{item_name}' deleted successfully.",
                }
            )

        except ExtraCharge.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Extra charge not found."}, status=404
            )

    except json.JSONDecodeError:
        logger.error("delete_extra_charge: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"delete_extra_charge: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


# Create your views here.

# Set up logger for this module
logger = logging.getLogger(__name__)


@require_staff_role(["admin", "manager"])
def system_settings(request):
    template = "settings_backoffice_page.html"
    company = CompanySettings.get()
    context = {"company": company}
    return render(request, template, context)


@require_staff_role(["admin", "manager"])
@require_POST  # Only allow POST requests
@csrf_protect  # Ensure CSRF protection is enforced
def create_subscription_plan(request):
    logger.info(
        f"create_subscription_plan called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "create_subscription_plan: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    # Parse JSON data from request body
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )

    # Debug: Log parsed data
    logger.info(f"JSON data received: {data}")

    name = data.get("name", "").strip()
    kit_type = data.get("kit_type", "").strip()
    plan_type = data.get("plan_type")
    if plan_type is None or plan_type == "":
        plan_type = None
    elif isinstance(plan_type, str):
        plan_type = plan_type.strip() or None
    else:
        plan_type = str(plan_type).strip() or None
    data_gb = data.get("data_gb") or data.get("standard_data_gb")
    if data_gb is None:
        data_gb = ""
    elif isinstance(data_gb, str):
        data_gb = data_gb.strip()
    else:
        data_gb = str(data_gb).strip()
    price_usd = data.get("price_usd", "").strip()
    description = data.get("description", "").strip()
    site_type = data.get("site_type", "").strip()

    if not name or not kit_type or not price_usd or not site_type:
        return JsonResponse(
            {
                "success": False,
                "message": "Name, Kit Type, Price, and Site Type are required.",
            },
            status=400,
        )

    # Parse price
    try:
        price = Decimal(price_usd)
        if price < 0:
            return JsonResponse(
                {"success": False, "message": "Price must be positive."}, status=400
            )
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "message": "Invalid price format."}, status=400
        )

    # Parse data cap if provided
    data_cap = None
    if data_gb:
        try:
            data_cap = int(data_gb)
            if data_cap < 0:
                return JsonResponse(
                    {"success": False, "message": "Data cap must be positive."},
                    status=400,
                )
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "Invalid data cap format."}, status=400
            )

    try:
        # Determine category name based on kit_type
        # category_name = (
        #     "Standard Category" if kit_type == "standard" else "Mini Category"
        # )

        plan = SubscriptionPlan.objects.create(
            name=name,
            category_name=kit_type.capitalize(),
            category_description=description,
            category_is_active=True,
            plan_type=plan_type,
            standard_data_gb=data_cap,
            monthly_price_usd=price,
            site_type=site_type,
            is_active=True,  # New plans are active by default
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Subscription plan added successfully.",
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "kit_type": plan.kit_type,
                    "plan_type": plan.plan_type or "",
                    "data_cap_gb": plan.standard_data_gb,
                    "monthly_price_usd": str(plan.monthly_price_usd),
                    "description": plan.category_description or "",
                    "is_active": plan.is_active,
                },
            }
        )
    except Exception as e:
        logger.error(f"Error creating subscription plan: {str(e)}", exc_info=True)
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "manager", "sales"])
def get_subscription_plans(request):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    plan_list = SubscriptionPlan.objects.all().order_by("id")
    paginator = Paginator(plan_list, 10)  # Show 10 plans per page

    page_number = request.GET.get("page", 1)
    try:
        plans_page = paginator.page(page_number)
    except PageNotAnInteger:
        plans_page = paginator.page(1)
    except EmptyPage:
        plans_page = paginator.page(paginator.num_pages)

    data = []
    for plan in plans_page:
        data.append(
            {
                "id": plan.id,
                "name": plan.name,
                "data_cap_gb": plan.standard_data_gb,  # Updated field name
                "monthly_price_usd": (
                    str(plan.monthly_price_usd) if plan.monthly_price_usd else ""
                ),  # Updated field name
                "description": plan.category_description
                or "",  # Use category_description instead of description
                "is_active": plan.is_active,
                "kit_type": plan.kit_type,
                "plan_type": plan.plan_type,
                "category_name": plan.category_name,
                "category_description": plan.category_description or "",
                "category_is_active": plan.category_is_active,
                "site_type": plan.site_type or "",
                "site_type_display": plan.get_site_type_display(),
            }
        )

    return JsonResponse(
        {
            "plans": data,
            "pagination": {
                "has_next": plans_page.has_next(),
                "has_previous": plans_page.has_previous(),
                "page_number": plans_page.number,
                "total_pages": paginator.num_pages,
            },
        }
    )


@require_staff_role(["admin", "manager", "sales"])
def get_subscription(request, pk):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )
    try:
        plan = SubscriptionPlan.objects.get(pk=pk)
        return JsonResponse(
            {
                "success": True,
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "kit_type": plan.kit_type,
                    "plan_type": plan.plan_type or "",
                    "data_cap_gb": plan.standard_data_gb,
                    "monthly_price_usd": (
                        float(plan.monthly_price_usd)
                        if plan.monthly_price_usd
                        else None
                    ),
                    "description": plan.category_description or "",
                    "is_active": plan.is_active,
                    "category_name": plan.category_name,
                    "category_description": plan.category_description or "",
                    "category_is_active": plan.category_is_active,
                },
            }
        )
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({"success": False, "message": "Plan not found"}, status=404)


@require_staff_role(["admin", "manager"])
@require_POST
def edit_subscription(request, pk):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        plan = SubscriptionPlan.objects.get(pk=pk)

        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()
        data_cap = request.POST.get("data_cap_gb")
        price_usd = request.POST.get("price_usd")
        is_active = request.POST.get("is_active") == "true"

        if not name or price_usd is None:
            return JsonResponse(
                {"success": False, "message": "Name and price are required."}
            )

        plan.name = name
        plan.description = description
        plan.standard_data_gb = int(data_cap) if data_cap else None
        plan.monthly_price_usd = float(price_usd)
        plan.is_active = is_active
        plan.save()

        return JsonResponse({"success": True, "message": "Plan updated successfully."})

    except SubscriptionPlan.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Plan not found."}, status=404
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Unexpected error: {str(e)}"}, status=500
        )


@require_staff_role(["admin"])
@require_POST
def toggle_plan_status(request, pk):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    print("Status", pk)
    try:
        plan = SubscriptionPlan.objects.get(pk=pk)
        plan.is_active = not plan.is_active
        plan.save()
        return JsonResponse(
            {
                "success": True,
                "message": "Plan status updated.",
                "is_active": plan.is_active,
            }
        )
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Plan not found."}, status=404
        )


@require_staff_role(["admin"])
def delete_plan(request, pk):
    """
    Delete a subscription plan.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        plan = SubscriptionPlan.objects.get(pk=pk)

        # Check if plan is being used by any orders/subscriptions
        from main.models import Order, Subscription

        active_orders = Order.objects.filter(plan=plan).exists()
        active_subscriptions = Subscription.objects.filter(plan=plan).exists()

        if active_orders or active_subscriptions:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cannot delete plan that is being used by existing orders or subscriptions.",
                },
                status=400,
            )

        plan_name = plan.name
        plan.delete()

        return JsonResponse(
            {
                "success": True,
                "message": f"Subscription plan '{plan_name}' deleted successfully.",
            }
        )

    except SubscriptionPlan.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Plan not found."}, status=404
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Unexpected error: {str(e)}"}, status=500
        )


@require_staff_role(["admin", "manager", "sales", "dispatcher"])
def get_kits(request):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    kits = StarlinkKit.objects.all()

    data = []
    for kit in kits:
        data.append(
            {
                "id": kit.id,
                "name": kit.name,
                "model": kit.model,
                "description": kit.description,
                "price_usd": str(kit.base_price_usd) if kit.base_price_usd else "",
                "kit_type": kit.kit_type,
            }
        )

    return JsonResponse({"kit": data})


@require_staff_role(["admin", "manager"])
@require_POST
def add_kit(request):
    """
    Create a StarlinkKit from a multipart/form-data POST (FormData).
    Expected fields:
      - name (str, required)
      - model (str, required)
      - kit_type (str, required)
      - description (str, optional)
      - price_usd (decimal, optional)
      - picture (file, optional)
    Returns JSON only.
    """
    name = (request.POST.get("name") or "").strip()
    model = (request.POST.get("model") or "").strip()
    kit_type = (request.POST.get("kit_type") or "").strip()
    description = (request.POST.get("description") or "").strip()
    price_raw = (request.POST.get("price_usd") or "").strip()
    picture = request.FILES.get(
        "picture"
    )  # <-- matches your modal's <input name="picture">

    # Validate required fields
    if not name or not model or not kit_type:
        return JsonResponse(
            {"success": False, "message": "Name, Model, and Kit Type are required."},
            status=400,
        )

    # Parse price (optional)
    price = None
    if price_raw:
        try:
            price = Decimal(price_raw)
            if price < 0:
                return JsonResponse(
                    {"success": False, "message": "Price must be a positive number."},
                    status=400,
                )
        except InvalidOperation:
            return JsonResponse(
                {"success": False, "message": "Price must be a valid number."},
                status=400,
            )

    try:
        kit = StarlinkKit.objects.create(
            name=name,
            model=model,
            kit_type=kit_type,
            description=description or None,
            base_price_usd=price,
            picture=picture,
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Kit created successfully.",
                "kit": {
                    "id": kit.id,
                    "name": kit.name,
                    "model": kit.model,
                    "kit_type": kit.kit_type,
                    "description": kit.description or "",
                    "price_usd": (
                        str(kit.base_price_usd)
                        if kit.base_price_usd is not None
                        else ""
                    ),
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "manager", "sales", "dispatcher"])
def get_kit(request, pk):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )
    try:
        kit = StarlinkKit.objects.get(pk=pk)
        return JsonResponse(
            {
                "success": True,
                "kit": {
                    "id": kit.id,
                    "name": kit.name,
                    "model": kit.model,
                    "description": kit.description,
                    "price_usd": (
                        float(kit.base_price_usd) if kit.base_price_usd else None
                    ),
                },
            }
        )
    except StarlinkKit.DoesNotExist:
        return JsonResponse({"success": False, "message": "Kit not found"}, status=404)


@require_staff_role(["admin"])
def delete_kit(request, pk):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )
    try:
        kit = StarlinkKit.objects.get(pk=pk)
        kit.delete()
        return JsonResponse({"success": True, "message": "Kit deleted successfully."})
    except StarlinkKit.DoesNotExist:
        return JsonResponse({"success": False, "message": "Kit not found"}, status=404)


@require_staff_role(["admin", "manager"])
@require_POST
def edit_kit(request, pk):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )
    try:
        kit = StarlinkKit.objects.get(pk=pk)
        name = request.POST.get("name", "").strip()
        model = request.POST.get("model", "").strip()
        description = request.POST.get("description")
        price_usd = request.POST.get("price_usd")
        kit_picture = request.FILES.get("kit_picture")

        if not name or not model or not price_usd:
            return JsonResponse(
                {"success": False, "message": "Name, Model, and Price are required."}
            )

        # Handle picture replacement
        if kit_picture:
            if kit.picture:
                # Delete the old file from storage
                if default_storage.exists(kit.picture.name):
                    default_storage.delete(kit.picture.name)
            kit.picture = kit_picture

        kit.name = name
        kit.description = description
        kit.model = model
        kit.base_price_usd = float(price_usd)
        kit.picture = kit_picture
        kit.save()
        return JsonResponse({"success": True, "message": "Kit updated successfully."})
    except StarlinkKit.DoesNotExist:
        return JsonResponse({"success": False, "message": "Kit not found."}, status=404)
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Unexpected error: {str(e)}"}, status=500
        )


@require_staff_role(["admin", "finance"])
@require_POST
def taxes_add(request):
    try:
        data = json.loads(request.body)
        description = data.get("description")
        percentage = data.get("percentage")

        if not description or percentage is None:
            return JsonResponse(
                {"success": False, "message": "Missing description or percentage."},
                status=400,
            )

        tax = TaxRate.objects.create(description=description, percentage=percentage)
        return JsonResponse(
            {
                "success": True,
                "message": "Tax rate added successfully.",
                "tax_id": tax.id,
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance", "manager"])
@require_GET
def taxes_list(request):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    taxes = TaxRate.objects.all().order_by("description")
    data = [
        {
            "id": tax.id,
            "description": tax.description,
            "percentage": float(tax.percentage),
        }
        for tax in taxes
    ]
    return JsonResponse({"success": True, "taxes": data})


@require_staff_role(["admin", "finance"])
@require_POST
def payments_method_add(request):
    try:
        data = json.loads(request.body)
        name = data.get("name")
        description = data.get("description")

        if not name or description is None:
            return JsonResponse(
                {"success": False, "message": "Missing description or name."},
                status=400,
            )

        method = PaymentMethod.objects.create(name=name, description=description)

        return JsonResponse(
            {
                "success": True,
                "message": "Payment method added successfully.",
                "name": method.name,
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance", "manager"])
@require_GET
def payments_method_list(request):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    methods = PaymentMethod.objects.all().order_by("name")
    data = [
        {
            "id": method.id,
            "name": method.name,
            "description": method.description,
        }
        for method in methods
    ]
    return JsonResponse({"success": True, "methods": data})


@require_staff_role(["admin", "manager"])
@require_POST
@csrf_protect
def region_add(request):
    # Check if it's an AJAX request
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    )
    if not is_ajax:
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    name = request.POST.get("name", "").strip()
    fence_data = request.POST.get("fence")

    if not name:
        return JsonResponse(
            {"success": False, "message": "Region name is required."}, status=400
        )

    if not fence_data:
        return JsonResponse(
            {"success": False, "message": "Region fence geometry is required."},
            status=400,
        )

    # Check if region already exists
    if Region.objects.filter(name__iexact=name).exists():
        return JsonResponse(
            {"success": False, "message": "Region with this name already exists."},
            status=400,
        )

    try:
        # Parse the fence geometry
        fence_geometry = None
        if isinstance(fence_data, str):
            fence_geometry = GEOSGeometry(fence_data)
        else:
            # If fence_data is already a dict (from JSON), convert to string first
            fence_geometry = GEOSGeometry(json.dumps(fence_data))

        # Ensure the geometry is a Polygon
        if fence_geometry.geom_type != "Polygon":
            return JsonResponse(
                {"success": False, "message": "Fence geometry must be a Polygon."},
                status=400,
            )

        region = Region.objects.create(name=name, fence=fence_geometry)
        return JsonResponse(
            {
                "success": True,
                "message": "Region added successfully.",
                "region": {
                    "id": region.id,
                    "name": region.name,
                },
            }
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid fence geometry JSON format."},
            status=400,
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Failed to add region: {str(e)}"}, status=500
        )


@require_staff_role(["admin", "manager"])
@require_GET
def region_list(request):
    # Accept standard AJAX header from either Django 4+ or older META
    is_ajax = (
        request.headers.get("x-requested-with") == "XMLHttpRequest"
        or request.META.get("HTTP_X_REQUESTED_WITH") == "XMLHttpRequest"
    )
    if not is_ajax:
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    regions = Region.objects.all().order_by("name")
    data = [
        {
            "id": r.id,
            "name": r.name,
        }
        for r in regions
    ]
    return JsonResponse({"success": True, "regions": data})


@require_staff_role(["admin", "finance"])
def taxes_detail(request, pk):
    """
    Handle GET, PUT, DELETE requests for a specific tax rate.
    """
    try:
        tax = TaxRate.objects.get(pk=pk)
    except TaxRate.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Tax rate not found"}, status=404
        )

    if request.method == "GET":
        # Return tax details
        return JsonResponse(
            {
                "success": True,
                "tax": {
                    "id": tax.id,
                    "description": tax.description,
                    "percentage": float(tax.percentage),
                },
            }
        )

    elif request.method == "PUT":
        # Update tax
        try:
            data = json.loads(request.body)
            description = data.get("description", "").strip()
            percentage = data.get("percentage")

            if not description or percentage is None:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Description and percentage are required.",
                    },
                    status=400,
                )

            tax.description = description
            tax.percentage = float(percentage)
            tax.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Tax rate updated successfully.",
                    "tax": {
                        "id": tax.id,
                        "description": tax.description,
                        "percentage": float(tax.percentage),
                    },
                }
            )

        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "message": "Invalid JSON data"}, status=400
            )
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    elif request.method == "DELETE":
        # Delete tax
        tax.delete()
        return JsonResponse(
            {"success": True, "message": "Tax rate deleted successfully."}
        )

    else:
        return JsonResponse(
            {"success": False, "message": "Method not allowed"}, status=405
        )


@require_staff_role(["admin", "finance", "manager"])
def taxes_choices(request):
    choices = [
        {"value": v, "label": l}
        for v, l in TaxRate._meta.get_field("description").choices
    ]
    return JsonResponse({"success": True, "choices": choices})


@require_staff_role(["admin", "finance"])
def payments_method_detail(request, pk):
    """
    Handle GET, PUT, DELETE requests for a specific payment method.
    """
    try:
        method = PaymentMethod.objects.get(pk=pk)
    except PaymentMethod.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Payment method not found"}, status=404
        )

    if request.method == "GET":
        # Return payment method details
        return JsonResponse(
            {
                "success": True,
                "method": {
                    "id": method.id,
                    "name": method.name,
                    "description": method.description,
                },
            }
        )

    elif request.method == "PUT":
        # Update payment method (only description can be changed)
        try:
            data = json.loads(request.body)
            description = data.get("description", "").strip()
            # name = data.get("name")  # Keep the original name

            if description is None:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Description is required.",
                    },
                    status=400,
                )

            method.description = description
            method.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Payment method updated successfully.",
                    "method": {
                        "id": method.id,
                        "name": method.name,
                        "description": method.description,
                    },
                }
            )

        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "message": "Invalid JSON data"}, status=400
            )
        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    elif request.method == "DELETE":
        # Delete payment method
        method.delete()
        return JsonResponse(
            {"success": True, "message": "Payment method deleted successfully."}
        )

    else:
        return JsonResponse(
            {"success": False, "message": "Method not allowed"}, status=405
        )


@require_staff_role(["admin", "finance"])
@require_POST
def installation_fee_add(request):
    try:
        data = json.loads(request.body)
        region_name = data.get("region", "").strip()
        amount_usd = data.get("amount_usd")

        if not region_name or amount_usd is None:
            return JsonResponse(
                {"success": False, "message": "Region and amount are required."},
                status=400,
            )

        # Validate amount
        try:
            amount_value = float(amount_usd)
            if amount_value < 0:
                return JsonResponse(
                    {"success": False, "message": "Amount must be positive."},
                    status=400,
                )
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "Invalid amount format."},
                status=400,
            )

        # Get or create the region
        try:
            region = Region.objects.get(name=region_name)
        except Region.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Region '{region_name}' does not exist.",
                },
                status=400,
            )

        fee = InstallationFee.objects.create(region=region, amount_usd=amount_value)

        return JsonResponse(
            {
                "success": True,
                "message": "Installation fee added successfully.",
                "fee": {
                    "id": fee.id,
                    "region": fee.region.name,  # Return region name
                    "amount_usd": float(fee.amount_usd),
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance", "manager"])
@require_GET
def installation_fee_choices(request):
    """
    Return list of available regions for installation fee dropdown.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    # Get all regions from Region model
    regions = Region.objects.all().order_by("name")
    choices = [{"value": region.name, "label": region.name} for region in regions]

    # If no regions exist, provide some default options
    if not choices:
        choices = [
            {"value": "Lubumbashi", "label": "Lubumbashi"},
            {"value": "Kinshasa", "label": "Kinshasa"},
            {"value": "Goma", "label": "Goma"},
            {"value": "Kisangani", "label": "Kisangani"},
            {"value": "Mbuji-Mayi", "label": "Mbuji-Mayi"},
        ]

    return JsonResponse({"success": True, "choices": choices})


@require_staff_role(["admin", "finance", "manager"])
@require_GET
def installation_fee_list(request):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    fees = InstallationFee.objects.all().order_by("region__name")
    data = [
        {
            "id": fee.id,
            "region": fee.region.name,  # Return region name
            "amount_usd": float(fee.amount_usd) if fee.amount_usd else None,
        }
        for fee in fees
    ]
    return JsonResponse({"success": True, "fees": data})


@require_staff_role(["admin", "finance"])
def installation_fee_detail(request, pk):
    """
    Handle GET, PUT, DELETE requests for a specific installation fee.
    """
    try:
        fee = InstallationFee.objects.get(pk=pk)
    except InstallationFee.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Installation fee not found"}, status=404
        )

    if request.method == "GET":
        return JsonResponse(
            {
                "success": True,
                "fee": {
                    "id": fee.id,
                    "region": fee.region.name,  # Return region name
                    "amount_usd": float(fee.amount_usd) if fee.amount_usd else None,
                },
            }
        )

    elif request.method == "PUT":
        return _update_installation_fee(fee, request)

    elif request.method == "DELETE":
        fee.delete()
        return JsonResponse(
            {"success": True, "message": "Installation fee deleted successfully."}
        )

    else:
        return JsonResponse(
            {"success": False, "message": "Method not allowed"}, status=405
        )


def _update_installation_fee(fee, request):
    """Helper function to update installation fee."""
    try:
        data = json.loads(request.body)
        region_name = data.get("region", "").strip()
        amount_usd = data.get("amount_usd")

        if not region_name or amount_usd is None:
            return JsonResponse(
                {"success": False, "message": "Region and amount are required."},
                status=400,
            )

        # Validate amount
        try:
            amount_value = float(amount_usd)
            if amount_value < 0:
                return JsonResponse(
                    {"success": False, "message": "Amount must be positive."},
                    status=400,
                )
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "Invalid amount format."}, status=400
            )

        # Get the region object
        try:
            region = Region.objects.get(name=region_name)
        except Region.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Region '{region_name}' does not exist.",
                },
                status=400,
            )

        fee.region = region
        fee.amount_usd = amount_value
        fee.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Installation fee updated successfully.",
                "fee": {
                    "id": fee.id,
                    "region": fee.region.name,  # Return region name
                    "amount_usd": float(fee.amount_usd),
                },
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance", "manager"])
def payment_choices(request):
    choices = [
        {"value": v, "label": l}
        for v, l in PaymentMethod._meta.get_field("name").choices
    ]
    return JsonResponse({"success": True, "choices": choices})


@require_staff_role(["admin", "manager"])
def starlink_kit_management(request):
    """
    View for Starlink Kit Management section.
    """
    return render(request, "partials/starlink_kit_management.html")


@require_staff_role(["admin", "manager", "sales", "dispatcher"])
def get_starlink_kits(request):
    """
    Get all Starlink kits for the management interface.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    kits = StarlinkKit.objects.all().order_by("name")

    data = []
    for kit in kits:
        data.append(
            {
                "id": kit.id,
                "name": kit.name,
                "model": kit.model,
                "description": kit.description,
                "price_usd": str(kit.base_price_usd) if kit.base_price_usd else "",
            }
        )

    return JsonResponse({"kits": data})


@require_staff_role(["admin", "manager"])
@require_POST
def add_starlink_kit(request):
    """
    Add a new Starlink kit.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    name = request.POST.get("name", "").strip()
    model = request.POST.get("model", "").strip()
    kit_type = request.POST.get("kit_type", "").strip()
    description = request.POST.get("description", "").strip()
    price_usd = request.POST.get("price_usd", "").strip()
    picture = request.FILES.get("picture")

    if not name or not model or not kit_type:
        return JsonResponse(
            {"success": False, "message": "Name, Model, and Kit Type are required."},
            status=400,
        )

    # Parse price if provided
    price = None
    if price_usd:
        try:
            price = Decimal(price_usd)
            if price < 0:
                return JsonResponse(
                    {"success": False, "message": "Price must be positive."}, status=400
                )
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "Invalid price format."}, status=400
            )

    try:
        kit = StarlinkKit.objects.create(
            name=name,
            model=model,
            kit_type=kit_type,
            description=description or None,
            base_price_usd=price,
            picture=picture,
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Starlink kit added successfully.",
                "kit": {
                    "id": kit.id,
                    "name": kit.name,
                    "model": kit.model,
                    "kit_type": kit.kit_type,
                    "description": kit.description or "",
                    "price_usd": str(kit.base_price_usd) if kit.base_price_usd else "",
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "manager", "sales", "dispatcher"])
def get_starlink_kit(request, pk):
    """
    Get a specific Starlink kit for editing.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        kit = StarlinkKit.objects.get(pk=pk)
        return JsonResponse(
            {
                "success": True,
                "kit": {
                    "id": kit.id,
                    "name": kit.name,
                    "model": kit.model,
                    "description": kit.description,
                    "price_usd": (
                        float(kit.base_price_usd) if kit.base_price_usd else None
                    ),
                },
            }
        )
    except StarlinkKit.DoesNotExist:
        return JsonResponse({"success": False, "message": "Kit not found"}, status=404)


@require_staff_role(["admin", "manager"])
@require_POST
def edit_starlink_kit(request, pk):
    """
    Edit an existing Starlink kit.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        kit = StarlinkKit.objects.get(pk=pk)

        name = request.POST.get("name", "").strip()
        model = request.POST.get("model", "").strip()
        description = request.POST.get("description", "").strip()
        price_usd = request.POST.get("price_usd", "").strip()
        picture = request.FILES.get("picture")

        if not name or not model:
            return JsonResponse(
                {"success": False, "message": "Name and Model are required."},
                status=400,
            )

        # Parse price if provided
        price = None
        if price_usd:
            try:
                price = Decimal(price_usd)
                if price < 0:
                    return JsonResponse(
                        {"success": False, "message": "Price must be positive."},
                        status=400,
                    )
            except (ValueError, TypeError):
                return JsonResponse(
                    {"success": False, "message": "Invalid price format."}, status=400
                )

        # Handle picture replacement
        if picture:
            if kit.picture:
                # Delete the old file from storage
                if default_storage.exists(kit.picture.name):
                    default_storage.delete(kit.picture.name)
            kit.picture = picture

        kit.name = name
        kit.model = model
        kit.description = description or None
        kit.base_price_usd = price
        kit.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Starlink kit updated successfully.",
                "kit": {
                    "id": kit.id,
                    "name": kit.name,
                    "model": kit.model,
                    "description": kit.description or "",
                    "price_usd": str(kit.base_price_usd) if kit.base_price_usd else "",
                },
            }
        )

    except StarlinkKit.DoesNotExist:
        return JsonResponse({"success": False, "message": "Kit not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "manager"])
def subscription_plan_management(request):
    """
    View for Subscription Plan Management section.
    """
    return render(request, "partials/subscription_plan_management.html")


@require_staff_role(["admin", "manager", "sales"])
def get_subscription_plans(request):
    """
    Get all subscription plans for the management interface (legacy - without pagination).
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    plans = SubscriptionPlan.objects.all().order_by("name")

    data = []
    for plan in plans:
        data.append(
            {
                "id": plan.id,
                "name": plan.name,
                "kit_type": plan.kit_type,
                "plan_type": plan.plan_type,
                "data_cap_gb": plan.standard_data_gb,
                "monthly_price_usd": (
                    str(plan.monthly_price_usd) if plan.monthly_price_usd else ""
                ),
                "description": plan.category_description or "",
                "is_active": plan.is_active,
            }
        )

    return JsonResponse({"plans": data})


@require_staff_role(["admin", "manager", "sales"])
def get_subscription_plans_paginated(request):
    """
    Get subscription plans with pagination support for better performance.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    # Pagination parameters
    try:
        page = int(request.GET.get("page", 1))
        per_page = int(request.GET.get("per_page", 10))

        # Validate parameters
        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:  # Limit max items per page
            per_page = 10

    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid pagination parameters"}, status=400)

    # Calculate offset
    offset = (page - 1) * per_page

    # Get plans with pagination
    plans_queryset = SubscriptionPlan.objects.all().order_by("name")
    total_plans = plans_queryset.count()

    # Apply pagination
    plans = plans_queryset[offset : offset + per_page]

    # Prepare data
    data = []
    for plan in plans:
        data.append(
            {
                "id": plan.id,
                "name": plan.name,
                "kit_type": plan.kit_type,
                "plan_type": plan.plan_type,
                "data_cap_gb": plan.standard_data_gb,
                "monthly_price_usd": (
                    str(plan.monthly_price_usd) if plan.monthly_price_usd else ""
                ),
                "description": plan.category_description or "",
                "is_active": plan.is_active,
                "site_type": plan.site_type or "",
                "site_type_display": plan.get_site_type_display(),
            }
        )

    # Pagination metadata
    total_pages = (total_plans + per_page - 1) // per_page

    return JsonResponse(
        {
            "plans": data,
            "pagination": {
                "current_page": page,
                "total_pages": total_pages,
                "total_items": total_plans,
                "per_page": per_page,
                "has_next": page < total_pages,
                "has_previous": page > 1,
                "next_page": page + 1 if page < total_pages else None,
                "previous_page": page - 1 if page > 1 else None,
            },
        }
    )


@require_staff_role(["admin", "manager"])
@require_POST
def add_subscription_plan(request):
    """
    Add a new subscription plan.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    # Parse JSON data from request body
    try:
        data = json.loads(request.body)
        print(data)
        print("#" * 50)
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )

    name = data.get("name", "").strip()
    kit_type = data.get("kit_type", "").strip()
    plan_type = data.get("plan_type")
    if plan_type is None or plan_type == "":
        plan_type = None
    elif isinstance(plan_type, str):
        plan_type = plan_type.strip() or None
    else:
        plan_type = str(plan_type).strip() or None
    data_gb = data.get("data_gb")
    if data_gb is None:
        data_gb = ""
    elif isinstance(data_gb, str):
        data_gb = data_gb.strip()
    else:
        data_gb = str(data_gb).strip()
    price_usd = data.get("price_usd", "").strip()
    description = data.get("description", "").strip()
    site_type = data.get("site_type", "").strip()

    if not name or not kit_type or not price_usd or not site_type:
        return JsonResponse(
            {
                "success": False,
                "message": "Name, Kit Type, Price, and Site Type are required.",
            },
            status=400,
        )

    # Parse price
    try:
        price = Decimal(price_usd)
        if price < 0:
            return JsonResponse(
                {"success": False, "message": "Price must be positive."}, status=400
            )
    except (ValueError, TypeError):
        return JsonResponse(
            {"success": False, "message": "Invalid price format."}, status=400
        )

    # Parse data cap if provided
    data_cap = None
    if data_gb:
        try:
            data_cap = int(data_gb)
            if data_cap < 0:
                return JsonResponse(
                    {"success": False, "message": "Data cap must be positive."},
                    status=400,
                )
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "Invalid data cap format."}, status=400
            )

    try:
        # Determine category name based on kit_type
        category_name = (
            "Standard Category" if kit_type == "standard" else "Mini Category"
        )

        plan = SubscriptionPlan.objects.create(
            name=name,
            category_name=category_name,
            category_description=description,
            category_is_active=True,
            plan_type=plan_type or None,
            standard_data_gb=data_cap,
            monthly_price_usd=price,
            site_type=site_type,
            # description=description or None,
            is_active=True,  # New plans are active by default
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Subscription plan added successfully.",
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "kit_type": plan.kit_type,
                    "plan_type": plan.plan_type or "",
                    "data_cap_gb": plan.standard_data_gb,
                    "monthly_price_usd": str(plan.monthly_price_usd),
                    "description": plan.category_description or "",
                    "is_active": plan.is_active,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "manager", "sales"])
def get_subscription_plan(request, pk):
    """
    Get a specific subscription plan for editing.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        plan = SubscriptionPlan.objects.get(pk=pk)
        return JsonResponse(
            {
                "success": True,
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "kit_type": plan.kit_type,
                    "plan_type": plan.plan_type or "",
                    "data_cap_gb": plan.standard_data_gb,
                    "monthly_price_usd": (
                        float(plan.monthly_price_usd)
                        if plan.monthly_price_usd
                        else None
                    ),
                    "description": plan.category_description or "",
                    "is_active": plan.is_active,
                    "category_name": plan.category_name,
                    "category_description": plan.category_description or "",
                    "category_is_active": plan.category_is_active,
                    "site_type": getattr(plan, "site_type", ""),
                },
            }
        )
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({"success": False, "message": "Plan not found"}, status=404)


@require_staff_role(["admin", "manager"])
def edit_subscription_plan(request, pk):
    """
    Handle GET (get plan data) and POST (edit plan) requests for subscription plans.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        plan = SubscriptionPlan.objects.get(pk=pk)
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({"success": False, "message": "Plan not found"}, status=404)

    if request.method == "GET":
        # Return plan data for editing
        return JsonResponse(
            {
                "success": True,
                "plan": {
                    "id": plan.id,
                    "name": plan.name,
                    "kit_type": plan.kit_type,
                    "plan_type": plan.plan_type or "",
                    "data_cap_gb": plan.standard_data_gb,
                    "monthly_price_usd": (
                        float(plan.monthly_price_usd)
                        if plan.monthly_price_usd
                        else None
                    ),
                    "description": plan.category_description or "",
                    "is_active": plan.is_active,
                    "category_name": plan.category_name,
                    "category_description": plan.category_description or "",
                    "category_is_active": plan.category_is_active,
                    "site_type": plan.site_type or "",
                },
            }
        )

    elif request.method == "POST":
        # Support both form and JSON requests
        if request.content_type == "application/json":
            import json

            try:
                data = json.loads(request.body)

                logger.info(f"Editing subscription plan {pk}: {data}")

            except Exception:
                return JsonResponse(
                    {"success": False, "message": "Invalid JSON."}, status=400
                )
            name = data.get("name", "").strip()
            kit_type = data.get("kit_type", "").strip()
            plan_type = data.get("plan_type", "").strip()
            data_gb = data.get("standard_data_gb")
            if data_gb is None:
                data_gb = ""
            else:
                data_gb = str(data_gb).strip()
            price_usd = data.get("price_usd", "").strip()
            description = data.get("description", "").strip()
            site_type = data.get("site_type", "").strip()
            is_active = data.get("is_active", True)  # Default to True if not provided
        else:
            name = request.POST.get("name", "").strip()
            kit_type = request.POST.get("kit_type", "").strip()
            plan_type = request.POST.get("plan_type", "").strip()
            data_gb = request.POST.get("standard_data_gb", "").strip()
            price_usd = request.POST.get("price_usd", "").strip()
            description = request.POST.get("description", "").strip()
            site_type = request.POST.get("site_type", "").strip()
            is_active = request.POST.get("is_active") == "true"  # Handle checkbox

        # Debug logging
        logger.info(
            f"Processing edit for plan {pk}: name='{name}', kit_type='{kit_type}', price_usd='{price_usd}', site_type='{site_type}', description='{description}'"
        )

        # Validate required fields (provide defaults for missing ones to avoid 500 errors)
        if not name:
            return JsonResponse(
                {"success": False, "message": "Name is required."},
                status=400,
            )
        if not kit_type:
            return JsonResponse(
                {"success": False, "message": "Kit Type is required."},
                status=400,
            )
        if not price_usd:
            return JsonResponse(
                {"success": False, "message": "Price is required."},
                status=400,
            )

        # Provide defaults for missing fields
        if not site_type:
            site_type = "fixed"  # Default value
            logger.warning(
                f"site_type not provided for plan {pk}, using default: {site_type}"
            )
        if not description:
            description = ""  # Can be empty

        # Parse price
        try:
            price = Decimal(price_usd)
            if price < 0:
                return JsonResponse(
                    {"success": False, "message": "Price must be positive."}, status=400
                )
        except (ValueError, TypeError):
            return JsonResponse(
                {"success": False, "message": "Invalid price format."}, status=400
            )

        # Parse data cap if provided
        data_cap = None
        if data_gb:
            try:
                data_cap = int(data_gb)
                if data_cap < 0:
                    return JsonResponse(
                        {"success": False, "message": "Data cap must be positive."},
                        status=400,
                    )
            except (ValueError, TypeError):
                return JsonResponse(
                    {"success": False, "message": "Invalid data cap format."},
                    status=400,
                )

        # Update the plan
        try:
            # Determine category name based on kit_type
            category_name = (
                "Standard Category" if kit_type == "standard" else "Mini Category"
            )

            plan.name = name
            plan.category_name = category_name
            plan.category_description = description or ""
            plan.category_is_active = True
            plan.plan_type = plan_type or None
            plan.standard_data_gb = data_cap
            plan.monthly_price_usd = price
            plan.site_type = site_type
            plan.is_active = is_active
            plan.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Subscription plan updated successfully.",
                    "plan": {
                        "id": plan.id,
                        "name": plan.name,
                        "kit_type": plan.kit_type,
                        "plan_type": plan.plan_type or "",
                        "data_cap_gb": plan.standard_data_gb,
                        "monthly_price_usd": str(plan.monthly_price_usd),
                        "description": plan.category_description or "",
                        "is_active": plan.is_active,
                        "site_type": plan.site_type or "",
                    },
                }
            )
        except Exception as e:
            logger.error(f"Error updating subscription plan: {str(e)}", exc_info=True)
            return JsonResponse(
                {"success": False, "message": "Internal server error"}, status=500
            )

    else:
        return JsonResponse(
            {"success": False, "message": "Method not allowed"}, status=405
        )


@require_staff_role(["admin"])
@require_POST
def toggle_subscription_plan_status(request, pk):
    """
    Toggle the active status of a subscription plan.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        plan = SubscriptionPlan.objects.get(pk=pk)
        plan.is_active = not plan.is_active
        plan.save()

        status_text = "activated" if plan.is_active else "deactivated"
        return JsonResponse(
            {
                "success": True,
                "message": f"Subscription plan {status_text} successfully.",
                "is_active": plan.is_active,
            }
        )
    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({"success": False, "message": "Plan not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin"])
@require_POST
def delete_subscription_plan(request, pk):
    """
    Delete a subscription plan.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        plan = SubscriptionPlan.objects.get(pk=pk)

        # Check if plan is being used by any orders or subscriptions
        from main.models import Order, Subscription

        active_orders = Order.objects.filter(plan=plan).exists()
        active_subscriptions = Subscription.objects.filter(plan=plan).exists()

        if active_orders or active_subscriptions:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cannot delete plan that is being used by existing orders or subscriptions.",
                },
                status=400,
            )

        plan_name = plan.name
        plan.delete()

        return JsonResponse(
            {
                "success": True,
                "message": f"Subscription plan '{plan_name}' deleted successfully.",
            }
        )

    except SubscriptionPlan.DoesNotExist:
        return JsonResponse({"success": False, "message": "Plan not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin"])
@require_POST
def delete_starlink_kit(request, pk):
    """
    Delete a Starlink kit.
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        kit = StarlinkKit.objects.get(pk=pk)

        # Check if kit is being used by any orders
        from main.models import Order

        active_orders = Order.objects.filter(kit_inventory__kit=kit).exists()

        if active_orders:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cannot delete kit that is being used by existing orders.",
                },
                status=400,
            )

        kit_name = kit.name

        # Delete associated picture if exists
        if kit.picture and default_storage.exists(kit.picture.name):
            default_storage.delete(kit.picture.name)

        kit.delete()

        return JsonResponse(
            {
                "success": True,
                "message": f"Starlink kit '{kit_name}' deleted successfully.",
            }
        )

    except StarlinkKit.DoesNotExist:
        return JsonResponse({"success": False, "message": "Kit not found"}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


# ===== Site Survey Checklist Management =====


@require_staff_role(["admin", "manager", "technician"])
def get_site_survey_checklist(request):
    """Get paginated list of site survey checklist items"""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    checklist_items = SiteSurveyChecklist.objects.all().order_by(
        "category", "display_order"
    )

    paginator = Paginator(checklist_items, 10)  # Show 10 items per page

    page_number = request.GET.get("page", 1)
    try:
        items_page = paginator.page(page_number)
    except PageNotAnInteger:
        items_page = paginator.page(1)
    except EmptyPage:
        items_page = paginator.page(paginator.num_pages)

    data = []
    for item in items_page:
        data.append(
            {
                "id": item.id,
                "category": item.category,
                "category_display": item.get_category_display(),
                "question": item.question,
                "question_type": item.question_type,
                "question_type_display": item.get_question_type_display(),
                "choices": item.choices,
                "is_required": item.is_required,
                "display_order": item.display_order,
                "is_active": item.is_active,
            }
        )

    return JsonResponse(
        {
            "checklist_items": data,
            "pagination": {
                "has_next": items_page.has_next(),
                "has_previous": items_page.has_previous(),
                "page_number": items_page.number,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
            },
        }
    )


@require_staff_role(["admin", "manager"])
@require_POST
@csrf_protect
def create_checklist_item(request):
    """Create a new checklist item"""
    logger.info(
        f"create_checklist_item called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "create_checklist_item: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        logger.info(f"create_checklist_item: Received data: {data}")

        # Extract data from request
        category = data.get("category")
        question = data.get("question")
        question_type = data.get("question_type")
        choices = data.get("choices")
        is_required = data.get("is_required", True)
        display_order = data.get("display_order", 0)
        is_active = data.get("is_active", True)

        # Validate required fields
        if not all([category, question, question_type]):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Category, question, and question type are required.",
                },
                status=400,
            )

        # Process choices for multiple choice questions
        choices_list = None
        if question_type == "multiple_choice" and choices:
            choices_list = [
                choice.strip() for choice in choices.split(",") if choice.strip()
            ]
            if not choices_list:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "At least one choice is required for multiple choice questions.",
                    },
                    status=400,
                )

        # Create the checklist item
        checklist_item = SiteSurveyChecklist.objects.create(
            category=category,
            question=question,
            question_type=question_type,
            choices=choices_list,
            is_required=bool(is_required),
            display_order=int(display_order),
            is_active=bool(is_active),
        )

        logger.info(f"create_checklist_item: Created item with ID {checklist_item.id}")

        return JsonResponse(
            {
                "success": True,
                "message": f"Checklist item '{question[:50]}...' created successfully.",
                "checklist_item": {
                    "id": checklist_item.id,
                    "category": checklist_item.category,
                    "category_display": checklist_item.get_category_display(),
                    "question": checklist_item.question,
                    "question_type": checklist_item.question_type,
                    "question_type_display": checklist_item.get_question_type_display(),
                    "choices": checklist_item.choices,
                    "is_required": checklist_item.is_required,
                    "display_order": checklist_item.display_order,
                    "is_active": checklist_item.is_active,
                },
            }
        )

    except json.JSONDecodeError:
        logger.error("create_checklist_item: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"create_checklist_item: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "manager"])
@require_POST
@csrf_protect
def update_checklist_item(request):
    """Update an existing checklist item"""
    logger.info(
        f"update_checklist_item called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "update_checklist_item: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        logger.info(f"update_checklist_item: Received data: {data}")

        # Extract data from request
        checklist_id = data.get("checklist_id")
        category = data.get("category")
        question = data.get("question")
        question_type = data.get("question_type")
        choices = data.get("choices")
        is_required = data.get("is_required", True)
        display_order = data.get("display_order", 0)
        is_active = data.get("is_active", True)

        # Validate required fields
        if not all([checklist_id, category, question, question_type]):
            return JsonResponse(
                {
                    "success": False,
                    "message": "ID, category, question, and question type are required.",
                },
                status=400,
            )

        # Get the checklist item
        try:
            checklist_item = SiteSurveyChecklist.objects.get(id=checklist_id)
        except SiteSurveyChecklist.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Checklist item not found."}, status=404
            )

        # Process choices for multiple choice questions
        choices_list = None
        if question_type == "multiple_choice" and choices:
            choices_list = [
                choice.strip() for choice in choices.split(",") if choice.strip()
            ]
            if not choices_list:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "At least one choice is required for multiple choice questions.",
                    },
                    status=400,
                )

        # Update the checklist item
        checklist_item.category = category
        checklist_item.question = question
        checklist_item.question_type = question_type
        checklist_item.choices = choices_list
        checklist_item.is_required = bool(is_required)
        checklist_item.display_order = int(display_order)
        checklist_item.is_active = bool(is_active)
        checklist_item.save()

        logger.info(f"update_checklist_item: Updated item with ID {checklist_item.id}")

        return JsonResponse(
            {
                "success": True,
                "message": f"Checklist item '{question[:50]}...' updated successfully.",
                "checklist_item": {
                    "id": checklist_item.id,
                    "category": checklist_item.category,
                    "category_display": checklist_item.get_category_display(),
                    "question": checklist_item.question,
                    "question_type": checklist_item.question_type,
                    "question_type_display": checklist_item.get_question_type_display(),
                    "choices": checklist_item.choices,
                    "is_required": checklist_item.is_required,
                    "display_order": checklist_item.display_order,
                    "is_active": checklist_item.is_active,
                },
            }
        )

    except json.JSONDecodeError:
        logger.error("update_checklist_item: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"update_checklist_item: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin"])
@require_POST
@csrf_protect
def delete_checklist_item(request):
    """Delete a checklist item"""
    logger.info(
        f"delete_checklist_item called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "delete_checklist_item: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        checklist_id = data.get("checklist_id")

        if not checklist_id:
            return JsonResponse(
                {"success": False, "message": "Checklist item ID is required."},
                status=400,
            )

        # Get and delete the checklist item
        try:
            checklist_item = SiteSurveyChecklist.objects.get(id=checklist_id)
            question = checklist_item.question[:50]
            checklist_item.delete()

            logger.info(f"delete_checklist_item: Deleted item with ID {checklist_id}")

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Checklist item '{question}...' deleted successfully.",
                }
            )

        except SiteSurveyChecklist.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Checklist item not found."}, status=404
            )

    except json.JSONDecodeError:
        logger.error("delete_checklist_item: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"delete_checklist_item: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


# ===== Extra Charges Management =====


@require_staff_role(["admin", "finance", "manager"])
def get_extra_charges(request):
    """Get paginated list of extra charges"""
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    extra_charges = ExtraCharge.objects.all().order_by(
        "cost_type", "display_order", "item_name"
    )
    paginator = Paginator(extra_charges, 10)  # Show 10 items per page

    page_number = request.GET.get("page", 1)
    try:
        items_page = paginator.page(page_number)
    except PageNotAnInteger:
        items_page = paginator.page(1)
    except EmptyPage:
        items_page = paginator.page(paginator.num_pages)

    data = []
    for item in items_page:
        data.append(
            {
                "id": item.id,
                "cost_type": item.cost_type,
                "cost_type_display": item.get_cost_type_display(),
                "item_name": item.item_name,
                "description": item.description,
                "brand": item.brand,
                "model": item.model,
                "unit_price": str(item.unit_price),
                "is_active": item.is_active,
                "display_order": item.display_order,
                "specifications": item.specifications,
            }
        )

    return JsonResponse(
        {
            "extra_charges": data,
            "pagination": {
                "has_next": items_page.has_next(),
                "has_previous": items_page.has_previous(),
                "page_number": items_page.number,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
            },
        }
    )


@require_staff_role(["admin", "finance"])
@require_POST
@csrf_protect
def update_extra_charge(request):
    """Update an existing extra charge"""
    logger.info(
        f"update_extra_charge called for user: {request.user.username if request.user else 'Anonymous'}"
    )

    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        logger.warning(
            "update_extra_charge: Invalid request type - not an AJAX request"
        )
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        logger.info(f"update_extra_charge: Received data: {data}")

        # Extract data from request
        extracharge_id = data.get("extracharge_id")
        cost_type = data.get("cost_type")
        item_name = data.get("item_name")
        description = data.get("description", "")
        brand = data.get("brand", "")
        model = data.get("model", "")
        unit_price = data.get("unit_price")
        is_active = data.get("is_active", True)
        display_order = data.get("display_order", 0)

        # Validate required fields
        if not all([extracharge_id, cost_type, item_name, unit_price]):
            return JsonResponse(
                {
                    "success": False,
                    "message": "ID, cost type, item name, and unit price are required.",
                },
                status=400,
            )

        # Get the extra charge
        try:
            extra_charge = ExtraCharge.objects.get(id=extracharge_id)
        except ExtraCharge.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Extra charge not found."}, status=404
            )

        # Validate unit price
        try:
            unit_price = Decimal(str(unit_price))
            if unit_price < 0:
                return JsonResponse(
                    {"success": False, "message": "Unit price must be positive."},
                    status=400,
                )
        except (ValueError, InvalidOperation):
            return JsonResponse(
                {"success": False, "message": "Invalid unit price format."}, status=400
            )

        # Check for duplicate item names (excluding current item)
        if (
            ExtraCharge.objects.filter(item_name=item_name)
            .exclude(id=extracharge_id)
            .exists()
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": "An extra charge with this item name already exists.",
                },
                status=400,
            )

        # Update the extra charge
        extra_charge.cost_type = cost_type
        extra_charge.item_name = item_name
        extra_charge.description = description
        extra_charge.brand = brand
        extra_charge.model = model
        extra_charge.unit_price = unit_price
        extra_charge.is_active = bool(is_active)
        extra_charge.display_order = int(display_order)
        extra_charge.save()

        logger.info(f"update_extra_charge: Updated item with ID {extra_charge.id}")

        return JsonResponse(
            {
                "success": True,
                "message": f"Extra charge '{item_name}' updated successfully.",
                "extra_charge": {
                    "id": extra_charge.id,
                    "cost_type": extra_charge.cost_type,
                    "cost_type_display": extra_charge.get_cost_type_display(),
                    "item_name": extra_charge.item_name,
                    "description": extra_charge.description,
                    "brand": extra_charge.brand,
                    "model": extra_charge.model,
                    "unit_price": str(extra_charge.unit_price),
                    "is_active": extra_charge.is_active,
                    "display_order": extra_charge.display_order,
                },
            }
        )

    except json.JSONDecodeError:
        logger.error("update_extra_charge: Invalid JSON data")
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"update_extra_charge: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)

        return JsonResponse({"success": False, "message": str(e)}, status=500)


# Additional Billing Management Views
@require_staff_role(["admin", "finance"])
def additional_billings_management(request):
    """Admin interface for managing additional billings"""
    template = "app_settings/additional_billings_management.html"
    return render(request, template)


@require_staff_role(["admin", "manager", "finance"])
@require_GET
def get_additional_billings(request):
    """Get paginated list of additional billings"""
    try:
        from site_survey.models import AdditionalBilling

        # Get filter parameters
        status_filter = request.GET.get("status", "")
        search_query = request.GET.get("search", "")
        page = int(request.GET.get("page", 1))
        per_page = int(request.GET.get("per_page", 20))

        # Build query
        billings = AdditionalBilling.objects.select_related(
            "survey", "order", "customer"
        ).all()

        # Apply filters
        if status_filter:
            billings = billings.filter(status=status_filter)

        if search_query:
            from django.db import models

            billings = billings.filter(
                models.Q(billing_reference__icontains=search_query)
                | models.Q(order__order_reference__icontains=search_query)
                | models.Q(customer__full_name__icontains=search_query)
            )

        # Order by creation date
        billings = billings.order_by("-created_at")

        # Paginate
        paginator = Paginator(billings, per_page)
        page_obj = paginator.get_page(page)

        # Prepare data
        billings_data = []
        for billing in page_obj:
            billings_data.append(
                {
                    "id": billing.id,
                    "billing_reference": billing.billing_reference,
                    "order_reference": billing.order.order_reference,
                    "customer_name": billing.customer.full_name
                    or billing.customer.username,
                    "customer_email": billing.customer.email,
                    "total_amount": float(billing.total_amount),
                    "status": billing.status,
                    "status_display": billing.get_status_display(),
                    "created_at": billing.created_at.strftime("%Y-%m-%d %H:%M"),
                    "sent_for_approval_at": (
                        billing.sent_for_approval_at.strftime("%Y-%m-%d %H:%M")
                        if billing.sent_for_approval_at
                        else None
                    ),
                    "approved_at": (
                        billing.approved_at.strftime("%Y-%m-%d %H:%M")
                        if billing.approved_at
                        else None
                    ),
                    "paid_at": (
                        billing.paid_at.strftime("%Y-%m-%d %H:%M")
                        if billing.paid_at
                        else None
                    ),
                    "survey_id": billing.survey.id,
                    "expires_at": (
                        billing.expires_at.strftime("%Y-%m-%d %H:%M")
                        if billing.expires_at
                        else None
                    ),
                    "is_expired": (
                        billing.is_expired()
                        if hasattr(billing, "is_expired")
                        else False
                    ),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "billings": billings_data,
                "pagination": {
                    "current_page": page_obj.number,
                    "total_pages": paginator.num_pages,
                    "total_items": paginator.count,
                    "has_next": page_obj.has_next(),
                    "has_previous": page_obj.has_previous(),
                },
            }
        )

    except Exception as e:
        logger.error(f"get_additional_billings: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance"])
@require_POST
@csrf_protect
def generate_survey_billing(request):
    """Generate additional billing for a completed survey"""
    try:
        data = json.loads(request.body)
        survey_id = data.get("survey_id")

        if not survey_id:
            return JsonResponse(
                {"success": False, "message": "Survey ID is required."}, status=400
            )

        from django.shortcuts import get_object_or_404

        from site_survey.models import AdditionalBilling, SiteSurvey

        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Validate survey state
        if survey.status != "approved":
            return JsonResponse(
                {"success": False, "message": "Survey must be approved first."},
                status=400,
            )

        if not survey.requires_additional_equipment:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Survey doesn't require additional equipment.",
                },
                status=400,
            )

        # Check if billing already exists
        if hasattr(survey, "additional_billing"):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Billing already exists for this survey.",
                },
                status=400,
            )

        # Create billing
        from django.utils import timezone

        billing = AdditionalBilling.objects.create(
            survey=survey,
            order=survey.order,
            customer=survey.order.user,
            expires_at=timezone.now() + timezone.timedelta(days=7),
            status="pending_approval",
        )

        # Send notification to customer
        try:
            from site_survey.notifications import send_billing_notification

            send_billing_notification(billing)
        except Exception as e:
            logger.warning(f"Failed to send billing notification: {e}")

        return JsonResponse(
            {
                "success": True,
                "message": "Additional billing generated successfully.",
                "billing_reference": billing.billing_reference,
                "total_amount": float(billing.total_amount),
                "approval_url": f"/site-survey/billing/approval/{billing.id}/",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"generate_survey_billing: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance"])
@require_POST
@csrf_protect
def update_billing_status(request):
    """Update billing status manually (admin action)"""
    try:
        data = json.loads(request.body)
        billing_id = data.get("billing_id")
        new_status = data.get("status")
        admin_notes = data.get("admin_notes", "")

        if not billing_id or not new_status:
            return JsonResponse(
                {"success": False, "message": "Billing ID and status are required."},
                status=400,
            )

        from django.shortcuts import get_object_or_404

        from site_survey.models import AdditionalBilling

        billing = get_object_or_404(AdditionalBilling, id=billing_id)

        # Validate status transition
        valid_statuses = [
            "draft",
            "pending_approval",
            "approved",
            "rejected",
            "paid",
            "cancelled",
        ]
        if new_status not in valid_statuses:
            return JsonResponse(
                {"success": False, "message": "Invalid status."}, status=400
            )

        old_status = billing.status
        billing.status = new_status
        billing.admin_notes = admin_notes
        billing.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Billing status updated from {old_status} to {new_status}.",
                "old_status": old_status,
                "new_status": new_status,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data."}, status=400
        )
    except Exception as e:
        logger.error(f"update_billing_status: Unexpected error: {str(e)}")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@require_staff_role(["admin", "finance"])
@require_GET
def billing_config_get(request):
    cfg = BillingConfig.get()
    return JsonResponse(
        {
            "anchor_day": cfg.anchor_day,
            "prebill_lead_days": cfg.prebill_lead_days,
            "invoice_start_date": cfg.invoice_start_date.isoformat()
            if cfg.invoice_start_date
            else None,
            "cutoff_days_before_anchor": cfg.cutoff_days_before_anchor,
            "auto_suspend_on_cutoff": cfg.auto_suspend_on_cutoff,
            "auto_apply_wallet": cfg.auto_apply_wallet,
            "align_first_cycle_to_anchor": cfg.align_first_cycle_to_anchor,
            "first_cycle_included_in_order": cfg.first_cycle_included_in_order,
            "success": True,
        }
    )


@require_staff_role(["admin"])
@require_POST
def billing_config_save(request):
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return HttpResponseBadRequest("Invalid JSON")

    # robust parsers (accept numbers/strings)
    def _int(name, lo, hi, default):
        raw = payload.get(name, default)
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise ValueError(f"{name} must be an integer")
        if not (lo <= val <= hi):
            raise ValueError(f"{name} must be between {lo} and {hi}")
        return val

    def _bool(name, default):
        raw = payload.get(name, default)
        if isinstance(raw, bool):
            return raw
        if isinstance(raw, str):
            s = raw.strip().lower()
            if s in ("true", "1", "yes", "on"):
                return True
            if s in ("false", "0", "no", "off"):
                return False
        raise ValueError(f"{name} must be a boolean")

    def _date_or_none(name):
        raw = payload.get(name)
        if raw in (None, "", "null"):
            return None
        if isinstance(raw, date):
            return raw
        if isinstance(raw, str):
            try:
                return datetime.strptime(raw, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError(f"{name} must be YYYY-MM-DD")
        raise ValueError(f"{name} must be YYYY-MM-DD or null")

    cfg = BillingConfig.get()
    try:
        cfg.anchor_day = _int("anchor_day", 1, 28, cfg.anchor_day)
        cfg.prebill_lead_days = _int("prebill_lead_days", 0, 30, cfg.prebill_lead_days)

        # 🔧 Parse date string -> date (or None)
        cfg.invoice_start_date = _date_or_none("invoice_start_date")

        cfg.cutoff_days_before_anchor = _int(
            "cutoff_days_before_anchor", 0, 30, cfg.cutoff_days_before_anchor
        )
        cfg.auto_suspend_on_cutoff = _bool(
            "auto_suspend_on_cutoff", cfg.auto_suspend_on_cutoff
        )
        cfg.auto_apply_wallet = _bool("auto_apply_wallet", cfg.auto_apply_wallet)
        cfg.align_first_cycle_to_anchor = _bool(
            "align_first_cycle_to_anchor", cfg.align_first_cycle_to_anchor
        )
        cfg.first_cycle_included_in_order = _bool(
            "first_cycle_included_in_order", cfg.first_cycle_included_in_order
        )

        cfg.save()
        # Optional: ensure Python types (DateField returns date on fresh fetch)
        # cfg.refresh_from_db(fields=["invoice_start_date"])
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)

    return JsonResponse(
        {
            "success": True,
            "message": "Saved",
            "anchor_day": cfg.anchor_day,
            "prebill_lead_days": cfg.prebill_lead_days,
            "invoice_start_date": cfg.invoice_start_date.isoformat()
            if cfg.invoice_start_date
            else None,
            "cutoff_days_before_anchor": cfg.cutoff_days_before_anchor,
            "auto_suspend_on_cutoff": cfg.auto_suspend_on_cutoff,
            "auto_apply_wallet": cfg.auto_apply_wallet,
            "align_first_cycle_to_anchor": cfg.align_first_cycle_to_anchor,
            "first_cycle_included_in_order": cfg.first_cycle_included_in_order,
        }
    )


def _json(request: HttpRequest):
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


@require_staff_role(["admin", "manager", "sales"])
@require_GET
def coupon_list(request: HttpRequest):
    qs = Coupon.objects.annotate(redemptions_count=Count("redemptions")).order_by(
        "-created_at"
    )

    data = []
    for c in qs:
        data.append(
            {
                "id": str(c.id),
                "code": c.code,
                # discount fields
                "discount_type": c.discount_type,  # "percent" | "amount"
                "percent_off": str(
                    c.percent_off or Decimal("0")
                ),  # keep as str to avoid float issues
                "amount_off": str(c.amount_off or Decimal("0")),
                # time window
                "valid_from": c.valid_from.isoformat() if c.valid_from else None,
                "valid_to": c.valid_to.isoformat() if c.valid_to else None,
                # status & meta
                "is_active": c.is_active,
                "notes": c.notes or "",
                # usage limits
                "max_redemptions": c.max_redemptions,
                "per_user_limit": c.per_user_limit,
                # scope/targeting
                "target_plan_types": c.target_plan_types or [],
                "target_site_types": c.target_site_types or [],
                "target_plan_ids": c.target_plan_ids or [],
                # first-N-cycles + stacking
                "applies_to_first_n_cycles": c.applies_to_first_n_cycles,
                "stack_policy": c.stack_policy,
                # counters
                "redemptions": c.redemptions_count or 0,
            }
        )

    return JsonResponse({"success": True, "coupons": data})


ALLOWED_SCOPES = {"any", "kit", "plan", "install", "extra"}


def _parse_scopes(val) -> List[str]:
    """
    Accepts a string (comma/space separated) or list for scopes.
    Normalizes and validates against ALLOWED_SCOPES.
    """
    if not val:
        return ["any"]
    if isinstance(val, str):
        parts = [p.strip().lower() for p in val.replace(",", " ").split() if p.strip()]
    elif isinstance(val, (list, tuple)):
        parts = [str(p).strip().lower() for p in val if str(p).strip()]
    else:
        parts = []
    scopes = [s for s in parts if s in ALLOWED_SCOPES]
    return scopes or ["any"]


def _parse_decimal(val):
    try:
        return Decimal(str(val))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _tz_aware(dt: datetime | None) -> datetime | None:
    """
    Ensure datetime is timezone-aware if USE_TZ is on.
    """
    if not dt:
        return None
    if timezone.is_naive(dt):
        return timezone.make_aware(dt, timezone.get_default_timezone())
    return dt


def _parse_when_for_dtfield(raw, *, end_of_day=False) -> datetime | None:
    """
    Accepts ISO datetime or date strings and returns an AWARE datetime.
    - If a date is supplied and the model field is DateTimeField,
      combine with 00:00 (start) or 23:59:59.999999 (end) per end_of_day flag.
    """
    if not raw:
        return None
    # Try datetime first
    dt = parse_datetime(str(raw))
    if dt:
        return _tz_aware(dt)

    # Fallback: parse as date and upcast to datetime
    d = parse_date(str(raw))
    if not d:
        return None

    if end_of_day:
        dt = datetime.combine(d, time(23, 59, 59, 999999))
    else:
        dt = datetime.combine(d, time(0, 0, 0))
    return _tz_aware(dt)


@require_staff_role(["admin", "manager"])
@require_POST
@transaction.atomic
def coupon_create(request: HttpRequest):
    body = _json(request)

    # ---------- Basics ----------
    length = int(body.get("length") or 10)
    prefix = (body.get("prefix") or "").strip().upper()

    raw_discount_type = (body.get("discount_type") or "percent").strip().lower()
    if raw_discount_type not in {"percent", "amount", "fixed", "fixed_amount"}:
        return JsonResponse(
            {
                "success": False,
                "message": "discount_type must be 'percent' or 'amount'.",
            },
            status=400,
        )

    discount_type = (
        DiscountType.PERCENT if raw_discount_type == "percent" else DiscountType.AMOUNT
    )

    # ---------- Value validation ----------
    percent_off = body.get("percent_off")
    amount_off = body.get("amount_off")

    if discount_type == DiscountType.PERCENT:
        percent_off = _parse_decimal(percent_off)
        if percent_off is None or percent_off <= 0 or percent_off > 100:
            return JsonResponse(
                {
                    "success": False,
                    "message": "percent_off must be a number between 0 and 100.",
                },
                status=400,
            )
        amount_off = None
    else:
        amount_off = _parse_decimal(amount_off)
        if amount_off is None or amount_off <= 0:
            return JsonResponse(
                {"success": False, "message": "amount_off must be a positive number."},
                status=400,
            )
        percent_off = None

    # ---------- Validity window (make AWARE) ----------
    valid_from = _parse_when_for_dtfield(body.get("valid_from"), end_of_day=False)
    valid_to = _parse_when_for_dtfield(body.get("valid_to"), end_of_day=True)

    # ---------- Limits & flags ----------
    per_user_limit = int(body.get("per_user_limit") or 1)
    max_redemptions = int(body.get("max_redemptions") or 1)
    is_active = bool(body.get("is_active", True))
    notes = (body.get("notes") or "").strip()

    # ---------- Scoping (write only to real, writable fields) ----------
    scopes = _parse_scopes(body.get("scopes") or body.get("target_line_kinds"))

    try:
        target_plan_ids = [
            int(x) for x in (body.get("target_plan_ids") or []) if str(x).isdigit()
        ]
    except Exception:
        target_plan_ids = []

    if isinstance(body.get("target_extra_charge_types"), (list, tuple)):
        target_extra_charge_types = [
            str(x).strip()
            for x in body.get("target_extra_charge_types")
            if str(x).strip()
        ]
    else:
        target_extra_charge_types = []

    stackable_with_promos = bool(body.get("stackable_with_promos", True))

    # ---------- Create coupon (code generator) ----------
    coupon = generate_unique_coupon(
        CouponModel=Coupon,
        length=length,
        prefix=prefix,
        discount_type=(
            "percent" if discount_type == DiscountType.PERCENT else "amount"
        ),
        percent_off=percent_off,
        amount_off=amount_off,
        valid_from=valid_from,
        valid_to=valid_to,
        per_user_limit=per_user_limit,
        max_redemptions=max_redemptions,
        is_active=is_active,
        notes=notes,
        created_by=request.user,
    )

    # ---------- Update optional targeting fields that EXIST on the model ----------
    # Build a set of real, writable field names on Coupon
    concrete_field_names = {
        f.name for f in Coupon._meta.get_fields() if getattr(f, "concrete", False)
    }

    fields_to_update = []

    # Prefer 'target_line_kinds' if present; DO NOT touch 'effective_line_scopes' (read-only property)
    if "target_line_kinds" in concrete_field_names:
        setattr(coupon, "target_line_kinds", scopes)
        fields_to_update.append("target_line_kinds")
    elif "scope" in concrete_field_names:
        # Legacy single text field – store a compact representation
        setattr(coupon, "scope", ",".join(scopes))
        fields_to_update.append("scope")

    if "target_plan_ids" in concrete_field_names:
        setattr(coupon, "target_plan_ids", target_plan_ids or [])
        fields_to_update.append("target_plan_ids")

    if "target_extra_charge_types" in concrete_field_names:
        setattr(coupon, "target_extra_charge_types", target_extra_charge_types or [])
        fields_to_update.append("target_extra_charge_types")

    if "stackable_with_promos" in concrete_field_names:
        setattr(coupon, "stackable_with_promos", stackable_with_promos)
        fields_to_update.append("stackable_with_promos")

    if fields_to_update:
        coupon.save(update_fields=fields_to_update)

    return JsonResponse(
        {
            "success": True,
            "id": str(coupon.id),
            "code": coupon.code,
            "scopes": scopes,
            "target_plan_ids": target_plan_ids,
            "target_extra_charge_types": target_extra_charge_types,
            "stackable_with_promos": stackable_with_promos,
            "valid_from": coupon.valid_from.isoformat()
            if getattr(coupon, "valid_from", None)
            else None,
            "valid_to": coupon.valid_to.isoformat()
            if getattr(coupon, "valid_to", None)
            else None,
        },
        status=201,
    )


@require_staff_role(["admin", "manager"])
@transaction.atomic
def coupon_bulk_create(request: HttpRequest):
    body = _json(request)

    # ---------- Base & validation ----------
    try:
        count = int(body.get("count") or 50)
        length = int(body.get("length") or 10)
        prefix = (body.get("prefix") or "").strip().upper()
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Invalid count/length."}, status=400
        )

    raw_discount_type = (body.get("discount_type") or "percent").strip().lower()
    if raw_discount_type not in {"percent", "amount", "fixed", "fixed_amount"}:
        return JsonResponse(
            {
                "success": False,
                "message": "discount_type must be 'percent' or 'amount'.",
            },
            status=400,
        )

    discount_type = (
        DiscountType.PERCENT if raw_discount_type == "percent" else DiscountType.AMOUNT
    )

    percent_off = body.get("percent_off")
    amount_off = body.get("amount_off")

    if discount_type == DiscountType.PERCENT:
        percent_off = _parse_decimal(percent_off)
        if percent_off is None or percent_off <= 0 or percent_off > 100:
            return JsonResponse(
                {
                    "success": False,
                    "message": "percent_off must be a number between 0 and 100.",
                },
                status=400,
            )
        amount_off = None
    else:
        amount_off = _parse_decimal(amount_off)
        if amount_off is None or amount_off <= 0:
            return JsonResponse(
                {"success": False, "message": "amount_off must be a positive number."},
                status=400,
            )
        percent_off = None

    # Limits / validity / flags
    try:
        max_redemptions = int(body.get("max_redemptions") or 1)
        per_user_limit = int(body.get("per_user_limit") or 1)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Invalid max_redemptions/per_user_limit."},
            status=400,
        )

    valid_from = body.get("valid_from") or None  # let your helper/model parse
    valid_to = body.get("valid_to") or None
    is_active = bool(body.get("is_active", True))
    notes = (body.get("notes") or "").strip()

    # ---------- Scoping (the missing piece) ----------
    scopes = _parse_scopes(body.get("scopes") or body.get("target_line_kinds"))

    try:
        target_plan_ids = [
            int(x) for x in (body.get("target_plan_ids") or []) if str(x).isdigit()
        ]
    except Exception:
        target_plan_ids = []

    if isinstance(body.get("target_extra_charge_types"), (list, tuple)):
        target_extra_charge_types = [
            str(x).strip()
            for x in body.get("target_extra_charge_types")
            if str(x).strip()
        ]
    else:
        target_extra_charge_types = []

    stackable_with_promos = bool(body.get("stackable_with_promos", True))

    # ---------- Create base coupons via bulk helper ----------
    try:
        result = bulk_generate_coupons(
            CouponModel=Coupon,  # <-- ensure we pass the model (like single create fix)
            count=count,
            length=length,
            prefix=prefix,
            discount_type=(
                "percent" if discount_type == DiscountType.PERCENT else "amount"
            ),
            percent_off=percent_off,
            amount_off=amount_off,
            valid_from=valid_from,
            valid_to=valid_to,
            max_redemptions=max_redemptions,
            per_user_limit=per_user_limit,
            is_active=is_active,
            notes=notes,
            created_by=request.user,
        )
    except ValueError as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)

    # The helper may return various shapes; normalize to a queryset/list of Coupon objects
    coupons: Iterable[Coupon] = []
    if isinstance(result, dict):
        if "coupons" in result and isinstance(result["coupons"], list):
            coupons = result["coupons"]
        elif "ids" in result and isinstance(result["ids"], list):
            coupons = list(Coupon.objects.filter(id__in=result["ids"]))
        else:
            # some helpers return {"count": N, "codes": [...]} — fetch by prefix/creator as a fallback (best effort)
            coupons = Coupon.objects.filter(
                prefix=prefix, created_by=request.user
            ).order_by("-created_at")[:count]
    elif isinstance(result, list):
        coupons = result
    else:
        # last resort: nothing we can do
        coupons = []

    coupons = list(coupons)
    if not coupons:
        # still return count from helper if present
        return JsonResponse(
            {
                "success": True,
                "count": int(result.get("count", 0)) if isinstance(result, dict) else 0,
            }
        )

    # ---------- Update scoping fields for all created coupons ----------
    # We keep this defensive (only set fields that exist on your model)
    fields_to_update = set()
    for c in coupons:
        if hasattr(c, "effective_line_scopes"):
            c.effective_line_scopes = scopes
            fields_to_update.add("effective_line_scopes")
        if hasattr(c, "target_line_kinds"):
            c.target_line_kinds = scopes
            fields_to_update.add("target_line_kinds")
        if hasattr(c, "target_plan_ids"):
            c.target_plan_ids = target_plan_ids or []
            fields_to_update.add("target_plan_ids")
        if hasattr(c, "target_extra_charge_types"):
            c.target_extra_charge_types = target_extra_charge_types or []
            fields_to_update.add("target_extra_charge_types")
        if hasattr(c, "stackable_with_promos"):
            c.stackable_with_promos = stackable_with_promos
            fields_to_update.add("stackable_with_promos")

    if fields_to_update:
        Coupon.objects.bulk_update(coupons, list(fields_to_update))

    # Useful response payload
    codes = [c.code for c in coupons if getattr(c, "code", None)]
    payload = {
        "success": True,
        "count": len(coupons),
        "codes": codes[:50],  # cap to keep payload small
        "scopes": scopes,
        "target_plan_ids": target_plan_ids,
        "target_extra_charge_types": target_extra_charge_types,
        "stackable_with_promos": stackable_with_promos,
    }

    # If original result had extra meta, merge non-conflicting basics
    if isinstance(result, dict):
        for k in ("count", "prefix"):
            if k in result and k not in payload:
                payload[k] = result[k]

    return JsonResponse(payload, status=201)


@require_staff_role(["admin"])
@require_POST
@transaction.atomic
def coupon_toggle(request: HttpRequest, coupon_id):
    try:
        c = Coupon.objects.get(id=coupon_id)
        print("TEST")
    except Coupon.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Coupon not found"}, status=404
        )
    c.is_active = not c.is_active
    c.save(update_fields=["is_active"])
    return JsonResponse({"success": True, "is_active": c.is_active})


@require_staff_role(["admin"])
@require_POST
@transaction.atomic
def coupon_delete(request: HttpRequest, coupon_id):
    try:
        c = Coupon.objects.get(id=coupon_id)
    except Coupon.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Coupon not found"}, status=404
        )
    c.delete()
    return JsonResponse({"success": True})


def _json_body(request: HttpRequest) -> dict:
    try:
        return json.loads(request.body.decode("utf-8") or "{}")
    except Exception:
        return {}


LINE_KINDS_ALLOWED = {"kit", "plan", "install", "extra", "any"}


# ---------- helpers ----------
def _aware_from_local(dt_str):
    """
    Accepts 'YYYY-MM-DDTHH:MM' (from <input type=datetime-local>) or ISO strings.
    Returns timezone-aware datetime or None.
    """
    if not dt_str:
        return None
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except ValueError:
        return None
    # Make aware if naive
    if dt.tzinfo is None:
        return timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def _promotion_to_dict(p: Promotion) -> dict:
    # Map value → percent_off/amount_off for the UI
    if p.discount_type == DiscountType.PERCENT:
        percent_off = p.value
        amount_off = None
    else:
        percent_off = None
        amount_off = p.value

    scopes = p.target_line_kinds or ["any"]
    scope_display = (
        "Any"
        if ("any" in [s.lower() for s in scopes] or not scopes)
        else ", ".join(scopes)
    )

    return {
        "id": str(p.id),
        "name": p.name,
        "discount_type": p.discount_type,  # "percent" | "amount"
        "percent_off": float(percent_off) if percent_off is not None else None,
        "amount_off": str(amount_off) if amount_off is not None else None,
        "valid_from": p.starts_at.isoformat() if p.starts_at else None,
        "valid_to": p.ends_at.isoformat() if p.ends_at else None,
        "valid_from_local": p.starts_at.strftime("%Y-%m-%d %H:%M")
        if p.starts_at
        else "",
        "valid_to_local": p.ends_at.strftime("%Y-%m-%d %H:%M") if p.ends_at else "",
        "scopes": scopes,
        "scope": scope_display,
        "scope_display": scope_display,
        "target_plan_types": p.target_plan_types or [],
        "target_site_types": p.target_site_types or [],
        "target_plan_ids": p.target_plan_ids or [],
        "target_kit_types": [],  # not used in model, kept for UI compatibility
        "target_extra_charge_types": p.target_extra_charge_types or [],
        "max_redemptions": p.max_uses_total or 0,
        "new_customers_only": bool(p.new_customers_only),
        "stack_policy": p.stack_policy,
        "active": bool(p.active),
        "status": "active" if p.active else "inactive",
    }


def _apply_promotion_payload(p: Promotion, payload: dict):
    # discount
    discount_type = (
        payload.get("discount_type") or "percent"
    )  # ui sends "percent" | "amount"
    if discount_type not in ("percent", "amount"):
        raise ValueError("Invalid discount_type")

    if discount_type == "percent":
        val = payload.get("percent_off") or payload.get("value")
    else:
        val = payload.get("amount_off") or payload.get("value")

    try:
        value = Decimal(str(val)) if val is not None else None
    except Exception:
        raise ValueError("Invalid discount value")

    if value is None or value <= 0:
        raise ValueError("Discount value must be > 0")

    # dates
    starts_at = _aware_from_local(payload.get("valid_from"))
    ends_at = _aware_from_local(payload.get("valid_to"))

    # scopes & targeting
    p.name = payload.get("name", p.name).strip()
    p.discount_type = (
        DiscountType.PERCENT if discount_type == "percent" else DiscountType.AMOUNT
    )
    p.value = value
    p.starts_at = starts_at
    p.ends_at = ends_at

    p.target_line_kinds = payload.get("scopes") or []
    p.target_plan_types = payload.get("target_plan_types") or []
    p.target_site_types = payload.get("target_site_types") or []
    p.target_plan_ids = payload.get("target_plan_ids") or []
    # UI may send kit types; model doesn't store them (ignore safely)
    p.target_extra_charge_types = payload.get("target_extra_charge_types") or []

    p.new_customers_only = bool(payload.get("new_customers_only", False))
    p.stack_policy = payload.get("stack_policy") or StackPolicy.PROMO_THEN_COUPON

    # limits
    max_red = payload.get("max_redemptions")
    p.max_uses_total = int(max_red) if max_red else None

    # status/active
    status = (payload.get("status") or "").lower()
    if status in ("active", "inactive"):
        p.active = status == "active"


@require_staff_role(["admin", "manager", "sales"])
@require_GET
def promotion_list(request: HttpRequest):
    qs = Promotion.objects.all().order_by("-starts_at", "-id")
    data = [_promotion_to_dict(p) for p in qs]
    return JsonResponse({"success": True, "promotions": data})


@require_staff_role(["admin", "manager", "sales"])
@require_GET
def promotion_detail(request: HttpRequest, promotion_id: int):
    try:
        p = Promotion.objects.get(id=promotion_id)
    except Promotion.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Promotion not found"}, status=404
        )
    return JsonResponse({"success": True, "promotion": _promotion_to_dict(p)})


@require_staff_role(["admin", "manager"])
@require_POST
@transaction.atomic
def promotion_create(request: HttpRequest):
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        p = Promotion(active=False)  # default inactive unless UI sets status
        _apply_promotion_payload(p, payload)
        if not p.name:
            return JsonResponse(
                {"success": False, "message": "Name is required"}, status=400
            )
        p.save()
        return JsonResponse({"success": True, "promotion": _promotion_to_dict(p)})
    except ValueError as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)


@require_staff_role(["admin", "manager"])
@require_POST
@transaction.atomic
def promotion_update(request: HttpRequest, promotion_id: int):
    try:
        p = Promotion.objects.get(id=promotion_id)
    except Promotion.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Promotion not found"}, status=404
        )

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
        _apply_promotion_payload(p, payload)
        if not p.name:
            return JsonResponse(
                {"success": False, "message": "Name is required"}, status=400
            )
        p.save()
        return JsonResponse({"success": True, "promotion": _promotion_to_dict(p)})
    except ValueError as e:
        return JsonResponse({"success": False, "message": str(e)}, status=400)


@require_staff_role(["admin"])
@require_POST
@transaction.atomic
def promotion_toggle(request: HttpRequest, promotion_id: int):
    try:
        p = Promotion.objects.get(id=promotion_id)
    except Promotion.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Promotion not found"}, status=404
        )

    p.active = not p.active
    p.save(update_fields=["active"])
    return JsonResponse({"success": True, "id": str(p.id), "active": p.active})


@require_staff_role(["admin"])
@require_POST
@transaction.atomic
def promotion_delete(request: HttpRequest, promotion_id: int):
    deleted = Promotion.objects.filter(id=promotion_id).delete()[0]
    if not deleted:
        return JsonResponse(
            {"success": False, "message": "Promotion not found"}, status=404
        )
    return JsonResponse({"success": True})


# Small, friendly currency list for the dropdown
CURRENCY_CHOICES = [
    ("USD", "US Dollar"),
    ("CDF", "Congolese Franc"),
    ("ZAR", "South African Rand"),
    ("EUR", "Euro"),
]


@require_staff_role(["admin", "manager"])
@require_http_methods(["GET"])
def company_settings_view(request: HttpRequest) -> HttpResponse:
    """
    Render the settings page. We pass the singleton instance as `company`
    so your template can use {{ company.* }} directly.
    """
    company = CompanySettings.get()
    context = {
        "company": company,
        "currencies": CURRENCY_CHOICES,
    }
    return render(request, "client/settings_company.html", context)


@require_staff_role(["admin"])
@require_http_methods(["POST"])
@transaction.atomic
def company_settings_update(request: HttpRequest) -> JsonResponse:
    """
    Accepts multipart FormData from your two forms:
      - Company panel (identity, address, legal IDs, logo)
      - Billing panel (invoice defaults, currency, bank/mm, footer, timezone)

    The template adds an optional hidden field `_section` = "billing" on the billing form,
    but this endpoint is flexible — it will upsert whatever fields you send.
    """
    cs = CompanySettings.get()

    # Helpers
    def g(name, default=""):
        return (request.POST.get(name) or default).strip()

    def to_int(val, default=0):
        try:
            return int(str(val).strip())
        except Exception:
            return default

    # ---------- COMMON/IDENTITY ----------
    # Form names (from your template) → Model fields (our new model)
    # Company Identity - FIXED: Support clearing fields
    if "legal_name" in request.POST:
        cs.legal_name = g("legal_name")
    if "trade_name" in request.POST:
        cs.trade_name = g("trade_name")
    if "email" in request.POST:
        cs.email = g("email")
    if "phone" in request.POST:
        cs.phone = g("phone")
    if "website" in request.POST:
        cs.website = g("website")

    # Address - FIXED: Support clearing fields
    if "street_address" in request.POST:
        cs.street_address = g("street_address")
    if "city" in request.POST:
        cs.city = g("city")
    if "province" in request.POST:
        cs.province = g("province")
    if "country" in request.POST:
        cs.country = g("country")
    if "postal_code" in request.POST:
        cs.postal_code = g("postal_code")

    # Legal identifiers (DRC)
    # template: rccm, id_nat, nif, arptc_license (fallback: tax_id → nif)
    # Support clearing: if the key is present in POST, update the field
    # even when the value is an empty string. If the key is absent, leave
    # the existing value unchanged to allow partial updates.
    if "rccm" in request.POST:
        cs.rccm = g("rccm")
    if "id_nat" in request.POST:
        cs.id_nat = g("id_nat")
    if "nif" in request.POST or "tax_id" in request.POST:
        cs.nif = g("nif") or g("tax_id")
    if "arptc_license" in request.POST:
        cs.arptc_license = g("arptc_license")

    # Logo (optional file)
    if "logo" in request.FILES:
        cs.logo = request.FILES["logo"]

    # ---------- BILLING/DEFAULTS ----------
    # These may arrive only when _section="billing", but we accept them anytime.
    if "invoice_prefix" in request.POST:
        cs.invoice_prefix = g("invoice_prefix")

    if "next_invoice_number" in request.POST:
        next_num = request.POST.get("next_invoice_number")
        cs.next_invoice_number = to_int(next_num, cs.next_invoice_number or 1)

    # ----- CURRENCY -----
    # Prefer explicit default_currency (allow clearing). Fallback to legacy `currency` only if
    # default_currency not provided in the POST payload.
    if "default_currency" in request.POST:
        dc = g("default_currency")
        cs.default_currency = dc.upper() if dc else ""
    else:
        legacy_currency = g("currency")
        if legacy_currency:
            cs.default_currency = legacy_currency.upper()

    # ----- PAYMENT TERMS -----
    # Support modern numeric `payment_terms_days` with clearing, with a legacy fallback to
    # string/integer `payment_terms` where non-numeric text is appended into payment_instructions.
    if "payment_terms_days" in request.POST:
        ptd = request.POST.get("payment_terms_days")
        if ptd is not None and str(ptd).strip() != "":
            cs.payment_terms_days = to_int(ptd, cs.payment_terms_days or 7)
        else:
            cs.payment_terms_days = None
    else:
        legacy_pt = request.POST.get("payment_terms")
        if legacy_pt is not None:
            if str(legacy_pt).strip().isdigit():
                cs.payment_terms_days = int(str(legacy_pt).strip())
            else:
                pt_existing = (cs.payment_instructions or "").strip()
                extra = f"Payment terms: {legacy_pt}".strip()
                cs.payment_instructions = (
                    extra if not pt_existing else f"{pt_existing}\n{extra}"
                )

    # ----- CHECKBOXES / BOOLEANS -----
    def to_bool(v):
        return str(v).lower() in {"1", "true", "on", "yes"}

    # reset_number_annually: accept either explicit value or *_cb presence, and infer False
    # when billing section is submitted but neither key is present.
    if request.POST.get("reset_number_annually") is not None:
        cs.reset_number_annually = to_bool(request.POST.get("reset_number_annually"))
    elif "reset_number_annually_cb" in request.POST:
        cs.reset_number_annually = True
    elif request.POST.get("_section") == "billing":
        cs.reset_number_annually = False

    # show_prices_in_cdf: accept either explicit value or *_cb presence with same semantics.
    if request.POST.get("show_prices_in_cdf") is not None:
        cs.show_prices_in_cdf = to_bool(request.POST.get("show_prices_in_cdf"))
    elif "show_prices_in_cdf_cb" in request.POST:
        cs.show_prices_in_cdf = True
    elif request.POST.get("_section") == "billing":
        cs.show_prices_in_cdf = False

    # Timezone
    if "timezone" in request.POST:
        cs.timezone = g("timezone")

    # Payment Instructions (allow clearing)
    if "payment_instructions" in request.POST:
        cs.payment_instructions = g("payment_instructions")

    # Invoice Footers (allow clearing; support legacy invoice_footer -> EN when no explicit EN footer)
    if "footer_text_fr" in request.POST:
        cs.footer_text_fr = g("footer_text_fr")
    if "footer_text_en" in request.POST:
        cs.footer_text_en = g("footer_text_en")
    inv_footer = request.POST.get("invoice_footer")
    if inv_footer is not None and "footer_text_en" not in request.POST:
        cs.footer_text_en = inv_footer

    # ---------- BRANDING ----------
    # Stamp and Signature files
    if "stamp" in request.FILES:
        cs.stamp = request.FILES["stamp"]
    if "signature" in request.FILES:
        cs.signature = request.FILES["signature"]

    # Signatory info (allow clearing)
    if "signatory_name" in request.POST:
        cs.signatory_name = g("signatory_name")
    if "signatory_title" in request.POST:
        cs.signatory_title = g("signatory_title")

    # ---------- COMPLIANCE & LEGAL ----------
    # Tax office and legal notes (allow clearing)
    if "tax_office_name" in request.POST:
        cs.tax_office_name = g("tax_office_name")
    if "legal_notes" in request.POST:
        cs.legal_notes = g("legal_notes")

    # Bank & payment coordinates
    if request.POST.get("bank_name") is not None:
        cs.bank_name = g("bank_name")
    if request.POST.get("bank_account_name") is not None:
        cs.bank_account_name = g("bank_account_name")
    if request.POST.get("bank_account_number_usd") is not None:
        cs.bank_account_number_usd = g("bank_account_number_usd")
    if request.POST.get("bank_account_number_cdf") is not None:
        cs.bank_account_number_cdf = g("bank_account_number_cdf")
    if request.POST.get("bank_swift") is not None:
        cs.bank_swift = g("bank_swift")
    if request.POST.get("bank_branch") is not None:
        cs.bank_branch = g("bank_branch")
    if request.POST.get("bank_iban") is not None:
        cs.bank_iban = g("bank_iban")

    if request.POST.get("mm_provider") is not None:
        cs.mm_provider = g("mm_provider")
    if request.POST.get("mm_number") is not None:
        cs.mm_number = g("mm_number")

    # ---------- BRANDING ----------
    if "stamp" in request.FILES:
        cs.stamp = request.FILES["stamp"]
    if "signature" in request.FILES:
        cs.signature = request.FILES["signature"]
    cs.signatory_name = g("signatory_name", cs.signatory_name)
    cs.signatory_title = g("signatory_title", cs.signatory_title)

    # ---------- COMPLIANCE & LEGAL ----------
    if request.POST.get("tax_office_name") is not None:
        cs.tax_office_name = g("tax_office_name")
    if request.POST.get("legal_notes") is not None:
        cs.legal_notes = request.POST.get("legal_notes", "")

    cs.save()

    # Minimal JSON response expected by your JS (toast + ok flag)
    return JsonResponse(
        {
            "ok": True,
            "message": "Settings saved.",
            "company": {
                "legal_name": cs.legal_name,
                "trade_name": cs.trade_name,
                "email": cs.email,
                "phone": cs.phone,
                "website": cs.website,
                "street_address": cs.street_address,
                "city": cs.city,
                "province": cs.province,
                "country": cs.country,
                "postal_code": cs.postal_code,
                "rccm": cs.rccm,
                "id_nat": cs.id_nat,
                "nif": cs.nif,
                "arptc_license": cs.arptc_license,
                "invoice_prefix": cs.invoice_prefix,
                "next_invoice_number": cs.next_invoice_number,
                "reset_number_annually": cs.reset_number_annually,
                "default_currency": cs.default_currency,
                "payment_terms_days": cs.payment_terms_days,
                "show_prices_in_cdf": cs.show_prices_in_cdf,
                "timezone": cs.timezone,
                "payment_instructions": cs.payment_instructions,
                "footer_text_fr": cs.footer_text_fr,
                "footer_text_en": cs.footer_text_en,
                "bank_name": cs.bank_name,
                "bank_account_name": cs.bank_account_name,
                "bank_account_number_usd": getattr(cs, "bank_account_number_usd", ""),
                "bank_account_number_cdf": getattr(cs, "bank_account_number_cdf", ""),
                "bank_swift": cs.bank_swift,
                "bank_branch": cs.bank_branch,
                "bank_iban": cs.bank_iban,
                "mm_provider": cs.mm_provider,
                "mm_number": cs.mm_number,
                "logo_url": (cs.logo.url if cs.logo else None),
                "stamp_url": (cs.stamp.url if cs.stamp else None),
                "signature_url": (cs.signature.url if cs.signature else None),
                "signatory_name": cs.signatory_name,
                "signatory_title": cs.signatory_title,
                "tax_office_name": cs.tax_office_name,
                "legal_notes": cs.legal_notes,
            },
        }
    )


@login_required
def company_settings_delete_file(request: HttpRequest) -> JsonResponse:
    """
    Delete a specific file (logo, stamp, or signature) from Company Settings.
    Expects POST with 'field_name' parameter.
    """
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "Method not allowed"}, status=405
        )

    field_name = request.POST.get("field_name", "").strip()
    allowed_fields = ["logo", "stamp", "signature"]

    if field_name not in allowed_fields:
        return JsonResponse(
            {
                "success": False,
                "message": f"Invalid field name. Must be one of: {', '.join(allowed_fields)}",
            },
            status=400,
        )

    cs = CompanySettings.get()
    file_field = getattr(cs, field_name, None)

    if not file_field:
        return JsonResponse(
            {"success": False, "message": f"No {field_name} file to delete"}, status=400
        )

    try:
        # Delete the file from storage
        file_field.delete(save=False)
        # Clear the field in the database
        setattr(cs, field_name, None)
        cs.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"{field_name.capitalize()} deleted successfully",
            }
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Error deleting {field_name}: {str(e)}"},
            status=500,
        )
