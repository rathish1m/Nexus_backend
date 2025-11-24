import glob
import json
import logging
import os
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from io import BytesIO
from os import environ
from types import SimpleNamespace

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

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.contrib.staticfiles import finders
from django.core.cache import cache
from django.core.exceptions import FieldError, PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.paginator import EmptyPage, Paginator
from django.db import DatabaseError, IntegrityError, connections, transaction
from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

# AJAX endpoint: retourne le statut KYC de l'utilisateur connecté
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.timezone import make_aware
from django.utils.translation import gettext as _
from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from client_app.client_helpers import (
    _get_billing_overview,
    _get_user_kyc,
    _is_success_status,
    _qmoney,
    _supports_skip_locked,
    compute_local_expiry_from_coords,
    installation_fee_for_coords,
    price_order_from_lines,
)
from feedbacks.models import Feedback
from feedbacks.serializers import FeedbackSerializer
from geo_regions.models import Region
from main.calculations import _fmt_date, _to_float
from main.invoices_helpers import issue_invoice
from main.models import (
    AccountEntry,
    BillingAccount,
    CompanyDocument,
    CompanyKYC,
    CompanySettings,
    CouponRedemption,
    DiscountType,
    ExtraCharge,
    InstallationActivity,
    Invoice,
    InvoiceLine,
    InvoiceOrder,
    Order,
    OrderLine,
    OrderTax,
    PaymentAttempt,
    PersonalKYC,
    StarlinkKit,
    StarlinkKitInventory,
    StarlinkKitMovement,
    StockLocation,
    Subscription,
    SubscriptionPlan,
    TaxRate,
    Ticket,
    User,
    UserPreferences,
)
from main.utilities.pricing_helpers import (
    DraftLine,
    apply_promotions_and_coupon_to_draft_lines,
)
from main.utilities.taxing import compute_totals_from_lines
from user.auth import customer_nonstaff_required, require_full_login
from user.erase_account_data import erase_user_personal_data


@require_POST
@customer_nonstaff_required
def delete_company_document(request):
    import json

    user = request.user
    try:
        data = json.loads(request.body)
        doc_id = data.get("doc_id")
        if not doc_id:
            return JsonResponse(
                {"success": False, "message": "ID du document manquant."}
            )
        doc = CompanyDocument.objects.filter(id=doc_id, company_kyc__user=user).first()
        if not doc:
            return JsonResponse({"success": False, "message": "Document introuvable."})
        doc.delete()
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


@require_POST
@customer_nonstaff_required
def delete_company_rep_id(request):
    user = request.user
    try:
        company_kyc = CompanyKYC.objects.filter(user=user).first()
        if not company_kyc or not company_kyc.representative_id_file:
            return JsonResponse(
                {"success": False, "message": "Aucun fichier à supprimer."}
            )
        company_kyc.representative_id_file.delete(save=True)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


@require_POST
@customer_nonstaff_required
def delete_personal_document(request):
    user = request.user
    try:
        personal_kyc = PersonalKYC.objects.filter(user=user).first()
        if not personal_kyc or not personal_kyc.document_file:
            return JsonResponse(
                {"success": False, "message": "Aucun fichier à supprimer."}
            )
        personal_kyc.document_file.delete(save=True)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


@require_POST
@customer_nonstaff_required
def delete_personal_visa(request):
    user = request.user
    try:
        personal_kyc = PersonalKYC.objects.filter(user=user).first()
        if not personal_kyc or not personal_kyc.visa_last_page:
            return JsonResponse(
                {"success": False, "message": "Aucun fichier visa à supprimer."}
            )
        personal_kyc.visa_last_page.delete(save=True)
        return JsonResponse({"success": True})
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)})


@require_full_login
@customer_nonstaff_required
@ensure_csrf_cookie
def feedback_view(request, job_id: int):
    installation = get_object_or_404(
        InstallationActivity.objects.select_related("order", "feedback"),
        pk=job_id,
        order__user=request.user,
    )
    feedback_instance = getattr(installation, "feedback", None)
    serializer_context = {"request": request}
    feedback_data = (
        FeedbackSerializer(feedback_instance, context=serializer_context).data
        if feedback_instance
        else None
    )
    errors = {}

    if request.method == "POST":
        payload = {
            "job_id": job_id,
            "rating": request.POST.get("rating"),
            "comment": request.POST.get("comment", ""),
        }
        serializer = FeedbackSerializer(data=payload, context=serializer_context)
        is_valid = serializer.is_valid()
        if is_valid:
            try:
                with transaction.atomic():
                    serializer.save()
                messages.success(
                    request,
                    _("Thank you! Your feedback has been saved."),
                )
                return redirect("client_feedback_detail", job_id=job_id)
            except Exception as exc:
                errors["__all__"] = [_("An error occurred while saving: %s") % exc]
        else:
            errors = serializer.errors
            messages.error(request, _("Please correct the highlighted errors."))
        feedback_data = payload

    can_edit = True
    edit_until = None
    if feedback_instance:
        serialized = FeedbackSerializer(
            feedback_instance, context=serializer_context
        ).data
        feedback_data = serialized
        can_edit = serialized.get("can_edit", False)
        edit_until = serialized.get("editable_until")
    else:
        can_edit = True

    order = installation.order
    return render(
        request,
        "client_app/feedback_form.html",
        {
            "installation": installation,
            "order": order,
            "feedback": feedback_data,
            "feedback_obj": feedback_instance,
            "errors": errors,
            "can_edit": can_edit,
            "edit_until": edit_until,
            "rating_options": range(1, 6),
        },
    )


# Set up logger for this module
logger = logging.getLogger(__name__)


@require_full_login
@customer_nonstaff_required
@ensure_csrf_cookie
def get_kyc_status(request):
    user = request.user.username
    user = User.objects.get(username=user)
    kyc_status = "Not submitted"
    kyc_rejection_reason = ""
    kyc_rejection_details = ""
    kyc_data = {}
    if hasattr(user, "personnal_kyc") and user.personnal_kyc:
        kyc_status = user.personnal_kyc.status
        if kyc_status == "rejected":
            kyc_rejection_reason = user.personnal_kyc.get_rejection_reason_display()
            kyc_rejection_details = user.personnal_kyc.remarks or ""

            kyc_data = {
                "full_name": user.personnal_kyc.full_name,
                "date_of_birth": (
                    user.personnal_kyc.date_of_birth.isoformat()
                    if user.personnal_kyc.date_of_birth
                    else None
                ),
                "nationality": user.personnal_kyc.nationality,
                "id_document_type": user.personnal_kyc.id_document_type,
                "id_number": user.personnal_kyc.document_number,  # Map to form field name
                "id_issue_date": (
                    user.personnal_kyc.id_issue_date.isoformat()
                    if user.personnal_kyc.id_issue_date
                    else None
                ),
                "id_expiry_date": (
                    user.personnal_kyc.id_expiry_date.isoformat()
                    if user.personnal_kyc.id_expiry_date
                    else None
                ),
                "address": user.personnal_kyc.address,
                "has_visa_file": bool(user.personnal_kyc.visa_last_page),
                "visa_file_url": (
                    user.personnal_kyc.visa_last_page.url
                    if user.personnal_kyc.visa_last_page
                    else None
                ),
            }
    elif hasattr(user, "company_kyc") and user.company_kyc:
        kyc_status = user.company_kyc.status
        if kyc_status == "rejected":
            kyc_rejection_reason = user.company_kyc.get_rejection_reason_display()
            kyc_rejection_details = user.company_kyc.remarks or ""

            kyc_data = {
                "company_name": user.company_kyc.company_name,
                "address": user.company_kyc.address,
                "representative_name": user.company_kyc.representative_name,
                "established_date": (
                    user.company_kyc.established_date.isoformat()
                    if user.company_kyc.established_date
                    else None
                ),
                "business_sector": user.company_kyc.business_sector,
                "legal_status": user.company_kyc.legal_status,
                "id_nat": user.company_kyc.id_nat,
                "rccm_number": user.company_kyc.rccm,
                "nif": user.company_kyc.nif,
            }
    return JsonResponse(
        {
            "kyc_status": kyc_status,
            "kyc_rejection_reason": kyc_rejection_reason,
            "kyc_rejection_details": kyc_rejection_details,
            "kyc_data": kyc_data,
        }
    )


# Create your views here.
@require_full_login
@customer_nonstaff_required
def dashboard(request):
    user = request.user.username
    user = User.objects.get(username=user)

    # Get Google Maps API
    google_map_api = environ.get("GOOGLE_MAPS_API_KEY")

    # Default KYC status
    kyc_status = "Not submitted"
    kyc_rejection_reason = ""
    kyc_rejection_details = ""

    # Check for existing KYC records
    if hasattr(user, "personnal_kyc") and user.personnal_kyc:
        kyc_status = user.personnal_kyc.status
        if kyc_status == "rejected":
            kyc_rejection_reason = user.personnal_kyc.get_rejection_reason_display()
            kyc_rejection_details = user.personnal_kyc.remarks or ""
    elif hasattr(user, "company_kyc") and user.company_kyc:
        kyc_status = user.company_kyc.status
        if kyc_status == "rejected":
            kyc_rejection_reason = user.company_kyc.get_rejection_reason_display()
            kyc_rejection_details = user.company_kyc.remarks or ""

    # Determine if user has any billing items (orders, subscriptions, or payment attempts)
    has_orders = Order.objects.filter(user=user).exists()
    has_subscriptions = Subscription.objects.filter(user=user).exists()
    has_payments = PaymentAttempt.objects.filter(order__user=user).exists()

    # ✅ CORRECTION: Si KYC est validé, permettre l'accès à toutes les fonctionnalités
    # Même sans historique de facturation, l'utilisateur peut utiliser le système
    has_billing = (
        has_orders or has_subscriptions or has_payments or (kyc_status == "approved")
    )

    # Redirect to landing if KYC not submitted
    if (
        kyc_status == "Not submitted"
        or kyc_status == "rejected"
        or kyc_status == "pending"
    ):
        from django.shortcuts import redirect

        return redirect("landing_page")

    context = {
        "full_name": user.full_name,
        "id_user": user.id_user,
        "kyc_status": kyc_status,
        "kyc_rejection_reason": kyc_rejection_reason,
        "kyc_rejection_details": kyc_rejection_details,
        "google_map_api": google_map_api,
        "has_billing": has_billing,
        "has_orders": has_orders,
        "has_subscriptions": has_subscriptions,
        "has_payments": has_payments,
    }

    return render(request, "dashboard_page.html", context)


@require_full_login
@customer_nonstaff_required
def landing_page(request):
    user = request.user
    template = "landing_page.html"

    # Get Google Maps API (fallback to empty if not set)
    google_map_api = os.environ.get("GOOGLE_MAPS_API_KEY", "")

    # Defaults
    kyc_status = "Not submitted"
    kyc_rejection_reason = ""
    kyc_rejection_details = ""

    # Safely retrieve KYC records (won't raise DoesNotExist)
    personal_kyc = PersonalKYC.objects.filter(user=user).first()
    company_kyc = CompanyKYC.objects.filter(user=user).first()

    # Personal KYC document (if any)
    personal_document = None
    if (
        personal_kyc
        and hasattr(personal_kyc, "document_file")
        and personal_kyc.document_file
    ):
        personal_document = {
            "name": getattr(personal_kyc, "document_name", "KYC Document"),
            "url": (
                personal_kyc.document_file.url if personal_kyc.document_file else None
            ),
            "uploaded_at": getattr(personal_kyc, "uploaded_at", None),
        }

    # Personal visa document (if any)
    personal_visa = None
    if (
        personal_kyc
        and hasattr(personal_kyc, "visa_last_page")
        and personal_kyc.visa_last_page
    ):
        personal_visa = {
            "name": "Visa Document",
            "url": personal_kyc.visa_last_page.url,
            "uploaded_at": getattr(personal_kyc, "submitted_at", None),
        }

    # Company KYC documents (list)
    company_documents = []
    company_rep_id = None
    if company_kyc:
        # Representative ID file
        if (
            hasattr(company_kyc, "representative_id_file")
            and company_kyc.representative_id_file
        ):
            company_rep_id = {
                "name": "ID du représentant",
                "url": company_kyc.representative_id_file.url,
                "uploaded_at": getattr(company_kyc, "submitted_at", None),
            }
        # Company documents
        docs_qs = getattr(company_kyc, "documents", None)
        if docs_qs:
            for doc in docs_qs.all():
                company_documents.append(
                    {
                        "id": doc.id,
                        "name": doc.document_name or "Company Document",
                        "type": doc.document_type,
                        "url": doc.document.url if doc.document else None,
                        "uploaded_at": doc.uploaded_at,
                    }
                )

    # Determine status (prefer detailed rejected record)
    if (
        personal_kyc
        and personal_kyc.status == "rejected"
        and (personal_kyc.remarks or personal_kyc.get_rejection_reason_display())
    ):
        kyc_status = personal_kyc.status
        kyc_rejection_reason = personal_kyc.get_rejection_reason_display()
        kyc_rejection_details = personal_kyc.remarks or ""
    elif (
        company_kyc
        and company_kyc.status == "rejected"
        and (company_kyc.remarks or company_kyc.get_rejection_reason_display())
    ):
        kyc_status = company_kyc.status
        kyc_rejection_reason = company_kyc.get_rejection_reason_display()
        kyc_rejection_details = company_kyc.remarks or ""
    elif personal_kyc:
        kyc_status = personal_kyc.status
    elif company_kyc:
        kyc_status = company_kyc.status

    # If approved (personal OR company), go straight to dashboard
    if (personal_kyc and personal_kyc.status == "approved") or (
        company_kyc and company_kyc.status == "approved"
    ):
        return redirect("dashboard")

    # Otherwise, render landing page
    context = {
        "full_name": user.full_name,
        "id_user": user.id_user,
        "kyc_status": kyc_status,
        "kyc_rejection_reason": kyc_rejection_reason,
        "kyc_rejection_details": kyc_rejection_details,
        "google_map_api": google_map_api,
        "personal_kyc": personal_kyc,
        "company_kyc": company_kyc,
        "personal_document": personal_document,
        "personal_visa": personal_visa,
        "company_documents": company_documents,
        "company_rep_id": company_rep_id,
        # "is_landing_page": True,  # Add this to indicate we're on the landing page
    }

    return render(request, template, context)


# =======
#     }
#     return render(request, template, context)


# >>>>>>> master


@require_full_login
@customer_nonstaff_required
def billing(request):
    user = request.user

    # Unpaid total (orders)
    unpaid_qs = Order.objects.filter(user=user, payment_status__iexact="unpaid")
    outstanding_total = sum((_to_float(o.total_price) for o in unpaid_qs), 0.0)

    # Next billing date via active subscription if any
    next_bill = None
    sub = (
        Subscription.objects.filter(user=user, status__in=["active", "suspended"])
        .order_by("next_billing_date")
        .first()
    )
    if sub and sub.next_billing_date:
        # date field: format simply as YYYY-MM-DD
        next_bill = sub.next_billing_date.strftime("%Y-%m-%d")

    context = {
        "outstanding_total": round(outstanding_total, 2),
        "next_billing_date": next_bill,
    }

    return render(request, "billing_management.html", context)


@require_full_login
@customer_nonstaff_required
def billing_approval_details(request, billing_id):
    """Dedicated page for reviewing and approving additional billing"""
    context = {
        "billing_id": billing_id,
    }
    return render(request, "billing_approval_details.html", context)


@require_full_login
@customer_nonstaff_required
def support(request):
    user = request.user.username
    user = User.objects.get(username=user)

    return render(request, "support_management.html")


@require_full_login
@customer_nonstaff_required
def settings(request):
    # Use the authenticated user directly (no re-lookup by username)
    user: User = request.user

    # Ensure preferences exist so template can read request.user.prefs.notify_*
    prefs, created = UserPreferences.objects.get_or_create(user=user)

    # ---- PROFILE payload expected by template ----
    #   - first_name, last_name, email, phone
    #   - avatar_url (or default)
    profile = {
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": (user.email or "").lower(),
        "phone": user.phone or "",
        "avatar_url": (
            prefs.avatar.url if prefs.avatar else "/static/icons/account_avatar.png"
        ),
    }

    # ---- KYC (your helpers already return exactly what the template needs) ----
    # kyc can be PersonalKYC or CompanyKYC (or None)
    # kyc_status: "pending"/"approved"/"rejected"/"not_submitted"
    # kyc_rejection_reason / kyc_rejection_details for rejected state
    kyc, kyc_status, kyc_rejection_reason, kyc_rejection_details = _get_user_kyc(user)

    # ---- Billing snapshot (lock/unlock handled in template via kyc.status) ----
    billing = _get_billing_overview(user)

    # ---- Active subscription preview (optional) ----
    subscription = (
        Subscription.objects.filter(user=user, status="active")
        .select_related("plan")
        .first()
    )

    ctx = {
        # Profile panel
        "profile": profile,
        # Notifications panel reads from request.user.prefs.* directly,
        # but we also expose them in ctx if you ever want to render elsewhere.
        "notify_updates": prefs.notify_updates,
        "notify_billing": prefs.notify_billing,
        "notify_tickets": prefs.notify_tickets,
        # KYC panel
        "kyc": kyc,
        "kyc_status": kyc_status,
        "kyc_rejection_reason": kyc_rejection_reason,
        "kyc_rejection_details": kyc_rejection_details,
        # Billing panel
        "billing": billing,
        # Optional subscription preview
        "active_subscription": subscription,
    }

    # Render the actual template you shared earlier
    return render(request, "settings_page.html", ctx)


