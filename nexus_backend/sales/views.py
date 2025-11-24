import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from decimal import Decimal

import phonenumbers
import requests

from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import DatabaseError, IntegrityError, transaction
from django.db.models import Count, ExpressionWrapper, F, Q, Sum, IntegerField
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.utils.crypto import get_random_string
from django.utils.timezone import localtime
from django.utils.translation import gettext as _
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_POST

from client_app.client_helpers import (
    compute_local_expiry_from_coords,
    installation_fee_for_coords,
)
from client_app.views import reserve_inventory_for_order
from main.invoices_helpers import create_consolidated_invoice, issue_invoice
from main.utilities.pricing_helpers import (
    DraftLine,
    apply_promotions_and_coupon_to_draft_lines,
)
from user.permissions import require_staff_role

try:
    from openlocationcode import openlocationcode as olc
except Exception:
    olc = None


from main.models import (
    ZERO,
    AccountEntry,
    BillingAccount,
    CompanyDocument,
    CompanyKYC,
    CompanySettings,
    ConsolidatedInvoice,
    CouponRedemption,
    DiscountType,
    ExtraCharge,
    Invoice,
    InvoiceLine,
    InvoiceOrder,
    Order,
    OrderLine,
    PaymentAttempt,
    PersonalKYC,
    StarlinkKit,
    StarlinkKitInventory,
    Subscription,
    SubscriptionPlan,
    TaxRate,
    User,
)
from main.utilities.taxing import compute_totals_from_lines
from nexus_backend.settings import env
from sales.sales_helpers import _dt, _qmoney, _supports_skip_locked

logger = logging.getLogger(__name__)


