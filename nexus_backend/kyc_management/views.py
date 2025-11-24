from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET

from user.permissions import require_staff_role

# ...existing code...


# Vue API pour retourner les métriques KYC au format JSON
@require_GET
@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
def kyc_metrics_api(request):
    pqs = PersonalKYC.objects.all()
    cqs = CompanyKYC.objects.all()

    personnal_kyc_pending = pqs.filter(status__iexact="pending").count()
    company_kyc_pending = cqs.filter(status__iexact="pending").count()
    personnal_kyc_rejected = pqs.filter(status__iexact="rejected").count()
    company_kyc_rejected = cqs.filter(status__iexact="rejected").count()
    personnal_kyc_approved = pqs.filter(status__iexact="approved").count()
    company_kyc_approved = cqs.filter(status__iexact="approved").count()

    pending = personnal_kyc_pending + company_kyc_pending
    rejected = personnal_kyc_rejected + company_kyc_rejected
    approved = personnal_kyc_approved + company_kyc_approved
    total = pending + rejected + approved

    today = timezone.localdate()
    start_today = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    end_today = timezone.make_aware(dt.datetime.combine(today, dt.time.max))
    first_of_month = today.replace(day=1)
    start_month = timezone.make_aware(dt.datetime.combine(first_of_month, dt.time.min))
    now_dt = timezone.now()

    kyc_today = (
        pqs.filter(submitted_at__range=(start_today, end_today)).count()
        + cqs.filter(submitted_at__range=(start_today, end_today)).count()
    )
    kyc_month = (
        pqs.filter(submitted_at__range=(start_month, now_dt)).count()
        + cqs.filter(submitted_at__range=(start_month, now_dt)).count()
    )

    return JsonResponse(
        {
            "pending": pending,
            "rejected": rejected,
            "approved": approved,
            "total": total,
            "kyc_today": kyc_today,
            "kyc_month": kyc_month,
        }
    )


# Endpoint AJAX pour le polling du nombre de KYC en attente
from django.views.decorators.http import require_GET


@require_GET
def get_pending_kyc_count(request):
    count = (
        PersonalKYC.objects.filter(status__iexact="pending").count()
        + CompanyKYC.objects.filter(status__iexact="pending").count()
    )
    return JsonResponse({"pending_count": count})


def _preview_rel_path(doc_kind: str, object_id: int) -> str:
    """
    Compute a deterministic relative path (under MEDIA_ROOT) for a preview image.
    We keep it simple: one PNG per (doc_kind, object_id).
    """
    safe_kind = str(doc_kind).replace("/", "_")
    return f"kyc_previews/{safe_kind}/{object_id}_page1.png"