@login_required
def submit_personal_kyc(request):
    if request.method == "POST":
        user = request.user

        # Récupérer tous les champs du formulaire
        full_name = (request.POST.get("full_name") or "").strip()
        date_of_birth = request.POST.get("date_of_birth")
        nationality = (request.POST.get("nationality") or "").strip()
        id_document_type = (request.POST.get("id_document_type") or "").strip()
        document_number = (request.POST.get("id_number") or "").strip()
        id_issue_date = request.POST.get("id_issue_date")
        id_expiry_date = request.POST.get("id_expiry_date")
        address = (request.POST.get("address") or "").strip()
        file = request.FILES.get("file")
        visa_file = request.FILES.get("visa_file")

        needs_visa = bool(nationality) and not nationality.lower().startswith("congol")

        # Check if there's an existing KYC record with documents
        existing_kyc = PersonalKYC.objects.filter(user=user).first()
        has_existing_document = existing_kyc and existing_kyc.document_file
        has_existing_visa = existing_kyc and existing_kyc.visa_last_page

        # Validation des champs requis
        required_fields = {
            "full_name": full_name,
            "date_of_birth": date_of_birth,
            "nationality": nationality,
            "id_document_type": id_document_type,
            "document_number": document_number,
            "id_issue_date": id_issue_date,
            "id_expiry_date": id_expiry_date,
            "address": address,
        }

        # Only require file upload if no existing document
        if not has_existing_document:
            required_fields["file"] = file

        # Handle visa requirements
        if needs_visa and not has_existing_visa:
            required_fields["visa_file"] = visa_file

        missing_fields = [
            field for field, value in required_fields.items() if not value
        ]
        if missing_fields:
            field_labels = {
                "full_name": _("Full name"),
                "date_of_birth": _("Date of birth"),
                "nationality": _("Nationality"),
                "id_document_type": _("ID document type"),
                "document_number": _("Document number"),
                "id_issue_date": _("Issue date"),
                "id_expiry_date": _("Expiry date"),
                "address": _("Address"),
                "file": _("ID document upload"),
                "visa_file": _("Last visa page"),
            }
            field_map = {
                "document_number": "id_number",
                "file": "file",
                "visa_file": "visa_file",
            }
            field_key = missing_fields[0]
            return JsonResponse(
                {
                    "success": False,
                    "message": _("%(field)s is required.")
                    % {"field": field_labels.get(field_key, field_key)},
                    "field": field_map.get(field_key, field_key),
                },
                status=422,
            )

        # Validation des dates
        try:
            from datetime import datetime

            date_of_birth_dt = datetime.strptime(date_of_birth, "%Y-%m-%d").date()
            id_issue_date_dt = datetime.strptime(id_issue_date, "%Y-%m-%d").date()
            id_expiry_date_dt = datetime.strptime(id_expiry_date, "%Y-%m-%d").date()

            # Vérifier que la date d'expiration est après la date de délivrance
            if id_expiry_date_dt <= id_issue_date_dt:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Expiry date must be after issue date.",
                    }
                )

            # Vérifier que la date de naissance est dans le passé
            today = datetime.now().date()
            if date_of_birth_dt >= today:
                return JsonResponse(
                    {"success": False, "message": "Date of birth must be in the past."}
                )

        except ValueError:
            return JsonResponse(
                {"success": False, "message": "Invalid date format. Use YYYY-MM-DD."}
            )

        # Uniqueness checks
        if (
            document_number
            and PersonalKYC.objects.filter(document_number__iexact=document_number)
            .exclude(user=user)
            .exists()
        ):
            return JsonResponse(
                {
                    "success": False,
                    "message": _("This document number is already registered."),
                    "field": "id_number",
                },
                status=409,
            )

        # Retrieve or create KYC entry
        kyc, created = PersonalKYC.objects.get_or_create(user=user)

        # Delete old file only if a new one is being uploaded
        if (
            file
            and not created
            and kyc.document_file
            and default_storage.exists(kyc.document_file.name)
        ):
            default_storage.delete(kyc.document_file.name)

        if (
            needs_visa
            and visa_file
            and not created
            and kyc.visa_last_page
            and default_storage.exists(kyc.visa_last_page.name)
        ):
            default_storage.delete(kyc.visa_last_page.name)

        if (
            not needs_visa
            and not visa_file
            and kyc.visa_last_page
            and default_storage.exists(kyc.visa_last_page.name)
        ):
            default_storage.delete(kyc.visa_last_page.name)
            kyc.visa_last_page = None

        # Update KYC fields with all new required fields
        kyc.full_name = full_name
        kyc.date_of_birth = date_of_birth_dt
        kyc.nationality = nationality
        kyc.id_document_type = id_document_type
        kyc.document_number = document_number
        kyc.id_issue_date = id_issue_date_dt
        kyc.id_expiry_date = id_expiry_date_dt
        kyc.address = address

        # Only update document file if a new one is provided
        if file:
            kyc.document_file = file

        # Handle visa file updates
        if visa_file:
            kyc.visa_last_page = visa_file

        kyc.submitted_at = timezone.now()

        # Reset status to pending (if re-submitted)
        kyc.status = PersonalKYC.Status.PENDING
        kyc.approved_by = None
        kyc.approved_at = None
        kyc.remarks = ""

        try:
            kyc.save()
            return JsonResponse(
                {
                    "success": True,
                    "message": "Personal KYC submitted successfully with all required fields.",
                }
            )
        except IntegrityError as e:
            msg = str(e)
            if "document_number" in msg:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("This document number is already registered."),
                        "field": "id_number",
                    },
                    status=409,
                )
            return JsonResponse(
                {
                    "success": False,
                    "message": _("A duplicate value was detected."),
                },
                status=409,
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Error saving KYC: %(error)s") % {"error": str(e)},
                },
                status=500,
            )

    return JsonResponse({"success": False, "message": "Invalid request method."})


@login_required
@customer_nonstaff_required
def submit_business_kyc(request):
    if request.method == "POST":
        user = request.user

        representative_name = (request.POST.get("representative_name") or "").strip()
        company_name = (request.POST.get("company_name") or "").strip()
        address = (request.POST.get("address") or "").strip()
        established_date = request.POST.get("established_date")
        business_sector = (request.POST.get("business_sector") or "").strip()
        legal_status = (request.POST.get("legal_status") or "").strip()
        rccm = (request.POST.get("rccm_number") or "").strip()
        nif = (request.POST.get("nif") or "").strip()
        id_nat = (request.POST.get("id_nat") or "").strip()
        representative_file = request.FILES.get("representative_file")

        # Handle multiple files for company documents
        company_documents = request.FILES.getlist("company_document_files")

        # Retained files from hidden fields
        retained_doc_ids = request.POST.get("retained_company_doc_ids", "")
        retained_doc_ids = [id for id in retained_doc_ids.split(",") if id]
        retained_rep_id = request.POST.get("retained_rep_id") == "1"

        # Validate required fields. Representative ID or retained rep counts as present.
        has_rep = bool(representative_file) or retained_rep_id
        has_company_docs = bool(company_documents) or len(retained_doc_ids) > 0

        if not representative_name:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Representative name is required."),
                    "field": "representative_name",
                },
                status=422,
            )
        if not company_name:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Company name is required."),
                    "field": "company_name",
                },
                status=422,
            )
        if not rccm:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("RCCM number is required."),
                    "field": "rccm_number",
                },
                status=422,
            )
        if not nif:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("NIF number is required."),
                    "field": "nif",
                },
                status=422,
            )
        if not id_nat:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("ID Nat is required."),
                    "field": "id_nat",
                },
                status=422,
            )
        if not has_rep:
            return JsonResponse(
                {
                    "success": False,
                    "message": _(
                        "Please provide a representative ID document (upload or keep existing)."
                    ),
                    "field": "representative_file",
                },
                status=422,
            )
        if not has_company_docs:
            return JsonResponse(
                {
                    "success": False,
                    "message": _(
                        "Please provide at least one company document (upload or keep existing)."
                    ),
                    "field": "company_document_files",
                },
                status=422,
            )

        duplicate_checks = [
            ("rccm", rccm, "rccm_number", _("This RCCM is already registered.")),
            ("nif", nif, "nif", _("This NIF is already registered.")),
            ("id_nat", id_nat, "id_nat", _("This ID Nat is already registered.")),
        ]
        for field_db, value, form_field, message in duplicate_checks:
            if (
                value
                and CompanyKYC.objects.filter(**{f"{field_db}__iexact": value})
                .exclude(user=user)
                .exists()
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": message,
                        "field": form_field,
                    },
                    status=409,
                )

        try:
            with transaction.atomic():
                # Retrieve or create KYC entry
                kyc, created = CompanyKYC.objects.get_or_create(user=user)

                # Delete old files if they exist, but keep retained ones
                if not created:
                    # Representative ID
                    if (
                        not retained_rep_id
                        and kyc.representative_id_file
                        and default_storage.exists(kyc.representative_id_file.name)
                    ):
                        default_storage.delete(kyc.representative_id_file.name)
                        kyc.representative_id_file = None

                    # Company documents
                    for doc in kyc.documents.all():
                        if str(doc.id) not in retained_doc_ids:
                            if doc.document and default_storage.exists(
                                doc.document.name
                            ):
                                default_storage.delete(doc.document.name)
                            doc.delete()

                # Update KYC fields
                kyc.representative_name = representative_name
                kyc.company_name = company_name
                kyc.address = address

                # Handle new fields with proper date parsing
                if established_date:
                    try:
                        kyc.established_date = datetime.strptime(
                            established_date, "%Y-%m-%d"
                        ).date()
                    except ValueError:
                        kyc.established_date = None
                else:
                    kyc.established_date = None

                kyc.business_sector = business_sector if business_sector else None
                kyc.legal_status = legal_status if legal_status else None

                # Existing fields
                kyc.rccm = rccm
                kyc.nif = nif
                kyc.id_nat = id_nat
                # Only update representative file if a new file was uploaded
                if representative_file:
                    kyc.representative_id_file = representative_file
                # Don't assign company_documents to the old field since we're creating separate CompanyDocument records
                # This prevents the file from being moved twice and causing the "No such file or directory" error
                kyc.submitted_at = timezone.now()

                # Reset status to pending (in case it was rejected before)
                kyc.status = CompanyKYC.Status.PENDING
                kyc.approved_by = None
                kyc.approved_at = None
                kyc.remarks = ""

                try:
                    kyc.save()
                except IntegrityError as e:
                    msg = str(e)
                    if "company_kyc_unique_rccm" in msg:
                        return JsonResponse(
                            {
                                "success": False,
                                "message": _("This RCCM is already registered."),
                                "field": "rccm_number",
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

                for i, document in enumerate(company_documents):
                    filename_lower = document.name.lower()
                    document_type = "other"

                    if "rccm" in filename_lower or "registre" in filename_lower:
                        document_type = "rccm"
                    elif (
                        "nif" in filename_lower
                        or "tax" in filename_lower
                        or "impot" in filename_lower
                    ):
                        document_type = "nif"
                    elif "id" in filename_lower and (
                        "nat" in filename_lower or "national" in filename_lower
                    ):
                        document_type = "id_nat"
                    elif (
                        "statut" in filename_lower
                        or "statutes" in filename_lower
                        or "articles" in filename_lower
                    ):
                        document_type = "statutes"
                    elif (
                        "registration" in filename_lower
                        or "certificate" in filename_lower
                    ):
                        document_type = "registration"

                    document_name = document.name or f"Document {i+1}"

                    try:
                        CompanyDocument.objects.create(
                            company_kyc=kyc,
                            document=document,
                            document_name=document_name,
                            document_type=document_type,
                        )
                    except IntegrityError:
                        raise IntegrityError("company_document_duplicate")

                return JsonResponse(
                    {
                        "success": True,
                        "message": "Business KYC submitted successfully with multiple documents.",
                    }
                )

        except IntegrityError as e:
            if "company_document_duplicate" in str(e):
                return JsonResponse(
                    {
                        "success": False,
                        "message": _(
                            "A company document with the same type already exists. Please rename or remove duplicates."
                        ),
                        "field": "company_document_files",
                    },
                    status=409,
                )
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Duplicate value detected."),
                },
                status=409,
            )
        except Exception as e:
            return JsonResponse(
                {
                    "success": False,
                    "message": _("Error saving KYC: %(error)s") % {"error": str(e)},
                },
                status=500,
            )

    return JsonResponse({"success": False, "message": "Invalid request method."})