# Create your views here.


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
@cache_page(30)  # cache the metrics for 30s – numbers don’t need millisecond freshness
def sales_dashboard(request):
    template = "sales_page.html"

    # Use .only() where possible (minimal columns), and avoid select_related on count() calls.
    user_count = User.objects.filter(is_staff=False).only("id_user").count()

    pending_order = Order.objects.filter(~Q(payment_status="paid")).only("id").count()
    completed_order = Order.objects.filter(payment_status="paid").only("id").count()

    # Aggregate directly
    amount_paid = (
        (
            Order.objects.filter(payment_status="paid").aggregate(
                total_paid=Sum("total_price")
            )["total_paid"]
        )
        or 0
    )

    context = {
        "user_count": user_count,
        "pending_order": pending_order,
        "completed_order": completed_order,
        "amount_paid": amount_paid,
        "google_maps_key": env.str("GOOGLE_MAPS_API_KEY"),
    }
    return render(request, template, context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
def user_subscriptions_list(request, user_id):
    # XHR only
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    # -------- Subscriptions (paginated: 5 per page) --------
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    # default to 5 per page, allow optional override but clamp to sensible range
    try:
        per_page = int(request.GET.get("per_page", 5))
    except (TypeError, ValueError):
        per_page = 5
    per_page = max(1, min(per_page, 50))  # safety clamp

    subs_qs = (
        Subscription.objects.filter(user_id=user_id)
        .select_related("plan", "order")
        .order_by("-started_at", "-id")
    )
    paginator = Paginator(subs_qs, per_page)
    page_obj = paginator.get_page(page)

    subscriptions_data = []
    for sub in page_obj.object_list:
        plan = sub.plan
        subscriptions_data.append(
            {
                "subscription_id": sub.id,
                "plan_id": plan.id if plan else None,
                "plan_name": plan.name if plan else "",
                "plan_type": plan.plan_type if plan else "",
                "data_cap_gb": plan.standard_data_gb if plan else None,
                "priority_data_gb": plan.priority_data_gb if plan else None,
                "price_usd": float(plan.effective_price)
                if (plan and plan.effective_price is not None)
                else 0.0,
                "status": sub.status,
                "billing_cycle": sub.billing_cycle,
                "start_date": sub.started_at.isoformat() if sub.started_at else "",
                "end_date": sub.ended_at.isoformat() if sub.ended_at else "",
                "next_billing_date": sub.next_billing_date.isoformat()
                if sub.next_billing_date
                else "",
                "order_reference": sub.order.order_reference if sub.order else "",
                "order_id": sub.order_id,
            }
        )

    # -------- Orders (not paginated; unchanged) --------
    orders_qs = (
        Order.objects.filter(user_id=user_id)
        .select_related("kit_inventory__kit", "plan")
        .prefetch_related("taxes")
        .order_by("-created_at", "-id")
    )

    orders_data = []
    for order in orders_qs:
        inv = order.kit_inventory
        kit = getattr(inv, "kit", None)
        plan = order.plan

        kit_price = (
            kit.base_price_usd
            if (kit and kit.base_price_usd is not None)
            else Decimal("0.00")
        )
        plan_price = (
            plan.effective_price
            if (plan and plan.effective_price is not None)
            else Decimal("0.00")
        )
        total_price = order.total_price or Decimal("0.00")

        vat = Decimal("0.00")
        exc = Decimal("0.00")
        for t in getattr(order, "taxes").all():
            kind = (t.kind or "").upper()
            if kind == "VAT":
                vat += t.amount or Decimal("0.00")
            elif kind == "EXCISE":
                exc += t.amount or Decimal("0.00")

        orders_data.append(
            {
                "order_id": order.id,
                "order_reference": order.order_reference,
                "status": order.status,
                "payment_status": order.payment_status,
                "payment_method": order.payment_method,
                "created_at": order.created_at.strftime("%Y-%m-%d %H:%M:%S")
                if order.created_at
                else "",
                "total_price": float(_qmoney(total_price)),
                "kit_inventory_id": inv.id if inv else None,
                "kit_number": inv.kit_number if inv else "",
                "kit_serial": inv.serial_number if inv else "",
                "kit_model": inv.model if inv else "",
                "kit_name": kit.name if kit else "",
                "kit_type": kit.kit_type if kit else "",
                "kit_price_usd": float(_qmoney(kit_price)),
                "plan_id": plan.id if plan else None,
                "plan_name": plan.name if plan else "",
                "plan_price_usd": float(_qmoney(plan_price)),
                "vat": float(_qmoney(vat)),
                "exc": float(_qmoney(exc)),
                "is_installed": order.is_installed,
                "installation_date": (
                    order.installation_date.strftime("%Y-%m-%d %H:%M:%S")
                    if order.installation_date
                    else ""
                ),
            }
        )

    return JsonResponse(
        {
            "success": True,
            # Subscriptions payload + pagination meta
            "subscriptions": subscriptions_data,
            "page": page_obj.number,
            "per_page": per_page,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page_obj.has_next(),
            "has_prev": page_obj.has_previous(),
            # Orders payload (not paginated)
            "orders": orders_data,
        }
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
@require_POST
@transaction.atomic
def register_customer(request):
    """
    Create a customer User and save Personal/Company KYC (with files),
    matching names from the new modal:
      - Common: first_name, last_name, full_name (hidden), email, phone, password/password_confirm,
                roles or roles_json, is_tax_exempt
      - Personal KYC: full_name_personal, date_of_birth, nationality, id_document_type,
                      document_number, id_issue_date, id_expiry_date, address_personal,
                      document_file (file)
      - Business KYC: representative_name, company_name, address_business, established_date,
                      business_sector, legal_status, rccm, nif, id_nat,
                      representative_id_file (file), company_documents (multiple files)
    """
    sales_agent = request.user  # for audit if needed

    # ---- Which KYC path? (default to personal) ----
    customer_type = (request.POST.get("kyc_type") or "personal").strip().lower()
    if customer_type not in {"personal", "business"}:
        return JsonResponse(
            {"success": False, "message": "Invalid KYC type."}, status=400
        )

    # ---- Account basics from Step 1 ----
    first_name = (request.POST.get("first_name") or "").strip()
    last_name = (request.POST.get("last_name") or "").strip()
    full_name_hidden = (request.POST.get("full_name") or "").strip()
    email = (request.POST.get("email") or "").strip().lower()
    username = (request.POST.get("username") or email or "").strip()
    phone_raw = (request.POST.get("phone") or "").strip()
    personal_document_number = (request.POST.get("document_number") or "").strip()
    nationality_value = (request.POST.get("nationality") or "").strip()
    visa_last_page_file = request.FILES.get("visa_last_page")

    # Passwords
    password = (request.POST.get("password") or "").strip()
    password_confirm = (request.POST.get("password_confirm") or "").strip()

    # Roles (JSON list) and tax status
    roles_raw = (
        request.POST.get("roles") or request.POST.get("roles_json") or '["customer"]'
    )
    try:
        roles = json.loads(roles_raw)
        if not isinstance(roles, list):
            roles = ["customer"]
    except Exception:
        roles = ["customer"]
    if "customer" not in roles:
        roles.append("customer")

    is_tax_exempt = str(request.POST.get("is_tax_exempt", "")).lower() in {
        "1",
        "true",
        "on",
        "yes",
    }

    # Derive full_name to store on User
    full_name = full_name_hidden or f"{first_name} {last_name}".strip()

    # ---- Basic validations ----
    if not full_name or not email or not phone_raw:
        return JsonResponse(
            {"success": False, "message": "Missing required fields."}, status=422
        )

    if password and password != password_confirm:
        return JsonResponse(
            {"success": False, "message": "Passwords do not match."}, status=422
        )

    # Unique email
    if User.objects.filter(email=email).exists():
        return JsonResponse(
            {"success": False, "message": _("Email already exists."), "field": "email"},
            status=409,
        )

    if username and User.objects.filter(username=username).exists():
        return JsonResponse(
            {
                "success": False,
                "message": _("Username already exists."),
                "field": "username",
            },
            status=409,
        )

    # Phone validation (normalize to E.164)
    try:
        parsed = phonenumbers.parse(phone_raw, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Invalid phone number")
        phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        print("Phone")
        print(parsed)
    except Exception:
        return JsonResponse(
            {
                "success": False,
                "message": _("Invalid phone number format."),
                "field": "phone",
            },
            status=422,
        )

    if User.objects.filter(phone=phone).exists():
        return JsonResponse(
            {
                "success": False,
                "message": _("Phone number already exists."),
                "field": "phone",
            },
            status=409,
        )

    needs_visa = (
        customer_type == "personal"
        and nationality_value
        and not nationality_value.lower().startswith("congol")
    )
    if needs_visa and not visa_last_page_file:
        return JsonResponse(
            {
                "success": False,
                "message": _(
                    "Please upload the last page of the visa for non-Congolese nationals."
                ),
                "field": "visa_last_page",
            },
            status=422,
        )

    if customer_type == "personal" and personal_document_number:
        if PersonalKYC.objects.filter(
            document_number__iexact=personal_document_number
        ).exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Document number already exists."),
                    "field": "document_number",
                },
                status=409,
            )

    # Ensure a password exists and meets minimal policy
    def _meets_policy(p: str) -> bool:
        return (
            len(p) >= 12
            and any(c.isupper() for c in p)
            and any(c.islower() for c in p)
            and any(c.isdigit() for c in p)
            and any(not c.isalnum() for c in p)
        )

    if not password or not _meets_policy(password):
        # fallback to a strong random that satisfies validators
        password = get_random_string(20) + "#A1a"

    # ---- Create User ----
    user = User.objects.create_user(
        username=username
        or email,  # even if USERNAME_FIELD=email, satisfy default manager
        email=email,
        password=password,
    )
    user.first_name = first_name
    user.last_name = last_name
    user.full_name = full_name
    user.phone = phone
    user.is_active = True
    user.is_verified = True
    user.roles = roles
    user.is_tax_exempt = is_tax_exempt
    user.save(
        update_fields=[
            "first_name",
            "last_name",
            "full_name",
            "phone",
            "is_active",
            "is_verified",
            "roles",
            "is_tax_exempt",
        ]
    )

    # ==== KYC capture ====
    if customer_type == "personal":
        # Fields
        full_name_personal = (
            request.POST.get("full_name_personal") or ""
        ).strip() or full_name
        date_of_birth = request.POST.get("date_of_birth")
        nationality = nationality_value
        id_document_type = (
            request.POST.get("id_document_type") or ""
        ).strip()  # voter_card/drivers_license/passport
        document_number = personal_document_number
        id_issue_date = request.POST.get("id_issue_date")
        id_expiry_date = request.POST.get("id_expiry_date")
        address_personal = (
            request.POST.get("address_personal") or request.POST.get("address") or ""
        ).strip()

        file_personal = request.FILES.get("document_file")
        visa_file = visa_last_page_file
        requires_visa = needs_visa

        kyc, created = PersonalKYC.objects.get_or_create(user=user)

        # Replace existing single file if present
        if (
            not created
            and kyc.document_file
            and default_storage.exists(kyc.document_file.name)
        ):
            try:
                default_storage.delete(kyc.document_file.name)
            except Exception:
                pass
        if (
            visa_file
            and not created
            and kyc.visa_last_page
            and default_storage.exists(kyc.visa_last_page.name)
        ):
            try:
                default_storage.delete(kyc.visa_last_page.name)
            except Exception:
                pass

        # Assign file
        if file_personal:
            kyc.document_file = file_personal
        if visa_file:
            kyc.visa_last_page = visa_file
        elif not requires_visa:
            kyc.visa_last_page = None

        # Dates
        def _parse_date(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date() if s else None
            except Exception:
                return None

        kyc.full_name = full_name_personal
        kyc.date_of_birth = _parse_date(date_of_birth)
        kyc.nationality = nationality
        kyc.id_document_type = id_document_type or None
        kyc.document_number = document_number
        kyc.id_issue_date = _parse_date(id_issue_date)
        kyc.id_expiry_date = _parse_date(id_expiry_date)
        kyc.address = address_personal
        kyc.submitted_at = timezone.now()
        kyc.status = PersonalKYC.Status.PENDING
        kyc.approved_by = None
        kyc.approved_at = None
        kyc.rejection_reason = ""
        kyc.remarks = ""
        kyc.save()

    else:
        # Business
        representative_name = (request.POST.get("representative_name") or "").strip()
        company_name = (request.POST.get("company_name") or "").strip()
        address_business = (
            request.POST.get("address_business") or request.POST.get("address") or ""
        ).strip()
        established_date = request.POST.get("established_date")
        business_sector = (request.POST.get("business_sector") or "").strip() or None
        legal_status = (request.POST.get("legal_status") or "").strip() or None
        rccm = (request.POST.get("rccm") or "").strip()
        nif = (request.POST.get("nif") or "").strip()
        id_nat = (request.POST.get("id_nat") or "").strip()

        rep_id_file = request.FILES.get("representative_id_file")
        company_docs = request.FILES.getlist("company_documents")  # multiple

        if not rep_id_file:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Please upload the representative ID document."),
                    "field": "representative_id_file",
                },
                status=422,
            )

        if not company_docs:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Please upload the company documents."),
                    "field": "company_documents",
                },
                status=422,
            )

        duplicate_checks = [
            ("rccm", rccm, _("This RCCM is already registered.")),
            ("nif", nif, _("This NIF is already registered.")),
            ("id_nat", id_nat, _("This ID Nat is already registered.")),
        ]
        for field_name, value, message in duplicate_checks:
            if (
                value
                and CompanyKYC.objects.filter(
                    **{f"{field_name}__iexact": value}
                ).exists()
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": message,
                        "field": field_name,
                    },
                    status=409,
                )

        kyc, created = CompanyKYC.objects.get_or_create(user=user)

        # Clean previous single-file fields and child docs if replacing
        if not created:
            if kyc.representative_id_file and default_storage.exists(
                kyc.representative_id_file.name
            ):
                try:
                    default_storage.delete(kyc.representative_id_file.name)
                except Exception:
                    pass
            if kyc.company_documents and default_storage.exists(
                kyc.company_documents.name
            ):
                try:
                    default_storage.delete(kyc.company_documents.name)
                except Exception:
                    pass
            # remove old document rows
            kyc.documents.all().delete()

        if rep_id_file:
            kyc.representative_id_file = rep_id_file
        if company_docs:
            # keep the first in legacy FileField for backward-compatibility
            kyc.company_documents = company_docs[0]

        def _parse_date(s):
            try:
                return datetime.strptime(s, "%Y-%m-%d").date() if s else None
            except Exception:
                return None

        kyc.representative_name = representative_name
        kyc.company_name = company_name
        kyc.address = address_business
        kyc.established_date = _parse_date(established_date)
        kyc.business_sector = business_sector
        kyc.legal_status = legal_status
        kyc.rccm = rccm
        kyc.nif = nif
        kyc.id_nat = id_nat
        kyc.submitted_at = timezone.now()
        kyc.status = CompanyKYC.Status.PENDING
        kyc.approved_by = None
        kyc.approved_at = None
        kyc.rejection_reason = ""
        kyc.remarks = ""
        try:
            kyc.save()
        except IntegrityError as exc:
            msg = str(exc)
            if "company_kyc_unique_rccm" in msg:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("This RCCM is already registered."),
                        "field": "rccm",
                    },
                    status=409,
                )
            if "company_kyc_unique_nif" in msg:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("This NIF is already registered."),
                        "field": "nif",
                    },
                    status=409,
                )
            if "company_kyc_unique_id_nat" in msg:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("This ID Nat is already registered."),
                        "field": "id_nat",
                    },
                    status=409,
                )
            raise

        # === IMPORTANT FIX ===
        # Your CompanyDocument.upload_to expects `instance.company_name`.
        # Since `instance` is CompanyDocument, we set that attribute before saving the file.
        for i, doc in enumerate(company_docs):
            doc_obj = CompanyDocument(
                company_kyc=kyc,
                document_name=(
                    f"Company Document {i+1}"
                    if len(company_docs) > 1
                    else "Company Document"
                ),
            )
            # Inject the attribute used by upload_to:
            doc_obj.company_name = kyc.company_name or "unknown_company"
            doc_obj.document = doc  # triggers upload_to
            if i > 0:
                doc_obj.document_type = f"other_{i+1}"
            try:
                doc_obj.save()
            except IntegrityError:
                transaction.set_rollback(True)
                return JsonResponse(
                    {
                        "success": False,
                        "message": _(
                            "Company document could not be saved. Please upload distinct files."
                        ),
                        "field": "company_documents",
                    },
                    status=409,
                )

    # ---- (Optional) send welcome email (kept as print for now) ----
    try:
        html = (
            f"<p>Hello {full_name},</p>"
            f"<p>Your account has been created.</p>"
            f"<p><strong>Email:</strong> {email}<br>"
            f"<strong>Password:</strong> {password}</p>"
        )
        print("[REGISTER OK] Welcome email body preview:")
        print(html)
        # TODO: use your email backend (SendGrid/etc.)
    except Exception as e:
        print(f"[Email warn] {e}")

    return JsonResponse(
        {"success": True, "message": "Customer registered and KYC submitted."}
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
def customer_list(request):
    """
    Hybrid pagination:
      - Page mode:   ?page=2[&per_page=5]
      - Cursor mode: ?after=<last_id_user>&limit=5[&q=...&status=Active|Inactive]

    Optimized and FIXED:
      - Use select_related() for reverse OneToOne KYC relations
      - Avoid only() (+ select_related) conflict by using defer() for heavyweight fields
      - Stable ordering by -id_user
    """
    # Base queryset
    qs = (
        User.objects.filter(is_staff=False)
        .select_related(
            "personnal_kyc", "company_kyc"
        )  # prefetch OneToOne in the same query
        # Safely exclude heavy/not-needed fields using defer() (does NOT conflict with select_related)
        .defer(
            "password",
            "last_login",
            "date_joined",
            "is_superuser",
            "user_permissions",
            "groups",
            # If you have large JSON/text fields on User, you can defer them too:
            # "roles",
        )
        .order_by("-id_user")
    )

    # ---- Optional filters ----
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    if q:
        qs = qs.filter(
            Q(full_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q)
        )
    if status in ("Active", "Inactive"):
        qs = qs.filter(is_active=(status == "Active"))

    # ---- Cursor mode ----
    after = request.GET.get("after")
    if after is not None:
        try:
            after_id = int(after)
            qs = qs.filter(id_user__lt=after_id)
        except (TypeError, ValueError):
            pass

        limit = int(request.GET.get("limit") or 10)
        limit = max(1, min(limit, 50))

        batch = list(qs[: limit + 1])
        has_more = len(batch) > limit
        items = batch[:limit]

        customers = [
            {
                "id": u.id_user,
                "full_name": u.full_name,
                "email": u.email,
                "phone": u.phone,
                "kyc_status": u.get_kyc_status(),  # safe now; relations are loaded
                "is_active": u.is_active,
                "subscriptions": [],
            }
            for u in items
        ]

        next_after = items[-1].id_user if (has_more and items) else None
        return JsonResponse(
            {
                "success": True,
                "mode": "cursor",
                "customers": customers,
                "has_more": has_more,
                "next_after": next_after,
                "limit": limit,
                "filters": {"q": q, "status": status},
            }
        )

    # ---- Page mode ----
    try:
        per_page = int(request.GET.get("per_page") or 10)
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(1, min(per_page, 50))

    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1

    paginator = Paginator(qs, per_page)
    try:
        page_obj = paginator.page(page)
    except Exception:
        # Empty page fallback with correct totals
        return JsonResponse(
            {
                "success": True,
                "mode": "page",
                "customers": [],
                "page": page,
                "per_page": per_page,
                "total_pages": paginator.num_pages,
                "total_count": paginator.count,
                "has_next": False,
                "has_previous": False,
                "filters": {"q": q, "status": status},
            }
        )

    customers = [
        {
            "id": u.id_user,
            "full_name": u.full_name,
            "email": u.email,
            "phone": u.phone,
            "kyc_status": u.get_kyc_status(),  # safe & fast
            "is_active": u.is_active,
            "subscriptions": [],
        }
        for u in page_obj.object_list
    ]

    return JsonResponse(
        {
            "success": True,
            "mode": "page",
            "customers": customers,
            "page": page,
            "per_page": per_page,
            "total_pages": paginator.num_pages,
            "total_count": paginator.count,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
            "filters": {"q": q, "status": status},
        }
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
def get_kits_dropdown(request):
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    # Annotate each kit with stock quantities based on movement types
    kits = StarlinkKit.objects.annotate(
        received=Count(
            "inventory_items__movements",
            filter=Q(inventory_items__movements__movement_type="received"),
        ),
        returned=Count(
            "inventory_items__movements",
            filter=Q(inventory_items__movements__movement_type="returned"),
        ),
        adjusted=Count(
            "inventory_items__movements",
            filter=Q(inventory_items__movements__movement_type="adjusted"),
        ),
        assigned=Count(
            "inventory_items__movements",
            filter=Q(inventory_items__movements__movement_type="assigned"),
        ),
        transferred=Count(
            "inventory_items__movements",
            filter=Q(inventory_items__movements__movement_type="transferred"),
        ),
        scrapped=Count(
            "inventory_items__movements",
            filter=Q(inventory_items__movements__movement_type="scrapped"),
        ),
    ).annotate(
        quantity=ExpressionWrapper(
            F("received")
            + F("returned")
            + F("adjusted")
            - F("assigned")
            - F("transferred")
            - F("scrapped"),
            output_field=IntegerField(),
        )
    )

    # Format results grouped by model
    kit_types = {}
    for kit in kits:
        model_key = kit.model.lower() if kit.model else "unknown"
        if model_key not in kit_types:
            kit_types[model_key] = []

        # Use base_price_usd as the kit price; fall back gracefully if missing
        price = getattr(kit, "base_price_usd", None) or 0

        kit_types[model_key].append(
            {
                "id": kit.id,
                "name": kit.name,
                "price_usd": float(price),
                "quantity": kit.quantity,
                "out_of_stock": kit.quantity <= 0,
            }
        )

    return JsonResponse({"kits": kit_types})


def _arr(data, key):
    """Return list for key supporting both 'key' and 'key[]'."""
    if f"{key}[]" in data:
        return [v for v in data.getlist(f"{key}[]")]
    vals = data.getlist(key)
    if vals:
        return vals
    v = data.get(key)
    return [v] if v not in (None, "") else []


def _coerce_len(lst, n):
    """Broadcast single value list to length n."""
    if not lst:
        return [None] * n
    if len(lst) == 1 and n > 1:
        return lst * n
    return lst


CYCLE_MAP = {
    "monthly": (1, "monthly"),
    "quarterly": (3, "quarterly"),
    "yearly": (12, "yearly"),
    "annual": (12, "yearly"),
    "annually": (12, "yearly"),
}


# ---- helper: base36 consolidated number ----
_CHARS36 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def _b36(n: int) -> str:
    if n == 0:
        return "0"
    out = []
    while n:
        n, i = divmod(n, 36)
        out.append(_CHARS36[i])
    return "".join(reversed(out))


def _gen_consolidated_number(max_tries: int = 5) -> str:
    """
    Returns a unique consolidated invoice number like: CI-LL2MBZQ9-7F3K
    - Base: current time in *milliseconds* (base36) for ordering
    - Suffix: 4 random base36 chars (≈1.6M combinations)
    - Retries up to max_tries against DB to avoid rare collisions.
    """

    # millisecond timestamp so IDs are time-sortable and denser than seconds
    ts_ms = int(time.time() * 1000)
    base = _b36(ts_ms)

    for _ in range(max_tries):
        # 4 random base36 chars (use secrets for cryptographic randomness)
        rnd = _b36(secrets.randbits(20)).rjust(4, "0")[:4]  # 2^20 ≈ 1,048,576 space
        code = f"CI-{base}-{rnd}"

        if not ConsolidatedInvoice.objects.filter(number=code).exists():
            return code

        # tiny backoff to change timestamp boundary in pathological stampedes
        time.sleep(0.001)

    # ultra-fallback: append extra randomness if we somehow failed max_tries
    tail = _b36(secrets.randbits(32)).rjust(6, "0")[:6]
    return f"CI-{base}-{tail}"


INVOICE_LINE_KIND_ITEM = (
    getattr(InvoiceLine, "Kind", None)
    and getattr(InvoiceLine.Kind, "ITEM", "item")
    or "item"
)


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
@require_POST
def submit_order_sales(request):
    """
    Creates one or many Orders, applies promos/coupons,
    issues per-order invoices OR one consolidated invoice,
    and (optionally) kicks a FlexPay mobile charge for single orders.
    """

    # Billing cycles map (robust to variants)
    CYCLE_MAP = {
        "monthly": (1, "monthly"),
        "quarterly": (3, "quarterly"),
        "yearly": (12, "yearly"),
        "annual": (12, "yearly"),
        "annually": (12, "yearly"),
    }

    sales_agent = request.user
    try:
        # ---------- 1) Inputs ----------
        email = (request.POST.get("email") or "").strip().lower()
        user = get_object_or_404(User, email=email)

        # Accept single or multiple values
        kit_ids = _arr(request.POST, "kit_id")
        plan_ids = _arr(request.POST, "subscription_plan_id")
        cycles_raw = _arr(request.POST, "billing_cycle")
        lats_raw = _arr(request.POST, "lat")
        lngs_raw = _arr(request.POST, "lng")

        # Optional shared fields
        coupon_code = (
            request.POST.get("coupon_code") or request.POST.get("coupon") or ""
        ).strip() or None
        payment_method = (request.POST.get("payment_method") or "").strip() or None
        phone = (request.POST.get("mobile_number") or "").strip() or None

        # Bulk / consolidated toggles
        consolidate_param = (
            (request.POST.get("consolidate") or request.POST.get("bulk") or "")
            .strip()
            .lower()
        )
        separate_param = (request.POST.get("separate") or "").strip().lower()

        # Optional per-order extras: services_0[], services_1[] ... OR shared services[]
        per_order_services = []
        has_indexed = False

        # First pass to see how many orders we will create
        n = max(
            len(kit_ids), len(plan_ids), len(cycles_raw), len(lats_raw), len(lngs_raw)
        )
        n = n or 1

        # Broadcast arrays to length n
        kit_ids = _coerce_len(kit_ids, n)
        plan_ids = _coerce_len(plan_ids, n)
        cycles_raw = _coerce_len(cycles_raw, n)
        lats_raw = _coerce_len(lats_raw, n)
        lngs_raw = _coerce_len(lngs_raw, n)

        for i in range(n):
            local = request.POST.getlist(f"services_{i}[]") or request.POST.getlist(
                f"services_{i}"
            )
            if local:
                has_indexed = True
                per_order_services.append(
                    [s for s in local if str(s).strip().isdigit()]
                )
            else:
                per_order_services.append([])

        if not has_indexed:
            shared = [
                s
                for s in request.POST.getlist("services[]")
                if str(s).strip().isdigit()
            ]
            if not shared:
                shared = [
                    s
                    for s in request.POST.getlist("services")
                    if str(s).strip().isdigit()
                ]
            per_order_services = [shared for _ in range(n)]

        # Decide bulk/consolidate
        is_bulk = n > 1
        consolidate = consolidate_param in ("1", "true", "yes") or (
            is_bulk and separate_param not in ("1", "true", "yes")
        )

        # ---------- 2) Per-order validation skeleton ----------
        items = []
        for i in range(n):
            raw_cycle = (cycles_raw[i] or "monthly").strip().lower()
            cycle_months, cycle_value = CYCLE_MAP.get(raw_cycle, (1, "monthly"))

            kit_id = (kit_ids[i] or "").strip()
            plan_id = (plan_ids[i] or "").strip()
            lat_s = (lats_raw[i] or "").strip()
            lng_s = (lngs_raw[i] or "").strip()

            if not kit_id:
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"[Item {i+1}] Please select a Starlink kit.",
                    },
                    status=400,
                )
            if not plan_id:
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"[Item {i+1}] Please select a subscription plan.",
                    },
                    status=400,
                )
            if not lat_s or not lng_s:
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"[Item {i+1}] Please select the installation address on the MAP.",
                    },
                    status=400,
                )

            try:
                lat = float(lat_s)
                lng = float(lng_s)
            except (TypeError, ValueError):
                return JsonResponse(
                    {"success": False, "message": f"[Item {i+1}] Invalid coordinates."},
                    status=400,
                )

            items.append(
                {
                    "i": i,
                    "kit_id": kit_id,
                    "plan_id": plan_id,
                    "cycle_months": cycle_months,
                    "cycle_value": cycle_value,
                    "lat": lat,
                    "lng": lng,
                    "service_ids": per_order_services[i],
                    "raw_cycle": raw_cycle,
                }
            )

        # ---------- 3) Process each order atomically (single transaction for the whole batch) ----------
        created_payload = []
        created_orders = []  # keep Order objects for consolidation
        created_invoices = []  # keep per-order Invoice objects when not consolidating
        expiry_hours = 1
        recent = timezone.now() - timedelta(seconds=30)
        using = "default"

        # Helper: build a draft invoice from an order then issue it
        def _create_issue_invoice_for_order(order):
            cs = CompanySettings.get()
            inv = Invoice.objects.using(using).create(
                user=order.user,
                currency=cs.default_currency or "USD",
                tax_regime=cs.tax_regime,
                vat_rate_percent=cs.vat_rate_percent,
                status=Invoice.Status.DRAFT,
                bill_to_name=(order.user.full_name or order.user.email or ""),
                bill_to_address="",  # fill from KYC if needed
            )
            # copy order lines to invoice lines
            for ol in order.lines.all():
                InvoiceLine.objects.using(using).create(
                    invoice=inv,
                    description=ol.description,
                    quantity=Decimal(ol.quantity or 1),
                    unit_price=ol.unit_price or ZERO,
                    kind=ol.kind,
                    order=order,
                    order_line=ol,
                )
            # link the order to this invoice (amount excl tax is the order subtotal)
            order_subtotal = sum(
                (
                    l.line_total
                    for l in order.lines.all()
                    if l.kind != OrderLine.Kind.ADJUST
                ),
                ZERO,
            )
            InvoiceOrder.objects.using(using).create(
                invoice=inv, order=order, amount_excl_tax=_qmoney(order_subtotal)
            )
            # issue (assign number via allocator, compute totals, ledger entry)
            return issue_invoice(inv)

        with transaction.atomic(using=using):
            for it in items:
                i = it["i"]
                lat = it["lat"]
                lng = it["lng"]
                cycle_months = it["cycle_months"]
                cycle_value = it["cycle_value"]

                # a) Fetch models
                kit = StarlinkKit.objects.filter(
                    id=it["kit_id"], is_active=True
                ).first()
                plan = SubscriptionPlan.objects.filter(
                    id=it["plan_id"], is_active=True
                ).first()
                if not kit:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": f"[Item {i+1}] Selected kit not found or inactive.",
                        },
                        status=400,
                    )
                if not plan:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": f"[Item {i+1}] Selected plan not found or inactive.",
                        },
                        status=400,
                    )

                # b) Expiry (1h, local tz from coords)
                try:
                    expires_at = compute_local_expiry_from_coords(
                        lat=lat, lng=lng, hours=expiry_hours
                    )
                except Exception:
                    expires_at = timezone.now() + timedelta(hours=expiry_hours)

                # c) Base prices
                kit_price = _qmoney(kit.base_price_usd or Decimal("0.00"))
                monthly_price = _qmoney(
                    plan.effective_price or plan.monthly_price_usd or Decimal("0.00")
                )
                plan_cycle_price = _qmoney(monthly_price * Decimal(cycle_months))

                # d) Install fee
                install_fee = installation_fee_for_coords(lat, lng)

                # e) Extras (services)
                service_ids = it["service_ids"] or []
                extras = (
                    list(
                        ExtraCharge.objects.filter(
                            id__in=service_ids, is_active=True
                        ).order_by("id")
                    )
                    if service_ids
                    else []
                )

                # f) Build draft lines (UNDISCOUNTED)
                draft_lines = []
                draft_lines.append(
                    DraftLine(
                        kind="kit",
                        description=f"{kit.name}",
                        quantity=1,
                        unit_price=kit_price,
                    )
                )
                plan_desc = f"{plan.name} – {cycle_value} ({cycle_months} mo)"
                draft_lines.append(
                    DraftLine(
                        kind="plan",
                        description=plan_desc,
                        quantity=1,
                        unit_price=plan_cycle_price,
                        plan_id=plan.id,
                    )
                )
                if install_fee > 0:
                    draft_lines.append(
                        DraftLine(
                            kind="install",
                            description="Installation fee",
                            quantity=1,
                            unit_price=install_fee,
                        )
                    )
                for ex in extras:
                    draft_lines.append(
                        DraftLine(
                            kind="extra",
                            description=ex.get_charge_type_display(),
                            quantity=1,
                            unit_price=_qmoney(ex.price_usd or Decimal("0.00")),
                            extra_charge_id=ex.id,
                        )
                    )

                # g) Apply promotions + optional coupon (pre-tax)
                disc_result = apply_promotions_and_coupon_to_draft_lines(
                    user=user if getattr(user, "pk", None) else None,
                    draft_lines=draft_lines,
                    coupon_code=coupon_code,
                )
                draft_lines_after = disc_result["lines"]  # includes ADJUST (negative)
                discount_pairs = disc_result["applied"]  # [(label, negative_amount)]
                coupon_obj = disc_result["coupon"]
                coupon_error = disc_result["coupon_error"]

                if coupon_code and coupon_error:
                    logger.info(
                        "[Item %s] Coupon provided but not applicable: %s",
                        i + 1,
                        coupon_error,
                    )

                # h) Anti-double submit for THIS location/order combo
                if Order.objects.filter(
                    user=user,
                    created_at__gte=recent,
                    status__in=["pending_payment", "awaiting_confirmation"],
                    latitude=lat,
                    longitude=lng,
                ).exists():
                    return JsonResponse(
                        {
                            "success": False,
                            "message": f"[Item {i+1}] An order is already being created for this location. Please wait.",
                        },
                        status=409,
                    )

                # i) Create atomically with inventory lock
                inv_qs = StarlinkKitInventory.objects.using(using).filter(
                    kit=kit, is_assigned=False, status__in=["available", ""]
                )
                inv_qs = (
                    inv_qs.select_for_update(skip_locked=True)
                    if _supports_skip_locked(using)
                    else inv_qs.select_for_update()
                )
                assigned_inventory = inv_qs.first()
                if not assigned_inventory:
                    raise ValidationError(
                        f"[Item {i+1}] No available inventory for the selected kit."
                    )

                # Order shell
                order = Order.objects.using(using).create(
                    user=user,
                    plan=plan,
                    kit_inventory=assigned_inventory,
                    latitude=lat,
                    longitude=lng,
                    status="pending_payment",
                    payment_status="unpaid",
                    payment_method=payment_method,
                    expires_at=expires_at,
                    created_by=sales_agent
                    if getattr(sales_agent, "pk", None)
                    else None,
                )

                # Logical reservation + movement
                reserve_inventory_for_order(
                    inv=assigned_inventory,
                    order=order,
                    planned_lat=lat,
                    planned_lng=lng,
                    hold_hours=expiry_hours,
                    by=(sales_agent if getattr(sales_agent, "pk", None) else None),
                    using=using,
                )

                # Persist selected extras to M2M
                if extras:
                    order.selected_extra_charges.add(*extras)

                # Persist lines (including ADJUST)
                for dl in draft_lines_after:
                    if dl.kind == "kit":
                        OrderLine.objects.using(using).create(
                            order=order,
                            kind=OrderLine.Kind.KIT,
                            description=dl.description,
                            quantity=dl.quantity,
                            unit_price=dl.unit_price,
                            kit_inventory=assigned_inventory,
                        )
                    elif dl.kind == "plan":
                        OrderLine.objects.using(using).create(
                            order=order,
                            kind=OrderLine.Kind.PLAN,
                            description=dl.description,
                            quantity=dl.quantity,
                            unit_price=dl.unit_price,
                            plan=plan,
                        )
                    elif dl.kind == "install":
                        OrderLine.objects.using(using).create(
                            order=order,
                            kind=OrderLine.Kind.INSTALL,
                            description=dl.description,
                            quantity=dl.quantity,
                            unit_price=dl.unit_price,
                        )
                    elif dl.kind == "extra":
                        ex = next(
                            (e for e in extras if e.id == dl.extra_charge_id), None
                        )
                        OrderLine.objects.using(using).create(
                            order=order,
                            kind=OrderLine.Kind.EXTRA,
                            description=dl.description,
                            quantity=dl.quantity,
                            unit_price=dl.unit_price,
                            extra_charge=ex,
                        )
                    elif dl.kind == "adjust":
                        OrderLine.objects.using(using).create(
                            order=order,
                            kind=OrderLine.Kind.ADJUST,
                            description=dl.description,
                            quantity=1,
                            unit_price=dl.unit_price,  # negative
                        )

                # Taxes & totals
                pricing = compute_totals_from_lines(order)
                final_total = _qmoney(Decimal(pricing["total"] or "0"))
                Order.objects.using(using).filter(pk=order.pk).update(
                    total_price=final_total
                )
                order.total_price = final_total

                # Subscription placeholder (inactive; billing alignment handled elsewhere)
                sub = Subscription.objects.using(using).create(
                    user=user,
                    plan=plan,
                    status="inactive",
                    billing_cycle=it["cycle_value"],
                    started_at=None,
                    next_billing_date=None,
                    last_billed_at=None,
                    order=order,
                )

                # Ledger adjustments for discounts (keep as before)
                if discount_pairs:
                    acct, _ = BillingAccount.objects.using(using).get_or_create(
                        user=user
                    )
                    for lbl, neg_amt in discount_pairs:  # neg_amt negative
                        AccountEntry.objects.using(using).create(
                            account=acct,
                            entry_type="adjustment",
                            amount_usd=_qmoney(Decimal(neg_amt)),
                            description=lbl,
                            order=order,
                            subscription=sub,
                            external_ref=(
                                f"COUPON:{(coupon_obj.code if coupon_obj else '')}"
                                if lbl.lower().startswith("coupon")
                                else (
                                    f"PROMO:{lbl.split(' ', 1)[-1]}"
                                    if lbl.lower().startswith("promotion")
                                    else ""
                                )
                            ),
                        )

                    if coupon_obj:
                        coupon_discount = sum(
                            (-amt)
                            for (lbl, amt) in discount_pairs
                            if lbl.lower().startswith("coupon")
                        )
                        if coupon_discount > 0:
                            CouponRedemption.objects.using(using).create(
                                coupon=coupon_obj,
                                user=user,
                                order=order,
                                subscription=sub,
                                discount_type=coupon_obj.discount_type,
                                value=(
                                    coupon_obj.percent_off
                                    if coupon_obj.discount_type == DiscountType.PERCENT
                                    else coupon_obj.amount_off
                                ),
                                discounted_amount=_qmoney(Decimal(coupon_discount)),
                            )

                # ⬇️ INVOICING (single)
                if final_total > 0 and not consolidate:
                    inv = _create_issue_invoice_for_order(
                        order
                    )  # safe numbering inside
                    created_invoices.append(inv)

                # Build response item
                taxes = list(
                    order.taxes.values("kind", "rate", "amount").order_by("kind")
                )
                lines = list(
                    order.lines.values(
                        "kind", "description", "quantity", "unit_price", "line_total"
                    )
                )

                install_fee_str = ""
                try:
                    il = next(
                        (l for l in lines if l["kind"] == OrderLine.Kind.INSTALL), None
                    )
                    if il:
                        install_fee_str = str(il["unit_price"])
                except Exception:
                    pass

                created_payload.append(
                    {
                        "id": order.order_reference,
                        "expires_at": order.expires_at.isoformat()
                        if order.expires_at
                        else None,
                        "latitude": order.latitude,
                        "longitude": order.longitude,
                        "billing_cycle": {
                            "raw": it["raw_cycle"] or "monthly",
                            "value": it["cycle_value"],
                            "months": it["cycle_months"],
                        },
                        "coupon_code": coupon_code or "",
                        "lines": [
                            {
                                "kind": l["kind"],
                                "description": l["description"],
                                "quantity": str(l["quantity"]),
                                "unit_price": str(l["unit_price"]),
                                "line_total": str(l["line_total"]),
                            }
                            for l in lines
                        ],
                        "taxes": [
                            {
                                "kind": t["kind"],
                                "rate": str(t["rate"]),
                                "amount": str(t["amount"]),
                            }
                            for t in taxes
                        ],
                        "subtotal": str(
                            _qmoney(
                                sum(
                                    Decimal(x["line_total"])
                                    for x in lines
                                    if x["kind"] != OrderLine.Kind.ADJUST
                                )
                            )
                        ),
                        "tax_total": str(
                            _qmoney(sum(Decimal(x["amount"]) for x in taxes))
                        ),
                        "total_price": str(order.total_price or "0.00"),
                        "install_fee": install_fee_str,
                        "discounts": [
                            {"label": lbl, "amount": str(amt)}
                            for (lbl, amt) in discount_pairs
                        ],
                        "coupon_applied": bool(coupon_obj),
                        "coupon_error": coupon_error or "",
                    }
                )

                created_orders.append(order)

            # ---------- 3.b) If consolidating: create ONE invoice that covers all orders ----------
            consolidated_block = None
            if consolidate and created_orders:
                inv, cons = create_consolidated_invoice(
                    user=user, orders=created_orders, using=using
                )
                order_refs = [o.order_reference or str(o.pk) for o in created_orders]
                consolidated_block = {
                    "number": inv.number,
                    "total": str(inv.grand_total),
                    "currency": inv.currency,
                    "orders": order_refs,
                }

        # ---------- 4) Optional FlexPay (only if a single order + valid phone + not consolidated) ----------
        if phone and len(created_payload) == 1 and not consolidate:
            if phone.startswith("0") and len(phone) == 10:
                formatted_phone = "243" + phone[1:]
            elif phone.startswith("243") and len(phone) == 12:
                formatted_phone = phone
            else:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Invalid phone number. It must start with 0XXXXXXXXX or 243XXXXXXXXX and total 10 or 12 digits.",
                    },
                    status=400,
                )

            try:
                payload0 = created_payload[0]
                flexpay_url = settings.FLEXPAY_MOBILE_URL
                flexpay_merchant = settings.FLEXPAY_MERCHANT_ID
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {settings.FLEXPAY_API_KEY}",
                }
                order_ref = payload0["id"]
                order = Order.objects.get(order_reference=order_ref)

                payload = {
                    "merchant": flexpay_merchant,
                    "type": "1",
                    "phone": formatted_phone,
                    "reference": order.order_reference,
                    "amount": str(order.total_price or "0.00"),
                    "currency": "USD",
                    "callbackUrl": request.build_absolute_uri(
                        reverse("flexpay_callback_mobile")
                    ),
                }
                resp = requests.post(
                    flexpay_url, json=payload, headers=headers, timeout=30
                )
                data = resp.json() if resp.content else {}
                if resp.status_code == 200 and data.get("status") == "success":
                    return JsonResponse(
                        {
                            "success": True,
                            "message": "FlexPay request sent successfully.",
                            "orders": created_payload,
                            "transaction_id": data.get("transid"),
                            "consolidated_invoice": None,
                        }
                    )
            except Exception:
                # If FlexPay request fails, still return success for order creation
                pass

        # ---------- 5) Success ----------
        return JsonResponse(
            {
                "success": True,
                "message": (
                    "Order(s) submitted successfully."
                    if not consolidate
                    else "Bulk order submitted with a consolidated invoice."
                ),
                "orders": created_payload,
                "consolidated_invoice": consolidated_block if consolidate else None,
            }
        )

    except User.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "User not found."}, status=404
        )
    except ValidationError as ve:
        return JsonResponse({"success": False, "message": str(ve)}, status=400)
    except (IntegrityError, DatabaseError) as e:
        logger.error("DB error in submit_order_sales: %s", e, exc_info=True)
        return JsonResponse(
            {"success": False, "message": "Database error. Please try again."},
            status=500,
        )
    except Exception as e:
        logger.error("Unexpected error in submit_order_sales: %s", e, exc_info=True)
        return JsonResponse(
            {
                "success": False,
                "message": "An unexpected error occurred. Please try again later.",
            },
            status=500,
        )