def _ensure_preview_image(
    file_field, doc_kind: str, object_id: int, viewer_label: str
) -> str:
    """
    Ensure a PNG preview image exists for the given document.

    Behaviour:
      - If the document is a PDF and `pdf2image` is available, render the first
        page to an image.
      - If the document is an image (jpeg/png/...), load it via Pillow.
      - In all cases, burn a textual watermark (viewer_label) into the image.
      - If anything fails, fall back to a dark placeholder with the watermark.

    Returns the storage URL to the preview image.
    """
    rel_path = _preview_rel_path(doc_kind, object_id)
    if default_storage.exists(rel_path):
        return default_storage.url(rel_path)

    # Lazy import to avoid hard dependency at module import time
    try:
        from PIL import Image, ImageDraw
    except Exception:
        # In the unlikely event Pillow is missing, just create an empty file
        default_storage.save(rel_path, ContentFile(b""))
        return default_storage.url(rel_path)

    base_image = None

    # Try to read the original file bytes (works with local and remote storages)
    file_bytes = None
    try:
        if file_field:
            f = file_field
            f.open("rb")
            try:
                file_bytes = f.read()
            finally:
                f.close()
    except Exception:
        file_bytes = None

    # Decide whether it's a PDF or an image based on name/mime
    is_pdf = False
    try:
        name = getattr(file_field, "name", "") or ""
        mime, _ = mimetypes.guess_type(name)
        ext = os.path.splitext(name)[1].lower()
        is_pdf = (mime == "application/pdf") or ext == ".pdf"
    except Exception:
        is_pdf = False

    if file_bytes:
        try:
            if is_pdf:
                # Attempt real PDF rendering via pdf2image if installed
                try:
                    from pdf2image import convert_from_bytes
                except Exception:
                    base_image = None
                else:
                    try:
                        pages = convert_from_bytes(
                            file_bytes, dpi=150, first_page=1, last_page=1
                        )
                        if pages:
                            base_image = pages[0].convert("RGB")
                    except Exception:
                        base_image = None
            else:
                # Assume it's an image Pillow can open
                try:
                    base_image = Image.open(io.BytesIO(file_bytes)).convert("RGB")
                except Exception:
                    base_image = None
        except Exception:
            base_image = None

    # Fallback placeholder if we couldn't render the original
    if base_image is None:
        base_image = Image.new("RGB", (900, 600), color=(10, 10, 20))

    # Burn watermark text into the image (visible mais dans un coin)
    draw = ImageDraw.Draw(base_image)
    text = f"KYC PREVIEW\n{viewer_label}"

    # Police : taille raisonnable pour ne pas masquer les détails
    font = None
    try:
        from PIL import ImageFont

        w, h = base_image.size
        # Taille plus petite qu'avant, proportionnelle à l'image
        size = max(w, h) // 35 or 12
        # DejaVuSans est généralement disponible avec Pillow, sinon exception
        font = ImageFont.truetype("DejaVuSans.ttf", size=size)
    except Exception:
        font = None

    try:
        # Calculer la bbox pour placer le texte dans un coin (bas droite)
        if font is not None and hasattr(draw, "multiline_textbbox"):
            bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=8)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            img_w, img_h = base_image.size
            margin = max(img_w, img_h) // 40 or 10
            x = img_w - text_w - margin
            y = img_h - text_h - margin
            draw.multiline_text(
                (x, y),
                text,
                fill=(40, 40, 40),  # gris foncé, lisible même sur fond clair
                font=font,
                spacing=8,
                align="right",
            )
        else:
            # Fallback : ancien comportement mais couleur plus foncée
            draw.multiline_text(
                (20, 20),
                text,
                fill=(40, 40, 40),
                spacing=8,
            )
    except Exception:
        # En cas de problème, ne pas casser le rendu : texte simple en haut à gauche
        draw.multiline_text(
            (20, 20),
            text,
            fill=(40, 40, 40),
            spacing=8,
        )

    buffer = io.BytesIO()
    base_image.save(buffer, format="PNG")
    buffer.seek(0)
    default_storage.save(rel_path, ContentFile(buffer.read()))
    return default_storage.url(rel_path)


import datetime as dt
import io
import json
import mimetypes
import os
from datetime import timedelta

from twilio.rest import Client

from django.contrib.auth.decorators import login_required
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import EmptyPage, Paginator
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.utils.timezone import localtime, now
from django.urls import reverse
from django.views.decorators.http import require_POST

from main.models import BaseKYC, CompanyDocument, CompanyKYC, PersonalKYC, User
from kyc_management.models import KycDocumentAccessLog
from user.permissions import require_staff_role


# Create your views here.
@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
def kyc_management(request):
    template = "kyc_management_page.html"

    # Base querysets
    pqs = PersonalKYC.objects.all()
    cqs = CompanyKYC.objects.all()

    # Status KPIs
    personnal_kyc_pending = pqs.filter(status__iexact="pending").count()
    company_kyc_pending = cqs.filter(status__iexact="pending").count()
    personnal_kyc_rejected = pqs.filter(status__iexact="rejected").count()
    company_kyc_rejected = cqs.filter(status__iexact="rejected").count()
    personnal_kyc_approved = pqs.filter(status__iexact="approved").count()
    company_kyc_approved = cqs.filter(status__iexact="approved").count()

    pending = personnal_kyc_pending + company_kyc_pending
    rejected = personnal_kyc_rejected + company_kyc_rejected
    approved = personnal_kyc_approved + company_kyc_approved
    total = pending + rejected + approved  # fixed

    # Time windows (today & month-to-date), timezone-aware
    today = timezone.localdate()
    start_today = timezone.make_aware(dt.datetime.combine(today, dt.time.min))
    end_today = timezone.make_aware(dt.datetime.combine(today, dt.time.max))

    first_of_month = today.replace(day=1)
    start_month = timezone.make_aware(dt.datetime.combine(first_of_month, dt.time.min))
    now = timezone.now()

    # Submitted Today / This Month (use submitted_at)
    kyc_today = (
        pqs.filter(submitted_at__range=(start_today, end_today)).count()
        + cqs.filter(submitted_at__range=(start_today, end_today)).count()
    )
    kyc_month = (
        pqs.filter(submitted_at__range=(start_month, now)).count()
        + cqs.filter(submitted_at__range=(start_month, now)).count()
    )

    context = {
        "pending": pending,
        "rejected": rejected,
        "approved": approved,
        "total": total,
        "kyc_today": kyc_today,
        "kyc_month": kyc_month,
    }
    return render(request, template, context)