@require_full_login
@require_GET
def get_plans_by_kit_type(request):
    """
    AJAX endpoint to get subscription plans filtered by kit type
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    kit_type = request.GET.get("kit_type")
    if not kit_type:
        return JsonResponse(
            {"success": False, "message": "Kit type is required"}, status=400
        )

    try:
        plans = (
            SubscriptionPlan.objects.filter(kit_type=kit_type, is_active=True)
            .values("id", "name", "base_price_usd", "standard_data_gb", "description")
            .order_by("name")
        )

        plan_list = [
            {
                "id": plan["id"],
                "name": plan["name"],
                "price_usd": float(plan["base_price_usd"] or 0),
                "data_cap_gb": plan["standard_data_gb"],
                "description": plan["description"] or "",
            }
            for plan in plans
        ]

        return JsonResponse({"success": True, "plans": plan_list})

    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Error fetching plans: {str(e)}"}, status=500
        )


# ---- GeoDjango (optional) ----
_HAS_GEO = False
_geom_field_name = None
_geom_field_srid = 4326

_stockloc_geom_field = None
_stockloc_geom_srid = 4326

try:
    from django.contrib.gis.db.models import GeometryField
    from django.contrib.gis.db.models.functions import Distance
    from django.contrib.gis.geos import Point

    _HAS_GEO = True

    # Auto-detect first geometry field on Region
    for f in Region._meta.get_fields():
        cand = getattr(f, "target_field", f)
        if isinstance(cand, GeometryField):
            _geom_field_name = f.name
            _geom_field_srid = getattr(cand, "srid", 4326) or 4326
            break

    # Auto-detect a point/geometry field on StockLocation for distance calc
    for f in StockLocation._meta.get_fields():
        cand = getattr(f, "target_field", f)
        if isinstance(cand, GeometryField):
            _stockloc_geom_field = f.name
            _stockloc_geom_srid = getattr(cand, "srid", 4326) or 4326
            break

except Exception:
    # GIS not available; region resolution from lat/lng will be disabled
    _HAS_GEO = False


def _looks_swapped(lat: float, lng: float) -> bool:
    """
    Heuristic: lat must be [-90,90], lng must be [-180,180].
    If violated and the swapped pair would be valid, assume inputs are swapped.
    """
    valid_lat = -90.0 <= lat <= 90.0
    valid_lng = -180.0 <= lng <= 180.0
    if valid_lat and valid_lng:
        return False
    return (-90.0 <= lng <= 90.0) and (-180.0 <= lat <= 180.0)


def _mk_pt(lat: float, lng: float):
    """
    Build a GEOS Point in the Region SRID (transforming from WGS84 if needed).
    """
    pt = Point(lng, lat, srid=4326)
    if _geom_field_srid and _geom_field_srid != 4326:
        try:
            pt.transform(_geom_field_srid)
        except Exception:
            pass
    return pt


def _resolve_region_with_diagnostics(request):
    """
    Resolve a Region from:
      1) region_id (fast path)
      2) lat,lng / lat,lon (requires GIS; tries multiple spatial predicates + tiny buffer)
      3) fallback to nearest in-stock StockLocation's Region within ~50 km
    Returns: (region_or_None, diagnostics_dict)
    """
    diag = {
        "has_geo": _HAS_GEO,
        "region_model_loaded": True,
        "geom_field": _geom_field_name,
        "geom_srid": _geom_field_srid,
        "stockloc_geom_field": _stockloc_geom_field,
        "stockloc_geom_srid": _stockloc_geom_srid,
        "path": None,
        "attempts": [],
    }

    # 1) region_id path
    region_id = request.GET.get("region_id")
    if region_id:
        diag["path"] = "region-id"
        try:
            reg = Region.objects.only("id", "name").get(pk=region_id)
            diag["attempts"].append({"by": "pk", "ok": bool(reg)})
            return reg, diag
        except Exception as e:
            diag["attempts"].append({"by": "pk", "ok": False, "err": str(e)})
            return None, diag

    # 2) lat/lng path
    if not _HAS_GEO or not _geom_field_name:
        diag["path"] = "no-geo"
        return None, diag

    lat_raw = request.GET.get("lat")
    lng_raw = request.GET.get("lng") or request.GET.get("lon")  # accept ?lon= too
    diag["path"] = "lat-lng"
    if not (lat_raw and lng_raw):
        diag["attempts"].append({"by": "missing-lat-lng"})
        return None, diag

    try:
        latf, lngf = float(lat_raw), float(lng_raw)
    except Exception as e:
        diag["attempts"].append({"by": "parse-float", "ok": False, "err": str(e)})
        return None, diag

    # Detect & auto-swap if needed
    swapped = False
    if _looks_swapped(latf, lngf):
        latf, lngf = lngf, latf
        swapped = True
    diag["coords"] = {"lat": latf, "lng": lngf, "auto_swapped": swapped}

    pt = _mk_pt(latf, lngf)
    qs = Region.objects.only("id", "name", _geom_field_name)

    # Try multiple spatial predicates in sequence
    for op in ("covers", "contains", "within", "intersects"):
        try:
            kw = {f"{_geom_field_name}__{op}": pt}
            reg = qs.filter(**kw).only("id", "name").first()
            diag["attempts"].append({"by": op, "ok": bool(reg)})
            if reg:
                return reg, diag
        except Exception as e:
            diag["attempts"].append({"by": op, "ok": False, "err": str(e)})

    # Intersects with a tiny buffer (50 m) to catch boundary precision issues
    try:
        # buffer distance is in SRID units
        buf_dist = 50.0 if _geom_field_srid != 4326 else 0.00045  # ~50m in degrees
        pt_buf = pt.buffer(buf_dist)
        kw = {f"{_geom_field_name}__intersects": pt_buf}
        reg = qs.filter(**kw).only("id", "name").first()
        diag["attempts"].append(
            {"by": "intersects-buffer", "ok": bool(reg), "buf": buf_dist}
        )
        if reg:
            return reg, diag
    except Exception as e:
        diag["attempts"].append({"by": "intersects-buffer", "ok": False, "err": str(e)})

    # 3) Fallback: nearest in-stock warehouse region within 50 km
    try:
        if not _stockloc_geom_field:
            raise RuntimeError("No StockLocation geometry field detected")

        # Build a point in the StockLocation SRID for distance (or use 4326 if it matches)
        pt_for_stock = Point(lngf, latf, srid=4326)
        if _stockloc_geom_srid != 4326:
            try:
                pt_for_stock.transform(_stockloc_geom_srid)
            except Exception:
                pass

        near_qs = (
            StockLocation.objects.exclude(region__isnull=True)
            .annotate(d=Distance(_stockloc_geom_field, pt_for_stock))
            .order_by("d")
        )

        nearest = None
        for loc in near_qs[:10]:  # check a few nearest
            # any available stock at this location?
            has_stock = StarlinkKitInventory.objects.filter(
                current_location=loc,
                is_assigned=False,
                status="available",
                kit__is_active=True,
            ).exists()
            if has_stock:
                nearest = loc
                break

        if nearest and getattr(nearest, "region_id", None):
            dist_m = None
            try:
                # Distance returns a Distance object; .m gives meters if geography is set, else best-effort
                dist_m = float(getattr(nearest, "d").m)
            except Exception:
                pass
            if dist_m is None or dist_m <= 50_000:  # <= 50 km
                diag["attempts"].append(
                    {
                        "by": "nearest-instock-warehouse",
                        "ok": True,
                        "distance_m": dist_m,
                    }
                )
                return nearest.region, diag

        diag["attempts"].append({"by": "nearest-instock-warehouse", "ok": False})
    except Exception as e:
        diag["attempts"].append(
            {"by": "nearest-instock-warehouse", "ok": False, "err": str(e)}
        )

    return None, diag


def _resolve_region(request):
    reg, _ = _resolve_region_with_diagnostics(request)
    return reg


def _as_money(x) -> float:
    try:
        return float(Decimal(x or 0))
    except Exception:
        return 0.0


@require_GET
def get_kits_by_location(request):
    """
    GET params:
      - lat (required)
      - lon or lng (required)
    Returns:
      {
        "success": true,
        "region": {"id": 7, "name": "Kinshasa"} or null,
        "kits": {
          "standard": [
            {"id": 123, "name": "Starlink Standard", "kit_type": "standard", "price_usd": "599.00", "quantity": 12},
            ...
          ],
          "mini": [...]
        }
      }
    """
    lat = request.GET.get("lat")
    lon = request.GET.get("lon") or request.GET.get("lng")
    try:
        lat = float(lat)
        lon = float(lon)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "lat/lon are required numeric params"},
            status=400,
        )

    region = None
    try:
        pt = Point(lon, lat, srid=4326)
        # adjust field name if your Region geometry field differs (e.g. polys, geom, boundary, etc.)
        region = (
            Region.objects.filter(fence__covers=pt).first()
            or Region.objects.filter(fence__contains=pt).first()
        )
    except Exception:
        region = None

    # Optional fallback without GIS: use nearest StockLocation by distance if you store coords on locations,
    # or call your own /geo_regions/check-point server-side here and map to Region.
    # For now, we just proceed without a region if GIS is not available.

    # --- 2) All locations within the resolved region ---
    if region:
        loc_qs = StockLocation.objects.filter(is_active=True, region=region)
    else:
        # If you prefer to hide stock when region is unknown, return no kits:
        # return JsonResponse({"success": True, "region": None, "kits": {}}, status=200)
        # Or be permissive and show all stock (not recommended). Here we show none:
        return JsonResponse({"success": True, "region": None, "kits": {}}, status=200)

    # --- 3) Aggregate available inventory for those locations ---
    inv_qs = (
        StarlinkKitInventory.objects.filter(
            current_location__in=loc_qs, status="available"
        )
        .values("kit_id", "kit__name", "kit__kit_type", "kit__base_price_usd")
        .annotate(quantity=Count("id"))
        .order_by("kit__kit_type", "kit__name")
    )

    # --- 4) Build response grouped by kit type to match your JS consumer ---
    kits_by_type = {"standard": [], "mini": []}
    for row in inv_qs:
        kit_type = (row["kit__kit_type"] or "standard").lower()
        item = {
            "id": row["kit_id"],
            "name": row["kit__name"],
            "kit_type": kit_type,
            "price_usd": str(row["kit__base_price_usd"]),  # keep as string for JSON
            "quantity": row["quantity"],
        }
        kits_by_type.setdefault(kit_type, []).append(item)

    payload = {
        "success": True,
        "region": {"id": region.id, "name": region.name} if region else None,
        "kits": kits_by_type,
    }

    return JsonResponse(payload, status=200)


@login_required
@require_GET
def get_plans(request):
    """
    Optional query params:
      - kit_type: logical filter for plans compatible with that kit type.
    Returns: { success, plans: [{id, name, data_cap_gb, price_usd, kit_match, description}] }
    """
    kit_type = (request.GET.get("kit_type") or "").strip() or None

    qs = SubscriptionPlan.objects.filter(is_active=True).order_by(
        "display_order", "name"
    )

    # Try to map the incoming "kit_type" to real fields on SubscriptionPlan.
    # We'll attempt exact matches on these fields, in order, and keep the first
    # one that yields results. If none work, we fall back to a fuzzy search.
    kit_match_field = None
    if kit_type:
        attempted_fields = ("plan_type", "site_type", "category_name")
        filtered_qs = None

        for field in attempted_fields:
            try:
                tmp = qs.filter(**{field: kit_type})
            except FieldError:
                # Field doesn't exist on the model; skip it.
                continue

            if tmp.exists():
                filtered_qs = tmp
                kit_match_field = field
                break

        if filtered_qs is None:
            # Fallback: fuzzy match on name / category_name
            fuzzy = qs.filter(
                Q(name__icontains=kit_type) | Q(category_name__icontains=kit_type)
            )
            if fuzzy.exists():
                filtered_qs = fuzzy

        if filtered_qs is not None:
            qs = filtered_qs

    plans_payload = []
    for plan in qs:
        # Data cap: prefer standard_data_gb; fall back to priority_data_gb; otherwise None.
        data_cap = getattr(plan, "standard_data_gb", None)
        if not data_cap:
            data_cap = getattr(plan, "priority_data_gb", None)

        # Price: use monthly_price_usd if present, else 0.0
        price_usd = float(getattr(plan, "monthly_price_usd", 0) or 0)

        # Description: try category_description, fall back to empty string
        description = getattr(plan, "category_description", "") or ""

        plans_payload.append(
            {
                "id": plan.id,
                "name": plan.name,
                "data_cap_gb": data_cap,
                "price_usd": price_usd,
                # Which field we matched on (useful for debugging/telemetry)
                "kit_match": kit_match_field,
                "description": description,
            }
        )

    return JsonResponse({"success": True, "plans": plans_payload})


@require_full_login
@require_GET
def get_checkout_options(request):
    """
    Region-aware availability:
    - If region_id is provided, use that.
    - Else if lat/lng are provided (or lon), resolve Region via GIS.
    - Only return kits that have inventory (>0) in StockLocations within that Region.
    Add `?debug=1` to get diagnostics in response.
    """
    # Accept both AJAX and non-AJAX calls; only reject explicitly malformed
    # X-Requested-With headers. This keeps the endpoint usable in tests and
    # for simple clients while still enforcing basic sanity.
    xrw = request.headers.get("x-requested-with")
    if xrw and xrw != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    KIT_TYPES = {"standard": "Standard Kit", "mini": "Mini Kit"}
    kit_types_payload = {k: [] for k in KIT_TYPES}

    region, diag = _resolve_region_with_diagnostics(request)
    want_debug = request.GET.get("debug") == "1"

    if region is None:
        payload = {
            "success": True,
            "region": None,
            "kits": kit_types_payload,
            "plans": [],
        }
        if want_debug:
            payload["debug"] = diag
        return JsonResponse(payload)

    # Inventory available in THIS region
    inv_by_kit = (
        StarlinkKitInventory.objects.filter(
            is_assigned=False,
            status="available",
            kit__is_active=True,
            current_location__region=region,
        )
        .values("kit_id")
        .annotate(qty=Count("id"))
    )
    availability = {row["kit_id"]: int(row["qty"]) for row in inv_by_kit}

    if not availability:
        payload = {
            "success": True,
            "region": {"id": region.id, "name": getattr(region, "name", str(region))},
            "kits": kit_types_payload,
            "plans": [],
        }
        if want_debug:
            payload["debug"] = diag
        return JsonResponse(payload)

    # Only active kits that have stock here
    kits_qs = StarlinkKit.objects.filter(
        is_active=True, id__in=availability.keys()
    ).order_by("name")
    for kit in kits_qs:
        qty = availability.get(kit.id, 0)
        if qty <= 0:
            continue
        key = kit.kit_type if kit.kit_type in KIT_TYPES else "standard"
        kit_types_payload[key].append(
            {
                "id": kit.id,
                "name": kit.name,
                "price_usd": _as_money(kit.base_price_usd),
                "quantity": qty,
                "out_of_stock": False,
                "kit_type": key,
            }
        )

    # Plans limited to kit types that actually have stock in this region
    types_with_stock = {
        kt
        for kt, items in kit_types_payload.items()
        if any(i["quantity"] > 0 for i in items)
    }
    plans_payload = []
    if types_with_stock:
        for plan in SubscriptionPlan.objects.filter(is_active=True).order_by(
            "display_order", "name"
        ):
            if (plan.kit_type or "standard") not in types_with_stock:
                continue
            kit_for_price = next(
                (
                    k
                    for k in kits_qs
                    if (k.kit_type if k.kit_type in KIT_TYPES else "standard")
                    == plan.kit_type
                ),
                None,
            )
            price_usd = _as_money(
                kit_for_price.base_price_usd if kit_for_price else 599.00
            )
            plans_payload.append(
                {
                    "id": plan.id,
                    "name": plan.name,
                    "data_cap_gb": plan.standard_data_gb,
                    "price_usd": price_usd,
                    "kit_type": plan.kit_type or "standard",
                    "description": "",
                }
            )

    payload = {
        "success": True,
        "region": {"id": region.id, "name": getattr(region, "name", str(region))},
        "kits": kit_types_payload,
        "plans": plans_payload,
    }
    if want_debug:
        payload["debug"] = diag
    return JsonResponse(payload)


# ------------------------- TAX / PRICING HELPERS -------------------------


def _get_rate_pct(code: str) -> Decimal:
    """
    Fetch a tax rate percentage (e.g., 16.00) from TaxRate.description.
    Returns Decimal('0.00') if not found.
    """
    val = (
        TaxRate.objects.filter(description=code)
        .values_list("percentage", flat=True)
        .first()
    )
    try:
        return (
            Decimal(val).quantize(Decimal("0.00"))
            if val is not None
            else Decimal("0.00")
        )
    except Exception:
        return Decimal("0.00")


def _pct(amount: Decimal, rate_pct: Decimal) -> Decimal:
    """amount * (rate/100), then quantize to money."""
    if not amount or not rate_pct:
        return Decimal("0.00")
    return _qmoney((amount * rate_pct) / Decimal("100"))


@transaction.atomic
def price_order_from_lines(order) -> dict:
    """
    Tax order:
      1) EXCISE applies ONLY to subscription (PLAN) line total
      2) VAT applies to (SUBTOTAL of all lines + EXCISE)

    Persists OrderTax rows and updates order.total_price.
    Returns dict with stringified money for JSON.
    """
    lines = list(order.lines.select_related("plan"))

    subtotal = _qmoney(sum((l.line_total or Decimal("0.00")) for l in lines))
    plan_total = _qmoney(
        sum(
            (l.line_total or Decimal("0.00"))
            for l in lines
            if l.kind == OrderLine.Kind.PLAN
        )
    )

    excise_pct = _get_rate_pct("EXCISE")
    vat_pct = _get_rate_pct("VAT")

    excise_amount = _pct(plan_total, excise_pct)  # only on plan
    vat_base = _qmoney(subtotal + excise_amount)  # subtotal + excise
    vat_amount = _pct(vat_base, vat_pct)

    tax_total = _qmoney(excise_amount + vat_amount)
    total = _qmoney(subtotal + tax_total)

    # rewrite taxes for this order
    order.taxes.all().delete()
    if excise_amount > 0:
        OrderTax.objects.create(
            order=order,
            kind=OrderTax.Kind.EXCISE,
            rate=excise_pct,
            amount=excise_amount,
        )
    if vat_amount > 0:
        OrderTax.objects.create(
            order=order, kind=OrderTax.Kind.VAT, rate=vat_pct, amount=vat_amount
        )

    order.total_price = total
    order.save(update_fields=["total_price"])

    return {
        "subtotal": str(subtotal),
        "tax_total": str(tax_total),
        "total": str(total),
    }


# ------------------------- MAIN ORDER SUBMISSION -------------------------
# -------------------------------------------------------------------
# Small money helper (matches your model-side _qmoney behavior)
# -------------------------------------------------------------------
ZERO = Decimal("0.00")


def _qmoney(x: Decimal | str | float | int | None) -> Decimal:
    x = Decimal(str(x or "0"))
    return x.quantize(ZERO, rounding=ROUND_HALF_UP)


# -------------------------------------------------------------------
# DB feature helper: supports select_for_update(skip_locked=True)?
# -------------------------------------------------------------------
def _supports_skip_locked(using: str = "default") -> bool:
    try:
        return bool(connections[using].features.has_select_for_update_skip_locked)
    except Exception:
        return False


# -------------------------------------------------------------------
# Inventory service helpers (clean, auditable)
# -------------------------------------------------------------------
def reserve_inventory_for_order(
    *,
    inv: StarlinkKitInventory,
    order: Order,
    planned_lat: float | None,
    planned_lng: float | None,
    hold_hours: int,
    by: User | None,
    using: str = "default",
) -> None:
    """
    Logically reserve a kit for an order (no physical move).
    - Flip flags on inventory
    - Keep current_location as-is (warehouse/van)
    - Write one StarlinkKitMovement row for the reservation
    """
    inv.is_assigned = True
    inv.assigned_to_order = order
    inv.status = "assigned"
    inv.save(update_fields=["is_assigned", "assigned_to_order", "status"], using=using)

    StarlinkKitMovement.objects.using(using).create(
        inventory_item=inv,
        movement_type="assigned",
        order=order,
        location=(inv.current_location.code if inv.current_location else ""),
        note=(
            f"Reserved for order {order.order_reference or order.pk}; "
            f"planned install at {planned_lat},{planned_lng}; "
            f"hold {hold_hours}h"
        ),
        created_by=by if getattr(by, "pk", None) else None,
    )


def transfer_inventory(
    *,
    inv: StarlinkKitInventory,
    to_location: StockLocation | None,
    reason: str = "",
    order: Order | None = None,
    by: User | None = None,
    using: str = "default",
) -> None:
    """
    Physical/logistical move (warehouse → van, etc.)
    """
    inv.current_location = to_location
    inv.save(update_fields=["current_location"], using=using)

    StarlinkKitMovement.objects.using(using).create(
        inventory_item=inv,
        movement_type="transferred",
        order=order,
        location=(to_location.code if to_location else ""),
        note=reason or f"Moved to {to_location}",
        created_by=by if getattr(by, "pk", None) else None,
    )


def release_reservation(
    *,
    inv: StarlinkKitInventory,
    order: Order,
    reason: str = "",
    by: User | None = None,
    using: str = "default",
) -> None:
    """
    Release a reserved kit back to available stock (before install).
    """
    inv.is_assigned = False
    inv.assigned_to_order = None
    inv.status = "available"
    inv.save(update_fields=["is_assigned", "assigned_to_order", "status"], using=using)

    StarlinkKitMovement.objects.using(using).create(
        inventory_item=inv,
        movement_type="adjusted",
        order=order,
        location=(inv.current_location.code if inv.current_location else ""),
        note=reason
        or f"Reservation released for order {order.order_reference or order.pk}",
        created_by=by if getattr(by, "pk", None) else None,
    )


# -------------------------------------------------------------------
# The modified submit_order view
# -------------------------------------------------------------------
def submit_order(request: HttpRequest):
    """
    Public order submit:
    - Supports single or multi-block payloads.
    - Accepts names: lat/lng, kit_id, subscription_plan_id, billing_cycle, coupon, services[] or services_{i}[].
    - Idempotent for 60s using X-Idempotency-Key or 'idem_key'.
    - Returns: {"success": bool, "results":[{success, index, order|message}]}
    - NOW: Always creates & issues an Invoice per created order (single or multiple orders).
    """
    user = getattr(request, "user", None)
    user_name = (
        user.username if getattr(user, "is_authenticated", False) else "Anonymous"
    )
    logger.info("submit_order called for user: %s", user_name)

    # ------------------ Idempotency (60s) ------------------
    idem_key = (
        request.headers.get("X-Idempotency-Key") or request.POST.get("idem_key") or ""
    ).strip()
    if not idem_key and request.content_type.startswith("application/json"):
        try:
            body = json.loads(request.body.decode("utf-8") or "{}")
            idem_key = (body.get("idem_key") or "").strip()
        except Exception:
            pass

    cache_key = f"submit_order:idem:{idem_key}" if idem_key else None
    if cache_key:
        cached = cache.get(cache_key)
        if cached is not None:
            logger.info(
                "Idempotency hit for key=%s -> returning cached response", idem_key
            )
            return JsonResponse(cached, status=200 if cached.get("success") else 400)

    # ------------------ Helpers ------------------
    def _coerce_to_postlists():
        """
        Normalizes JSON body (if any) into request.POST-like lists.
        If request is already form/multipart, we use it as-is.
        """
        if request.content_type.startswith("application/json"):
            try:
                data = json.loads(request.body.decode("utf-8") or "{}")
            except Exception:
                data = {}

            class _Shim:
                def __init__(self, d):
                    self.d = d

                def get(self, k, default=None):
                    v = self.d.get(k, default)
                    return "" if v is None else str(v)

                def getlist(self, k):
                    v = self.d.get(k, [])
                    if isinstance(v, list):
                        return ["" if x is None else str(x) for x in v]
                    return ["" if v is None else str(v)]

            return _Shim(data)
        return request.POST

    POST = _coerce_to_postlists()

    def _getlist_any(*names):
        for n in names:
            vals = POST.getlist(n)
            if vals:
                return vals
        return []

    def _get_any(*names, default=""):
        for n in names:
            v = (POST.get(n) or "").strip()
            if v:
                return v
        return default

    # ------------------ Gather multi-block payloads ------------------
    lat_list = _getlist_any("lat[]", "latitude[]", "lat", "latitude")
    lng_list = _getlist_any("lng[]", "longitude[]", "lng", "longitude")
    kit_list = _getlist_any("kit_id[]", "kit_type[]", "kit_id", "kit_type")
    plan_list = _getlist_any(
        "subscription_plan_id[]",
        "subscription_plan[]",
        "plan_id[]",
        "plan_id",
        "subscription_plan",
    )

    cycle_list = _getlist_any("billing_cycle[]", "billing_cycle")
    if not cycle_list:
        cycle_list = ["monthly"] * max(
            len(lat_list), len(kit_list), len(plan_list), len(lng_list), 1
        )

    coupon_list = _getlist_any("coupon_code[]")
    if not coupon_list:
        single_coupon = _get_any("coupon") or None
        if single_coupon:
            coupon_list = [single_coupon]

    global_services = _getlist_any("services[]")  # optional
    payment_method = _get_any("payment_method", default="cash") or "cash"

    n = max(len(lat_list), len(lng_list), len(kit_list), len(plan_list), 1)
    created_payloads = []

    CYCLE_MAP = {
        "monthly": (1, "monthly"),
        "quarterly": (3, "quarterly"),
        "yearly": (12, "yearly"),
        "annual": (12, "yearly"),
        "annually": (12, "yearly"),
    }

    thirty_seconds_ago = timezone.now() - timedelta(seconds=30)

    # ---- Invoicing helper: ALWAYS create & issue an invoice from an Order ----
    def _create_issue_invoice_for_order(order):
        # Imports are assumed existing in your codebase
        # from .models import CompanySettings, Invoice, InvoiceLine, InvoiceOrder, OrderLine
        # from .billing import issue_invoice
        cs = CompanySettings.get()
        # NOTE: If Invoice.user is non-nullable, ensure `order.user` exists; otherwise make field nullable or adapt assignment.
        inv = Invoice.objects.create(
            user=order.user,  # may be None if your model allows; else ensure authenticated user
            currency=cs.default_currency or "USD",
            tax_regime=cs.tax_regime,
            vat_rate_percent=cs.vat_rate_percent,
            status=Invoice.Status.DRAFT,
            bill_to_name=(
                (
                    order.user.full_name
                    if getattr(order.user, "full_name", None)
                    else None
                )
                or (order.user.email if getattr(order.user, "email", None) else "")
                or ""
            ),
            bill_to_address="",  # optionally fill from KYC snapshot
        )

        # Copy order lines to invoice lines (preserves kinds)
        for ol in order.lines.all():
            InvoiceLine.objects.create(
                invoice=inv,
                description=ol.description,
                quantity=Decimal(ol.quantity or 1),
                unit_price=ol.unit_price or ZERO,
                kind=ol.kind,
                order=order,
                order_line=ol,
            )

        # Link order↔invoice with amount excl. tax = order subtotal (exclude ADJUST negatives)
        subtotal_excl = sum(
            (
                l.line_total
                for l in order.lines.all()
                if l.kind != OrderLine.Kind.ADJUST
            ),
            ZERO,
        )
        InvoiceOrder.objects.create(
            invoice=inv, order=order, amount_excl_tax=(subtotal_excl or ZERO)
        )

        # Issue: assign number, compute taxes/totals, create ledger entries, etc.
        inv = issue_invoice(inv)
        return inv

    try:
        using = "default"
        with transaction.atomic(using=using):
            for i in range(n):
                raw_lat = (lat_list[i] if i < len(lat_list) else "").strip()
                raw_lng = (lng_list[i] if i < len(lng_list) else "").strip()
                raw_kit = (kit_list[i] if i < len(kit_list) else "").strip()
                raw_plan = (plan_list[i] if i < len(plan_list) else "").strip()
                raw_cycle = (
                    (cycle_list[i] if i < len(cycle_list) else "monthly")
                    .strip()
                    .lower()
                )

                services_key = f"services_{i}[]"
                per_block_services = POST.getlist(services_key) or global_services
                extra_ids = [
                    int(str(s).strip())
                    for s in per_block_services
                    if str(s).strip().isdigit()
                ]

                coupon_code = None
                if coupon_list:
                    coupon_code = (
                        coupon_list[i] if i < len(coupon_list) else coupon_list[-1]
                    )

                # Basic validations
                if not raw_kit:
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] Please select a Starlink kit.",
                            "index": i,
                        }
                    )
                    continue
                if not raw_plan:
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] Please select a subscription plan.",
                            "index": i,
                        }
                    )
                    continue
                if not raw_lat or not raw_lng:
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] Please select the installation address on the MAP.",
                            "index": i,
                        }
                    )
                    continue

                try:
                    lat_f = float(raw_lat)
                    lng_f = float(raw_lng)
                except (TypeError, ValueError):
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] Invalid coordinates.",
                            "index": i,
                        }
                    )
                    continue

                # Resolve kit (id or kit_type)
                if raw_kit.isdigit():
                    kit = StarlinkKit.objects.filter(
                        id=int(raw_kit), is_active=True
                    ).first()
                else:
                    kit = (
                        StarlinkKit.objects.filter(kit_type=raw_kit, is_active=True)
                        .order_by("id")
                        .first()
                    )

                # Resolve plan (must be id)
                plan = (
                    SubscriptionPlan.objects.filter(id=raw_plan, is_active=True).first()
                    if raw_plan.isdigit()
                    else None
                )

                if not kit:
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] Selected kit not found or inactive.",
                            "index": i,
                        }
                    )
                    continue
                if not plan:
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] Selected plan not found or inactive.",
                            "index": i,
                        }
                    )
                    continue

                cycle_months, cycle_value = CYCLE_MAP.get(raw_cycle, (1, "monthly"))

                # Compute expiry
                expiry_hours = 1
                try:
                    expires_at = compute_local_expiry_from_coords(
                        lat=lat_f, lng=lng_f, hours=expiry_hours
                    )
                    logger.info(
                        "[Order #%s] Expiry set using local timezone from coords (%s, %s) for %d hour(s): %s",
                        i + 1,
                        lat_f,
                        lng_f,
                        expiry_hours,
                        expires_at.isoformat(),
                    )
                except Exception as e:
                    logger.warning(
                        "[Order #%s] Timezone calc failed, using UTC fallback: %s",
                        i + 1,
                        e,
                    )
                    expires_at = timezone.now() + timedelta(hours=expiry_hours)

                # Duplicate guard: same user+coords within 30s and pending state
                dup_exists = Order.objects.filter(
                    user=user if getattr(user, "pk", None) else None,
                    created_at__gte=thirty_seconds_ago,
                    status__in=["pending_payment", "awaiting_confirmation"],
                    latitude=lat_f,
                    longitude=lng_f,
                ).exists()
                if dup_exists:
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] An order is already being created for this location. Please wait.",
                            "index": i,
                        }
                    )
                    continue

                # ---------- Pricing draft (base) ----------
                kit_price = _qmoney(kit.base_price_usd or Decimal("0.00"))
                monthly_price = _qmoney(
                    plan.effective_price or plan.monthly_price_usd or Decimal("0.00")
                )
                plan_cycle_price = _qmoney(monthly_price * Decimal(cycle_months))
                install_fee = installation_fee_for_coords(lat_f, lng_f)

                draft_lines = [
                    DraftLine(
                        kind="kit",
                        description=f"{kit.name}",
                        quantity=1,
                        unit_price=kit_price,
                    ),
                    DraftLine(
                        kind="plan",
                        description=f"{plan.name} – {cycle_value} ({cycle_months} mo)",
                        quantity=1,
                        unit_price=plan_cycle_price,
                        plan_id=plan.id,
                    ),
                ]
                if install_fee > 0:
                    draft_lines.append(
                        DraftLine(
                            kind="install",
                            description="Installation fee",
                            quantity=1,
                            unit_price=install_fee,
                        )
                    )

                extras = []
                if extra_ids:
                    extras = list(
                        ExtraCharge.objects.filter(id__in=extra_ids, is_active=True)
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

                # ---------- Promotions + Coupon ----------
                coupon_input = coupon_code if getattr(user, "pk", None) else None
                disc_result = apply_promotions_and_coupon_to_draft_lines(
                    user=user if getattr(user, "pk", None) else None,
                    draft_lines=draft_lines,
                    coupon_code=coupon_input,
                )
                draft_lines_after = disc_result["lines"]
                discount_pairs = disc_result["applied"]
                coupon_obj = disc_result["coupon"]
                coupon_error = disc_result["coupon_error"]

                if coupon_code and not getattr(user, "pk", None):
                    coupon_error = "You must be signed in to use a coupon."
                if coupon_code and coupon_error:
                    logger.info(
                        "[Order #%s] Coupon provided but not applicable: %s",
                        i + 1,
                        coupon_error,
                    )

                # ---------- Inventory reservation ----------
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
                    created_payloads.append(
                        {
                            "success": False,
                            "message": f"[Order #{i+1}] No available inventory for the selected kit.",
                            "index": i,
                        }
                    )
                    continue

                # ---------- Order ----------
                order = Order.objects.using(using).create(
                    user=user if getattr(user, "pk", None) else None,
                    plan=plan,
                    kit_inventory=assigned_inventory,
                    latitude=lat_f,
                    longitude=lng_f,
                    status="pending_payment",
                    payment_status="unpaid",
                    expires_at=expires_at,
                    created_by=user if getattr(user, "pk", None) else None,
                    payment_method=payment_method,
                )

                reserve_inventory_for_order(
                    inv=assigned_inventory,
                    order=order,
                    planned_lat=lat_f,
                    planned_lng=lng_f,
                    hold_hours=expiry_hours,
                    by=(user if getattr(user, "pk", None) else None),
                    using=using,
                )

                if extras:
                    order.selected_extra_charges.add(*extras)

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

                # ---------- Taxes & totals ----------
                pricing = compute_totals_from_lines(order)
                final_total = _qmoney(Decimal(pricing["total"] or "0"))
                Order.objects.using(using).filter(pk=order.pk).update(
                    total_price=final_total
                )
                order.total_price = final_total

                # ---------- Subscription shell (inactive) ----------
                sub = Subscription.objects.using(using).create(
                    user=user if getattr(user, "pk", None) else None,
                    plan=plan,
                    status="inactive",
                    billing_cycle=cycle_value,
                    started_at=None,
                    next_billing_date=None,
                    last_billed_at=None,
                    order=order,
                )

                # ---------- Ledger for promos/coupon ----------
                if getattr(user, "pk", None) and discount_pairs:
                    acct, _ = BillingAccount.objects.using(using).get_or_create(
                        user=user
                    )
                    for lbl, neg_amt in discount_pairs:
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

                # ---------- Legacy ledger invoice entry (kept) ----------
                if getattr(user, "pk", None) and final_total > 0:
                    acct, _ = BillingAccount.objects.using(using).get_or_create(
                        user=user
                    )
                    AccountEntry.objects.using(using).create(
                        account=acct,
                        entry_type="invoice",
                        amount_usd=final_total,
                        description=f"Order {order.order_reference} – full amount due ({cycle_value} plan charge included)",
                        order=order,
                        subscription=sub,
                    )

                # ---------- NEW: ALWAYS create + issue Invoice model ----------
                invoice_number = None
                try:
                    inv = _create_issue_invoice_for_order(order)
                    invoice_number = inv.number
                except Exception as inv_err:
                    # We still allow the order to be created even if invoicing fails;
                    # but we log for diagnosis.
                    logger.error(
                        "Failed to create/issue invoice for order %s: %s",
                        order.order_reference,
                        inv_err,
                        exc_info=True,
                    )

                # ---------- Response payload ----------
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
                    install_line = next(
                        (l for l in lines if l["kind"] == OrderLine.Kind.INSTALL), None
                    )
                    if install_line:
                        install_fee_str = str(install_line["unit_price"])
                except Exception:
                    pass

                created_payloads.append(
                    {
                        "success": True,
                        "index": i,
                        "order": {
                            "id": order.order_reference,
                            "invoice_number": invoice_number,  # ← surfaced to the client
                            "expires_at": order.expires_at_iso,
                            "latitude": order.latitude,
                            "longitude": order.longitude,
                            "billing_cycle": {
                                "raw": raw_cycle or "monthly",
                                "value": cycle_value,
                                "months": CYCLE_MAP.get(raw_cycle, (1, "monthly"))[0],
                            },
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
                            "subtotal": str(pricing["subtotal"]),
                            "tax_total": str(pricing["tax_total"]),
                            "total_price": str(order.total_price),
                            "install_fee": install_fee_str,
                            "discounts": [
                                {"label": lbl, "amount": str(amt)}
                                for (lbl, amt) in discount_pairs
                            ],
                            "coupon_applied": bool(coupon_obj),
                            "coupon_error": coupon_error or "",
                            "payment_method": payment_method,
                        },
                    }
                )

        # ------------------ Final response + cache idempotent result ------------------
        if any(p.get("success") for p in created_payloads):
            resp = {"success": True, "results": created_payloads}
            if cache_key:
                cache.set(cache_key, resp, timeout=60)
            return JsonResponse(resp, status=200)
        else:
            first_err = next(
                (p for p in created_payloads if not p.get("success")), None
            )
            resp = {
                "success": False,
                "results": created_payloads,
                "message": first_err.get("message")
                if first_err
                else "No orders created.",
            }
            if cache_key:
                cache.set(cache_key, resp, timeout=60)
            return JsonResponse(resp, status=400)

    except ValidationError as ve:
        logger.warning("Validation error in submit_order: %s", ve)
        return JsonResponse({"success": False, "message": str(ve)}, status=400)
    except (IntegrityError, DatabaseError) as db_err:
        logger.error("DB error in submit_order: %s", db_err, exc_info=True)
        return JsonResponse(
            {"success": False, "message": "Database error. Please try again."},
            status=500,
        )
    except Exception as e:
        logger.error("Unexpected error in submit_order: %s", e, exc_info=True)
        return JsonResponse(
            {"success": False, "message": "An unexpected error occurred."}, status=500
        )


@require_full_login
@customer_nonstaff_required
def get_order_details_print(request, reference):
    print("TEST INVOICE PDF")
    print(reference)
    """
    Minimalist, Starlink-like invoice (by order_reference):
      - Header: company logo + company meta (left)
      - Parties row: Bill To (left) + Invoice meta (right)
      - Items from Order.lines; VAT/EXCISE from OrderTax
      - Centered bottom section (divider, QR/Barcode placeholder, note)
    """

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
    order = get_object_or_404(Order, order_reference=reference)
    created = order.created_at or timezone.now()
    inv_no = order.order_reference or f"ORD-{order.id}"

    # Resolve "Bill To" from KYC if available
    u = order.user
    company_kyc = getattr(u, "company_kyc", None) if u else None
    personal_kyc = getattr(u, "personnal_kyc", None) if u else None

    bill_to_lines = [("BILL TO", "header")]
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
    vat = sum(
        (t.amount for t in taxes_qs if t.kind == OrderTax.Kind.VAT), Decimal("0.00")
    )
    exc = sum(
        (t.amount for t in taxes_qs if t.kind == OrderTax.Kind.EXCISE), Decimal("0.00")
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
    logo_path = os.path.join(
        django_settings.BASE_DIR, "static", "images", "logo", "logo.png"
    )
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
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
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
            Paragraph("VAT", styles["TOTALS_LABEL"]),
            Paragraph(_money(vat), styles["TOTALS_VAL"]),
        ],
        [
            Paragraph("EXCISE", styles["TOTALS_LABEL"]),
            Paragraph(_money(exc), styles["TOTALS_VAL"]),
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

    # Optional QR card (placeholder)
    try:
        # from .pdf_utils import make_qr_card
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


@require_full_login
@customer_nonstaff_required
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


@require_full_login
@customer_nonstaff_required
def get_billing_details(request, order_Id):
    # Validate request type
    if not request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request type"}, status=400
        )

    try:
        # Validate and parse input parameters
        try:
            page = int(request.GET.get("page", 1))
            if page < 1:
                raise ValueError("Page must be positive integer")
        except ValueError:
            return JsonResponse(
                {"success": False, "message": "Invalid page number"}, status=400
            )

        # Build filter dictionary
        filters = {}
        filter_fields = {
            "payment_type": "payment_type",
            "payment_for": "payment_for",
            "status": "status",
        }

        for param, field in filter_fields.items():
            value = request.GET.get(param)
            if value:
                filters[field] = value

        # Verify order ownership and existence
        try:
            order = Order.objects.get(id=order_Id, user=request.user)
        except Order.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": "Order not found or access denied"},
                status=404,
            )

        # Base queryset
        payments_qs = (
            PaymentAttempt.objects.filter(order=order, **filters)
            .order_by("-created_at")
            .select_related("order")
        )
        # Get all payment_for choices
        payment_for_choices = PaymentAttempt._meta.get_field("payment_for").choices
        # Get all payment_type choices
        payment_type_choices = PaymentAttempt._meta.get_field("payment_type").choices

        # Apply date range filter if provided
        start_date_str = request.GET.get("start_date")
        end_date_str = request.GET.get("end_date")

        if start_date_str and end_date_str:
            try:
                start_date = make_aware(datetime.strptime(start_date_str, "%Y-%m-%d"))
                end_date = make_aware(
                    datetime.strptime(end_date_str, "%Y-%m-%d")
                ) + timedelta(days=1)

                if start_date > end_date:
                    return JsonResponse(
                        {
                            "success": False,
                            "message": "Start date cannot be after end date",
                        },
                        status=400,
                    )

                payments_qs = payments_qs.filter(
                    created_at__range=(start_date, end_date)
                )
            except ValueError:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Invalid date format. Use YYYY-MM-DD",
                    },
                    status=400,
                )

        # Pagination
        paginator = Paginator(payments_qs, 10)

        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            return JsonResponse(
                {"success": False, "message": "Page out of range"}, status=400
            )

        # Prepare response data
        payments_data = [
            {
                "id": payment.id,
                "amount": str(payment.amount) if payment.amount else "0.00",
                "status": payment.status,
                "payment_type": payment.payment_type,
                "payment_for": payment.payment_for,
                "payment_for_choices": payment_for_choices,
                "payment_type_choices": payment_type_choices,
                "created_at": (
                    payment.created_at.strftime("%Y-%m-%d %H:%M")
                    if payment.created_at
                    else "—"
                ),
            }
            for payment in page_obj
        ]

        return JsonResponse(
            {
                "success": True,
                "payments": payments_data,
                "total_pages": paginator.num_pages,
                "current_page": page_obj.number,
                "total_items": paginator.count,
            }
        )

    except Exception as e:
        # Log the error for debugging
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error in get_billing_details: {str(e)}", exc_info=True)

        return JsonResponse(
            {"success": False, "message": "An unexpected error occurred"}, status=500
        )


@require_full_login
@customer_nonstaff_required
def invoice_view(request, payment_id):
    try:
        # Get payment with related order and plan in single query
        payment = get_object_or_404(
            PaymentAttempt.objects.select_related("order__plan", "order__user"),
            pk=payment_id,
        )

        # Verify the requesting user owns this payment
        if payment.order.user != request.user:
            raise PermissionDenied("You don't have permission to view this invoice")

        # Prepare invoice data with fallback values
        invoice_data = {
            "number": payment.reference or f"INV-{payment.id:08d}",
            "date": (
                payment.created_at.strftime("%B %d, %Y")
                if payment.created_at
                else "N/A"
            ),
            "amount": f"{payment.amount:.2f}" if payment.amount else "0.00",
            "currency": payment.currency or "USD",
            "status": payment.status.capitalize() if payment.status else "Unknown",
            "payment_for": (
                payment.payment_for.capitalize() if payment.payment_for else "N/A"
            ),
            "plan_name": (
                payment.order.plan.name
                if payment.order and payment.order.plan
                else "No plan"
            ),
            "plan_description": (
                payment.order.plan.description
                if payment.order and payment.order.plan
                else ""
            ),
            "customer_name": request.user.get_full_name() or request.user.username,
            "customer_email": request.user.email,
        }

        context = {
            "payment": payment,
            "invoice_data": invoice_data,
            "is_pdf": "pdf" in request.GET,  # Flag for PDF generation
        }

        return render(request, "partials/payment_invoice.html", context)
    except PermissionDenied:
        raise  # Will return 403
    except Exception:
        # Return a user-friendly error page
        return render(request, "invoice_error.html", status=500)


@require_full_login
@customer_nonstaff_required
def get_invoice_details(request, order_ref):
    """
    Returns invoice details for the given order reference,
    including address from PersonalKYC or CompanyKYC.
    """
    order = get_object_or_404(Order, order_reference=order_ref)

    # Default values
    address = ""
    customer_name = ""
    customer_email = ""
    customer_type = ""
    nif = rccm = idnat = ""

    if order.user:
        customer_name = order.user.full_name
        customer_email = order.user.email

        # Check if this is a personal KYC user
        if hasattr(order.user, "personnal_kyc") and order.user.personnal_kyc:
            kyc = order.user.personnal_kyc
            address = kyc.address or ""
            customer_type = "personal"

        # Otherwise check if this is a company KYC user
        elif hasattr(order.user, "company_kyc") and order.user.company_kyc:
            kyc = order.user.company_kyc
            address = kyc.address or ""
            customer_name = kyc.company_name or customer_name
            customer_type = "business"
            nif = kyc.nif or ""
            rccm = kyc.rccm or ""
            idnat = kyc.idnat or ""

    # Build items list from OrderLine snapshots (authoritative for pricing)
    items = []
    for line in order.lines.all():
        # Prefer human-friendly names when traceability fields are present
        if (
            line.kind == OrderLine.Kind.KIT
            and getattr(line, "kit_inventory", None)
            and getattr(line.kit_inventory, "kit", None)
        ):
            name = line.kit_inventory.kit.name or (line.description or "Kit")
        elif line.kind == OrderLine.Kind.PLAN and getattr(line, "plan", None):
            name = line.plan.name or (line.description or "Subscription plan")
        elif line.kind == OrderLine.Kind.INSTALL:
            name = line.description or "Installation fee"
        elif line.kind == OrderLine.Kind.EXTRA and getattr(line, "extra_charge", None):
            name = line.extra_charge.item_name or (line.description or "Extra charge")
        else:
            name = line.description or line.get_kind_display()

        items.append(
            {
                "name": name,
                "qty": int(line.quantity or 0),
                "price": float(line.unit_price or 0),
            }
        )
    for addon in order.addons.all():
        items.append(
            {
                "name": addon.service.name,
                "qty": 1,
                "price": float(addon.service.price_usd or 0),
            }
        )

    # Compute VAT/Excise from OrderTax snapshots (if present)
    try:
        from django.db.models import Sum

        vat_amount = order.taxes.filter(kind="VAT").aggregate(s=Sum("amount"))[
            "s"
        ] or Decimal("0.00")
        excise_amount = order.taxes.filter(kind="EXCISE").aggregate(s=Sum("amount"))[
            "s"
        ] or Decimal("0.00")
    except Exception:
        vat_amount = Decimal("0.00")
        excise_amount = Decimal("0.00")

    data = {
        "success": True,
        "invoice": {
            "order_id": order.order_reference,
            "customer_type": customer_type,
            "customer_name": customer_name,
            "customer_email": customer_email,
            "address": address,
            "nif": nif,
            "rccm": rccm,
            "idnat": idnat,
            "date": order.created_at.strftime("%Y-%m-%d") if order.created_at else "",
            "items": items,
            "total": float(order.total_price or 0),
            "vat": float(vat_amount or 0),
            "excise": float(excise_amount or 0),
        },
    }

    return JsonResponse(data)


@require_full_login
@customer_nonstaff_required
def orders_page(request):
    return render(request, "orders_page.html")


@require_full_login
@customer_nonstaff_required
def get_user_subscriptions(request):
    """
    AJAX endpoint to get the authenticated user's subscriptions.

    Returns a paginated payload with normalized subscription data.
    IMPORTANT: `cycle_fee` reflects the actual fee charged per billing cycle,
               computed from the plan's monthly price and the subscription's cycle.

    Query params:
      - page: int (default 1)
      - per_page: int (default 10, max 100)

    Response:
    {
      "success": true,
      "subscriptions": [
        {
          "id": int,
          "plan_name": str|null,
          "status": "active"|"suspended"|"cancelled"|"inactive",
          "billing_cycle": "monthly"|"quarterly"|"yearly",
          "cycle_fee": float,
          "monthly_fee": float,
          "started_at": "YYYY-MM-DD"|null,
          "next_billing_date": "YYYY-MM-DD"|null,
          "kit_number": str|null,     # <-- we return kit_number only
          "kit_serial": str|null,
          "order_reference": str|null,

          # GPS location from the linked Order
          "lat": float|null,
          "lng": float|null,
          "latitude": float|null,     # alias of lat
          "longitude": float|null     # alias of lng
        },
        ...
      ],
      "pagination": {
        "current_page": int,
        "total_pages": int,
        "total_items": int,
        "per_page": int,
        "has_next": bool,
        "has_previous": bool
      }
    }
    """
    # Prefer AJAX, but allow plain GET in tests / simple clients.
    xrw = request.headers.get("x-requested-with")
    if xrw and xrw != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": _("Invalid request")}, status=400
        )

    user = getattr(request, "user", None)
    if not user or not user.is_authenticated:
        return JsonResponse(
            {"success": False, "message": _("Unauthorized")}, status=401
        )

    try:
        from main.models import Subscription

        def _iso(d):
            try:
                return d.isoformat() if d else None
            except Exception:
                return None

        def _to_decimal(val):
            try:
                if val is None:
                    return Decimal("0")
                if isinstance(val, Decimal):
                    return val
                return Decimal(str(val))
            except (InvalidOperation, ValueError, TypeError):
                return Decimal("0")

        CYCLE_MONTHS = {"monthly": 1, "quarterly": 3, "yearly": 12}

        # ---- Queryset ----
        qs = (
            Subscription.objects.filter(user=user)
            .select_related(
                "plan", "order__kit_inventory"
            )  # includes Order + KitInventory
            .order_by("-started_at", "-id")
        )

        # Pagination
        try:
            page = int(request.GET.get("page", 1))
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = int(request.GET.get("per_page", 10))
        except (TypeError, ValueError):
            per_page = 10

        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10

        total_subscriptions = qs.count()
        offset = (page - 1) * per_page
        paginated = qs[offset : offset + per_page]

        subscriptions_data = []
        for s in paginated:
            plan = getattr(s, "plan", None)
            plan_price_monthly = _to_decimal(getattr(plan, "effective_price", 0))

            billing_cycle_raw = getattr(s, "billing_cycle", None) or "monthly"
            billing_cycle = str(billing_cycle_raw).lower().strip()
            months = CYCLE_MONTHS.get(billing_cycle, 1)
            cycle_fee = plan_price_monthly * months

            status_raw = getattr(s, "status", None) or ""
            status = str(status_raw).lower().strip()
            if status not in ("active", "suspended", "cancelled", "inactive"):
                if "cancel" in status:
                    status = "cancelled"
                elif "active" in status:
                    status = "active"
                elif "suspend" in status:
                    status = "suspended"
                elif "inactive" in status:
                    status = "inactive"
                else:
                    status = "cancelled"

            # From linked order: kit_number + kit_serial + GPS
            kit_number = None
            kit_serial = None
            lat = lng = None
            order = getattr(s, "order", None)
            if order is not None:
                kit_inv = getattr(order, "kit_inventory", None)
                if kit_inv is not None:
                    kit_number = getattr(
                        kit_inv, "kit_number", None
                    )  # <-- ONLY kit_number
                    kit_serial = getattr(kit_inv, "serial_number", None)
                lat = getattr(order, "latitude", None)
                lng = getattr(order, "longitude", None)

            subscriptions_data.append(
                {
                    "id": s.id,
                    "plan_name": getattr(plan, "name", None),
                    "status": status,
                    "billing_cycle": billing_cycle,
                    "cycle_fee": float(cycle_fee),
                    "monthly_fee": float(plan_price_monthly),
                    "started_at": _iso(getattr(s, "started_at", None)),
                    "next_billing_date": _iso(getattr(s, "next_billing_date", None)),
                    "kit_number": kit_number,  # <-- returned to UI
                    "kit_serial": kit_serial,
                    "order_reference": getattr(order, "order_reference", None),
                    "lat": float(lat) if lat is not None else None,
                    "lng": float(lng) if lng is not None else None,
                    "latitude": float(lat) if lat is not None else None,
                    "longitude": float(lng) if lng is not None else None,
                }
            )

            # print(kit_serial)

        total_pages = (total_subscriptions + per_page - 1) // per_page

        return JsonResponse(
            {
                "success": True,
                "subscriptions": subscriptions_data,
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "total_items": total_subscriptions,
                    "per_page": per_page,
                    "has_next": page < total_pages,
                    "has_previous": page > 1,
                },
            },
            status=200,
        )
    except Exception as e:
        logger.error("Error fetching user subscriptions: %s", str(e), exc_info=True)
        return JsonResponse(
            {"success": False, "message": _("Error fetching subscriptions.")},
            status=500,
        )


@require_full_login
@customer_nonstaff_required
def orders_list(request):
    """
    AJAX endpoint to get user's orders list
    """
    xrw = request.headers.get("x-requested-with")
    if xrw and xrw != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        user = request.user
        orders = (
            Order.objects.filter(user=user)
            .select_related("installation_activity", "installation_activity__feedback")
            .order_by("-created_at")
        )

        payment_filter = (request.GET.get("payment_status") or "").strip().lower()
        if payment_filter in {"paid", "unpaid", "awaiting_confirmation"}:
            orders = orders.filter(payment_status__iexact=payment_filter)

        # Pagination
        page = int(request.GET.get("page", 1))
        per_page = int(request.GET.get("per_page", 10))

        if page < 1:
            page = 1
        if per_page < 1 or per_page > 100:
            per_page = 10

        offset = (page - 1) * per_page
        total_orders = orders.count()
        paginated_orders = orders[offset : offset + per_page]

        orders_data = []
        for order in paginated_orders:
            installation = getattr(order, "installation_activity", None)
            feedback = getattr(installation, "feedback", None) if installation else None
            feedback_url = (
                reverse("client_feedback_detail", args=[installation.id])
                if installation
                else None
            )
            feedback_status = getattr(feedback, "status", None)
            feedback_locked = (
                feedback_status == Feedback.Status.LOCKED if feedback else False
            )
            feedback_exists = bool(feedback)
            can_feedback = bool(
                installation
                and (
                    not feedback
                    or feedback_status
                    in (Feedback.Status.SUBMITTED, Feedback.Status.EDITED)
                )
            )

            orders_data.append(
                {
                    "id": order.id,
                    "order_reference": order.order_reference,
                    "status": order.status,
                    "payment_status": order.payment_status,
                    "total_price": float(order.total_price or 0),
                    "created_at": (
                        order.created_at.strftime("%Y-%m-%d %H:%M")
                        if order.created_at
                        else None
                    ),
                    "order_date": (
                        order.created_at.strftime("%Y-%m-%d %H:%M")
                        if order.created_at
                        else None
                    ),
                    "kit_name": (
                        order.kit_inventory.kit.name
                        if order.kit_inventory and order.kit_inventory.kit
                        else None
                    ),
                    "plan_name": order.plan.name if order.plan else None,
                    "installation_id": installation.id if installation else None,
                    "feedback_url": feedback_url,
                    "feedback_status": feedback_status,
                    "feedback_locked": feedback_locked,
                    "feedback_exists": feedback_exists,
                    "can_feedback": can_feedback,
                }
            )

        total_pages = (total_orders + per_page - 1) // per_page

        return JsonResponse(
            {
                "success": True,
                "orders": orders_data,
                "pagination": {
                    "current_page": page,
                    "total_pages": total_pages,
                    "total_items": total_orders,
                    "per_page": per_page,
                    "has_next": page < total_pages,
                    "has_previous": page > 1,
                },
            }
        )

    except Exception as e:
        logger.error(f"Error fetching orders list: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "message": f"Error fetching orders: {str(e)}"},
            status=500,
        )


@require_full_login
@customer_nonstaff_required
def billing_page(request):
    """Client billing page with additional billings"""
    from site_survey.models import AdditionalBilling

    # Get additional billings for the current user
    additional_billings = (
        AdditionalBilling.objects.filter(survey__order__user=request.user)
        .select_related("survey", "survey__order", "order", "customer")
        .order_by("-created_at")
    )

    # Opportunistically ensure invoices exist for approved/paid billings
    invoice_refs = []
    for billing in additional_billings:
        if billing.status in {"approved", "paid"}:
            try:
                billing.ensure_invoice_entry()
            except Exception as exc:  # pragma: no cover - guard against ledger issues without breaking UI
                logger.warning(
                    "Unable to ensure invoice for AdditionalBilling %s: %s",
                    billing.billing_reference,
                    exc,
                )
        ref = billing.invoice_external_ref
        if ref:
            invoice_refs.append(ref)

    invoice_ready_map = {}
    if invoice_refs:
        existing_refs = set(
            AccountEntry.objects.filter(external_ref__in=invoice_refs).values_list(
                "external_ref", flat=True
            )
        )
        invoice_ready_map = {ref: ref in existing_refs for ref in invoice_refs}

    for billing in additional_billings:
        ref = billing.invoice_external_ref
        if ref:
            billing._has_invoice_cache = invoice_ready_map.get(ref, False)
        else:
            billing._has_invoice_cache = False

    context = {"additional_billings": additional_billings}

    return render(request, "billing_management.html", context)


@require_full_login
@customer_nonstaff_required
def support_page(request):
    return render(request, "support_management.html")


@require_full_login
@customer_nonstaff_required
def subscriptions(request):
    return render(request, "subscriptions_page.html")


@require_full_login
@customer_nonstaff_required
def subscription_details(request, id):
    # Store for session-based fetch
    request.session["order_id"] = id
    return render(request, "subscription_details_page.html")


@require_full_login
@customer_nonstaff_required
def subscriptions_details_fetch(request, subscription_id=None, order_id=None):
    """
    Return a single subscription's details for the frontpage modal.

    Accepts identifiers from:
      • Subscription ID: URL kwarg <int:subscription_id>, ?subscription_id=..., or session["subscription_id"]
      • (Fallback) Order ID: URL kwarg <int:order_id>, ?order_id=..., or session["order_id"]

    The frontend calls this with `?subscription_id=<id>`.
    """

    # ---------- Resolve identifiers (prefer subscription_id; fallback to order_id)
    def _as_int(v):
        if v in (None, "", "null", "None"):
            return None
        try:
            return int(v)
        except (TypeError, ValueError):
            return "invalid"

    sid = _as_int(
        subscription_id
        or request.GET.get("subscription_id")
        or request.session.get("subscription_id")
    )
    oid = _as_int(
        order_id or request.GET.get("order_id") or request.session.get("order_id")
    )

    if sid == "invalid":
        return JsonResponse(
            {"success": False, "error": "Invalid 'subscription_id'."}, status=400
        )
    if oid == "invalid":
        return JsonResponse(
            {"success": False, "error": "Invalid 'order_id'."}, status=400
        )
    if sid is None and oid is None:
        return JsonResponse(
            {"success": False, "error": "Missing 'subscription_id' or 'order_id'."},
            status=400,
        )

    # ---------- Query (ensure the subscription belongs to the current user)
    qs = Subscription.objects.select_related(
        "plan",
        "order",
        "order__kit_inventory",
        "order__kit_inventory__kit",
        # reverse O2O is valid for select_related
        "order__installation_activity",
    ).filter(user=request.user)
    if sid is not None:
        qs = qs.filter(id=sid)
    else:
        qs = qs.filter(order__id=oid)

    sub = qs.first()
    if not sub:
        return JsonResponse(
            {"success": False, "error": "Subscription not found."}, status=404
        )

    # ---------- Related objects
    plan = sub.plan
    order = sub.order
    inv = order.kit_inventory if order else None
    kit = inv.kit if inv else None
    ia = getattr(order, "installation_activity", None) if order else None

    # ---------- Helpers
    def _to_float(v):
        try:
            return float(v) if v is not None else None
        except (TypeError, ValueError):
            return None

    def _fmt_date(d):
        """Accepts date or datetime; returns ISO date string (YYYY-MM-DD) or None."""
        if not d:
            return None
        try:
            # If it's a datetime, localize then take .date()
            if hasattr(d, "date") and not hasattr(d, "year"):  # unlikely branch
                d = d.date()
            if hasattr(d, "tzinfo"):  # datetime
                return timezone.localdate(d).isoformat()
            # date
            return d.isoformat()
        except Exception:
            # fallback to str
            return str(d)

    # ---------- Monetary
    monthly_fee = _to_float(
        getattr(plan, "effective_price", None)
        or getattr(plan, "monthly_price_usd", None)
    )

    # ---------- Coordinates from Order
    lat = _to_float(getattr(order, "latitude", None)) if order else None
    lng = _to_float(getattr(order, "longitude", None)) if order else None

    # ---------- Usage (not modeled here -> return None; UI copes with null)
    usage_used_gb = None
    usage_cap_gb = _to_float(getattr(plan, "standard_data_gb", None))
    period_start = None
    period_end = None

    # ---------- Next billing (present on Subscription)
    next_bill = _fmt_date(getattr(sub, "next_billing_date", None))

    # ---------- Kit serials:
    # Prefer installation activity recorded serials if present; otherwise inventory serial
    dish_sn = (
        ia.dish_serial_number
        if ia and ia.dish_serial_number
        else (inv.serial_number if inv else None)
    )
    router_sn = ia.router_serial_number if ia and ia.router_serial_number else None

    # ---------- Build payload the frontend expects (include aliases for robustness)
    payload = {
        # identifiers / references
        "id": sub.id,
        "order_id": order.id if order else None,
        "order_reference": getattr(order, "order_reference", None),
        # plan & billing
        "plan_name": getattr(plan, "name", None),
        "billing_cycle": getattr(sub, "billing_cycle", None),
        "monthly_fee_usd": monthly_fee,  # modal uses this
        "monthly_fee": monthly_fee,  # alias
        "cycle_fee": monthly_fee,  # alias (table row uses this)
        # status & dates
        "status": getattr(sub, "status", None),
        "start_date": _fmt_date(getattr(sub, "started_at", None)),
        "started_at": _fmt_date(getattr(sub, "started_at", None)),  # alias
        "next_billing_date": next_bill,
        # kit details (UI shows kit_serial in "Kit ID" column)
        "kit_serial": dish_sn or (inv.serial_number if inv else None),
        "kit_number": getattr(inv, "kit_number", None),
        "kit_name": getattr(kit, "name", None) or "Starlink Kit",
        "dish_sn": dish_sn,
        "router_sn": router_sn,
        # usage
        "usage_used_gb": _to_float(usage_used_gb),
        "usage_cap_gb": usage_cap_gb,
        "data_cap_gb": usage_cap_gb,  # alias
        "usage_period_start": _fmt_date(period_start),
        "usage_period_end": _fmt_date(period_end),
        "period_start": _fmt_date(period_start),  # aliases for UI fallbacks
        "period_end": _fmt_date(period_end),
        # location (multiple keys so the JS `pickInstallCoords` can find them)
        "order_install_lat": lat,
        "order_install_lng": lng,
        "order_installation_lat": lat,
        "order_installation_lng": lng,
        "order_latitude": lat,
        "order_longitude": lng,
        "installation_latitude": lat,
        "installation_longitude": lng,
        "lat": lat,
        "lng": lng,
    }

    return JsonResponse({"success": True, "subscription": payload})


@require_full_login
@customer_nonstaff_required
@transaction.atomic
def cancel_order(request, order_ref):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # Ensure the order belongs to the logged-in user
    order = get_object_or_404(Order, order_reference=order_ref, user=request.user)

    # Only allow cancel if not already final and not shipped/delivered
    if order.status in ("shipped", "delivered", "cancelled"):
        return JsonResponse(
            {"success": False, "error": "Order cannot be cancelled at this stage."},
            status=400,
        )

    # Only allow if not paid (or still awaiting confirmation)
    if order.payment_status == "paid":
        return JsonResponse(
            {"success": False, "error": "Paid orders cannot be cancelled."}, status=400
        )

    # Use centralized cancellation (transactional, idempotent) so all side-effects apply
    res = order.cancel(reason="manual_cancel")

    return JsonResponse(
        {
            "success": True,
            "order_reference": order.order_reference,
            "status": "cancelled",
            "result": res,
        }
    )


# ---- view -----------------------------------------------------------------


def billing_history(request):
    """
    Grouped billing history for the logged-in user.

    Returns ONE row per invoice (order_reference) with:
      - order_id: the Order.pk
      - order_reference
      - date: charge date (or earliest payment date if no charge in window)
      - charge: { amount, status, currency }
      - payments: { total, count, currency }
      - can_download: bool (true only if there is at least one successful payment)
      - links: { invoice_pdf }
      - is_expired: bool
      - order_status: str (lowercased Order.status)

    Also returns a 'summary' containing wallet/account info and
    active_unpaid_balance_usd (ONLY unpaid orders that are not cancelled and not expired).
    """
    user = request.user
    if not user or not user.is_authenticated:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    q = (request.GET.get("q") or "").strip()
    type_filter = (request.GET.get("type") or "").lower()
    pay_status = (request.GET.get("payment_status") or "").lower()
    date_from = request.GET.get("date_from")
    date_to = request.GET.get("date_to")
    page = int(request.GET.get("page") or 1)

    # ---------- Date window (shared) ----------
    start_dt = None
    end_dt = None
    if date_from:
        try:
            start_dt = timezone.make_aware(datetime.strptime(date_from, "%Y-%m-%d"))
        except Exception:
            start_dt = None
    if date_to:
        try:
            end_dt = timezone.make_aware(
                datetime.strptime(date_to, "%Y-%m-%d")
            ) + timedelta(days=1)
        except Exception:
            end_dt = None

    # ---------- Charges (Orders) ----------
    orders_qs = Order.objects.filter(user=user).order_by("-created_at")
    if q:
        orders_qs = orders_qs.filter(order_reference__icontains=q)
    if pay_status:
        orders_qs = orders_qs.filter(payment_status__iexact=pay_status)
    if start_dt:
        orders_qs = orders_qs.filter(created_at__gte=start_dt)
    if end_dt:
        orders_qs = orders_qs.filter(created_at__lt=end_dt)

    # ---------- Payments (PaymentAttempt) ----------
    attempts_qs = (
        PaymentAttempt.objects.filter(order__user=user)
        .select_related("order")
        .order_by("-created_at")
    )
    if q:
        attempts_qs = attempts_qs.filter(order__order_reference__icontains=q)
    if start_dt:
        attempts_qs = attempts_qs.filter(created_at__gte=start_dt)
    if end_dt:
        attempts_qs = attempts_qs.filter(created_at__lt=end_dt)

    # Only successful payments are counted toward "Payment" column and "can_download"
    attempts_qs = [
        att for att in attempts_qs if _is_success_status((att.status or "").lower())
    ]

    # ---------- Build GROUPED rows (one per invoice/order_reference) ----------
    groups = {}
    order_of_refs = []  # preserve ordering before pagination

    # Seed from charges
    if type_filter in ("", "charge"):
        for o in orders_qs.select_related("plan"):
            ref = o.order_reference or "-"
            if ref not in groups:
                groups[ref] = {
                    "order_id": o.pk,
                    "order_reference": ref,
                    "date": _fmt_date(o.created_at),
                    "charge": {
                        "amount": _to_float(o.total_price),
                        "status": (o.payment_status or "").lower(),
                        "currency": "USD",
                    },
                    "payments": {
                        "total": 0.0,
                        "count": 0,
                        "currency": "USD",
                    },
                    "can_download": False,
                    "links": {
                        "invoice_pdf": request.build_absolute_uri(
                            f"/client/orders/details/{ref}/print/"
                        )
                    },
                    "is_expired": bool(o.is_expired()),
                    "order_status": (o.status or "").lower(),
                }
                order_of_refs.append(ref)
            else:
                g = groups[ref]
                if not g.get("order_id"):
                    g["order_id"] = o.pk
                if not g.get("charge"):
                    g["charge"] = {
                        "amount": _to_float(o.total_price),
                        "status": (o.payment_status or "").lower(),
                        "currency": "USD",
                    }
                if not g.get("date"):
                    g["date"] = _fmt_date(o.created_at)
                # merge expiry + status
                g["is_expired"] = bool(g.get("is_expired")) or bool(o.is_expired())
                if not g.get("order_status"):
                    g["order_status"] = (o.status or "").lower()

    # Merge in payments
    if type_filter in ("", "payment"):
        for att in attempts_qs:
            order = att.order  # not null
            ref = getattr(order, "order_reference", None) or "-"
            if ref not in groups:
                groups[ref] = {
                    "order_id": getattr(order, "pk", None),
                    "order_reference": ref,
                    "date": _fmt_date(att.created_at or att.transaction_time),
                    "charge": None,
                    "payments": {
                        "total": 0.0,
                        "count": 0,
                        "currency": att.currency or "USD",
                    },
                    "can_download": False,
                    "links": {
                        "invoice_pdf": request.build_absolute_uri(
                            f"/client/orders/details/{ref}/print/"
                        )
                    },
                    "is_expired": bool(order.is_expired()),
                    "order_status": (order.status or "").lower(),
                }
                order_of_refs.append(ref)

            g = groups[ref]
            if not g.get("order_id"):
                g["order_id"] = getattr(order, "pk", None)

            # Aggregate successful payments
            amt = _to_float(
                att.amount if att.amount is not None else (order.total_price or 0)
            )
            g["payments"]["total"] = round(
                float(g["payments"]["total"]) + float(amt), 2
            )
            g["payments"]["count"] = int(g["payments"]["count"] or 0) + 1
            if not g["payments"].get("currency"):
                g["payments"]["currency"] = att.currency or "USD"

            if not g.get("date"):
                g["date"] = _fmt_date(att.created_at or att.transaction_time)

            g["can_download"] = True

            # merge expiry + status
            g["is_expired"] = bool(g.get("is_expired")) or bool(order.is_expired())
            if not g.get("order_status"):
                g["order_status"] = (order.status or "").lower()

    # Apply "type" filter at the GROUP level, if provided
    if type_filter == "charge":
        order_of_refs = [
            ref for ref in order_of_refs if groups[ref].get("charge") is not None
        ]
    elif type_filter == "payment":
        order_of_refs = [
            ref for ref in order_of_refs if (groups[ref]["payments"]["count"] or 0) > 0
        ]

    # ---------- Sort groups by date DESC ----------
    order_of_refs.sort(key=lambda r: (groups[r].get("date") or ""), reverse=True)

    # ---------- Pagination over GROUPS ----------
    group_rows = [groups[ref] for ref in order_of_refs]
    paginator = Paginator(group_rows, 10)
    page_obj = paginator.get_page(page)

    # ---------- Summary via BillingAccount ----------
    acct = getattr(user, "billing_account", None)
    unpaid_due = Decimal("0.00")
    balance = Decimal("0.00")
    credit = Decimal("0.00")
    if acct:
        unpaid_due = acct.due_usd
        balance = acct.balance_usd
        credit = acct.credit_usd

    unpaid_due_f = _to_float(unpaid_due)
    balance_f = _to_float(balance)
    credit_f = _to_float(credit)

    # ---------- Wallet balance ----------
    wallet = getattr(user, "wallet", None)
    wallet_balance = (
        getattr(wallet, "balance", Decimal("0.00")) if wallet else Decimal("0.00")
    )
    wallet_balance_f = _to_float(wallet_balance)

    # Paid this month (successful payments only)
    paid_this_month = 0.0
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_attempts = PaymentAttempt.objects.filter(
        order__user=user, created_at__gte=month_start
    ).only("status", "amount")
    now_local = timezone.localtime()
    month_start = now_local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_attempts = PaymentAttempt.objects.filter(
        order__user=user, created_at__gte=month_start
    ).only("status", "amount")
    for a in month_attempts:
        if _is_success_status(a.status):
            paid_this_month += _to_float(a.amount)

    # Next billing date from active/suspended subscription
    sub = (
        Subscription.objects.filter(user=user, status__in=["active", "suspended"])
        .order_by("next_billing_date")
        .first()
    )
    next_billing_date = (
        sub.next_billing_date if (sub and sub.next_billing_date) else None
    )

    today = timezone.localdate()
    next_payment = {
        "date": next_billing_date.strftime("%Y-%m-%d") if next_billing_date else None,
        "days_until": None,
        "is_due_soon": False,
        "is_overdue": False,
        "status": None,
    }
    if next_billing_date:
        days_until = (next_billing_date - today).days
        next_payment["days_until"] = days_until
        if days_until < 0:
            next_payment["is_overdue"] = True
            next_payment["status"] = "overdue"
        elif days_until == 0:
            next_payment["is_due_soon"] = True
            next_payment["status"] = "due_today"
        elif 1 <= days_until <= 7:
            next_payment["is_due_soon"] = True
            next_payment["status"] = f"due_in_{days_until}_days"
        else:
            next_payment["status"] = "scheduled"

    # ---------- NEW: Only active unpaid orders (not cancelled, not expired) ----------
    now_ts = timezone.now()
    active_unpaid_qs = Order.objects.active_unpaid_for(user, now_ts)
    active_unpaid_total = active_unpaid_qs.aggregate(
        s=Coalesce(Sum("total_price"), Decimal("0.00"))
    )["s"] or Decimal("0.00")
    active_unpaid_f = _to_float(active_unpaid_total)

    return JsonResponse(
        {
            "success": True,
            "summary": {
                "unpaid_total_usd": round(unpaid_due_f, 2),
                "current_balance_usd": round(balance_f, 2),
                "account_credit_usd": round(credit_f, 2),
                "wallet_balance_usd": round(wallet_balance_f, 2),
                "paid_this_month_usd": round(paid_this_month, 2),
                "next_billing_date": next_payment["date"],
                "next_payment": next_payment,
                # ← what your card should display
                "active_unpaid_balance_usd": round(active_unpaid_f, 2),
            },
            # each row includes "order_id", "is_expired", "order_status"
            "history": list(
                page_obj
            ),  # each row now includes "order_id", "is_expired", "order_status"
            "page": page_obj.number,
            "total_pages": paginator.num_pages,
            "has_next": page_obj.has_next(),
            "has_previous": page_obj.has_previous(),
        },
        status=200,
    )


@require_full_login
@customer_nonstaff_required
@require_GET
def unpaid_due_total(request):
    """
    Return the total due amount (USD) for the logged-in user, based on orders table.
    New rule (per requirement): include all active orders that are NOT paid, NOT expired, and NOT cancelled.
      - Exclude orders with payment_status='paid'.
      - Exclude orders with status='cancelled'.
      - Exclude expired orders (expires_at <= now). If expires_at is NULL → treat as active.
      - Sum the order's total_price.
    Response JSON:
      { ok: true, unpaid_due_usd: float, count: int }
    """
    user = request.user
    if not user or not user.is_authenticated:
        return JsonResponse({"ok": False, "message": "Unauthorized"}, status=401)

    now_ts = timezone.now()
    qs = (
        Order.objects.filter(user=user)
        .exclude(payment_status="paid")
        .exclude(status="cancelled")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now_ts))
    )
    total = qs.aggregate(s=Coalesce(Sum("total_price"), Decimal("0.00")))
    amount = float(total["s"] or Decimal("0.00"))
    return JsonResponse(
        {"ok": True, "unpaid_due_usd": round(amount, 2), "count": qs.count()}
    )


@require_full_login
@customer_nonstaff_required
@require_GET
def net_due_total(request):
    """
    Return the Net Due amount (USD) for the logged-in user.
    New rule: include all active orders that are NOT paid, NOT expired, and NOT cancelled.
    Response JSON:
      { ok: true, net_due_usd: float, count: int }
    """
    user = request.user
    if not user or not user.is_authenticated:
        return JsonResponse({"ok": False, "message": "Unauthorized"}, status=401)

    now_ts = timezone.now()
    qs = (
        Order.objects.filter(user=user)
        .exclude(payment_status="paid")
        .exclude(status="cancelled")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now_ts))
    )
    total = qs.aggregate(s=Coalesce(Sum("total_price"), Decimal("0.00")))
    amount = float(total["s"] or Decimal("0.00"))
    return JsonResponse(
        {"ok": True, "net_due_usd": round(amount, 2), "count": qs.count()}
    )


@require_full_login
@customer_nonstaff_required
@require_GET
def current_balance_total(request):
    """
    Current Balance = sum of orders for the logged-in user where:
      - payment_status != 'paid'
      - status != 'cancelled'
      - not expired (expires_at is NULL or in the future)
    Summed over Order.total_price (USD).
    Response: { ok: true, current_balance_usd: float, count: int }
    """
    user = request.user
    if not user or not user.is_authenticated:
        return JsonResponse({"ok": False, "message": "Unauthorized"}, status=401)

    now_ts = timezone.now()
    qs = (
        Order.objects.filter(user=user)
        .exclude(status="cancelled")
        .exclude(payment_status="paid")
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now_ts))
    )
    total = qs.aggregate(s=Coalesce(Sum("total_price"), Decimal("0.00")))
    amount = float(total["s"] or Decimal("0.00"))
    return JsonResponse(
        {"ok": True, "current_balance_usd": round(amount, 2), "count": qs.count()}
    )


@require_full_login
@require_GET
def get_payment_methods(request):
    """
    AJAX endpoint to get available payment methods
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        from main.models import PaymentMethod

        methods = PaymentMethod.objects.all().order_by("name")

        method_list = [
            {
                "id": method.id,
                "name": method.name,
                "description": method.description or "",
            }
            for method in methods
        ]

        return JsonResponse({"success": True, "methods": method_list})

    except Exception as e:
        logger.error(f"Error fetching payment methods: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "message": f"Error fetching payment methods: {str(e)}"},
            status=500,
        )


