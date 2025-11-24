import json
import logging
import re

import requests
from xhtml2pdf import pisa

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

import nexus_backend.settings
from main.models import Order, PaymentAttempt, Subscription

logger = logging.getLogger(__name__)


def home_page(request):
    template = ("home_page.html",)
    return render(request, template)


@login_required(login_url="login_page")
def book_my_kit(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            order_id = data.get("order_id")
            print("Order ID:", order_id)

            # Do something with the order_id...
            return JsonResponse(
                {"success": True, "message": "Order confirmed successfully."}
            )
        except Exception as e:
            print("Error:", e)
            return JsonResponse({"success": False, "message": "An error occurred."})
    return JsonResponse({"success": False, "message": "Invalid request method."})


@login_required(login_url="login_page")
def mobile_payment(request):
    try:
        data = json.loads(request.body or "{}")
        phone = (data.get("phone_number") or "").strip()
        order_id = (data.get("order_id") or "").strip()

        if not phone or not order_id:
            return JsonResponse(
                {"success": False, "message": "Missing phone number or order ID"},
                status=400,
            )

        order = (
            Order.objects.filter(order_reference=order_id)
            .select_related("user", "plan")
            .first()
        )
        if not order:
            return JsonResponse(
                {"success": False, "message": "Order not found"}, status=404
            )

        if order.is_expired():
            return JsonResponse(
                {
                    "success": False,
                    "message": "This order has expired and was cancelled.",
                },
                status=400,
            )

        if order.payment_status == "cancelled" or order.status == "cancelled":
            return JsonResponse(
                {"success": False, "message": "This order is cancelled."}, status=400
            )

        # Normalize CD numbers -> 243XXXXXXXXX
        raw = (phone or "").strip()
        digits = re.sub(r"\D", "", raw)  # keep only digits

        if len(digits) == 9:
            # e.g. 970000000  -> 243970000000
            formatted_phone = "243" + digits
        elif len(digits) == 10 and digits.startswith("0"):
            # e.g. 0970000000 -> 243970000000
            formatted_phone = "243" + digits[1:]
        elif len(digits) == 12 and digits.startswith("243"):
            # e.g. 243970000000 (already normalized)
            formatted_phone = digits
        else:
            return JsonResponse(
                {"success": False, "message": "Invalid phone number."},
                status=400,
            )

        # Build FlexPay payload
        flexpay_payload = {
            "merchant": nexus_backend.settings.FLEXPAY_MERCHANT_ID,
            "type": "1",  # Mobile Money
            "phone": formatted_phone,
            "reference": order_id,
            "amount": str(order.total_price or "0.00"),
            "currency": "USD",
            "callbackUrl": request.build_absolute_uri(
                reverse("flexpay_callback_mobile")
            ),
        }

        flexpay_url = nexus_backend.settings.FLEXPAY_MOBILE_URL
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {nexus_backend.settings.FLEXPAY_API_KEY}",
        }

        response = requests.post(flexpay_url, json=flexpay_payload, headers=headers)
        fp = {}
        try:
            fp = response.json()
        except Exception:
            pass

        # FlexPay said the request itself is accepted
        if response.status_code == 200:
            # If FlexPay code == "0" we consider it PENDING (awaiting mobile push approval)
            code = str(fp.get("code", "")).strip()
            order_number = fp.get("orderNumber") or fp.get("order_number")

            # Decide what this payment is for (subscription vs hardware)
            payment_for = (
                "subscription" if getattr(order, "plan_id", None) else "hardware"
            )

            if code == "0" and order_number:
                try:
                    with transaction.atomic():
                        # Upsert a pending attempt keyed by the FlexPay orderNumber (unique)
                        attempt, created = PaymentAttempt.objects.get_or_create(
                            order=order,
                            order_number=str(order_number),
                            defaults={
                                "code": code,
                                "reference": order.order_reference,
                                "amount": order.total_price or None,
                                "amount_customer": order.total_price or None,
                                "currency": "USD",
                                "status": "pending",
                                "payment_type": "mobile",
                                "payment_for": payment_for,
                                "transaction_time": timezone.now(),
                                "raw_payload": {
                                    "request": flexpay_payload,  # what we sent
                                    "response": fp,  # what we got
                                },
                            },
                        )

                        # If it already exists but was not pending, keep the most informative state
                        if not created and attempt.status != "completed":
                            attempt.code = code
                            attempt.reference = order.order_reference
                            attempt.amount = order.total_price or attempt.amount
                            attempt.amount_customer = (
                                order.total_price or attempt.amount_customer
                            )
                            attempt.currency = "USD"
                            attempt.status = "pending"
                            attempt.payment_type = "mobile"
                            attempt.payment_for = payment_for
                            attempt.transaction_time = timezone.now()
                            # keep raw history but store latest response
                            attempt.raw_payload = {
                                "request": flexpay_payload,
                                "response": fp,
                            }
                            attempt.save(
                                update_fields=[
                                    "code",
                                    "reference",
                                    "amount",
                                    "amount_customer",
                                    "currency",
                                    "status",
                                    "payment_type",
                                    "payment_for",
                                    "transaction_time",
                                    "raw_payload",
                                ]
                            )

                        # Put order into awaiting confirmation
                        if (
                            order.payment_status != "awaiting_confirmation"
                            or order.status != "pending_payment"
                        ):
                            order.payment_status = "awaiting_confirmation"
                            order.status = "pending_payment"
                            order.save(update_fields=["payment_status", "status"])
                except IntegrityError:
                    # Race-safe: if unique constraint hit, consider it recorded
                    pass

            return JsonResponse(
                {
                    "success": True,
                    "message": fp.get("message")
                    or "FlexPay request sent successfully.",
                    "transaction_id": fp.get("transid"),
                    "order_number": order_number,
                    "code": code,
                },
                status=200,
            )

        # FlexPay refused / error path
        return JsonResponse(
            {
                "success": False,
                "message": fp.get("message", "FlexPay payment initiation failed."),
            },
            status=400,
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"An error occurred: {e}"}, status=500
        )