@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
@require_GET
def kyc_document_view(request, doc_kind, pk):
    """
    Secure, view-only endpoint for KYC documents.

    It never streams the raw PDF to the browser. Instead, it serves a simple
    HTML snippet containing a PNG preview stored under MEDIA_ROOT.

    doc_kind:
        - personal-main  -> PersonalKYC.document_file
        - personal-visa  -> PersonalKYC.visa_last_page
        - company-rep    -> CompanyKYC.representative_id_file
        - company-main   -> CompanyKYC.company_documents
        - company-doc    -> CompanyDocument.document (pk = CompanyDocument.id)
    """
    kind = (doc_kind or "").lower()
    file_field = None
    kyc_type = ""
    kyc_id = None
    document_label = kind

    if kind == "personal-main":
        kyc = get_object_or_404(PersonalKYC, pk=pk)
        file_field = kyc.document_file
        kyc_type = "personal"
        kyc_id = kyc.id
    elif kind == "personal-visa":
        kyc = get_object_or_404(PersonalKYC, pk=pk)
        file_field = kyc.visa_last_page
        kyc_type = "personal"
        kyc_id = kyc.id
    elif kind == "company-rep":
        company = get_object_or_404(CompanyKYC, pk=pk)
        file_field = company.representative_id_file
        kyc_type = "company"
        kyc_id = company.id
    elif kind == "company-main":
        company = get_object_or_404(CompanyKYC, pk=pk)
        file_field = company.company_documents
        kyc_type = "company"
        kyc_id = company.id
    elif kind == "company-doc":
        doc = get_object_or_404(CompanyDocument, pk=pk)
        file_field = doc.document
        kyc_type = "company"
        kyc_id = doc.company_kyc_id
        document_label = doc.document_name or document_label
    else:
        return HttpResponse(status=404)

    if not file_field:
        return HttpResponse("Document not available", status=404)

    viewer_label = f"{kyc_type} #{kyc_id} / {document_label}\nViewer: {getattr(request.user, 'email', '') or getattr(request.user, 'username', '')}"
    preview_url = _ensure_preview_image(file_field, kind, pk, viewer_label)

    # Log access for audit/compliance
    if kyc_type and kyc_id is not None:
        KycDocumentAccessLog.objects.create(
            user=request.user,
            kyc_type=kyc_type,
            kyc_id=kyc_id,
            document_label=document_label,
        )

    html = f"""
    <div class="relative w-full h-full flex flex-col">
      <div class="flex-1 p-4 bg-black flex items-center justify-center" oncontextmenu="return false;">
        <img src="{preview_url}"
             class="max-h-[80vh] w-auto mx-auto select-none"
             alt="KYC preview"
             style="-webkit-user-drag:none;user-select:none;pointer-events:none;">
      </div>
      <div class="p-3 bg-gray-900 text-center">
        <button type="button"
                onclick="if (typeof closeKycLightbox === 'function') closeKycLightbox();"
                class="inline-flex items-center px-4 py-1.5 rounded-lg text-xs font-semibold text-white"
                style="background:linear-gradient(90deg,#0ea5e9,#6366f1);">
          ✕ Close
        </button>
      </div>
    </div>
    """
    return HttpResponse(html)


def _file_url_or_none(request, f):
    """
    Safely build an absolute URL to a FileField (supports private storages exposing .url).
    Returns None if file is missing.
    """
    try:
        if not f:
            return None
        url = getattr(f, "url", None)
        if not url:
            return None
        return request.build_absolute_uri(url)
    except Exception:
        return None