@require_full_login
@require_GET
def get_tax_rates(request):
    """
    AJAX endpoint to get available tax rates
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    try:
        from main.models import TaxRate

        taxes = TaxRate.objects.all().order_by("description")

        tax_list = [
            {
                "id": tax.id,
                "description": tax.description,
                "percentage": float(tax.percentage),
            }
            for tax in taxes
        ]

        return JsonResponse({"success": True, "taxes": tax_list})

    except Exception as e:
        logger.error(f"Error fetching tax rates: {str(e)}", exc_info=True)
        return JsonResponse(
            {"success": False, "message": f"Error fetching tax rates: {str(e)}"},
            status=500,
        )


@require_full_login
@require_GET
def get_installation_fee(request):
    """
    AJAX endpoint to get installation fee based on location.
    Responds with:
      { success: true, amount_usd: "123.45", region: "Kinshasa" }
    """
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    lat = request.GET.get("lat")
    lng = request.GET.get("lng")
    if lat is None or lng is None:
        return JsonResponse(
            {"success": False, "message": "Latitude and longitude are required"},
            status=400,
        )

    # Parse/validate numbers early
    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return JsonResponse(
            {"success": False, "message": "Invalid coordinates."}, status=400
        )

    try:
        # 1) Get the amount via your helper
        fee: Decimal = installation_fee_for_coords(lat_f, lng_f)

        # 2) (Optional) Also return the region name if we can determine it
        region_name = None
        try:
            pt = Point(lng_f, lat_f, srid=4326)  # x=lng, y=lat
            region = (
                Region.objects.filter(fence__contains=pt).only("name").first()
            )  # <-- field matches your helper
            if region:
                region_name = region.name
        except Exception as sub_e:
            # Don't fail the whole endpoint if region lookup fails; just omit the name
            logger.debug("Region name lookup failed: %s", sub_e, exc_info=True)

        # Ensure Decimal is safe to serialize; send as string for precision
        amount_str = f"{fee:.2f}"

        resp = JsonResponse(
            {"success": True, "amount_usd": amount_str, "region": region_name},
            status=200,
        )
        resp["Cache-Control"] = "no-store"
        return resp

    except InvalidOperation as e:
        logger.error("Decimal error computing install fee: %s", e, exc_info=True)
        return JsonResponse(
            {"success": False, "message": "Failed to compute fee."}, status=500
        )
    except Exception as e:
        logger.error("Error calculating installation fee: %s", e, exc_info=True)
        return JsonResponse(
            {"success": False, "message": "Error calculating fee."}, status=500
        )


@require_full_login
def wallet_ledger(request):
    """
    Return wallet transactions for the logged-in user in JSON.
    Used by the 'View Ledger' modal.
    """
    user = request.user
    wallet = getattr(user, "wallet", None)

    if not wallet:
        return JsonResponse(
            {"success": True, "transactions": [], "balance_usd": "0.00"}
        )

    txs = wallet.transactions.select_related("order", "payment_attempt").order_by(
        "-created_at"
    )[:50]

    data = []
    for t in txs:
        data.append(
            {
                "id": t.id,
                "tx_type": t.tx_type,  # credit | debit
                "amount": f"{t.amount:.2f}",
                "currency": t.currency,
                "note": t.note,
                "date": timezone.localtime(t.created_at).strftime("%Y-%m-%d %H:%M"),
                "order_reference": getattr(t.order, "order_reference", None),
                "payment_attempt_id": getattr(t.payment_attempt, "id", None),
            }
        )

    return JsonResponse(
        {
            "success": True,
            "balance_usd": f"{wallet.balance:.2f}",
            "transactions": data,
        }
    )


@require_full_login
def report_invoice_pdf(request, order_id: int):
    """
    Minimalist, Starlink-like invoice:
      - Header: company logo + company meta (left)
      - Parties row: Bill To (left) + Invoice meta (right)
      - Items from Order.lines; VAT/EXCISE from OrderTax
      - Centered bottom section (divider, QR/Barcode placeholder, note)

    NOTE: This client endpoint now attempts to resolve the Invoice for the given order
    and redirects to the unified invoice-by-number PDF under /billing/invoice/<id>/pdf/.
    If no Invoice exists yet, it falls back to legacy rendering below.
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
        t = Table([[flow]], colWidths=[width], hAlign="CENTER")
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        return t

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

    # Line items
    line_items = []
    for ln in order.lines.all().order_by("id"):
        label = ln.description or ln.get_kind_display() or "Item"
        detail = f"Qty {ln.quantity}"
        line_items.append([label.upper(), _safe(detail), _money(ln.line_total)])

    # Taxes
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
    GRAY_700 = colors.HexColor("#5A5AF")
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

    # Top band
    band = Table(
        [[Paragraph("&nbsp;", styles["H_META"])]], colWidths=[W], rowHeights=[6]
    )
    band.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BLACK)]))
    elems.append(band)
    elems.append(Spacer(1, 10))

    # ----- Resolve logo path safely (no reliance on "settings" name) ----------
    LOGO_STATIC_PATH = "images/logo/logo.png"
    logo_path = None

    # 1) Try staticfiles finder (works with DEBUG and collectstatic)
    try:
        logo_path = finders.find(LOGO_STATIC_PATH)
    except Exception:
        logo_path = None

    # 2) Try common filesystem fallbacks
    if not logo_path and getattr(django_settings, "BASE_DIR", None):
        p = os.path.join(django_settings.BASE_DIR, "static", LOGO_STATIC_PATH)
        if os.path.exists(p):
            logo_path = p
    if not logo_path and getattr(django_settings, "STATIC_ROOT", None):
        p = os.path.join(django_settings.STATIC_ROOT, LOGO_STATIC_PATH)
        if os.path.exists(p):
            logo_path = p
    if not logo_path:
        for d in getattr(django_settings, "STATICFILES_DIRS", []):
            p = os.path.join(d, LOGO_STATIC_PATH)
            if os.path.exists(p):
                logo_path = p
                break

    # Header — LEFT ONLY
    left_block = []
    if logo_path and os.path.exists(logo_path):
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
    for txt, kind in bill_to_lines[1:]:
        bill_to_paras.append(
            Paragraph(_safe(txt), styles["BODY" if kind == "body" else "SMALL"])
        )

    # Invoice meta (right)
    invoice_meta_right = [Paragraph("<b>INVOICE</b>", styles["LBL_UP"]), Spacer(1, 4)]
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

    # Totals
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

    # Bottom
    elems.append(
        center_flow(HR(W * 0.6, thickness=0.4, color=GRAY_300, vspace=3), width=W)
    )
    elems.append(Spacer(1, 6))

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


