# views.py
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, Paginator
from django.db import DatabaseError
from django.db.utils import OperationalError, ProgrammingError
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_GET, require_POST

from main.models import Ticket

logger = logging.getLogger(__name__)


def _ticket_dict(t: Ticket) -> Dict[str, Any]:
    msg = t.message or ""
    preview = (msg[:120] + "…") if len(msg) > 120 else msg
    return {
        "id": t.id,
        "subject": t.subject,
        "category": t.category,
        "priority": t.priority,
        "status": t.status,
        "message_preview": preview,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "detail_url": t.get_absolute_url() if hasattr(t, "get_absolute_url") else "",
    }


@login_required
@require_GET
def tickets_list_api(request: HttpRequest) -> JsonResponse:
    try:
        page = int(request.GET.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = int(request.GET.get("per_page", 10))
    except (TypeError, ValueError):
        per_page = 10
    per_page = max(1, min(per_page, 50))

    try:
        qs = Ticket.objects.filter(user=request.user).order_by("-updated_at", "-id")
        paginator = Paginator(qs, per_page)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages or 1)
        data = [_ticket_dict(t) for t in page_obj.object_list]
        return JsonResponse(
            {
                "success": True,
                "tickets": data,
                "page": page_obj.number,
                "total_pages": paginator.num_pages,
            },
            status=200,
        )
    except (ProgrammingError, OperationalError) as db_err:
        # Most likely: relation "main_ticket" does not exist (migrations not run yet)
        logger.warning("tickets_list_api: table missing or DB not ready: %s", db_err)
        return JsonResponse(
            {"success": True, "tickets": [], "page": 1, "total_pages": 1}, status=200
        )
    except DatabaseError:
        logger.exception("tickets_list_api DB error")
        return JsonResponse(
            {"success": False, "message": _("Database error.")}, status=500
        )
    except Exception as e:
        logger.exception("tickets_list_api failed")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
@require_POST
def ticket_create_api(request: HttpRequest) -> JsonResponse:
    try:
        if request.content_type and "application/json" in request.content_type:
            payload = json.loads(request.body or "{}")
            getv = payload.get
        else:
            getv = request.POST.get

        subject = (getv("subject") or "").strip()
        category = (getv("category") or Ticket.Category.TECHNICAL).strip().lower()
        priority = (getv("priority") or Ticket.Priority.NORMAL).strip().lower()
        message = (getv("message") or "").strip()

        if not subject or not message:
            return JsonResponse(
                {"success": False, "message": _("Subject and message are required.")},
                status=400,
            )

        if category not in {c for c, _ in Ticket.Category.choices}:
            return JsonResponse(
                {"success": False, "message": _("Invalid category.")}, status=400
            )
        if priority not in {p for p, _ in Ticket.Priority.choices}:
            return JsonResponse(
                {"success": False, "message": _("Invalid priority.")}, status=400
            )

        t = Ticket.objects.create(
            user=request.user,
            subject=subject,
            category=category,
            priority=priority,
            status=Ticket.Status.OPEN,
            message=message,
        )
        return JsonResponse(
            {"success": True, "id": t.id, "detail_url": t.get_absolute_url()},
            status=201,
        )
    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": _("Invalid JSON payload.")}, status=400
        )
    except Exception as e:
        logger.exception("ticket_create_api failed")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def ticket_detail(request: HttpRequest, pk: int) -> HttpResponse:
    ticket = get_object_or_404(Ticket, pk=pk, user=request.user)
    return render(request, "support_ticket_detail.html", {"ticket": ticket})