@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
def get_kyc(request):
    # Prefer AJAX but allow plain GET in tests and simple clients.
    xrw = request.headers.get("x-requested-with")
    if xrw and xrw != "XMLHttpRequest":
        return JsonResponse({"error": "Invalid request"}, status=400)

    # Inputs (with sane defaults)
    query = (request.GET.get("q") or "").strip()
    status_val = (request.GET.get("status") or "").strip()
    try:
        page = int(request.GET.get("page", 1))
    except ValueError:
        page = 1

    # Accept `page_size` from the new UI; keep `per_page` for backward compatibility
    page_size_param = request.GET.get("page_size") or request.GET.get("per_page") or 10
    try:
        per_page = max(1, int(page_size_param))
    except ValueError:
        per_page = 10

    sort_by = (request.GET.get("sort") or "submitted_at").strip()
    sort_order = (request.GET.get("order") or "desc").strip().lower()
    sort_desc = sort_order != "asc"  # default desc

    # Base querysets
    personal_kycs = PersonalKYC.objects.select_related("user")
    company_kycs = CompanyKYC.objects.select_related("user")

    # Filtering
    if query:
        q = Q(user__full_name__icontains=query) | Q(user__email__icontains=query)
        personal_kycs = personal_kycs.filter(q)
        company_kycs = company_kycs.filter(q)

    if status_val:
        personal_kycs = personal_kycs.filter(status=status_val)
        company_kycs = company_kycs.filter(status=status_val)

    # Materialize combined results (keeps Python-level grouping below simple)
    combined_kycs = list(personal_kycs) + list(company_kycs)

    # Group by date “buckets”
    today = now().date()
    yesterday = today - timedelta(days=1)
    week_ago = today - timedelta(days=7)

    grouped = {
        "Today": [],
        "Yesterday": [],
        "Last 7 Days": [],
        "This Month": [],
        "Older": [],
    }

    for kyc in combined_kycs:
        submitted_date = kyc.submitted_at.date()
        if submitted_date == today:
            group = "Today"
        elif submitted_date == yesterday:
            group = "Yesterday"
        elif submitted_date >= week_ago:
            group = "Last 7 Days"
        elif submitted_date.month == today.month and submitted_date.year == today.year:
            group = "This Month"
        else:
            group = "Older"

        grouped[group].append(
            {
                "id": kyc.id,
                "user_id": kyc.user.id_user,
                "user": kyc.user.full_name,
                "type": "Personal" if isinstance(kyc, PersonalKYC) else "Business",
                "status": kyc.status,
                "status_display": kyc.get_status_display(),
                "submitted_at": kyc.submitted_at.strftime("%Y-%m-%d %H:%M"),
                "submitted_at_raw": kyc.submitted_at,  # temp for sorting
                "rejection_reason": getattr(kyc, "rejection_reason", "") or "",
                "remarks": getattr(kyc, "remarks", "") or "",
            }
        )

    # Flatten for sorting/pagination
    flat_results = []
    for group, records in grouped.items():
        for r in records:
            r["group"] = group
            flat_results.append(r)

    # Sort (supports only submitted_at; default desc)
    if sort_by == "submitted_at":
        flat_results.sort(key=lambda k: k["submitted_at_raw"], reverse=sort_desc)
    else:
        # fallback: always sort by submitted_at desc if unsupported field
        flat_results.sort(key=lambda k: k["submitted_at_raw"], reverse=True)

    # Remove raw datetime before returning
    for item in flat_results:
        item.pop("submitted_at_raw", None)

    # Paginate
    paginator = Paginator(flat_results, per_page)
    try:
        page_obj = paginator.page(page)
    except EmptyPage:
        # If page is out of range, return empty result with correct totals
        return JsonResponse(
            {
                "kycs": [],
                "page": page,
                "total_pages": paginator.num_pages,
                "total_items": paginator.count,
            },
            status=200,
        )

    return JsonResponse(
        {
            "kycs": list(page_obj),  # already dicts (JSON-serializable)
            "page": page_obj.number,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
        },
        status=200,
    )


def _abs_url(request, file_field):
    """Return absolute URL for a FileField (handles empty)."""
    try:
        if file_field and getattr(file_field, "url", None):
            return request.build_absolute_uri(file_field.url)
    except Exception:
        pass
    return ""


def _file_info(request, file_field):
    """Uniform file metadata dict for frontend."""
    url = _abs_url(request, file_field)
    name = ""
    try:
        name = getattr(file_field, "name", "") or ""
    except Exception:
        name = ""
    mime, _ = mimetypes.guess_type(url or name or "")
    size = None
    try:
        size = file_field.size if file_field else None
    except Exception:
        size = None
    return {
        "url": url,
        "name": name.split("/")[-1] if name else "",
        "mime": mime or "application/octet-stream",
        "size": size,  # bytes (may be None for remote storages)
    }