@require_full_login
def additional_billing_invoice_pdf(request, billing_id: int):
    """
    Generate a PDF invoice for additional equipment billing (post site-survey).
    """
    from site_survey.models import AdditionalBilling

    billing = get_object_or_404(
        AdditionalBilling.objects.select_related(
            "order", "order__user", "customer", "survey"
        ).prefetch_related("survey__additional_costs__extra_charge"),
        pk=billing_id,
    )

    if request.user != billing.customer and not request.user.is_staff:
        raise PermissionDenied(_("You are not authorized to view this invoice."))

    billing.ensure_invoice_entry()

    # ------------------- helper funcs (local to keep styling consistent) -----
    def _safe(val, dash="—"):
        s = (
            (val or "").strip()
            if isinstance(val, str)
            else ("" if val is None else str(val))
        )
        return s or dash

    def _money(val):
        try:
            return f"${Decimal(val or 0).quantize(Decimal('0.01')):,.2f}"
        except Exception:
            return "$0.00"

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

    def center_flow(flow, width):
        t = Table([[flow]], colWidths=[width], hAlign="CENTER")
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
        return t

    # ------------------- invoice data ---------------------------------------
    order = billing.order
    user = order.user if order else billing.customer
    invoice_number = billing.billing_reference
    order_reference = order.order_reference if order else "—"
    issued_at = billing.approved_at or billing.created_at or timezone.now()

    # Cost breakdown
    cost_rows = []
    for cost in billing.get_cost_breakdown():
        label = cost.item_name or _("Additional item")
        cost_rows.append(
            [
                label.upper(),
                str(cost.quantity),
                _money(cost.total_price),
            ]
        )

    if not cost_rows:
        cost_rows.append(
            [
                _("ADDITIONAL EQUIPMENT").upper(),
                "0",
                _money(0),
            ]
        )

    subtotal = billing.subtotal or Decimal("0.00")
    vat_amount = billing.tax_amount or Decimal("0.00")
    total_amount = billing.total_amount or Decimal("0.00")

    # KYC / address lines
    bill_to_lines: list[tuple[str, str]] = [("BILL TO", "header")]
    company_kyc = getattr(user, "company_kyc", None) if user else None
    personal_kyc = getattr(user, "personnal_kyc", None) if user else None

    if company_kyc and (
        _safe(company_kyc.company_name) != "—" or _safe(company_kyc.address) != "—"
    ):
        bill_to_lines += [
            (_safe(company_kyc.company_name), "body"),
            (_safe(company_kyc.address), "small"),
        ]
        identifiers = []
        if _safe(company_kyc.rccm) != "—":
            identifiers.append(f"RCCM: {company_kyc.rccm}")
        if _safe(company_kyc.nif) != "—":
            identifiers.append(f"NIF: {company_kyc.nif}")
        if _safe(company_kyc.id_nat) != "—":
            identifiers.append(f"ID NAT: {company_kyc.id_nat}")
        if identifiers:
            bill_to_lines.append((" • ".join(identifiers), "small"))
        if _safe(company_kyc.representative_name) != "—":
            bill_to_lines.append(
                (
                    _("Rep: %(name)s") % {"name": company_kyc.representative_name},
                    "small",
                )
            )
        bill_to_lines.append((_safe(getattr(user, "email", "")), "small"))
        bill_to_lines.append((_safe(getattr(user, "phone", "")), "small"))
    elif personal_kyc and (
        _safe(personal_kyc.full_name) != "—" or _safe(personal_kyc.address) != "—"
    ):
        bill_to_lines += [
            (_safe(personal_kyc.full_name or getattr(user, "full_name", "")), "body"),
        ]
        if _safe(personal_kyc.address) != "—":
            bill_to_lines.append((_safe(personal_kyc.address), "small"))
        if _safe(personal_kyc.document_number) != "—":
            bill_to_lines.append(
                (
                    _("Document: %(doc)s") % {"doc": personal_kyc.document_number},
                    "small",
                )
            )
        bill_to_lines.append((_safe(getattr(user, "email", "")), "small"))
        bill_to_lines.append((_safe(getattr(user, "phone", "")), "small"))
    else:
        customer_name = (
            (getattr(user, "full_name", None) or getattr(user, "username", None) or "")
            if user
            else ""
        )
        bill_to_lines += [
            (_safe(customer_name), "body"),
            (_safe(getattr(user, "email", "") if user else ""), "small"),
            (_safe(getattr(user, "phone", "") if user else ""), "small"),
        ]

    # ------------------- PDF document ---------------------------------------
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=f"Invoice {invoice_number}",
        author="Nexus Telecoms SA",
    )
    W = doc.width

    BLACK = colors.black
    GRAY_900 = colors.HexColor("#0B0B0C")
    GRAY_700 = colors.HexColor("#5A5A5F")
    GRAY_300 = colors.HexColor("#D1D5DB")
    GRAY_200 = colors.HexColor("#E5E7EB")
    GRAY_100 = colors.HexColor("#F5F5F5")

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

    elems.append(Paragraph(_("Invoice for Additional Equipment"), styles["H_BIG"]))
    elems.append(
        Paragraph(
            _("Issued on %(date)s") % {"date": issued_at.strftime("%Y-%m-%d")},
            styles["H_META"],
        )
    )
    elems.append(Spacer(1, 10))

    meta_tbl = Table(
        [
            [
                Paragraph(_("Invoice #"), styles["LBL_UP"]),
                Paragraph(invoice_number, styles["BODY"]),
                Paragraph(_("Order #"), styles["LBL_UP"]),
                Paragraph(order_reference, styles["BODY"]),
            ],
            [
                Paragraph(_("Customer"), styles["LBL_UP"]),
                Paragraph(_safe(getattr(user, "full_name", "")), styles["BODY"]),
                Paragraph(_("Email"), styles["LBL_UP"]),
                Paragraph(_safe(getattr(user, "email", "")), styles["BODY"]),
            ],
        ],
        colWidths=[W * 0.12, W * 0.38, W * 0.12, W * 0.38],
    )
    meta_tbl.setStyle(
        TableStyle(
            [
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elems.append(meta_tbl)
    elems.append(Spacer(1, 12))

    bill_to_data = []
    for text, style_key in bill_to_lines:
        if style_key == "header":
            bill_to_data.append(
                [
                    Paragraph(_("Bill To"), styles["LBL_UP"]),
                    "",
                ]
            )
        elif style_key == "body":
            bill_to_data.append([Paragraph(text, styles["BODY"]), ""])
        else:
            bill_to_data.append([Paragraph(text, styles["SMALL"]), ""])

    bill_to_tbl = Table(bill_to_data, colWidths=[W * 0.6, W * 0.4])
    bill_to_tbl.setStyle(
        TableStyle(
            [
                ("SPAN", (0, 0), (1, 0)),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
            ]
        )
    )
    elems.append(bill_to_tbl)
    elems.append(Spacer(1, 12))

    items_data = [[_("Item").upper(), _("Quantity"), _("Amount")]]
    items_data += cost_rows
    items_tbl = Table(
        items_data,
        colWidths=[W * 0.55, W * 0.20, W * 0.25],
        hAlign="LEFT",
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

    totals_data = [
        [
            Paragraph(_("Subtotal"), styles["TOTALS_LABEL"]),
            Paragraph(_money(subtotal), styles["TOTALS_VAL"]),
        ],
        [
            Paragraph(_("VAT"), styles["TOTALS_LABEL"]),
            Paragraph(_money(vat_amount), styles["TOTALS_VAL"]),
        ],
        [
            Paragraph(_("Total"), styles["TOTALS_LABEL"]),
            Paragraph(_money(total_amount), styles["TOTALS_VAL"]),
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

    elems.append(
        center_flow(HR(W * 0.6, thickness=0.4, color=GRAY_300, vspace=3), width=W)
    )
    elems.append(Spacer(1, 6))

    note = Paragraph(
        _(
            "Thank you for your prompt attention. For support, contact billing@nexus.cd."
        ),
        styles["SMALL_CENTER"],
    )
    elems.append(center_flow(note, width=W))

    doc.build(elems)
    pdf = buf.getvalue()
    buf.close()

    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="Invoice_{invoice_number}.pdf"'
    )
    return response


# ---------- tiny helpers ----------


def _media_subdir(*parts) -> str:
    """Ensure a subdir exists under MEDIA_ROOT and return its path."""
    base = django_settings.MEDIA_ROOT
    path = os.path.join(base, *parts)
    os.makedirs(path, exist_ok=True)
    return path


def _avatar_disk_pattern(user: User) -> str:
    return os.path.join(_media_subdir("avatars"), f"user_{user.pk}.*")


def _avatar_disk_path(user: User, ext: str) -> str:
    ext = (ext or "").lower().strip(".")
    if ext not in {"jpg", "jpeg", "png", "webp"}:
        ext = "jpg"
    return os.path.join(_media_subdir("avatars"), f"user_{user.pk}.{ext}")


def _avatar_url(user: User) -> str | None:
    matches = glob.glob(_avatar_disk_pattern(user))
    if not matches:
        return None
    # pick the newest saved file
    latest = max(matches, key=os.path.getmtime)
    rel = os.path.relpath(latest, django_settings.MEDIA_ROOT).replace("\\", "/")
    return django_settings.MEDIA_URL.rstrip("/") + "/" + rel


def _avatar_delete(user: User) -> None:
    for p in glob.glob(_avatar_disk_pattern(user)):
        try:
            os.remove(p)
        except OSError:
            pass


def _prefs_file(user: User) -> str:
    return os.path.join(_media_subdir("user_prefs"), f"{user.pk}.json")


DEFAULT_PREFS = {
    "notify_updates": False,
    "notify_billing": True,
    "notify_tickets": True,
    "twofa_enabled": False,
}


def _prefs_load(user: User) -> dict:
    try:
        with open(_prefs_file(user), "r", encoding="utf-8") as f:
            data = json.load(f)
            return {**DEFAULT_PREFS, **(data or {})}
    except FileNotFoundError:
        return DEFAULT_PREFS.copy()
    except Exception:
        return DEFAULT_PREFS.copy()


def _prefs_save(user: User, prefs: dict) -> dict:
    full = {**DEFAULT_PREFS, **(prefs or {})}
    with open(_prefs_file(user), "w", encoding="utf-8") as f:
        json.dump(full, f)
    return full


def _kyc_for(user: User):
    """Prefer CompanyKYC when present, otherwise PersonalKYC; else None."""
    try:
        ck = getattr(user, "company_kyc", None)
        if ck:
            return ck
    except CompanyKYC.DoesNotExist:
        pass
    try:
        pk = getattr(user, "personnal_kyc", None)
        if pk:
            return pk
    except PersonalKYC.DoesNotExist:
        pass
    return None


# ---------- main page ----------


@login_required
def settings_sidebar_page(request: HttpRequest) -> HttpResponse:
    user = request.user

    # Build a simple "profile" dict for the template
    profile = {
        "first_name": user.first_name or "",
        "last_name": user.last_name or "",
        "email": user.email or "",
        "phone": getattr(user, "phone", "") or "",
        "avatar_url": _avatar_url(user) or "/static/icons/account_avatar.png",
    }

    # Attach runtime prefs object so template can do `request.user.prefs.*`
    prefs_dict = _prefs_load(user)
    user.prefs = SimpleNamespace(**prefs_dict)  # exposed to template via RequestContext

    ctx = {
        "profile": profile,
        "kyc": _kyc_for(user),
        # Optional rejection extra context if you use these names in template
        "kyc_rejection_reason": getattr(
            getattr(user, "personnal_kyc", None), "rejection_reason", ""
        )
        or getattr(getattr(user, "company_kyc", None), "rejection_reason", ""),
        "kyc_rejection_details": getattr(
            getattr(user, "personnal_kyc", None), "remarks", ""
        )
        or getattr(getattr(user, "company_kyc", None), "remarks", ""),
    }
    return render(request, "client/settings_sidebar_clean.html", ctx)


# ---------- AJAX endpoints ----------


@login_required
@require_POST
def settings_profile_update(request: HttpRequest) -> JsonResponse:
    user = request.user
    data = request.POST

    # Names & contact
    user.first_name = (data.get("first_name") or "").strip()
    user.last_name = (data.get("last_name") or "").strip()
    user.phone = (data.get("phone") or "").strip()

    new_email = (data.get("email") or "").strip().lower()
    if new_email and new_email != user.email:
        if User.objects.filter(email=new_email).exclude(pk=user.pk).exists():
            return JsonResponse(
                {"success": False, "message": _("Email already in use.")}, status=400
            )
        user.email = new_email
    user.save(update_fields=["first_name", "last_name", "phone", "email"])

    # Ensure prefs exists
    prefs, created = UserPreferences.objects.get_or_create(user=user)

    # Avatar handling via ImageField storage
    remove_avatar = (data.get("remove_avatar") or "0") == "1"
    if remove_avatar and prefs.avatar:
        prefs.avatar.delete(save=False)
        prefs.avatar = None

    f = request.FILES.get("avatar")
    if f:
        # Name file predictably (storage will place it under MEDIA_ROOT/avatars/)
        ts = timezone.now().strftime("%Y%m%d_%H%M%S")
        base, ext = (f.name.rsplit(".", 1) + [""])[:2]
        filename = (
            f"avatars/user_{user.pk}_{ts}.{ext.lower()}"
            if ext
            else f"avatars/user_{user.pk}_{ts}"
        )
        prefs.avatar.save(filename, f, save=False)

    if remove_avatar or f:
        prefs.save(update_fields=["avatar"])

    # Build avatar URL (fallback to your static default)
    avatar_url = (
        prefs.avatar.url if prefs.avatar else "/static/icons/account_avatar.png"
    )

    return JsonResponse(
        {
            "success": True,
            "message": _("Saved."),
            "profile": {
                "first_name": user.first_name,
                "last_name": user.last_name,
                "email": user.email,
                "phone": user.phone,
                "avatar_url": avatar_url,
            },
        }
    )


@login_required
@require_POST
def settings_password_update(request: HttpRequest) -> JsonResponse:
    cur = request.POST.get("current_password") or ""
    npw = request.POST.get("new_password") or ""
    cpw = request.POST.get("confirm_password") or ""

    if not cur or not npw or not cpw:
        return JsonResponse(
            {"success": False, "message": _("All fields are required.")}, status=400
        )

    if npw != cpw:
        return JsonResponse(
            {"success": False, "message": _("Passwords do not match.")}, status=400
        )

    user = request.user
    if not user.check_password(cur):
        return JsonResponse(
            {"success": False, "message": _("Current password is incorrect.")},
            status=400,
        )

    user.set_password(npw)
    user.save()
    update_session_auth_hash(request, user)  # keep the user logged in

    return JsonResponse({"success": True, "message": _("Password updated.")})


@login_required
@require_POST
def settings_notifications_update(request):
    # DON'T use underscore for get_or_create's second return value
    prefs, created = UserPreferences.objects.get_or_create(user=request.user)

    prefs.notify_updates = "updates" in request.POST
    prefs.notify_billing = "billing" in request.POST
    prefs.notify_tickets = "tickets" in request.POST
    prefs.save(update_fields=["notify_updates", "notify_billing", "notify_tickets"])

    return JsonResponse(
        {
            "success": True,
            "message": _("Saved."),
            "prefs": {
                "updates": prefs.notify_updates,
                "billing": prefs.notify_billing,
                "tickets": prefs.notify_tickets,
            },
        }
    )


@login_required
@require_POST
def settings_twofa_toggle(request: HttpRequest) -> JsonResponse:
    user = request.user
    prefs = _prefs_load(user)

    enabled = (request.POST.get("enabled") or "0") in {"1", "true", "True", "on"}
    prefs["twofa_enabled"] = bool(enabled)
    _prefs_save(user, prefs)

    return JsonResponse(
        {
            "success": True,
            "message": _("Two-factor enabled.")
            if enabled
            else _("Two-factor disabled."),
        }
    )


@login_required
@require_POST
def settings_delete_account(request: HttpRequest) -> JsonResponse:
    user = request.user

    # 1) Guard: no active subscriptions may remain
    if Subscription.objects.filter(user=user, status="active").exists():
        return JsonResponse(
            {
                "success": False,
                "message": _(
                    "You still have an active subscription. Please cancel it before deactivating your account."
                ),
            },
            status=409,
        )

    # 2) Soft-deactivate & schedule synchronous PII erasure after commit
    with transaction.atomic():
        user.is_active = False
        user.save(update_fields=["is_active"])

        uid = user.id
        # Run PII erasure/anonymization only after the deactivation commit is durable
        transaction.on_commit(lambda: erase_user_personal_data(uid))

    # 3) Log out current session (ignore errors)
    try:
        logout(request)
    except Exception:
        pass

    return JsonResponse(
        {
            "success": True,
            "message": _(
                "Account scheduled for deactivation. Your personal data will now be removed or anonymized."
            ),
        }
    )


# ---------- Utilities ----------


def _json_error(message: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"success": False, "error": message}, status=status)


def _parse_json(request: HttpRequest) -> dict:
    """
    Parse JSON from request.body when Content-Type is application/json,
    otherwise fall back to request.POST.
    """
    if request.content_type and "application/json" in request.content_type:
        try:
            body = request.body.decode("utf-8") or "{}"
            return json.loads(body)
        except json.JSONDecodeError:
            return {}
    # fallback to form POST
    return request.POST.dict()


def _coerce_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _subscription_payload(sub: Subscription) -> dict:
    plan = sub.plan
    order = sub.order
    inv = getattr(order, "kit_inventory", None)
    kit = getattr(inv, "kit", None)

    def _fmt_dt(d):
        if not d:
            return None
        if hasattr(d, "isoformat"):
            return d.isoformat()
        # handle date/datetime gracefully
        try:
            return d.strftime("%Y-%m-%d")
        except Exception:
            return str(d)

    def _to_float(x):
        try:
            return float(x)
        except Exception:
            return None

    return {
        "id": sub.id,
        "order_id": order.id if order else None,
        "plan_name": plan.name if plan else None,
        "billing_cycle": sub.billing_cycle,
        "monthly_fee_usd": _to_float(
            getattr(plan, "effective_price", None)
            or getattr(plan, "monthly_price_usd", None)
        ),
        "status": sub.status,
        "kit_serial": inv.serial_number if inv else None,
        "kit_name": (kit.name if kit else None) or "Starlink Kit",
        "data_cap_gb": plan.standard_data_gb if plan else None,
        "start_date": _fmt_dt(sub.started_at),
        "next_billing_date": _fmt_dt(sub.next_billing_date),
        "usage_period_start": None,
        "usage_period_end": None,
        # Optional coordinates if your Order has them:
        "order_latitude": getattr(order, "latitude", None),
        "order_longitude": getattr(order, "longitude", None),
    }


def _get_user_subscription_for_update(user, sid: int) -> Subscription | None:
    if not sid:
        return None
    return (
        Subscription.objects.select_for_update()
        .select_related(
            "plan", "order", "order__kit_inventory", "order__kit_inventory__kit"
        )
        .filter(user=user, id=sid)
        .first()
    )


# ---------- Actions: pause / resume / cancel ----------


@require_POST
@require_full_login
@customer_nonstaff_required
@transaction.atomic
def subscriptions_pause(request: HttpRequest) -> JsonResponse:
    """
    Pause a subscription (status => 'suspended').
    Only allowed from 'active'.
    """
    data = _parse_json(request)
    sid = _coerce_int(data.get("subscription_id") or data.get("id"))
    if not sid:
        return _json_error("Missing 'subscription_id'.", status=400)

    sub = _get_user_subscription_for_update(request.user, sid)
    if not sub:
        return _json_error("Subscription not found.", status=404)

    if sub.status == "cancelled":
        return _json_error("Cannot pause a cancelled subscription.", status=409)
    if sub.status == "suspended":
        # idempotent success
        return JsonResponse(
            {
                "success": True,
                "message": "Already paused.",
                "subscription": _subscription_payload(sub),
            }
        )

    if sub.status != "active":
        return _json_error(
            f"Cannot pause a subscription from state '{sub.status}'.", status=409
        )

    sub.status = "suspended"
    sub.save(update_fields=["status"])
    return JsonResponse({"success": True, "subscription": _subscription_payload(sub)})


@require_POST
@require_full_login
@customer_nonstaff_required
@transaction.atomic
def subscriptions_resume(request: HttpRequest) -> JsonResponse:
    """
    Resume a subscription (status => 'active').
    Only allowed from 'suspended'.
    """
    data = _parse_json(request)
    sid = _coerce_int(data.get("subscription_id") or data.get("id"))
    if not sid:
        return _json_error("Missing 'subscription_id'.", status=400)

    sub = _get_user_subscription_for_update(request.user, sid)
    if not sub:
        return _json_error("Subscription not found.", status=404)

    if sub.status == "cancelled":
        return _json_error("Cannot resume a cancelled subscription.", status=409)
    if sub.status == "active":
        # idempotent success
        return JsonResponse(
            {
                "success": True,
                "message": "Already active.",
                "subscription": _subscription_payload(sub),
            }
        )

    if sub.status != "suspended":
        return _json_error(
            f"Cannot resume a subscription from state '{sub.status}'.", status=409
        )

    sub.status = "active"
    sub.save(update_fields=["status"])
    return JsonResponse({"success": True, "subscription": _subscription_payload(sub)})


@require_POST
@require_full_login
@customer_nonstaff_required
@transaction.atomic
def subscriptions_cancel(request: HttpRequest) -> JsonResponse:
    """
    Cancel a subscription (status => 'cancelled', sets ended_at).
    Allowed from 'active' or 'suspended'. Idempotent if already cancelled.
    """
    data = _parse_json(request)
    sid = _coerce_int(data.get("subscription_id") or data.get("id"))
    if not sid:
        return _json_error("Missing 'subscription_id'.", status=400)

    sub = _get_user_subscription_for_update(request.user, sid)
    if not sub:
        return _json_error("Subscription not found.", status=404)

    if sub.status == "cancelled":
        return JsonResponse(
            {
                "success": True,
                "message": "Already cancelled.",
                "subscription": _subscription_payload(sub),
            }
        )

    if sub.status not in ("active", "suspended"):
        return _json_error(
            f"Cannot cancel a subscription from state '{sub.status}'.", status=409
        )

    sub.status = "cancelled"
    sub.ended_at = timezone.now().date()
    # optional: you may want to clear next_billing_date
    # sub.next_billing_date = None
    sub.save(update_fields=["status", "ended_at"])
    return JsonResponse({"success": True, "subscription": _subscription_payload(sub)})


# ---------- Quick ticket creation ----------


@require_POST
@require_full_login
@customer_nonstaff_required
@transaction.atomic
def tickets_quick_create(request: HttpRequest) -> JsonResponse:
    """
    Create a support ticket quickly from the modal.

    Expected JSON:
      {
        "subscription_id": 123,     # required (ensures ownership)
        "subject": "Issue ...",     # optional
        "category": "technical",    # optional -> one of Ticket.Category values
        "priority": "normal",       # optional -> one of Ticket.Priority values
        "message": "Optional text"  # optional
      }
    """
    data = _parse_json(request)
    sid = _coerce_int(data.get("subscription_id") or data.get("id"))
    if not sid:
        return _json_error("Missing 'subscription_id'.", status=400)

    # Ensure the subscription exists and belongs to the user
    sub = (
        Subscription.objects.filter(id=sid, user=request.user)
        .select_related("plan")
        .first()
    )
    if not sub:
        return _json_error("Subscription not found.", status=404)

    # Sanitize enums
    category = (data.get("category") or "").lower().strip() or Ticket.Category.TECHNICAL
    priority = (data.get("priority") or "").lower().strip() or Ticket.Priority.NORMAL

    if category not in Ticket.Category.values:
        category = Ticket.Category.TECHNICAL
    if priority not in Ticket.Priority.values:
        priority = Ticket.Priority.NORMAL

    # Subject/message defaults
    plan_name = getattr(sub.plan, "name", None) or "Subscription"
    default_subject = f"{plan_name} – subscription #{sub.id}"
    subject = (data.get("subject") or "").strip() or default_subject
    message = (data.get("message") or "").strip()

    # Helpful context injected into message
    extra_context = f"\n\n[Context]\n- Subscription ID: {sub.id}\n- Status: {sub.status}\n- Plan: {plan_name}\n"
    if not message:
        message = (
            "User raised a ticket from the subscription details modal." + extra_context
        )
    else:
        message = message + extra_context

    ticket = Ticket.objects.create(
        user=request.user,
        subject=subject,
        category=category,
        priority=priority,
        status=Ticket.Status.OPEN,
        message=message,
    )

    # Build an absolute URL to the ticket detail page
    try:
        ticket_url = request.build_absolute_uri(ticket.get_absolute_url())
    except Exception:
        ticket_url = ticket.get_absolute_url()

    return JsonResponse(
        {
            "success": True,
            "ticket_id": ticket.id,
            "ticket_url": ticket_url,
        }
    )


PAGE_SIZE_DEFAULT = 10  # tune as you like


def _ticket_json(request, t: Ticket):
    """Serialize a ticket for list API."""
    return {
        "id": t.id,
        "subject": t.subject or "",
        "status": t.status or "",
        "updated_at": (t.updated_at.isoformat() if t.updated_at else None),
        "detail_url": reverse("ticket_detail", args=[t.pk]),
    }


@login_required
@require_GET
def tickets_list_api(request):
    """
    JSON list for Support page:
    returns {"tickets":[...], "page":1, "total_pages":N, "total_items":M}
    """
    page = int(request.GET.get("page", 1) or 1)
    per_page = int(request.GET.get("per_page", PAGE_SIZE_DEFAULT) or PAGE_SIZE_DEFAULT)

    qs = (
        Ticket.objects.filter(user=request.user)
        .only("id", "subject", "status", "updated_at")  # efficient fields
        .order_by("-updated_at", "-id")
    )

    paginator = Paginator(qs, per_page)
    try:
        pg = paginator.page(page)
    except EmptyPage:
        pg = paginator.page(paginator.num_pages or 1)

    data = {
        "tickets": [_ticket_json(request, t) for t in pg.object_list],
        "page": pg.number,
        "total_pages": paginator.num_pages,
        "total_items": paginator.count,
    }
    return JsonResponse(data, status=200)


@login_required
@require_POST
def ticket_create_api(request):
    """
    AJAX create endpoint used by your form.
    Expects: subject, message, category, priority
    Returns: {success, id, detail_url}
    """
    subject = (request.POST.get("subject") or "").strip()
    message = (request.POST.get("message") or "").strip()
    category = (request.POST.get("category") or "technical").strip()
    priority = (request.POST.get("priority") or "normal").strip()

    if not subject or not message:
        return JsonResponse(
            {"success": False, "message": "Subject and message are required."},
            status=400,
        )

    t = Ticket.objects.create(
        user=request.user,
        subject=subject,
        message=message,
        category=category,
        priority=priority,
        # status defaults to "open" via model default
    )

    return JsonResponse(
        {
            "success": True,
            "id": t.pk,
            "detail_url": reverse("ticket_detail", args=[t.pk]),
        },
        status=201,
    )


@login_required
@xframe_options_exempt  # allow rendering in the iframe modal
def ticket_detail(request, pk: int):
    """
    HTML detail page.
    - If `?inmodal=1` or AJAX: render a compact, iframe-friendly template.
    - Otherwise render the full page.
    """
    ticket = get_object_or_404(Ticket, pk=pk, user=request.user)

    # Small helper for consistent badge classes in template (optional)
    def status_badge_classes(s: str) -> str:
        s = (s or "").lower()
        if s == "open":
            return "bg-emerald-50 text-emerald-700 ring-emerald-200"
        if s == "pending":
            return "bg-amber-50 text-amber-700 ring-amber-200"
        if s == "closed":
            return "bg-gray-100 text-gray-700 ring-gray-200"
        return "bg-gray-100 text-gray-700 ring-gray-200"

    ctx = {
        "ticket": ticket,
        "status_badge_classes": status_badge_classes(ticket.status),
    }

    # When opened from your modal, you append ?inmodal=1 — serve a compact template
    in_modal = (
        request.GET.get("inmodal") == "1"
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )

    if in_modal:
        return render(request, "client/ticket_detail_embed.html", ctx, status=200)

    # Full page (if you have one). You can reuse the embed template if you prefer.
    return render(request, "client/ticket_detail.html", ctx, status=200)


def _parse_date(val: str | None) -> date | None:
    """Safe ISO (YYYY-MM-DD) date parser."""
    if not val:
        return None
    try:
        return date.fromisoformat(val)
    except Exception:
        return None


@login_required
@require_POST
def client_kyc_update(request):
    """
    Create or update the current user's KYC.

    Expects form-data (multipart) from the modal:
      - kyc_type: "personal" | "company"

    Personal fields:
      - full_name, date_of_birth (YYYY-MM-DD), nationality
      - id_document_type (voter_card|drivers_license|passport)
      - document_number, id_issue_date (YYYY-MM-DD), id_expiry_date (YYYY-MM-DD)
      - address
      - document_file (file)

    Company fields:
      - company_name, rccm, nif, id_nat, representative_name
      - company_address
      - representative_id_file (file), company_documents (file)

    Server behavior:
      - If user's KYC is approved => reject changes (frontend also disables).
      - On submit, set status="pending".
      - Clear the opposite type's fields to avoid hybrid records.
      - Only replace file fields if a new file is provided.
    """
    user = request.user
    kyc_type = (request.POST.get("kyc_type") or "personal").strip().lower()
    if kyc_type not in ("personal", "company"):
        return JsonResponse(
            {"success": False, "message": "Invalid KYC type."}, status=400
        )

    # Get or create the user's KYC record
    kyc = getattr(user, "kyc", None)
    if not kyc:
        try:
            kyc = PersonalKYC.objects.create(user=user, status="draft")
        except Exception:
            # if OneToOne not set on reverse, fallback
            kyc = PersonalKYC.objects.filter(user=user).first()
            if not kyc:
                kyc = PersonalKYC(user=user, status="draft")

    # If already approved, do not allow edits (defense-in-depth)
    if (kyc.status or "").lower() == "approved":
        return JsonResponse(
            {
                "success": False,
                "message": "Your KYC is already approved and cannot be modified.",
            },
            status=403,
        )

    try:
        with transaction.atomic():
            if kyc_type == "personal":
                # --------- PERSONAL KYC ---------
                kyc.company_name = ""
                kyc.rccm = ""
                kyc.nif = ""
                kyc.id_nat = ""
                kyc.representative_name = ""

                kyc.full_name = (request.POST.get("full_name") or "").strip()
                kyc.date_of_birth = _parse_date(request.POST.get("date_of_birth"))
                kyc.nationality = (request.POST.get("nationality") or "").strip()
                kyc.id_document_type = (
                    request.POST.get("id_document_type") or ""
                ).strip()
                kyc.document_number = (
                    request.POST.get("document_number") or ""
                ).strip()
                kyc.id_issue_date = _parse_date(request.POST.get("id_issue_date"))
                kyc.id_expiry_date = _parse_date(request.POST.get("id_expiry_date"))

                # Address (personal uses "address")
                kyc.address = (request.POST.get("address") or "").strip()

                # Files (replace only if provided)
                if "document_file" in request.FILES:
                    kyc.document_file = request.FILES["document_file"]

                # Clear company file fields if present
                if hasattr(kyc, "representative_id_file"):
                    # don't delete existing files from storage here; just unlink if needed
                    pass
                if hasattr(kyc, "company_documents"):
                    pass

            else:
                # --------- COMPANY KYC ---------
                kyc.full_name = ""
                kyc.date_of_birth = None
                kyc.nationality = ""
                kyc.id_document_type = ""
                kyc.document_number = ""
                kyc.id_issue_date = None
                kyc.id_expiry_date = None

                kyc.company_name = (request.POST.get("company_name") or "").strip()
                kyc.rccm = (request.POST.get("rccm") or "").strip()
                kyc.nif = (request.POST.get("nif") or "").strip()
                kyc.id_nat = (request.POST.get("id_nat") or "").strip()
                kyc.representative_name = (
                    request.POST.get("representative_name") or ""
                ).strip()

                # Address (company uses "company_address")
                kyc.address = (request.POST.get("company_address") or "").strip()

                # Files (replace only if provided)
                if "representative_id_file" in request.FILES:
                    kyc.representative_id_file = request.FILES["representative_id_file"]
                if "company_documents" in request.FILES:
                    kyc.company_documents = request.FILES["company_documents"]

                # Clear personal file if present
                if hasattr(kyc, "document_file"):
                    pass

            # When customer edits/submits, push to pending for review
            kyc.status = "pending"
            # Optional: clear any previous rejection metadata
            if hasattr(kyc, "rejection_reason"):
                kyc.rejection_reason = ""
            if hasattr(kyc, "rejection_details"):
                kyc.rejection_details = ""

            kyc.save()

        return JsonResponse(
            {
                "success": True,
                "message": "KYC submitted successfully and is now pending review.",
                "status": kyc.status,
            }
        )

    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Unable to update KYC: {e}"},
            status=500,
        )


# --- KPI endpoint for Unpaid Due and Net Due ---
@require_full_login
@customer_nonstaff_required
@require_GET
def billing_kpis(request):
    """
    Return KPI values for the Unpaid Due and Net Due cards for the logged-in user.

    Definitions
    - Unpaid Due (USD): sum of `total_price` for the user's orders that are:
        unpaid, not cancelled, and not expired (expires_at is NULL or > now).
      This equals the backend summary field `active_unpaid_balance_usd` used by billing_history.
    - Net Due (USD): mirrors Unpaid Due (no credit offsets applied) unless specified otherwise.

    Notes
    - Expiry rule is inclusive: an order is expired iff `timezone.now() >= expires_at`.
    - Credits are returned separately for the frontend if needed.
    """
    user = request.user
    if not user or not user.is_authenticated:
        return JsonResponse({"success": False, "message": "Unauthorized"}, status=401)

    now_ts = timezone.now()

    # Active unpaid total using centralized helpers
    active_unpaid_qs = Order.objects.active_unpaid_for(user, now_ts)
    active_unpaid_total = active_unpaid_qs.aggregate(
        s=Coalesce(Sum("total_price"), Decimal("0.00"))
    ).get("s") or Decimal("0.00")
    unpaid_due = round(_to_float(active_unpaid_total), 2)

    # Credits and balances (exposed separately)
    acct = getattr(user, "billing_account", None)
    account_credit = (
        getattr(acct, "credit_usd", Decimal("0.00")) if acct else Decimal("0.00")
    )

    wallet = getattr(user, "wallet", None)
    wallet_balance = (
        getattr(wallet, "balance", Decimal("0.00")) if wallet else Decimal("0.00")
    )

    payload = {
        "success": True,
        "kpis": {
            "unpaid_due_usd": unpaid_due,
            # Net Due mirrors Unpaid Due by default (no offsets). Adjust if business rules change.
            "net_due_usd": unpaid_due,
        },
        "credits": {
            "wallet_balance_usd": round(_to_float(wallet_balance), 2),
            "account_credit_usd": round(_to_float(account_credit), 2),
        },
        "meta": {
            "as_of": timezone.now().isoformat(),
            "currency": "USD",
        },
    }

    return JsonResponse(payload, status=200)