@login_required(login_url="login_page")
@require_POST
def initiate_card_payment(request):
    try:
        # ---- Parse input
        data = json.loads(request.body or "{}")
        order_id = (data.get("order_id") or "").strip()
        email = (data.get("email") or "").strip()  # optional
        description = "Starlink Payment"

        # ---- Validate order
        order = (
            Order.objects.filter(order_reference=order_id)
            .select_related("user", "plan")
            .first()
        )
        if not order:
            return JsonResponse(
                {"success": False, "message": "Order not found"}, status=404
            )

        if order.is_expired():
            return JsonResponse(
                {
                    "success": False,
                    "message": "This order has expired and was cancelled.",
                },
                status=400,
            )

        if order.payment_status == "cancelled" or order.status == "cancelled":
            return JsonResponse(
                {"success": False, "message": "This order is cancelled."}, status=400
            )

        amount_str = str(order.total_price or "0.00")

        # ---- Build FlexPay (CARD) request
        flexpay_url = nexus_backend.settings.FLEXPAY_CARD_URL

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {nexus_backend.settings.FLEXPAY_API_KEY}",
        }
        # NOTE: Put token INSIDE the JSON as "authorization", use snake_case keys.
        payload = {
            "authorization": f"Bearer {nexus_backend.settings.FLEXPAY_API_KEY}",
            "merchant": nexus_backend.settings.FLEXPAY_MERCHANT_ID,
            "reference": order_id,
            "amount": amount_str,
            "currency": "USD",
            "description": description,
            "callback_url": "https://flexpaie.com",
            "approve_url": "https://flexpaie.com",
            "cancel_url": "https://flexpaie.com",
            "decline_url": "https://flexpaie.com",
            # If FlexPay supports passing email for card, add the exact key they expect, e.g.:
            # "email": email,
        }

        resp = requests.post(flexpay_url, json=payload, headers=headers)
        fp = resp.json()

        if not (200 <= resp.status_code < 300):
            logger.error("FlexPay (card) HTTP %s: %s", resp.status_code, resp.text)
            print("ERROR", resp.status_code, resp.text)
            return JsonResponse(
                {"success": False, "message": "FlexPay returned an error"}, status=502
            )

        try:
            fp = resp.json()
        except ValueError:
            logger.error("FlexPay (card) non-JSON response: %s", resp.text[:1000])
            return JsonResponse(
                {"success": False, "message": "Invalid response from FlexPay"},
                status=502,
            )

        # Expected example:
        # {"code":"0","message":"Redirection en cours","orderNumber":"...","url":"https://..."}
        code = str(fp.get("code", "")).strip()
        order_number = fp.get("orderNumber") or fp.get("order_number")
        redirect_url = fp.get("url")

        # Decide what this payment is for
        payment_for = "subscription" if getattr(order, "plan_id", None) else "hardware"

        if code == "0" and order_number:
            # Record a PENDING attempt (idempotent on unique order_number)
            try:
                with transaction.atomic():
                    attempt, created = PaymentAttempt.objects.get_or_create(
                        order=order,
                        order_number=str(order_number),
                        defaults={
                            "code": code,
                            "reference": order.order_reference,
                            "amount": order.total_price or None,
                            "amount_customer": order.total_price or None,
                            "currency": "USD",
                            "status": "pending",
                            "payment_type": "card",
                            "payment_for": payment_for,
                            "transaction_time": timezone.now(),
                            "raw_payload": {
                                "request": {**payload, "email": email},
                                "response": fp,
                            },
                        },
                    )
                    if not created and attempt.status != "completed":
                        attempt.code = code
                        attempt.reference = order.order_reference
                        attempt.amount = order.total_price or attempt.amount
                        attempt.amount_customer = (
                            order.total_price or attempt.amount_customer
                        )
                        attempt.currency = "USD"
                        attempt.status = "pending"
                        attempt.payment_type = "card"
                        attempt.payment_for = payment_for
                        attempt.transaction_time = timezone.now()
                        attempt.raw_payload = {
                            "request": {**payload, "email": email},
                            "response": fp,
                        }
                        attempt.save(
                            update_fields=[
                                "code",
                                "reference",
                                "amount",
                                "amount_customer",
                                "currency",
                                "status",
                                "payment_type",
                                "payment_for",
                                "transaction_time",
                                "raw_payload",
                            ]
                        )

                    # Put order into awaiting confirmation while user completes card flow
                    if (
                        order.payment_status != "awaiting_confirmation"
                        or order.status != "pending_payment"
                    ):
                        order.payment_status = "awaiting_confirmation"
                        order.status = "pending_payment"
                        order.save(update_fields=["payment_status", "status"])
            except IntegrityError:
                # Unique collision → treat as already recorded
                pass

            # Return redirect URL to complete payment
            if redirect_url:
                return JsonResponse(
                    {
                        "success": True,
                        "url": redirect_url,
                        "order_number": order_number,
                        "code": code,
                    },
                    status=200,
                )
            return JsonResponse(
                {
                    "success": True,
                    "message": "Payment initiated but no redirect URL was returned.",
                    "order_number": order_number,
                    "code": code,
                },
                status=200,
            )

        # FlexPay did not return success code
        logger.warning("FlexPay (card) non-success response: %s", fp)
        return JsonResponse(
            {
                "success": False,
                "message": fp.get("message", "Payment initialization failed"),
            },
            status=400,
        )

    except Exception as e:
        logger.exception("Unexpected error in initiate_card_payment")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_GET