@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
def view_kyc(request, kyc_type, kyc_id):
    # Require AJAX
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    kyc_type = (kyc_type or "").lower().strip()
    if kyc_type not in ("personal", "company"):
        return JsonResponse(
            {"success": False, "message": "Invalid KYC type."}, status=400
        )

    # Optional hint for default tab on company docs: ?doc=rep|company
    doc_hint = (request.GET.get("doc") or "").lower().strip()
    # If callers pass ?full=1 we always return the full payload (skip legacy short form)
    want_full = bool(request.GET.get("full"))

    if kyc_type == "personal":
        kyc = get_object_or_404(PersonalKYC.objects.select_related("user"), pk=kyc_id)
        user = kyc.user

        # Common/meta
        kyc_meta = {
            "id": kyc.id,
            "type": "personal",
            "status": kyc.status,
            "status_display": kyc.get_status_display(),
            "submitted_at": (
                localtime(kyc.submitted_at).strftime("%Y-%m-%d %H:%M")
                if kyc.submitted_at
                else ""
            ),
            "submitted_at_iso": (
                localtime(kyc.submitted_at).isoformat() if kyc.submitted_at else ""
            ),
            "remarks": getattr(kyc, "remarks", "") or "",
            "approved_by": getattr(getattr(kyc, "approved_by", None), "email", "")
            or "",
            "approved_at": (
                localtime(kyc.approved_at).isoformat()
                if getattr(kyc, "approved_at", None)
                else ""
            ),
        }

        # User section (always present in full payload)
        user_block = {
            "id": getattr(user, "id_user", None),
            "email": getattr(user, "email", "") or "",
            "phone": getattr(user, "phone", "") or "",
            "full_name": getattr(user, "full_name", "") or "",
            "is_verified": bool(getattr(user, "is_verified", False)),
            "roles": getattr(user, "roles", []) or [],
        }

        # Personal KYC fields
        kyc_fields = {
            "full_name": kyc.full_name or (user.full_name if user else "") or "",
            "date_of_birth": (
                kyc.date_of_birth.strftime("%Y-%m-%d") if kyc.date_of_birth else ""
            ),
            "nationality": kyc.nationality or "",
            "id_document_type": kyc.id_document_type or "",
            "document_number": kyc.document_number or "",
            "id_issue_date": (
                kyc.id_issue_date.strftime("%Y-%m-%d") if kyc.id_issue_date else ""
            ),
            "id_expiry_date": (
                kyc.id_expiry_date.strftime("%Y-%m-%d") if kyc.id_expiry_date else ""
            ),
            "address": kyc.address or "",
        }

        # File(s)
        doc_info = _file_info(request, kyc.document_file)
        visa_info = _file_info(request, getattr(kyc, "visa_last_page", None))
        files = {
            "document": doc_info,  # rich info
            "document_url": doc_info["url"],  # convenience (legacy)
            "visa": visa_info,
            "visa_url": visa_info["url"],
        }

        # Legacy short response (only if full not requested)
        if doc_info["url"] and not want_full:
            return JsonResponse(
                {"success": True, "url": doc_info["url"], "mime": doc_info["mime"]}
            )

        # Full JSON
        return JsonResponse(
            {
                "success": True,
                "type": "personal",
                "kyc": {
                    **kyc_meta,
                    "user": user_block,
                    **kyc_fields,
                },
                "files": files,
            },
            status=200,
        )

    # ---- Company KYC ----
    kyc = get_object_or_404(CompanyKYC.objects.select_related("user"), pk=kyc_id)
    user = kyc.user

    kyc_meta = {
        "id": kyc.id,
        "type": "company",
        "status": kyc.status,
        "status_display": kyc.get_status_display(),
        "submitted_at": (
            localtime(kyc.submitted_at).strftime("%Y-%m-%d %H:%M")
            if kyc.submitted_at
            else ""
        ),
        "submitted_at_iso": (
            localtime(kyc.submitted_at).isoformat() if kyc.submitted_at else ""
        ),
        "remarks": getattr(kyc, "remarks", "") or "",
        "approved_by": getattr(getattr(kyc, "approved_by", None), "email", "") or "",
        "approved_at": (
            localtime(kyc.approved_at).isoformat()
            if getattr(kyc, "approved_at", None)
            else ""
        ),
    }

    user_block = {
        "id": getattr(user, "id_user", None),
        "email": getattr(user, "email", "") or "",
        "phone": getattr(user, "phone", "") or "",
        "full_name": getattr(user, "full_name", "") or "",
        "is_verified": bool(getattr(user, "is_verified", False)),
        "roles": getattr(user, "roles", []) or [],
    }

    kyc_fields = {
        "company_name": kyc.company_name or "",
        "address": kyc.address or "",
        "established_date": (
            kyc.established_date.strftime("%Y-%m-%d") if kyc.established_date else ""
        ),
        "business_sector": kyc.business_sector or "",
        "business_sector_display": (
            kyc.get_business_sector_display() if kyc.business_sector else ""
        ),
        "legal_status": kyc.legal_status or "",
        "legal_status_display": (
            kyc.get_legal_status_display() if kyc.legal_status else ""
        ),
        "rccm": kyc.rccm or "",
        "nif": kyc.nif or "",
        "id_nat": kyc.id_nat or "",
        "representative_name": kyc.representative_name or "",
    }

    rep_info = _file_info(request, kyc.representative_id_file)
    comp_info = _file_info(request, kyc.company_documents)

    # Get all company documents
    company_documents = kyc.documents.all()
    multiple_docs_info = [
        {
            "name": doc.document_name or f"Document {i+1}",
            "info": _file_info(request, doc.document),
            "uploaded_at": doc.uploaded_at.isoformat() if doc.uploaded_at else None,
        }
        for i, doc in enumerate(company_documents)
    ]

    default_doc = (
        "company"
        if (doc_hint == "company" and comp_info["url"])
        else ("rep" if rep_info["url"] else ("company" if comp_info["url"] else ""))
    )

    files = {
        "rep_id": rep_info,  # rich info
        "company_doc": comp_info,  # rich info (legacy single document)
        "rep_id_url": rep_info["url"],  # convenience (legacy)
        "company_doc_url": comp_info["url"],  # convenience (legacy)
        "multiple_documents": multiple_docs_info,  # new multiple documents
        "documents_count": len(multiple_docs_info),
        "default_doc": default_doc,
    }

    # Legacy short response (only if full not requested and ?doc provided)
    if doc_hint in ("rep", "company") and not want_full:
        chosen = rep_info["url"] if doc_hint == "rep" else comp_info["url"]
        if not chosen:
            return JsonResponse(
                {"success": False, "message": "Requested document not available."},
                status=404,
            )
        mime, _ = mimetypes.guess_type(chosen)
        return JsonResponse(
            {"success": True, "url": chosen, "mime": mime or "application/octet-stream"}
        )

    return JsonResponse(
        {
            "success": True,
            "type": "company",
            "kyc": {
                **kyc_meta,
                "user": user_block,
                **kyc_fields,
            },
            "files": files,
        },
        status=200,
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
@require_POST
def update_kyc_status(request, user_id):
    xrw = request.headers.get("x-requested-with")
    if xrw and xrw != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request type."}, status=400
        )

    try:
        data = json.loads(request.body)
        status = data.get("status")
        kyc_type = data.get("type")

        # optional, only used if rejected
        rejection_reason = data.get("reason", "")
        rejection_category = data.get("rejection_category", "")

        if status not in ["approved", "rejected"]:
            return JsonResponse(
                {"success": False, "message": "Invalid status value."}, status=400
            )
        if kyc_type not in ["personal", "business"]:
            return JsonResponse(
                {"success": False, "message": "Invalid KYC type."}, status=400
            )

        user = get_object_or_404(User, pk=user_id)

        # Determine which KYC object to update, creating one on-demand if missing
        if kyc_type == "personal":
            kyc = getattr(user, "personnal_kyc", None)
            if not kyc:
                kyc = PersonalKYC.objects.create(user=user, status=status)
        else:  # company
            kyc = getattr(user, "company_kyc", None)
            if not kyc:
                kyc = CompanyKYC.objects.create(user=user, status=status)

        # Update KYC status and rejection details if applicable
        kyc.status = status
        kyc.approved_by = request.user

        if status == "rejected":
            if not rejection_category:
                return JsonResponse(
                    {"success": False, "message": "Rejection category is required."},
                    status=400,
                )

            kyc.rejection_reason = rejection_category
            kyc.rejected_at = timezone.now()
            kyc.rejected_by = request.user

            # Store additional remarks if provided
            if rejection_reason:
                kyc.remarks = rejection_reason
            else:
                kyc.remarks = ""

            # Send rejection notification
            _send_kyc_rejection_notification(
                user, kyc, rejection_category, rejection_reason
            )

        else:
            # Clear rejection fields if approved
            kyc.rejection_reason = None
            kyc.rejected_at = None
            kyc.rejected_by = None
            kyc.remarks = ""

        kyc.save()

        return JsonResponse({"success": True, "message": f"KYC {status} successfully."})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON format."})
    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error: {str(e)}"})