def _q2(x: Decimal) -> str:
    return f"{(x or ZERO):.2f}"


@login_required
def get_subscription_billing(request, subscription_id):
    """
    Return billing rows for a subscription with the *exact* order.payment_status
    on the 'status' field, while also returning helpful context:

      - invoice_status: computed status for the period invoice (paid / partially_paid / unpaid)
      - attempt_status: raw PaymentAttempt.status for payment/credit rows (or 'applied')
      - payment_status: exact Order.payment_status tied to that row's order (fallback: subscription.order)

    The UI can use 'status' to display the exact order payment_status as requested.
    """
    try:
        subscription = get_object_or_404(Subscription, id=subscription_id)
        user = subscription.user
        plan = subscription.plan
        sub_order = subscription.order  # may be None

        # ---- Helpers ---------------------------------------------------------
        def get_order_payment_status(order_like):
            """Safely fetch a lowercased payment_status from an order-like object."""
            ps = (getattr(order_like, "payment_status", None) or "").strip()
            return ps.lower() if ps else ""

        def pick_period_order_payment_status(qs_period, fallback_order):
            """
            From entries in the same period, pick *an* order (if any) to read payment_status.
            Otherwise fall back to subscription.order (if any).
            """
            period_o = (
                qs_period.exclude(order__isnull=True)
                .values_list("order__payment_status", flat=True)
                .first()
            )
            if period_o:
                return (period_o or "").strip().lower()
            return get_order_payment_status(fallback_order)

        # ---- Reference amounts (plan monthly price + tax preview) -----------
        plan_price = (
            plan.effective_price
            if (plan and plan.effective_price) is not None
            else ZERO
        )

        vat_rate = TaxRate.objects.filter(description__iexact="VAT").first()
        excise_rate = TaxRate.objects.filter(description__iexact="EXCISE").first()
        vat_pct = (vat_rate.percentage / 100) if vat_rate else Decimal("0.00")
        excise_pct = (excise_rate.percentage / 100) if excise_rate else Decimal("0.00")

        vat_amount = ZERO
        excise_amount = ZERO
        total_with_tax = plan_price
        if plan_price > 0 and not getattr(user, "is_tax_exempt", False):
            excise_amount = plan_price * excise_pct
            # If VAT policy is (base + excise), keep consistent:
            vat_amount = (plan_price + excise_amount) * vat_pct
            total_with_tax = plan_price + excise_amount + vat_amount

        # ---- Gather all ledger entries for this subscription ----------------
        qs = (
            AccountEntry.objects.filter(subscription=subscription)
            .select_related("order", "payment")
            .order_by("-created_at")
        )

        rows = []

        # 1) Index of (period_start, period_end) to compute invoice status
        period_keys = set(
            qs.exclude(period_start__isnull=True, period_end__isnull=True).values_list(
                "period_start", "period_end"
            )
        )

        def period_sums(p_start, p_end):
            p_qs = qs.filter(period_start=p_start, period_end=p_end)
            billed = (
                p_qs.filter(entry_type__in=["invoice", "tax", "adjustment"]).aggregate(
                    s=Sum("amount_usd")
                )["s"]
                or ZERO
            )
            credits = (
                p_qs.filter(entry_type__in=["payment", "credit_note"]).aggregate(
                    s=Sum("amount_usd")
                )["s"]
                or ZERO
            )
            net = billed + credits
            display_billed = billed if billed > 0 else ZERO
            return (
                display_billed,
                net,
                p_qs,
            )  # also return the period queryset for status lookups

        # 2) Emit one invoice row per period (status = exact order.payment_status)
        for p_start, p_end in sorted(period_keys, reverse=True):
            billed_amt, net_amt, p_qs = period_sums(p_start, p_end)
            if billed_amt == ZERO:
                continue

            # Computed invoice status (kept for reference)
            if net_amt <= 0:
                invoice_status = "paid"
            elif ZERO < net_amt < billed_amt:
                invoice_status = "partially_paid"
            else:
                invoice_status = "unpaid"

            # For display status: use the exact order.payment_status from any order in this period,
            # else from the subscription's order, else ''
            order_payment_status = pick_period_order_payment_status(p_qs, sub_order)

            # Choose an order_ref/id to show (period order first, else subscription.order)
            period_order_tuple = (
                p_qs.exclude(order__isnull=True)
                .values_list("order__order_reference", "order__id")
                .first()
            )
            order_ref, oid = period_order_tuple or (
                getattr(sub_order, "order_reference", None),
                getattr(sub_order, "id", None),
            )

            rows.append(
                {
                    "id": f"inv-{p_start}-{p_end}",
                    "amount": _q2(billed_amt),
                    # REQUIRED: exact order payment_status goes to 'status'
                    "status": order_payment_status or "",
                    # Extras for reference / UI if needed
                    "invoice_status": invoice_status,  # computed per-period invoice status
                    "attempt_status": "",  # not applicable to invoices
                    "payment_status": order_payment_status or "",
                    "payment_type": "Invoice",
                    "payment_for": "subscription",
                    "created_at": (p_start.strftime("%Y-%m-%d") if p_start else "—"),
                    "invoice_id": f"{p_start or ''}_{p_end or ''}",
                    "order_reference": order_ref or "-",
                    "order_id": oid,
                }
            )

        # 3) Payment/credit rows (status = exact order.payment_status; attempt_status kept)
        for e in qs:
            if e.entry_type not in {"payment", "credit_note"}:
                continue

            pa = getattr(e, "payment", None)
            attempt_status = (pa.status or "").strip().lower() if pa else "applied"

            # Determine which order to read payment_status from
            row_order = e.order if e.order else sub_order
            order_payment_status = get_order_payment_status(row_order)

            # Friendly payment type label
            if pa and pa.payment_type:
                pt = (pa.payment_type or "").strip().lower()
                if pt == "mobile":
                    ptype = "Mobile Money"
                elif pt == "card":
                    ptype = "Card Payment"
                elif pt == "cash":
                    ptype = "Cash"
                elif pt == "terminal":
                    ptype = "Terminal"
                else:
                    ptype = pa.payment_type
            else:
                ptype = "Credit" if e.entry_type == "credit_note" else "Payment"

            created_ts = (
                e.created_at.strftime("%Y-%m-%d %H:%M") if e.created_at else "—"
            )
            order_ref = (
                e.order.order_reference
                if e.order
                else (sub_order.order_reference if sub_order else None)
            )
            oid = e.order.id if e.order else (sub_order.id if sub_order else None)

            rows.append(
                {
                    "id": e.id,
                    "amount": _q2(abs(e.amount_usd or ZERO)),  # show positive
                    # REQUIRED: exact order payment_status goes to 'status'
                    "status": order_payment_status or "",
                    # Extras for reference / UI if needed
                    "invoice_status": "",  # not applicable to payments
                    "attempt_status": attempt_status,  # raw PaymentAttempt.status
                    "payment_status": order_payment_status or "",
                    "payment_type": ptype,
                    "payment_for": (
                        pa.payment_for if pa and pa.payment_for else "subscription"
                    ),
                    "created_at": created_ts,
                    "invoice_id": e.id,  # placeholder for invoice button link
                    "order_reference": order_ref or "-",
                    "order_id": oid,
                }
            )

        # Fallback: no ledger rows — use PaymentAttempt from the linked order (if any)
        if not rows and sub_order:
            attempts = (
                PaymentAttempt.objects.filter(order=sub_order)
                .order_by("-created_at")
                .select_related("order")
            )
            sub_order_ps = get_order_payment_status(sub_order)
            for p in attempts:
                rows.append(
                    {
                        "id": p.id,
                        "amount": _q2(total_with_tax),  # preview amount
                        "status": sub_order_ps,  # exact order.payment_status
                        "invoice_status": "",
                        "attempt_status": (p.status or "").strip().lower() or "unknown",
                        "payment_status": sub_order_ps,
                        "payment_type": p.payment_type or "-",
                        "payment_for": p.payment_for or "subscription",
                        "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")
                        if p.created_at
                        else "—",
                        "invoice_id": p.id,
                        "order_reference": sub_order.order_reference or "-",
                        "order_id": sub_order.id,
                    }
                )

        payment_for_choices = list(
            PaymentAttempt._meta.get_field("payment_for").choices
        )
        payment_type_choices = list(
            PaymentAttempt._meta.get_field("payment_type").choices
        )

        return JsonResponse(
            {
                "success": True,
                "payments": rows,  # each row has .status = exact order.payment_status
                "payment_for_choices": payment_for_choices,
                "payment_type_choices": payment_type_choices,
                "total_items": len(rows),
                # reference (monthly) for summary chip
                "subscription_plan_price": _q2(plan_price),
                "vat_amount": _q2(vat_amount),
                "excise_amount": _q2(excise_amount),
                "total_with_tax": _q2(total_with_tax),
                "tax_exempt": bool(getattr(user, "is_tax_exempt", False)),
            }
        )

    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"An unexpected error occurred: {str(e)}"},
            status=500,
        )