def orders_list(request):
    user = request.user
    orders = Order.objects.filter(user=user).order_by("-created_at")

    order_list = []
    for order in orders:
        # Determine what the payment is for
        has_kit = order.lines.filter(kind="kit").exists()
        has_plan = order.lines.filter(kind="plan").exists()
        if has_kit and has_plan:
            payment_for = "hardware + subscription"
        elif has_kit:
            payment_for = "hardware"
        elif has_plan:
            payment_for = "subscription"
        else:
            payment_for = "unknown"

        # Get latest payment attempt if any
        payment_type = None
        latest_attempt = order.payment_attempts.order_by("-created_at").first()
        if latest_attempt:
            payment_type = latest_attempt.payment_type

        order_list.append(
            {
                "order_reference": order.order_reference,
                "status": order.status,
                "payment_status": order.payment_status,
                "payment_method": order.payment_method,
                "payment_type": payment_type,
                "payment_for": payment_for,
                "plan_name": order.plan.name if has_plan and order.plan else "",
                "total_price": float(order.total_price or 0),
                "order_date": order.created_at.strftime("%Y-%m-%d"),
                "full_name": order.user.get_full_name(),
                "email": order.user.email,
                "taxes": (
                    [
                        {"name": t.name, "amount": float(t.amount)}
                        for t in order.taxes.all()
                    ]
                    if hasattr(order, "taxes")
                    else []
                ),
            }
        )

    # Get page number from query string (default to 1)
    page_number = request.GET.get("page", 1)
    paginator = Paginator(order_list, 5)  # 5 orders per page
    page_obj = paginator.get_page(page_number)

    return JsonResponse(
        {
            "orders": list(page_obj),
            "page": page_obj.number,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        status=200,
    )


@login_required(login_url="login_page")
def get_user_subscriptions(request):
    try:
        subscriptions = Subscription.objects.filter(user=request.user).select_related(
            "plan", "order"
        )

        data = []
        for sub in subscriptions:
            data.append(
                {
                    "id": sub.id,
                    # "order_ref": sub.order_reference,
                    "order_id": sub.order.id if sub.order else None,
                    "plan_name": sub.plan.name,
                    "data_cap_gb": sub.plan.standard_data_gb,
                    "price_usd": float(sub.plan.effective_price),
                    "status": sub.status,
                    "billing_cycle": sub.billing_cycle,
                    # "start_date": sub.started_at.strftime("%Y-%m-%d"),
                    # "end_date": sub.ended_at.strftime("%Y-%m-%d"),
                    # "next_billing_date": sub.next_billing_date.strftime("%Y-%m-%d"),
                }
            )
        return JsonResponse({"success": True, "subscriptions": data})
    except Exception:
        return JsonResponse(
            {
                "success": False,
                "error": "An error occurred while fetching subscriptions",
            },
            status=500,
        )


@login_required(login_url="login_page")
def get_order_details_print(request, reference):
    order = get_object_or_404(Order, order_reference=reference)
    user = order.user

    # Determine account type
    account_type = "unknown"
    full_name = ""
    address = ""
    nif = ""
    rccm = ""
    idnat = ""

    def get_applied_taxes(order):
        taxes = []
        if not order.user.is_tax_exempt:
            agg = order.taxes.aggregate(
                vat=Sum("amount", filter=models.Q(kind="VAT")),
                exc=Sum("amount", filter=models.Q(kind="EXCISE")),
            )
            vat = agg.get("vat") or 0
            exc = agg.get("exc") or 0
            if vat:
                taxes.append({"name": "VAT", "amount": float(vat)})
            if exc:
                taxes.append({"name": "EXCISE", "amount": float(exc)})
        return taxes

    if hasattr(user, "personnal_kyc") and user.personnal_kyc:
        account_type = "personal"
        full_name = (
            user.personnal_kyc.full_name or f"{user.first_name} {user.last_name}"
        )
        address = user.personnal_kyc.address or f"{user.first_name} {user.last_name}"

    elif hasattr(user, "company_kyc") and user.company_kyc:
        account_type = "business"
        full_name = user.company_kyc.company_name or "Company Account"
        nif = user.company_kyc.nif or ""
        rccm = user.company_kyc.rccm or ""
        idnat = user.company_kyc.id_nat or ""
        address = user.company_kyc.address or ""

    context = {
        "order_reference": order.order_reference,
        "status": order.status,
        "payment_status": order.payment_status,
        "payment_method": (
            order.payment_attempts.last().payment_type
            if order.payment_attempts.exists()
            else None
        ),
        "payment_for": (
            order.payment_attempts.last().payment_for
            if order.payment_attempts.exists()
            else None
        ),
        "kit_name": (
            order.kit_inventory.kit.name
            if order.kit_inventory and order.kit_inventory.kit
            else None
        ),
        "kit_price": float(
            order.lines.filter(kind="kit").aggregate(s=Sum("line_total"))["s"] or 0
        ),
        "plan_name": (
            order.subscription.plan.name
            if order.subscription and order.subscription.plan
            else None
        ),
        "plan_price": float(
            order.lines.filter(kind="plan").aggregate(s=Sum("line_total"))["s"] or 0
        ),
        "total_price": float(order.total_price or 0),
        "order_date": order.created_at.strftime("%Y-%m-%d"),
        "full_name": full_name,
        "email": user.email,
        "address": address,
        "nif": nif,
        "rccm": rccm,
        "idnat": idnat,
        "kyc_type": account_type,
        "taxes": get_applied_taxes(order),
    }

    # Render HTML to string using Django template engine
    template = get_template("pdf_templates/invoice_page.html")  # Correct relative path
    html_string = template.render(context)

    # Generate PDF using xhtml2pdf
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'filename="invoice_{reference}.pdf"'

    pisa_status = pisa.CreatePDF(html_string, dest=response)

    if pisa_status.err:
        return HttpResponse("PDF generation failed", status=500)

    return response


@login_required(login_url="login_page")
def get_subscription_payments(request, subscription_id):
    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        subscription = Subscription.objects.select_related("order").get(
            id=subscription_id, user=request.user
        )
        payments = subscription.get_payment_attempts()

        data = [
            {
                "id": p.id,
                "amount": str(p.amount or "0.00"),
                "status": p.status,
                "payment_type": p.payment_type,
                "transaction_time": (
                    p.transaction_time.strftime("%Y-%m-%d %H:%M")
                    if p.transaction_time
                    else "—"
                ),
            }
            for p in payments
        ]

        return JsonResponse({"success": True, "payments": data})
    except Subscription.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Subscription not found"}, status=404
        )