def _safe_url(f):
    """
    Return a public URL (or empty string) from a FileField/Storage-backed file.
    Works with your PrivateMediaStorage (will use .url if accessible).
    """
    try:
        return f.url if f else ""
    except Exception:
        return ""


@login_required(login_url="login_page")
@require_staff_role(["admin", "compliance"])
def kyc_user_info(request, user_id):
    """
    Returns:
      {
        success: true/false,
        user: { full_name, email, phone, username, address, city, country, identifiers: [...] },
        meta: { is_active, date_joined },
        type: "personal" | "company" | "none",
        kyc: {...}  // fields depend on type
        files: {...} // urls to documents
      }
    """
    # Only allow AJAX (optional but recommended to mirror your other endpoints)
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        return JsonResponse(
            {"success": False, "message": "Invalid request"}, status=400
        )

    u = get_object_or_404(User.objects.all(), pk=user_id)

    # ---- Assemble User Block ----
    full_name = (
        u.full_name or ""
    ).strip() or f"{(u.first_name or '').strip()} {(u.last_name or '').strip()}".strip()
    user_block = {
        "full_name": full_name or u.email or u.username,
        "email": u.email or "",
        "phone": u.phone or "",
        "username": u.username or "",
        # If you later add these to your User/Profile, they'll populate automatically:
        "address": getattr(u, "address", "") or "",
        "city": getattr(u, "city", "") or "",
        "country": getattr(u, "country", "") or "",
        # Example identifiers section (kept for compatibility with your UI)
        "identifiers": [
            {"label": "RCCM", "value": getattr(u, "rccm", "") or ""},
            {"label": "NIF", "value": getattr(u, "nif", "") or ""},
            {"label": "ID NAT", "value": getattr(u, "id_nat", "") or ""},
        ],
    }

    meta_block = {
        "is_active": bool(u.is_active),
        "date_joined": localtime(u.date_joined).strftime("%Y-%m-%d %H:%M"),
    }

    # ---- Determine KYC Type & Load ----
    # NB: your related_name on PersonalKYC is spelled 'personnal_kyc'
    personal = getattr(u, "personnal_kyc", None)
    company = getattr(u, "company_kyc", None)

    kyc_type = "none"
    kyc_block = {}
    files_block = {}

    if personal:
        kyc_type = "personal"
        kyc_block = {
            "id": personal.id,
            "status": personal.status,
            "status_display": personal.get_status_display(),
            "submitted_at": (
                localtime(personal.submitted_at).strftime("%Y-%m-%d %H:%M")
                if personal.submitted_at
                else ""
            ),
            "full_name": personal.full_name or "",  # Personal KYC name
            "date_of_birth": (
                personal.date_of_birth.strftime("%Y-%m-%d")
                if personal.date_of_birth
                else ""
            ),
            "nationality": personal.nationality or "",
            "id_document_type": personal.id_document_type or "",
            "document_number": personal.document_number or "",
            "id_issue_date": (
                personal.id_issue_date.strftime("%Y-%m-%d")
                if personal.id_issue_date
                else ""
            ),
            "id_expiry_date": (
                personal.id_expiry_date.strftime("%Y-%m-%d")
                if personal.id_expiry_date
                else ""
            ),
            "address": personal.address or "",
        }
        doc_info = _file_info(request, personal.document_file)
        visa_info = _file_info(request, getattr(personal, "visa_last_page", None))

        doc_mime = (doc_info.get("mime") or "").lower()
        visa_mime = (visa_info.get("mime") or "").lower()

        doc_view_url = doc_info.get("url", "")
        visa_view_url = visa_info.get("url", "")

        if doc_view_url and doc_mime == "application/pdf":
            doc_view_url = request.build_absolute_uri(
                reverse("kyc_document_view", args=("personal-main", personal.id))
            )
        if visa_view_url and visa_mime == "application/pdf":
            visa_view_url = request.build_absolute_uri(
                reverse("kyc_document_view", args=("personal-visa", personal.id))
            )

        files_block = {
            "document": doc_info,
            "document_url": doc_info.get("url", ""),
            "document_view_url": doc_view_url,
            "visa": visa_info,
            "visa_url": visa_info.get("url", ""),
            "visa_view_url": visa_view_url,
        }

    elif company:
        kyc_type = "company"
        kyc_block = {
            "id": company.id,
            "status": company.status,
            "status_display": company.get_status_display(),
            "submitted_at": (
                localtime(company.submitted_at).strftime("%Y-%m-%d %H:%M")
                if company.submitted_at
                else ""
            ),
            "company_name": company.company_name or "",
            "address": company.address or "",
            "rccm": company.rccm or "",
            "nif": company.nif or "",
            "id_nat": company.id_nat or "",
            "representative_name": company.representative_name or "",
        }
        # Individual document infos
        rep_info = _file_info(request, company.representative_id_file)
        company_doc_info = _file_info(request, company.company_documents)

        rep_mime = (rep_info.get("mime") or "").lower()
        rep_view_url = rep_info.get("url", "")
        if rep_view_url and rep_mime == "application/pdf":
            rep_view_url = request.build_absolute_uri(
                reverse("kyc_document_view", args=("company-rep", company.id))
            )

        company_doc_mime = (company_doc_info.get("mime") or "").lower()
        company_doc_view_url = company_doc_info.get("url", "")
        if company_doc_view_url and company_doc_mime == "application/pdf":
            company_doc_view_url = request.build_absolute_uri(
                reverse("kyc_document_view", args=("company-main", company.id))
            )

        # Build multiple documents info from related CompanyDocument records
        company_docs_qs = getattr(company, "documents", None)
        multiple_docs = []
        if company_docs_qs:
            for i, doc in enumerate(company_docs_qs.all()):
                info = _file_info(request, doc.document)
                mime = (info.get("mime") or "").lower()
                view_url = info.get("url", "")
                if view_url and mime == "application/pdf":
                    view_url = request.build_absolute_uri(
                        reverse("kyc_document_view", args=("company-doc", doc.id))
                    )
                multiple_docs.append(
                    {
                        "id": doc.id,
                        "name": doc.document_name or f"Document {i+1}",
                        "info": info,
                        "view_url": view_url,
                        "uploaded_at": (
                            doc.uploaded_at.isoformat() if doc.uploaded_at else None
                        ),
                    }
                )

        files_block = {
            "rep_id": rep_info,
            "rep_id_url": rep_info.get("url", ""),
            "rep_id_view_url": rep_view_url,
            "company_doc": company_doc_info,
            "company_doc_url": company_doc_info.get("url", ""),
            "company_doc_view_url": company_doc_view_url,
            "multiple_documents": multiple_docs,
            "documents_count": len(multiple_docs),
        }

    data = {
        "success": True,
        "user": user_block,
        "meta": meta_block,
        "type": kyc_type,
        "kyc": kyc_block,
        "files": files_block,
    }
    return JsonResponse(data, status=200)