@login_required
def customer_details(request, customer_id: int):
    """
    Returns customer details + KYC (Personal or Company) based on your models.
    Works with PrivateMediaStorage by exposing filenames/flags (not public URLs).
    """
    if (
        request.method != "GET"
        or request.headers.get("X-Requested-With") != "XMLHttpRequest"
    ):
        # Keep this endpoint AJAX-only to match your frontend usage.
        raise Http404()

    customer = get_object_or_404(User, pk=customer_id)

    # Base customer block
    payload = {
        "id": customer.id_user if hasattr(customer, "id_user") else customer.id,
        "full_name": customer.full_name,
        "email": customer.email,
        "phone": customer.phone,
        "is_active": bool(customer.is_active),
        "kyc_status": customer.get_kyc_status(),
    }

    kyc_type = None
    kyc_payload = {}

    # PERSONAL KYC (note the related_name: personnal_kyc)
    if hasattr(customer, "personnal_kyc") and customer.personnal_kyc:
        k = customer.personnal_kyc
        kyc_type = "personal"
        kyc_payload = {
            "status": k.status,
            "submitted_at": _dt(k.submitted_at),
            "approved_at": _dt(k.approved_at),
            "approved_by": (k.approved_by.full_name if k.approved_by else None),
            "rejected_at": _dt(getattr(k, "rejected_at", None)),
            "rejected_at_iso": (
                localtime(k.rejected_at).isoformat()
                if getattr(k, "rejected_at", None)
                else ""
            ),
            "rejected_by": (
                getattr(getattr(k, "rejected_by", None), "full_name", None)
                if getattr(k, "rejected_by", None)
                else None
            ),
            "rejection_reason": getattr(k, "rejection_reason", "") or "",
            "rejection_reason_display": (
                k.get_rejection_reason_display()
                if getattr(k, "rejection_reason", None)
                else ""
            ),
            "remarks": k.remarks or "",
            "full_name": k.full_name or customer.full_name,
            "address": k.address,
            "document_number": k.document_number,
            "date_of_birth": (
                k.date_of_birth.strftime("%Y-%m-%d") if k.date_of_birth else None
            ),
            "nationality": k.nationality,
            "id_document_type": k.id_document_type,
            "id_issue_date": (
                k.id_issue_date.strftime("%Y-%m-%d") if k.id_issue_date else None
            ),
            "id_expiry_date": (
                k.id_expiry_date.strftime("%Y-%m-%d") if k.id_expiry_date else None
            ),
            # do not expose private file URL; just indicate presence + filename
            "document_available": bool(k.document_file),
            "document_name": (
                os.path.basename(k.document_file.name) if k.document_file else None
            ),
            "visa_available": bool(getattr(k, "visa_last_page", None)),
            "visa_name": (
                os.path.basename(k.visa_last_page.name)
                if getattr(k, "visa_last_page", None)
                else None
            ),
        }

    # COMPANY KYC
    elif hasattr(customer, "company_kyc") and customer.company_kyc:
        k = customer.company_kyc
        kyc_type = "company"

        # Get all company documents
        company_documents = k.documents.all()
        documents_data = [
            {
                "name": doc.document_name or f"Document {i+1}",
                "filename": (
                    os.path.basename(doc.document.name) if doc.document else None
                ),
                "uploaded_at": _dt(doc.uploaded_at),
            }
            for i, doc in enumerate(company_documents)
        ]

        kyc_payload = {
            "status": k.status,
            "submitted_at": _dt(k.submitted_at),
            "approved_at": _dt(k.approved_at),
            "approved_by": (k.approved_by.full_name if k.approved_by else None),
            "rejected_at": _dt(getattr(k, "rejected_at", None)),
            "rejected_at_iso": (
                localtime(k.rejected_at).isoformat()
                if getattr(k, "rejected_at", None)
                else ""
            ),
            "rejected_by": (
                getattr(getattr(k, "rejected_by", None), "full_name", None)
                if getattr(k, "rejected_by", None)
                else None
            ),
            "rejection_reason": getattr(k, "rejection_reason", "") or "",
            "rejection_reason_display": (
                k.get_rejection_reason_display()
                if getattr(k, "rejection_reason", None)
                else ""
            ),
            "remarks": k.remarks or "",
            "company_name": k.company_name,
            "address": k.address,
            "rccm": k.rccm,
            "nif": k.nif,
            "id_nat": k.id_nat,
            "representative_name": k.representative_name,
            # indicate presence + filenames for private files
            "rep_id_available": bool(k.representative_id_file),
            "rep_id_name": (
                os.path.basename(k.representative_id_file.name)
                if k.representative_id_file
                else None
            ),
            # Legacy single document field for backward compatibility
            "company_docs_available": bool(k.company_documents),
            "company_docs_name": (
                os.path.basename(k.company_documents.name)
                if k.company_documents
                else None
            ),
            # New multiple documents field
            "multiple_documents": documents_data,
            "documents_count": len(documents_data),
        }

    return JsonResponse(
        {
            "success": True,
            "customer": {**payload, "kyc_type": kyc_type, "kyc": kyc_payload},
        }
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "manager", "sales", "finance"])
@require_POST
@transaction.atomic
def resubmit_personal_kyc(request, customer_id):
    customer = get_object_or_404(User, pk=customer_id)

    kyc = getattr(customer, "personnal_kyc", None)
    if not kyc:
        kyc = PersonalKYC.objects.create(user=customer)

    full_name = (request.POST.get("full_name") or "").strip()
    date_of_birth = request.POST.get("date_of_birth")
    nationality = (request.POST.get("nationality") or "").strip()
    id_document_type = (request.POST.get("id_document_type") or "").strip()
    document_number = (request.POST.get("document_number") or "").strip()
    id_issue_date = request.POST.get("id_issue_date")
    id_expiry_date = request.POST.get("id_expiry_date")
    address = (request.POST.get("address") or "").strip()
    document_file = request.FILES.get("document_file")
    visa_file = request.FILES.get("visa_file")

    needs_visa = bool(nationality) and not nationality.lower().startswith("congol")

    field_labels = {
        "full_name": _("Full name"),
        "date_of_birth": _("Date of birth"),
        "nationality": _("Nationality"),
        "id_document_type": _("ID document type"),
        "document_number": _("Document number"),
        "id_issue_date": _("Issue date"),
        "id_expiry_date": _("Expiry date"),
        "address": _("Address"),
        "document_file": _("ID document"),
        "visa_file": _("Visa page"),
    }

    if not full_name:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["full_name"]},
                "field": "full_name",
            },
            status=422,
        )
    if not date_of_birth:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["date_of_birth"]},
                "field": "date_of_birth",
            },
            status=422,
        )
    if not nationality:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["nationality"]},
                "field": "nationality",
            },
            status=422,
        )
    if not id_document_type:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["id_document_type"]},
                "field": "id_document_type",
            },
            status=422,
        )
    if not document_number:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["document_number"]},
                "field": "document_number",
            },
            status=422,
        )
    if not id_issue_date or not id_expiry_date:
        missing_field = "id_issue_date" if not id_issue_date else "id_expiry_date"
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels[missing_field]},
                "field": missing_field,
            },
            status=422,
        )
    if not address:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["address"]},
                "field": "address",
            },
            status=422,
        )
    if not document_file and not kyc.document_file:
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["document_file"]},
                "field": "document_file",
            },
            status=422,
        )
    if needs_visa and not visa_file and not getattr(kyc, "visa_last_page", None):
        return JsonResponse(
            {
                "success": False,
                "message": _("%(field)s is required.")
                % {"field": field_labels["visa_file"]},
                "field": "visa_file",
            },
            status=422,
        )

    # Parse dates
    try:
        dob_dt = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
        issue_dt = datetime.strptime(id_issue_date, "%Y-%m-%d").date()
        expiry_dt = datetime.strptime(id_expiry_date, "%Y-%m-%d").date()
    except ValueError:
        return JsonResponse(
            {
                "success": False,
                "message": _("Invalid date format. Use YYYY-MM-DD."),
                "field": "date_of_birth",
            },
            status=422,
        )

    if expiry_dt <= issue_dt:
        return JsonResponse(
            {
                "success": False,
                "message": _("Expiry date must be after issue date."),
                "field": "id_expiry_date",
            },
            status=422,
        )

    if dob_dt >= timezone.localdate():
        return JsonResponse(
            {
                "success": False,
                "message": _("Date of birth must be in the past."),
                "field": "date_of_birth",
            },
            status=422,
        )

    # Uniqueness checks
    if (
        document_number
        and PersonalKYC.objects.filter(document_number__iexact=document_number)
        .exclude(pk=kyc.pk)
        .exists()
    ):
        return JsonResponse(
            {
                "success": False,
                "message": _("This document number is already registered."),
                "field": "document_number",
            },
            status=409,
        )

    # Replace files if new ones provided
    if document_file:
        if kyc.document_file and default_storage.exists(kyc.document_file.name):
            default_storage.delete(kyc.document_file.name)
        kyc.document_file = document_file

    if visa_file:
        if getattr(kyc, "visa_last_page", None) and default_storage.exists(
            kyc.visa_last_page.name
        ):
            default_storage.delete(kyc.visa_last_page.name)
        kyc.visa_last_page = visa_file
    elif not needs_visa and getattr(kyc, "visa_last_page", None):
        if default_storage.exists(kyc.visa_last_page.name):
            default_storage.delete(kyc.visa_last_page.name)
        kyc.visa_last_page = None

    kyc.full_name = full_name
    kyc.date_of_birth = dob_dt
    kyc.nationality = nationality
    kyc.id_document_type = id_document_type
    kyc.document_number = document_number
    kyc.id_issue_date = issue_dt
    kyc.id_expiry_date = expiry_dt
    kyc.address = address
    kyc.submitted_at = timezone.now()
    kyc.status = PersonalKYC.Status.PENDING
    kyc.approved_by = None
    kyc.approved_at = None
    kyc.rejection_reason = ""
    kyc.rejected_at = None
    kyc.rejected_by = None
    kyc.remarks = ""
    kyc.save()

    if full_name and full_name != customer.full_name:
        customer.full_name = full_name
        customer.save(update_fields=["full_name"])

    return JsonResponse(
        {
            "success": True,
            "message": _("KYC resubmitted successfully."),
        },
        status=200,
    )