def _send_kyc_rejection_notification(user, kyc, rejection_category, rejection_reason):
    """
    Send email and SMS notifications to user when their KYC is rejected.
    """
    try:
        # Get rejection reason display text
        rejection_display = dict(BaseKYC.REJECTION_REASONS).get(
            rejection_category, rejection_category
        )

        # Prepare notification content
        full_name = user.get_full_name() or user.username or "User"
        kyc_type = "Personal" if isinstance(kyc, PersonalKYC) else "Business"

        # Email content
        email_subject = f"Nexus - {kyc_type} KYC Application Rejected"
        email_body = f"""
        Dear {full_name},

        We regret to inform you that your {kyc_type.lower()} KYC application has been rejected.

        Rejection Reason: {rejection_display}
        {"Additional Details: " + rejection_reason if rejection_reason else ""}

        Please review the requirements and resubmit your application with the necessary corrections.

        If you have any questions, please contact our support team.

        Best regards,
        Nexus Support Team
        """

        # SMS content (keep it short)
        sms_body = f"Hi {full_name}, your {kyc_type.lower()} KYC application was rejected. Reason: {rejection_display}. Please check your email for details."

        # Send email (if email is available)
        if user.email:
            try:
                # For now, just print the email content (you can integrate with your email service)
                print(f"EMAIL TO: {user.email}")
                print(f"SUBJECT: {email_subject}")
                print(f"BODY: {email_body}")
                print("--- Email notification prepared ---")
            except Exception as e:
                print(f"Email sending failed: {str(e)}")

        # Send SMS (if phone is available)
        if user.phone:
            try:
                # Get Twilio credentials from environment
                twilio_sid = os.environ.get("TWILIO_ACCOUNT_SID")
                twilio_token = os.environ.get("TWILIO_AUTH_TOKEN")
                twilio_phone = os.environ.get("TWILIO_PHONE_NUMBER")

                if twilio_sid and twilio_token and twilio_phone:
                    twilio_client = Client(twilio_sid, twilio_token)
                    message = twilio_client.messages.create(
                        body=sms_body, from_=twilio_phone, to=user.phone
                    )
                    print(f"SMS sent to {user.phone}: {message.sid}")
                else:
                    print(f"SMS TO: {user.phone}")
                    print(f"BODY: {sms_body}")
                    print("--- SMS notification prepared (Twilio not configured) ---")
            except Exception as e:
                print(f"SMS sending failed: {str(e)}")

    except Exception as e:
        print(f"KYC rejection notification failed: {str(e)}")
