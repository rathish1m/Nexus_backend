import json
from datetime import datetime, timedelta
from time import localtime

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from main.models import (
    InstallationActivity,
    InstallationPhoto,
    Order,
    Subscription,
    TechnicianAssignment,
    User,
)
from user.permissions import require_staff_role


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
def tech_dashboard(request):
    template = "main_dashboard.html"
    return render(request, template)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
def installation_job_list(request):
    # Get filter parameters from GET request
    filter_status = request.GET.get("status", "").strip()
    filter_technician = request.GET.get("technician", "").strip()
    search_query = request.GET.get("search", "").strip()

    # Base queryset
    jobs = InstallationActivity.objects.select_related(
        "order__user", "technician"
    ).all()

    # Apply status filter
    if filter_status:
        if filter_status.lower() == "pending":
            jobs = jobs.filter(started_at__isnull=True, completed_at__isnull=True)
        elif filter_status.lower() == "in progress":
            jobs = jobs.filter(started_at__isnull=False, completed_at__isnull=True)
        elif filter_status.lower() == "completed":
            jobs = jobs.filter(completed_at__isnull=False)

    # Apply technician filter
    if filter_technician:
        jobs = jobs.filter(technician__full_name__iexact=filter_technician)

    # Apply search filter
    if search_query:
        print("HIT")
        jobs = jobs.filter(
            Q(order__order_reference__icontains=search_query)
            | Q(order__user__full_name__icontains=search_query)
            | Q(order__user__phone__icontains=search_query)
        )

    # Prepare data for JSON
    data = []
    for job in jobs:
        order = job.order
        user = order.user if order else None

        started_at_str = ""
        if job.started_at:
            try:
                started_at_str = localtime(job.started_at).strftime("%Y-%m-%d %H:%M")
            except Exception:
                started_at_str = job.started_at.strftime("%Y-%m-%d %H:%M")

        completed_at_str = ""
        if job.completed_at:
            try:
                completed_at_str = localtime(job.completed_at).strftime(
                    "%Y-%m-%d %H:%M"
                )
            except Exception:
                completed_at_str = job.completed_at.strftime("%Y-%m-%d %H:%M")

        scheduled_at_str = ""
        if job.planned_at:
            try:
                scheduled_at_str = localtime(job.planned_at).strftime("%Y-%m-%d")
            except Exception:
                scheduled_at_str = job.planned_at.strftime("%Y-%m-%d")

        # Determine status
        if job.completed_at:
            status = "Completed"
        elif job.started_at:
            status = "In Progress"
        else:
            status = "Pending"

        data.append(
            {
                "id": job.id,
                "order_reference": order.order_reference if order else "",
                "customer_name": user.full_name if user else "",
                "customer_phone": user.phone if user else "",
                "latitude": order.latitude if order else "",
                "longitude": order.longitude if order else "",
                "status": status,
                "technician": (
                    job.technician.full_name if job.technician else "Not Assigned"
                ),
                "scheduled_at": scheduled_at_str,
                "started_at": started_at_str,
                "completed_at": completed_at_str,
                "location_confirmed": job.location_confirmed,
                "notes": job.notes or "",
            }
        )

    return JsonResponse({"success": True, "jobs": data})


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_POST
def assign_to_technician(request):
    """
    Assign a technician to an installation task and track technician-kit assignment.
    Expects POST data: order_id, technician_id, assign_date
    """
    try:
        data = json.loads(request.body)
        order_id = data.get("order_id")
        technician_id = data.get("technician_id")
        planned_at = data.get("planned_at")

        if not (order_id and technician_id and planned_at):
            return JsonResponse(
                {"success": False, "message": "Missing required fields."}, status=400
            )

        # Get order and technician
        order = get_object_or_404(Order, order_reference=order_id)
        technician = get_object_or_404(User, id_user=technician_id)

        # Assign technician to installation activity
        activity, created = InstallationActivity.objects.get_or_create(order=order)
        activity.technician = technician
        activity.planned_at = planned_at  # Expecting formatted date string
        activity.save()
        #
        # Assign the kit to the technician if not already
        if order.kit_inventory:
            assignment_exists = TechnicianAssignment.objects.filter(
                technician=technician,
                inventory_item=order.kit_inventory,
                is_active=True,
            ).exists()
            #
            if not assignment_exists:
                TechnicianAssignment.objects.create(
                    technician=technician,
                    inventory_item=order.kit_inventory,
                    assigned_by=request.user,
                    note=f"Assigned during installation task for Order {order.order_reference}",
                )

        return JsonResponse(
            {
                "success": True,
                "message": f"Technician {technician.full_name} assigned successfully to order {order.order_reference}.",
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
def fe_ops_dashboard(request):
    user = request.user
    # ✅ Ensure we use the logged-in user's id directly
    technician_id = user.id_user

    today = datetime.today().date()  # Get today's date in local timezone

    # ✅ Planned for today
    planned_today = InstallationActivity.objects.filter(
        technician_id=technician_id, planned_at=today
    ).count()

    template = "fe_dashboard.html"
    return render(request, template, {"planned_today": planned_today})


def _fmt_date(d):
    """YYYY-MM-DD for Date/DateTime/None."""
    if not d:
        return None
    try:
        # if datetime, use localtime then date()
        if hasattr(d, "tzinfo"):
            d = timezone.localtime(d).date()
        return d.strftime("%Y-%m-%d")
    except Exception:
        return None


def _fmt_iso(dt):
    """ISO 8601 for Date/DateTime/None (localtime for datetimes)."""
    if not dt:
        return None
    try:
        if hasattr(dt, "tzinfo"):
            dt = timezone.localtime(dt)
        return dt.isoformat()
    except Exception:
        return None


@login_required(login_url="login_page")
def technician_job_list(request):
    """
    Return all installation jobs assigned to the logged-in technician.

    Response:
    {
      "jobs": [
        {
          "activity_id": int,
          "order_reference": str|null,
          "customer_name": str,
          "customer_phone": str,
          "latitude": float|null,
          "longitude": float|null,
          "scheduled_date": "YYYY-MM-DD"|null,
          "scheduled_at": "ISO8601"|null,
          "started_at": "ISO8601"|null,
          "completed_at": "ISO8601"|null,
          "status": "pending"|"in_progress"|"completed"
        },
        ...
      ],
      "total_pages": int,
      "current_page": int,
      "total_jobs": int
    }
    """
    user = request.user

    # Pagination inputs (robust)
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

    # Query - FIFO ordering (First In First Out): oldest assigned jobs first
    # Include jobs that are:
    # 1. Not completed yet (traditional logic)
    # 2. Completed but still within edit window (24h)
    activities = (
        InstallationActivity.objects.select_related(
            "order", "technician", "order__user"
        )
        .filter(technician=user)
        .filter(
            # Include: not submitted OR submitted but still editable
            Q(submitted_at__isnull=True)
            | Q(status="submitted", edit_deadline__gte=timezone.now())
        )
        .order_by("planned_at", "id")
    )

    paginator = Paginator(activities, per_page)
    page_obj = paginator.get_page(page)

    jobs_payload = []
    for activity in page_obj.object_list:
        customer = activity.order.user
        # Construire l'adresse à partir des coordonnées de la commande
        address = "N/A"
        if activity.order.latitude is not None and activity.order.longitude is not None:
            address = f"{activity.order.latitude:.6f}, {activity.order.longitude:.6f}"

        # Status - enhanced to handle submitted reports
        if activity.status == "submitted":
            status = "submitted"

        jobs_payload.append(
            {
                "activity_id": activity.id,
                "order_id": activity.order.id,
                "order_reference": activity.order.order_reference,
                "status": activity.status,
                # --- NOUVEAUX CHAMPS AJOUTÉS ---
                "customer_name": customer.full_name if customer else "N/A",
                "customer_phone": customer.phone if customer else "N/A",
                "address": address,
                "scheduled_at": _fmt_iso(
                    getattr(activity, "planned_at", None)
                ),  # Utilise planned_at
                # --- FIN DES NOUVEAUX CHAMPS ---
                "is_draft": getattr(activity, "is_draft", False),
                # For your table & “next job” card:
                "scheduled_date": _fmt_date(getattr(activity, "planned_at", None)),
                "started_at": _fmt_iso(getattr(activity, "started_at", None)),
                "completed_at": _fmt_iso(getattr(activity, "completed_at", None)),
                "submitted_at": _fmt_iso(getattr(activity, "submitted_at", None)),
                # Edition information
                "can_be_edited": activity.can_be_edited(),
                "time_left_hours": round(activity.time_left_for_editing(), 1),
                "edit_deadline": _fmt_iso(getattr(activity, "edit_deadline", None)),
                "version_number": getattr(activity, "version_number", 1),
                # Whether an activation request exists for this activity/subscription (non-cancelled)
                "activation_requested": (
                    __import__("tech")
                    .models.ActivationRequest.objects.filter(
                        requested_activity=activity
                    )
                    .exclude(status="cancelled")
                    .exists()
                    or (
                        getattr(activity.order, "subscription", None) is not None
                        and getattr(
                            activity.order.subscription, "activation_requested", False
                        )
                    )
                ),
            }
        )

    return JsonResponse(
        {
            "jobs": jobs_payload,
            "total_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "total_jobs": paginator.count,
        }
    )


def debug_session(request):
    """Development-only: return cookies, headers and authentication status.

    Use from browser to confirm whether sessionid and csrftoken are sent with fetch.
    """
    try:
        data = {
            "cookies": dict(request.COOKIES),
            "user_is_authenticated": bool(
                getattr(request, "user", None) and request.user.is_authenticated
            ),
            "user_str": str(getattr(request, "user", None)),
            # include a few headers for quick inspection
            "headers": {
                k: v
                for k, v in request.headers.items()
                if k in ["Cookie", "Referer", "Host", "User-Agent", "X-Requested-With"]
            },
        }
        return JsonResponse({"success": True, "debug": data})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)})


@login_required(login_url="login_page")
def surveys_summary(request):
    """
    JSON summary for the Survey Panel.

    Response:
    {
      "completed": int,          # number of jobs with a submitted survey
      "total": int,              # number of eligible jobs (completed installs)
      "avg_rating": float|null,  # average rating 1..5
      "nps": float|null,         # Net Promoter Score (-100..100)
      "ratings_breakdown": {"1":n,"2":n,"3":n,"4":n,"5":n}
    }
    """
    user = request.user

    # Eligible set: completed installs for this technician
    completed_qs = InstallationActivity.objects.filter(
        technician=user, completed_at__isnull=False
    )

    total = completed_qs.count()

    # --- Optional Survey model support (fallbacks if not present) ---
    # Try to locate a SurveyResponse-like model dynamically
    SurveyModel = None
    survey_qs = None
    rating_field = None
    nps_field = None
    link_field_name = None

    # We’ll try a few common names/relations:
    POSSIBLE_MODELS = [
        ("surveys", "SurveyResponse"),
        ("main", "SurveyResponse"),
        ("feedback", "SurveyResponse"),
    ]

    for app, model in POSSIBLE_MODELS:
        try:
            from django.apps import apps

            SurveyModel = apps.get_model(app_label=app, model_name=model)
            break
        except Exception:
            SurveyModel = None

    if SurveyModel:
        # Heuristics to find relation to InstallationActivity
        # Try activity ForeignKey first, else try order or technician
        link_field_name = None
        for fname in ("activity", "installation", "installation_activity"):
            if fname in [f.name for f in SurveyModel._meta.fields]:
                link_field_name = fname
                break
        # Ratings & NPS fields
        for fname in ("rating", "stars", "score"):
            if fname in [f.name for f in SurveyModel._meta.fields]:
                rating_field = fname
                break
        for fname in ("nps", "promoter_score"):
            if fname in [f.name for f in SurveyModel._meta.fields]:
                nps_field = fname
                break

        if link_field_name:
            activity_ids = list(completed_qs.values_list("id", flat=True))
            kwargs = {f"{link_field_name}__in": activity_ids}
            survey_qs = SurveyModel.objects.filter(**kwargs)

    if SurveyModel and survey_qs is not None:
        # Compute metrics from survey responses
        completed = survey_qs.count()

        # ratings breakdown 1..5 if rating field exists
        ratings_breakdown = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}
        avg_rating = None
        nps_value = None

        if rating_field:
            # Count how many of each rating
            rb = survey_qs.values(rating_field).annotate(n=Count("id"))
            total_rated = 0
            sum_ratings = 0
            for row in rb:
                r = row.get(rating_field)
                n = row.get("n", 0)
                if r in [1, 2, 3, 4, 5]:
                    ratings_breakdown[str(r)] = n
                    total_rated += n
                    sum_ratings += r * n
            if total_rated:
                avg_rating = round(sum_ratings / total_rated, 2)

        if nps_field:
            # NPS: %promoters(9-10) - %detractors(0-6)
            counts = survey_qs.values(nps_field).annotate(n=Count("id"))
            total_nps = 0
            detr = 0
            prom = 0
            for row in counts:
                sc = row.get(nps_field)
                n = row.get("n", 0)
                if sc is None:
                    continue
                total_nps += n
                if sc <= 6:
                    detr += n
                elif sc >= 9:
                    prom += n
            if total_nps:
                nps_value = round(((prom / total_nps) - (detr / total_nps)) * 100, 1)

        return JsonResponse(
            {
                "success": True,
                "completed": completed,
                "total": total,
                "avg_rating": avg_rating,
                "nps": nps_value,
                "ratings_breakdown": ratings_breakdown,
            }
        )

    # --- Fallback when no Survey model is present ---
    # Show totals, but no ratings/NPS.
    return JsonResponse(
        {
            "success": True,
            "completed": total,  # treat completed installs as “survey-completed” placeholder
            "total": total,
            "avg_rating": None,
            "nps": None,
            "ratings_breakdown": {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0},
        }
    )


# @login_required(login_url="login_page")
# # @require_staff_role(["admin", "technician"])
# def technician_job_list(request):
#     """
#     Return all installation jobs assigned to the logged-in technician.
#     """
#     user = request.user
#     page = int(request.GET.get("page", 1))
#     per_page = int(request.GET.get("per_page", 10))
#
#     # Ensure only users with role 'technician' can access
#     if "technician" not in user.roles:
#         return JsonResponse({"error": "Unauthorized"}, status=403)
#
#     activities = (
#         InstallationActivity.objects.select_related("order", "technician")
#         .filter(technician=user)
#         .order_by("-planned_at")
#     )
#
#     paginator = Paginator(activities, per_page)
#     page_obj = paginator.get_page(page)
#
#     jobs = []
#
#     jobs = []
#     for activity in page_obj.object_list:
#         order = activity.order
#         customer = order.user
#         jobs.append(
#             {
#                 "activity_id": activity.id,
#                 "order_reference": order.order_reference,
#                 "customer_name": customer.full_name if customer else "N/A",
#                 "customer_phone": customer.phone if customer else "N/A",
#                 "latitude": order.latitude,
#                 "longitude": order.longitude,
#                 "scheduled_date": (
#                     activity.planned_at.strftime("%Y-%m-%d")
#                     if activity.planned_at
#                     else None
#                 ),
#                 "status": (
#                     "completed"
#                     if activity.completed_at
#                     else "in_progress" if activity.started_at else "pending"
#                 ),
#             }
#         )
#
#     return JsonResponse(
#         {
#             "jobs": jobs,
#             "total_pages": paginator.num_pages,
#             "current_page": page,
#             "total_jobs": paginator.count,
#         }
#     )


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_GET
def get_technicians(request):
    technicians = User.objects.filter(roles__contains=["technician"])
    data = [{"id": tech.id_user, "full_name": tech.full_name} for tech in technicians]
    print(data)
    return JsonResponse({"technicians": data})


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_GET
def technicians_api(request):
    """API endpoint for technicians list (for site survey assignment)"""
    technicians = User.objects.filter(roles__contains=["technician"])
    data = [
        {"id": tech.id_user, "name": tech.full_name or tech.email}
        for tech in technicians
    ]
    return JsonResponse({"technicians": data})


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_POST
def job_start(request):
    try:
        data = json.loads(request.body)  # Parse JSON body
        job_id = data.get("job_id")  # Get job_id from request

        print("JOB ID", job_id)

        if not job_id:
            return JsonResponse(
                {"success": False, "message": "Missing job_id."}, status=400
            )

        # Find the job
        activity = get_object_or_404(InstallationActivity, id=job_id)

        # Update the status to "in progress" by setting started_at
        activity.started_at = timezone.now()
        activity.save()

        return JsonResponse(
            {"success": True, "message": f"Job {job_id} marked as In Progress."}
        )

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_POST
def job_notes(request, job_id):
    try:
        activity = InstallationActivity.objects.get(id=job_id)
    except InstallationActivity.DoesNotExist:
        return JsonResponse({"success": False, "message": "Job not found."}, status=404)

    if request.method == "POST":
        data = json.loads(request.body)
        note = data.get("note")
        print("NOTE", note)
        if not note:
            return JsonResponse(
                {"success": False, "message": "Note cannot be empty."}, status=400
            )

        activity.notes = note
        activity.save()
        return JsonResponse({"success": True, "message": "Note saved."})

    return JsonResponse(
        {"success": False, "message": "Invalid request method."}, status=405
    )


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_POST
def job_complete(request, job_id):
    try:
        with transaction.atomic():
            activity = InstallationActivity.objects.select_related(
                "order", "order__plan", "order__user"
            ).get(id=job_id)

            # Mark job completed
            activity.completed_at = timezone.now()
            activity.save()

            # Update the order as installed
            order = activity.order
            if order:
                order.is_installed = True
                order.installation_date = timezone.now()
                order.installed_by = request.user
                order.save()

                # Find or create subscription
                subscription = Subscription.objects.filter(order=order).first()
                if not subscription and order.plan:
                    subscription = Subscription.objects.create(
                        user=order.user,
                        plan=order.plan,
                        order=order,
                        billing_cycle="monthly",  # Default, could be dynamic
                    )

                if subscription:
                    today = timezone.now().date()
                    subscription.started_at = today
                    subscription.status = "active"

                    # Set next billing date based on cycle
                    if subscription.billing_cycle == "monthly":
                        subscription.next_billing_date = today + timedelta(days=30)
                    elif subscription.billing_cycle == "quarterly":
                        subscription.next_billing_date = today + timedelta(days=90)
                    elif subscription.billing_cycle == "yearly":
                        subscription.next_billing_date = today + timedelta(days=365)

                    subscription.save()

        return JsonResponse(
            {
                "success": True,
                "message": "Installation marked as Completed and subscription started.",
            }
        )

    except InstallationActivity.DoesNotExist:
        return JsonResponse({"success": False, "message": "Job not found."}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)

    #
    #
    # try:
    #     activity = InstallationActivity.objects.get(id=job_id)
    #     activity.completed_at = timezone.now()
    #     activity.save()
    #
    #     return JsonResponse({"success": True, "message": "Installation marked as Completed."})
    # except InstallationActivity.DoesNotExist:
    #     return JsonResponse({"success": False, "message": "Job not found."}, status=404)
    # except Exception as e:
    #     return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician", "leadtechnician"])
@require_POST
def upload_installation_photos(request, job_id):
    job = InstallationActivity.objects.filter(id=job_id).first()
    if not job:
        return JsonResponse({"success": False, "message": "Job not found."}, status=404)

    photos = request.FILES.getlist("photos")
    if not photos:
        return JsonResponse(
            {"success": False, "message": "No photos uploaded."}, status=400
        )

    for photo in photos:
        InstallationPhoto.objects.create(installation_activity=job, image=photo)

    return JsonResponse({"success": True, "message": "Photos uploaded successfully."})


@login_required(login_url="login_page")
@require_POST
def save_installation_report(request, activity_id):
    """
    Sauvegarde ou met à jour un rapport d'installation complet.
    Gère tous les champs du formulaire en 9 étapes.
    """
    try:
        # Vérifier que l'installation existe et appartient au technicien
        activity = InstallationActivity.objects.select_related(
            "order", "technician"
        ).get(id=activity_id, technician=request.user)

        # Helper function pour gérer les valeurs vides
        def get_value(key, default=None):
            value = request.POST.get(key, "").strip()
            return value if value else default

        # STEP 1: Job & Site
        if get_value("on_site_arrival"):
            activity.on_site_arrival = get_value("on_site_arrival")
        activity.site_address = get_value("site_address", "")
        if get_value("site_latitude"):
            activity.site_latitude = get_value("site_latitude")
        if get_value("site_longitude"):
            activity.site_longitude = get_value("site_longitude")
        activity.access_level = get_value("access_level", "")
        activity.power_availability = get_value("power_availability", "")
        activity.site_notes = get_value("site_notes", "")

        # STEP 2: Equipment - CPE Details
        activity.dish_serial_number = get_value("dish_serial_number", "")
        activity.router_serial_number = get_value("router_serial_number", "")
        activity.firmware_version = get_value("firmware_version", "")
        activity.power_source = get_value("power_source", "")
        if get_value("cable_length"):
            activity.cable_length = get_value("cable_length")
        if get_value("splices_connectors"):
            activity.splices_connectors = get_value("splices_connectors")

        # STEP 2: Equipment - LAN / Wi-Fi
        activity.wifi_ssid = get_value("wifi_ssid", "")
        activity.wifi_password = get_value("wifi_password", "")
        if get_value("lan_ip"):
            activity.lan_ip = get_value("lan_ip")
        activity.dhcp_range = get_value("dhcp_range", "")

        # STEP 3: Mount & Alignment
        activity.mount_type = get_value("mount_type", "")
        if get_value("mount_height"):
            activity.mount_height = get_value("mount_height")
        activity.grounding = get_value("grounding", "")
        activity.weatherproofing = get_value("weatherproofing", "")
        if get_value("obstruction_percentage"):
            activity.obstruction_percentage = get_value("obstruction_percentage")
        if get_value("elevation_angle"):
            activity.elevation_angle = get_value("elevation_angle")
        if get_value("azimuth_angle"):
            activity.azimuth_angle = get_value("azimuth_angle")
        activity.obstruction_notes = get_value("obstruction_notes", "")
        activity.mounting_notes = get_value("mounting_notes", "")

        # STEP 4: Environment & Safety
        activity.weather_conditions = get_value("weather_conditions", "")
        activity.safety_helmet = request.POST.get("safety_helmet") == "on"
        activity.safety_harness = request.POST.get("safety_harness") == "on"
        activity.safety_gloves = request.POST.get("safety_gloves") == "on"
        activity.safety_ladder = request.POST.get("safety_ladder") == "on"
        activity.hazards_noted = get_value("hazards_noted", "")

        # STEP 5: Cabling & Routing
        activity.cable_entry_point = get_value("cable_entry_point", "")
        activity.cable_protection = get_value("cable_protection", "")
        activity.termination_type = get_value("termination_type", "")
        activity.routing_notes = get_value("routing_notes", "")

        # STEP 6: Power & Backup
        activity.power_stability_test = get_value("power_stability_test", "")
        activity.ups_installed = get_value("ups_installed", "")
        activity.ups_model = get_value("ups_model", "")
        if get_value("ups_runtime_minutes"):
            activity.ups_runtime_minutes = get_value("ups_runtime_minutes")

        # STEP 7: Connectivity & Tests
        if get_value("snr_db"):
            activity.snr_db = get_value("snr_db")
        if get_value("speed_download_mbps"):
            activity.speed_download_mbps = get_value("speed_download_mbps")
        if get_value("speed_upload_mbps"):
            activity.speed_upload_mbps = get_value("speed_upload_mbps")
        if get_value("latency_ms"):
            activity.latency_ms = get_value("latency_ms")
        activity.test_tool = get_value("test_tool", "")
        if get_value("public_ip"):
            activity.public_ip = get_value("public_ip")
        activity.qos_vlan = get_value("qos_vlan", "")
        activity.final_link_status = get_value("final_link_status", "")
        activity.test_notes = get_value("test_notes", "")

        # STEP 9: Customer Sign-off
        activity.customer_full_name = get_value("customer_full_name", "")
        activity.customer_id_document = get_value("customer_id_document", "")
        activity.customer_acceptance = request.POST.get("customer_acceptance") == "on"
        activity.customer_signature = get_value("customer_signature", "")
        if get_value("customer_signoff_at"):
            activity.customer_signoff_at = get_value("customer_signoff_at")
        if get_value("customer_rating"):
            activity.customer_rating = get_value("customer_rating")
        activity.customer_comments = get_value("customer_comments", "")

        # Reseller Information
        activity.reseller_name = get_value("reseller_name", "")
        activity.reseller_id = get_value("reseller_id", "")
        activity.sla_tier = get_value("sla_tier", "")
        activity.reseller_notes = get_value("reseller_notes", "")

        # STEP 8: Photos - Gérer l'upload des photos
        photos_before = request.FILES.getlist("photos_before")
        photos_after = request.FILES.getlist("photos_after")
        photos_evidence = request.FILES.getlist("photos_evidence")

        # Créer les objets InstallationPhoto pour chaque photo uploadée avec le bon type
        for photo in photos_before:
            InstallationPhoto.objects.create(
                installation_activity=activity, image=photo, photo_type="before"
            )

        for photo in photos_after:
            InstallationPhoto.objects.create(
                installation_activity=activity, image=photo, photo_type="after"
            )

        for photo in photos_evidence:
            InstallationPhoto.objects.create(
                installation_activity=activity, image=photo, photo_type="evidence"
            )

        # Déterminer si c'est une soumission finale ou un brouillon
        submit_final = request.POST.get("submit_final") == "true"

        if submit_final:
            # Marquer comme soumis
            activity.mark_as_submitted()
            message = "Rapport d'installation soumis avec succès !"
        else:
            # Sauvegarder en brouillon
            activity.save()
            message = "Brouillon sauvegardé avec succès !"

        return JsonResponse(
            {
                "success": True,
                "message": message,
                "is_draft": activity.is_draft,
                "submitted_at": (
                    activity.submitted_at.isoformat() if activity.submitted_at else None
                ),
            }
        )

    except InstallationActivity.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "error": "Installation non trouvée ou vous n'avez pas accès à cette installation.",
            },
            status=404,
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"Erreur lors de la sauvegarde: {str(e)}"},
            status=500,
        )


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
def completed_installations(request):
    """
    Page affichant toutes les installations terminées avec rapport soumis.
    """
    # Récupérer toutes les installations avec submitted_at non null
    installations = (
        InstallationActivity.objects.select_related(
            "order", "order__user", "technician"
        )
        .filter(submitted_at__isnull=False)
        .order_by("-submitted_at")
    )

    # Pagination
    paginator = Paginator(installations, 20)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    context = {
        "installations": page_obj,
        "total_count": installations.count(),
    }

    return render(request, "tech/completed_installations.html", context)


@login_required(login_url="login_page")
@require_GET
def get_installation_report_data(request, activity_id):
    """
    Vue GET pour récupérer les données d'un rapport d'installation existant pour l'édition.
    """
    print(
        f"DEBUG: get_installation_report_data called for activity_id={activity_id}, user={request.user}"
    )
    try:
        # Vérifier que l'installation existe et appartient au technicien
        activity = (
            InstallationActivity.objects.select_related("order", "technician")
            .prefetch_related("photos")
            .get(id=activity_id, technician=request.user)
        )

        print(f"DEBUG: Found activity {activity.id}, status={activity.status}")

        # Only check edit window for reports that have already been submitted
        if activity.status == "submitted" and not activity.can_be_edited():
            print("DEBUG: Activity cannot be edited - edit window expired")
            return JsonResponse(
                {
                    "success": False,
                    "error": "Edit window has expired. Report can no longer be modified.",
                },
                status=403,
            )

        # Prepare report data, pre-filling from order if activity fields are empty
        order = activity.order

        # Helper to safely get attributes
        def safe_get(obj, attr, default=""):
            if not obj:
                return default
            val = getattr(obj, attr, default)
            return val if val is not None else default

        report_data = {
            "success": True,
            "data": {
                # Basic job info from order and user
                "customer_phone": safe_get(safe_get(order, "user"), "phone"),
                "customer_name": safe_get(safe_get(order, "user"), "full_name"),
                "customer_full_name": activity.customer_full_name
                or safe_get(safe_get(order, "user"), "full_name")
                or safe_get(order, "customer_name"),
                "customer_id_document": activity.customer_id_document
                or safe_get(safe_get(order, "user"), "document_id"),
                "scheduled_date": (
                    activity.planned_at.strftime("%Y-%m-%d %H:%M")
                    if activity.planned_at
                    else ""
                ),
                "order_reference": safe_get(order, "order_reference"),
                # Job & Site (pre-fill from order if empty)
                "on_site_arrival": (
                    activity.on_site_arrival.strftime("%Y-%m-%dT%H:%M")
                    if activity.on_site_arrival
                    else ""
                ),
                "site_address": activity.site_address
                or safe_get(order, "delivery_address"),
                "site_latitude": str(
                    activity.site_latitude or safe_get(order, "latitude")
                ),
                "site_longitude": str(
                    activity.site_longitude or safe_get(order, "longitude")
                ),
                "access_level": activity.access_level or "",
                "power_availability": activity.power_availability or "",
                "site_notes": activity.site_notes or "",
                # Equipment - CPE Details
                "dish_serial_number": activity.dish_serial_number or "",
                "router_serial_number": activity.router_serial_number or "",
                "firmware_version": activity.firmware_version or "",
                "power_source": activity.power_source or "",
                "cable_length": (
                    str(activity.cable_length) if activity.cable_length else ""
                ),
                "splices_connectors": (
                    str(activity.splices_connectors)
                    if activity.splices_connectors
                    else ""
                ),
                # LAN / Wi-Fi
                "wifi_ssid": activity.wifi_ssid or "",
                "wifi_password": activity.wifi_password or "",
                "lan_ip": activity.lan_ip or "",
                "dhcp_range": activity.dhcp_range or "",
                # Mount & Alignment
                "mount_type": activity.mount_type or "",
                "mount_height": (
                    str(activity.mount_height) if activity.mount_height else ""
                ),
                "grounding": activity.grounding or "",
                "weatherproofing": activity.weatherproofing or "",
                "obstruction_percentage": (
                    str(activity.obstruction_percentage)
                    if activity.obstruction_percentage
                    else ""
                ),
                "elevation_angle": (
                    str(activity.elevation_angle) if activity.elevation_angle else ""
                ),
                "azimuth_angle": (
                    str(activity.azimuth_angle) if activity.azimuth_angle else ""
                ),
                "obstruction_notes": activity.obstruction_notes or "",
                "mounting_notes": activity.mounting_notes or "",
                # Cabling & Routing
                "cable_entry_point": activity.cable_entry_point or "",
                "cable_protection": activity.cable_protection or "",
                "termination_type": activity.termination_type or "",
                "routing_notes": activity.routing_notes or "",
                # Power & Backup
                "power_stability_test": activity.power_stability_test or "",
                "ups_installed": activity.ups_installed or "",
                "ups_model": activity.ups_model or "",
                "ups_runtime_minutes": (
                    str(activity.ups_runtime_minutes)
                    if activity.ups_runtime_minutes
                    else ""
                ),
                # Environment & Safety
                "weather_conditions": activity.weather_conditions or "",
                "safety_helmet": activity.safety_helmet,
                "safety_harness": activity.safety_harness,
                "safety_gloves": activity.safety_gloves,
                "safety_ladder": activity.safety_ladder,
                "hazards_noted": activity.hazards_noted or "",
                # Tests et validation
                "snr_db": str(activity.snr_db) if activity.snr_db else "",
                "speed_download_mbps": (
                    str(activity.speed_download_mbps)
                    if activity.speed_download_mbps
                    else ""
                ),
                "speed_upload_mbps": (
                    str(activity.speed_upload_mbps)
                    if activity.speed_upload_mbps
                    else ""
                ),
                "latency_ms": str(activity.latency_ms) if activity.latency_ms else "",
                "final_link_status": activity.final_link_status or "",
                "test_notes": activity.test_notes or "",
                "test_tool": activity.test_tool or "",
                "public_ip": activity.public_ip or "",
                "qos_vlan": activity.qos_vlan or "",
                # Customer
                "customer_full_name": activity.customer_full_name or "",
                "customer_acceptance": activity.customer_acceptance,
                "customer_comments": activity.customer_comments or "",
                "customer_rating": (
                    str(activity.customer_rating) if activity.customer_rating else ""
                ),
                "customer_id_document": activity.customer_id_document or "",
                "customer_signature": activity.customer_signature or "",
                "customer_signoff_at": (
                    activity.customer_signoff_at.strftime("%Y-%m-%d %H:%M:%S")
                    if activity.customer_signoff_at
                    else ""
                ),
                # Reseller Information (if available)
                "reseller_name": activity.reseller_name or "",
                "sla_tier": activity.sla_tier or "",
                "reseller_notes": activity.reseller_notes or "",
            },
            "photos": [
                {
                    "id": photo.id,
                    "url": photo.image.url if photo.image else "",
                    "uploaded_at": photo.uploaded_at.strftime("%Y-%m-%d %H:%M:%S"),
                    "photo_type": photo.photo_type,
                }
                for photo in activity.photos.all()
            ],
            "edit_info": {
                "version_number": activity.version_number,
                "time_left_hours": round(activity.time_left_for_editing(), 1),
                "last_edited_at": (
                    activity.last_edited_at.strftime("%Y-%m-%d %H:%M:%S")
                    if activity.last_edited_at
                    else None
                ),
            },
        }

        print(f"DEBUG: Returning {len(report_data['data'])} data fields")
        print(f"DEBUG: Sample fields: {list(report_data['data'].keys())[:10]}")

        return JsonResponse(report_data)

    except InstallationActivity.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Installation not found."}, status=404
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"An error occurred: {str(e)}"}, status=500
        )


@login_required(login_url="login_page")
@require_POST
def edit_installation_report(request, activity_id):
    """
    Vue d'édition pour modifier un rapport d'installation pendant la période de grâce de 24h.
    Réutilise la même logique que save_installation_report avec validation de période d'édition.
    """
    try:
        # Vérifier que l'installation existe et appartient au technicien
        activity = InstallationActivity.objects.select_related(
            "order", "technician"
        ).get(id=activity_id, technician=request.user)

        # Vérifier que le rapport peut encore être édité
        if not activity.can_be_edited():
            return JsonResponse(
                {
                    "success": False,
                    "error": "Edit window has expired. Report can no longer be modified.",
                },
                status=403,
            )

        # Helper function pour gérer les valeurs vides
        def get_value(key, default=None):
            value = request.POST.get(key, "").strip()
            return value if value else default

        # STEP 1: Job & Site (copié de save_installation_report)
        if get_value("on_site_arrival"):
            activity.on_site_arrival = get_value("on_site_arrival")
        activity.site_address = get_value("site_address", "")
        if get_value("site_latitude"):
            activity.site_latitude = get_value("site_latitude")
        if get_value("site_longitude"):
            activity.site_longitude = get_value("site_longitude")
        activity.access_level = get_value("access_level", "")
        activity.power_availability = get_value("power_availability", "")
        activity.site_notes = get_value("site_notes", "")

        # STEP 2: Equipment - CPE Details
        activity.dish_serial_number = get_value("dish_serial_number", "")
        activity.router_serial_number = get_value("router_serial_number", "")
        activity.firmware_version = get_value("firmware_version", "")
        activity.power_source = get_value("power_source", "")
        if get_value("cable_length"):
            activity.cable_length = get_value("cable_length")
        if get_value("splices_connectors"):
            activity.splices_connectors = get_value("splices_connectors")

        # STEP 2: Equipment - LAN / Wi-Fi
        activity.wifi_ssid = get_value("wifi_ssid", "")
        activity.wifi_password = get_value("wifi_password", "")
        if get_value("lan_ip"):
            activity.lan_ip = get_value("lan_ip")
        activity.dhcp_range = get_value("dhcp_range", "")

        # STEP 3: Mount & Alignment
        activity.mount_type = get_value("mount_type", "")
        if get_value("mount_height"):
            activity.mount_height = get_value("mount_height")
        activity.grounding = get_value("grounding", "")
        activity.weatherproofing = get_value("weatherproofing", "")
        if get_value("obstruction_percentage"):
            activity.obstruction_percentage = get_value("obstruction_percentage")
        if get_value("elevation_angle"):
            activity.elevation_angle = get_value("elevation_angle")
        if get_value("azimuth_angle"):
            activity.azimuth_angle = get_value("azimuth_angle")
        activity.obstruction_notes = get_value("obstruction_notes", "")
        activity.mounting_notes = get_value("mounting_notes", "")

        # STEP 4: Environment & Safety
        activity.weather_conditions = get_value("weather_conditions", "")
        activity.safety_helmet = get_value("safety_helmet") == "on"
        activity.safety_harness = get_value("safety_harness") == "on"
        activity.safety_gloves = get_value("safety_gloves") == "on"
        activity.safety_ladder = get_value("safety_ladder") == "on"
        activity.hazards_noted = get_value("hazards_noted", "")

        # STEP 5: Tests et validation
        if get_value("snr_db"):
            activity.snr_db = get_value("snr_db")
        if get_value("speed_download_mbps"):
            activity.speed_download_mbps = get_value("speed_download_mbps")
        if get_value("speed_upload_mbps"):
            activity.speed_upload_mbps = get_value("speed_upload_mbps")
        if get_value("latency_ms"):
            activity.latency_ms = get_value("latency_ms")
        activity.test_tool = get_value("test_tool", "")
        if get_value("public_ip"):
            activity.public_ip = get_value("public_ip")
        activity.qos_vlan = get_value("qos_vlan", "")
        activity.final_link_status = get_value("final_link_status", "")
        activity.test_notes = get_value("test_notes", "")

        # STEP 6: Customer
        activity.customer_full_name = get_value("customer_full_name", "")
        activity.customer_acceptance = get_value("customer_acceptance") == "on"
        activity.customer_comments = get_value("customer_comments", "")
        if get_value("customer_rating"):
            activity.customer_rating = get_value("customer_rating")

        # Reseller Information (if available)
        activity.reseller_name = get_value("reseller_name", "")
        activity.sla_tier = get_value("sla_tier", "")
        activity.reseller_notes = get_value("reseller_notes", "")

        # STEP 8: Photos - Gérer l'upload des nouvelles photos
        photos_before = request.FILES.getlist("photos_before")
        photos_after = request.FILES.getlist("photos_after")
        photos_evidence = request.FILES.getlist("photos_evidence")

        # Créer les objets InstallationPhoto pour chaque nouvelle photo uploadée avec le bon type
        for photo in photos_before:
            InstallationPhoto.objects.create(
                installation_activity=activity, image=photo, photo_type="before"
            )

        for photo in photos_after:
            InstallationPhoto.objects.create(
                installation_activity=activity, image=photo, photo_type="after"
            )

        for photo in photos_evidence:
            InstallationPhoto.objects.create(
                installation_activity=activity, image=photo, photo_type="evidence"
            )

        # Marquer comme édité et sauvegarder
        activity.mark_as_edited()
        activity.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Report successfully updated (Version {activity.version_number})",
                "version_number": activity.version_number,
                "time_left_hours": round(activity.time_left_for_editing(), 1),
            }
        )

    except InstallationActivity.DoesNotExist:
        return JsonResponse(
            {"success": False, "error": "Installation not found."}, status=404
        )
    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse(
            {"success": False, "error": f"An error occurred: {str(e)}"}, status=500
        )


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_http_methods(["DELETE"])
def delete_installation_photo(request, photo_id):
    """
    Supprime une photo d'installation.
    Seul le technicien qui a créé le rapport peut supprimer ses photos.
    """
    try:
        # Récupérer la photo et vérifier les permissions
        photo = InstallationPhoto.objects.select_related(
            "installation_activity", "installation_activity__technician"
        ).get(id=photo_id)

        # Vérifier que le technicien actuel est le propriétaire du rapport
        if photo.installation_activity.technician != request.user:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Vous n'êtes pas autorisé à supprimer cette photo.",
                },
                status=403,
            )

        # Vérifier que le rapport est encore modifiable (dans la fenêtre de 24h)
        if not photo.installation_activity.can_be_edited():
            return JsonResponse(
                {
                    "success": False,
                    "message": "Cette photo ne peut plus être supprimée car la période de modification (24h) est écoulée.",
                },
                status=403,
            )

        # Supprimer le fichier physique si nécessaire
        if photo.image:
            try:
                photo.image.delete(save=False)
            except Exception as e:
                print(f"Erreur lors de la suppression du fichier image: {e}")

        # Supprimer l'enregistrement de la base de données
        photo.delete()

        return JsonResponse(
            {"success": True, "message": "Photo supprimée avec succès."}
        )

    except InstallationPhoto.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Photo non trouvée."}, status=404
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Erreur lors de la suppression: {str(e)}"},
            status=500,
        )


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
def activation_view(request):
    template = "client_activation.html"
    return render(request, template)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_GET
def activation_pending_api(request):
    """Return pending subscription activations for staff UI with page-number pagination.

    Query params:
      - page (int, default=1)
      - page_size (int, default=10, max=50)
    """
    try:
        # pagination params
        try:
            page = int(request.GET.get("page", 1))
        except Exception:
            page = 1
        try:
            page_size = int(request.GET.get("page_size", 10))
        except Exception:
            page_size = 10
        page = max(1, page)
        page_size = max(1, min(50, page_size))

        subs = (
            Subscription.objects.filter(status__iexact="pending")
            .select_related("user", "plan", "order", "order__kit_inventory")
            .order_by("-started_at")
        )

        data = []
        for s in subs:
            order = s.order
            kit = None
            if order and getattr(order, "kit_inventory", None):
                kit = (
                    order.kit_inventory.kit_number or order.kit_inventory.serial_number
                )

            data.append(
                {
                    "id": s.id,
                    "type": "subscription",
                    "user_name": s.user.full_name if s.user else "—",
                    "user_email": s.user.email if s.user else "",
                    "plan_name": s.plan.name if s.plan else "—",
                    "billing_cycle": (s.billing_cycle or "monthly").lower(),
                    "started_at": s.started_at.isoformat() if s.started_at else None,
                    "order_ref": order.order_reference if order else "",
                    "kit_id": kit or "—",
                    "status": s.status,
                }
            )

        # Also include activation requests created by technicians
        from tech.models import ActivationRequest

        reqs = ActivationRequest.objects.all().order_by("-requested_at")[:200]
        req_data = []
        for r in reqs:
            req_data.append(
                {
                    "id": f"req-{r.id}",
                    "type": "request",
                    "plan_name": r.plan_name,
                    "user_name": r.client_name,
                    "user_email": "",  # not stored on ActivationRequest
                    "kit_id": r.kit_serial or "—",
                    "plus_code": r.plus_code or "",
                    "order_ref": (
                        getattr(r.order, "order_reference", "") if r.order else ""
                    ),
                    "subscription_plan": (
                        getattr(r.subscription, "plan_name", "")
                        if getattr(r, "subscription", None)
                        else ""
                    ),
                    "latitude": r.latitude,
                    "longitude": r.longitude,
                    "requested_at": (
                        r.requested_at.isoformat() if r.requested_at else None
                    ),
                    "status": r.status,
                }
            )

        # Combine and sort by requested_at (or started_at) descending for a stable view
        all_items = data + req_data

        def _item_ts(it):
            # prefer requested_at, then started_at, then 0
            ts = None
            if it.get("requested_at"):
                try:
                    from django.utils.dateparse import parse_datetime

                    ts = parse_datetime(it.get("requested_at"))
                except Exception:
                    ts = None
            if not ts and it.get("started_at"):
                try:
                    from django.utils.dateparse import parse_datetime

                    ts = parse_datetime(it.get("started_at"))
                except Exception:
                    ts = None
            return ts or 0

        all_items.sort(key=lambda x: _item_ts(x), reverse=True)

        # paginate the combined list
        from django.core.paginator import EmptyPage, Paginator

        paginator = Paginator(all_items, page_size)
        try:
            page_obj = paginator.page(page)
            page_items = list(page_obj.object_list)
        except EmptyPage:
            page_items = []

        meta = {
            "page": page,
            "page_size": page_size,
            "total_pages": paginator.num_pages,
            "total_items": paginator.count,
        }

        return JsonResponse(
            {"success": True, "pending_activations": page_items, "meta": meta}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_GET
def activation_detail(request, activation_id):
    """Return detailed information for a technician-created ActivationRequest or subscription activation.

    activation_id may be prefixed with 'req-' for ActivationRequest rows.
    """
    try:
        from main.models import Subscription
        from tech.models import ActivationRequest

        aid = str(activation_id)
        if aid.startswith("req-"):
            # ActivationRequest
            aid_num = int(aid.split("-", 1)[1])
            ar = (
                ActivationRequest.objects.select_related(
                    "order", "subscription", "requested_by"
                )
                .filter(id=aid_num)
                .first()
            )
            if not ar:
                return JsonResponse(
                    {"success": False, "error": "Activation not found."}, status=404
                )

            payload = {
                "id": f"req-{ar.id}",
                "type": "request",
                "plan_name": ar.plan_name,
                "order_ref": (
                    getattr(ar.order, "order_reference", "") if ar.order else ""
                ),
                "subscription_id": (
                    getattr(ar.subscription, "id", None)
                    if getattr(ar, "subscription", None)
                    else None
                ),
                "kit_serial": ar.kit_serial,
                "client_name": ar.client_name,
                "requested_by": (
                    getattr(ar.requested_by, "full_name", None)
                    if getattr(ar, "requested_by", None)
                    else None
                ),
                "requested_by_id": (
                    getattr(ar.requested_by, "id_user", None)
                    if getattr(ar, "requested_by", None)
                    else None
                ),
                "requested_at": (
                    ar.requested_at.isoformat() if ar.requested_at else None
                ),
                "latitude": ar.latitude,
                "longitude": ar.longitude,
                "plus_code": ar.plus_code,
                # Attempt to include client contact info when available
                "client_phone": (
                    getattr(ar.order, "user", None)
                    and getattr(ar.order.user, "phone", None)
                )
                or None,
                "client_address": getattr(ar.order, "delivery_address", None)
                or (
                    getattr(ar, "requested_activity", None)
                    and getattr(ar.requested_activity, "site_address", None)
                )
                or None,
                "status": ar.status,
            }
            return JsonResponse({"success": True, "activation": payload})

        else:
            # subscription id
            sid = int(aid)
            s = (
                Subscription.objects.select_related("user", "plan", "order")
                .filter(id=sid)
                .first()
            )
            if not s:
                return JsonResponse(
                    {"success": False, "error": "Subscription not found."}, status=404
                )

            order = s.order
            kit = None
            if order and getattr(order, "kit_inventory", None):
                kit = (
                    order.kit_inventory.kit_number or order.kit_inventory.serial_number
                )

            payload = {
                "id": s.id,
                "type": "subscription",
                "user_name": s.user.full_name if s.user else None,
                "user_email": s.user.email if s.user else None,
                "user_phone": getattr(s.user, "phone", None) if s.user else None,
                "plan_name": s.plan.name if s.plan else None,
                "order_ref": order.order_reference if order else "",
                "kit_serial": kit,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "status": s.status,
                "client_address": getattr(order, "delivery_address", None) or None,
            }
            return JsonResponse({"success": True, "activation": payload})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
def activation_detail_page(request, activation_id):
    """Render a full details page for an activation (Subscription id or ActivationRequest id).

    The user asked to drop the 'req-' prefix in the URL: we accept either a plain integer
    (subscription id) or 'req-<id>' and normalize accordingly.
    """
    try:
        aid = str(activation_id)
        # Normalize: allow either 'req-123' or just '123' for subscription id.
        template_name = "tech/activation_detail.html"

        # Safety: if user visited /activation/12/ but an ActivationRequest with id=12 exists,
        # redirect to the canonical 'req-12' URL to show the request details instead of 'Subscription not found'.
        try:
            from tech.models import ActivationRequest

            if not aid.startswith("req-") and aid.isdigit():
                ar = ActivationRequest.objects.filter(id=int(aid)).first()
                if ar:
                    # redirect to req-<id>
                    return redirect(
                        "activation_detail_page", activation_id=f"req-{int(aid)}"
                    )
        except Exception:
            # best-effort; continue normally if models import fails
            pass

        # Reuse the JSON payload builder by calling the existing activation_detail view
        # but since activation_detail returns JsonResponse, call the function and extract data.
        # Build a fake GET request to pass through; simpler: import and reuse internal logic.
        from django.test.client import RequestFactory

        rf = RequestFactory()
        fake_req = rf.get("/")
        fake_req.user = request.user

        # Call existing activation_detail view to get JSON payload
        resp = activation_detail(fake_req, activation_id=aid)
        # activation_detail returns a JsonResponse-like object. Try to parse its content
        try:
            payload = json.loads(resp.content)
        except Exception:
            payload = {"success": False, "error": "Failed to load activation"}

        # If the detail endpoint reported failure, continue to fallback DB lookups below
        if not payload.get("success"):
            # Attempt a best-effort fallback: try to load ActivationRequest or Subscription directly
            try:
                from main.models import Subscription
                from tech.models import ActivationRequest

                # Try ActivationRequest with possible 'req-' prefix or raw id
                ar = None
                try:
                    if aid.startswith("req-"):
                        ar_id = int(aid.split("-", 1)[1])
                    else:
                        ar_id = int(aid)
                except Exception:
                    ar_id = None

                if ar_id is not None:
                    ar = (
                        ActivationRequest.objects.select_related(
                            "order", "subscription", "requested_by"
                        )
                        .filter(id=ar_id)
                        .first()
                    )

                if ar:
                    # build activation payload similar to activation_detail
                    activation = {
                        "id": f"req-{ar.id}",
                        "type": "request",
                        "plan_name": ar.plan_name,
                        "order_ref": (
                            getattr(ar.order, "order_reference", "") if ar.order else ""
                        ),
                        "subscription_id": (
                            getattr(ar.subscription, "id", None)
                            if getattr(ar, "subscription", None)
                            else None
                        ),
                        "kit_serial": ar.kit_serial,
                        "client_name": ar.client_name,
                        "requested_by": (
                            getattr(ar.requested_by, "full_name", None)
                            if getattr(ar, "requested_by", None)
                            else None
                        ),
                        "requested_by_id": (
                            getattr(ar.requested_by, "id_user", None)
                            if getattr(ar, "requested_by", None)
                            else None
                        ),
                        "requested_at": (
                            ar.requested_at.isoformat() if ar.requested_at else None
                        ),
                        "latitude": ar.latitude,
                        "longitude": ar.longitude,
                        "plus_code": ar.plus_code,
                        "client_phone": (
                            getattr(ar.order, "user", None)
                            and getattr(ar.order.user, "phone", None)
                        )
                        or None,
                        "client_address": getattr(ar.order, "delivery_address", None)
                        or (
                            getattr(ar, "requested_activity", None)
                            and getattr(ar.requested_activity, "site_address", None)
                        )
                        or None,
                        "status": ar.status,
                    }
                else:
                    # Try subscription numeric id
                    try:
                        sid = int(aid)
                    except Exception:
                        sid = None
                    s = None
                    if sid is not None:
                        s = (
                            Subscription.objects.select_related("user", "plan", "order")
                            .filter(id=sid)
                            .first()
                        )
                    if s:
                        order = s.order
                        kit = None
                        if order and getattr(order, "kit_inventory", None):
                            kit = (
                                order.kit_inventory.kit_number
                                or order.kit_inventory.serial_number
                            )
                        activation = {
                            "id": s.id,
                            "type": "subscription",
                            "user_name": s.user.full_name if s.user else None,
                            "user_email": s.user.email if s.user else None,
                            "user_phone": (
                                getattr(s.user, "phone", None) if s.user else None
                            ),
                            "plan_name": s.plan.name if s.plan else None,
                            "order_ref": order.order_reference if order else "",
                            "kit_serial": kit,
                            "started_at": (
                                s.started_at.isoformat() if s.started_at else None
                            ),
                            "status": s.status,
                            "client_address": getattr(order, "delivery_address", None)
                            or None,
                        }
                    else:
                        return render(
                            request,
                            template_name,
                            {"error": payload.get("error", "Not found")},
                        )
            except Exception:
                return render(
                    request, template_name, {"error": payload.get("error", "Not found")}
                )
        else:
            activation = payload.get("activation") or {}
        # Normalize common keys for template consistency
        activation["client_name"] = (
            activation.get("client_name") or activation.get("user_name") or ""
        )
        activation["client_phone"] = (
            activation.get("client_phone") or activation.get("user_phone") or ""
        )
        activation["order_ref"] = (
            activation.get("order_ref") or activation.get("order_reference") or ""
        )
        activation["kit_serial"] = (
            activation.get("kit_serial") or activation.get("kit") or ""
        )
        activation["started_at"] = (
            activation.get("started_at") or activation.get("startedAt") or ""
        )
        activation["reason"] = activation.get("reason") or ""
        activation["user_email"] = activation.get("user_email") or ""
        # Enrich context: try to find related InstallationActivity timeline (by order)
        activities = []
        try:
            order_ref = activation.get("order_ref") or activation.get("order_reference")
            order_obj = None
            if order_ref:
                order_obj = Order.objects.filter(order_reference=order_ref).first()
            # If subscription provides an order via subscription id, try that
            if not order_obj and activation.get("subscription_id"):
                try:
                    sub = Subscription.objects.filter(
                        id=activation.get("subscription_id")
                    ).first()
                    order_obj = getattr(sub, "order", None)
                except Exception:
                    order_obj = None

            if order_obj:
                qs = (
                    InstallationActivity.objects.select_related("technician")
                    .filter(order=order_obj)
                    .order_by("planned_at", "id")
                )
                for a in qs:
                    activities.append(
                        {
                            "planned_at": _fmt_iso(getattr(a, "planned_at", None)),
                            "started_at": _fmt_iso(getattr(a, "started_at", None)),
                            "completed_at": _fmt_iso(getattr(a, "completed_at", None)),
                            "technician": (
                                getattr(a.technician, "full_name", None)
                                if getattr(a, "technician", None)
                                else None
                            ),
                            "notes": getattr(a, "notes", None) or "",
                        }
                    )
        except Exception:
            activities = []

        # Map providers (friendly names + tile urls) - keep a small set of free providers
        map_providers = [
            {
                "id": "osm",
                "name": "OpenStreetMap",
                "url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
                "attribution": "&copy; OpenStreetMap contributors",
            },
            {
                "id": "carto",
                "name": "CartoDB Positron",
                "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
                "attribution": "&copy; CartoDB",
            },
        ]

        # Enrich activation context with DB-sourced objects where possible
        try:
            # If we have a subscription id, fetch it
            if activation.get("subscription_id"):
                try:
                    sub_obj = (
                        Subscription.objects.select_related("plan", "user", "order")
                        .filter(id=activation.get("subscription_id"))
                        .first()
                    )
                except Exception:
                    sub_obj = None
                if sub_obj:
                    activation["subscription_id"] = sub_obj.id
                    activation["subscription_status"] = getattr(sub_obj, "status", None)
                    activation["plan_name"] = getattr(
                        sub_obj.plan, "name", activation.get("plan_name")
                    )
                    activation["billing_cycle"] = getattr(
                        sub_obj, "billing_cycle", activation.get("billing_cycle")
                    )
                    # subscription started_at may be a date; provide an ISO or readable string
                    activation["started_at"] = activation.get("started_at") or (
                        _fmt_date(getattr(sub_obj, "started_at", None))
                        if getattr(sub_obj, "started_at", None)
                        else activation.get("started_at")
                    )
                    activation["plan_id"] = getattr(sub_obj.plan, "id", None)
                    activation["user_email"] = getattr(
                        sub_obj.user, "email", activation.get("user_email")
                    )
                    activation["order_ref"] = activation.get("order_ref") or (
                        getattr(sub_obj.order, "order_reference", None)
                        if getattr(sub_obj, "order", None)
                        else activation.get("order_ref")
                    )

            # If we have an order_ref, try to fetch the order and kit inventory info
            order_obj = None
            if activation.get("order_ref"):
                try:
                    order_obj = (
                        Order.objects.filter(
                            order_reference=activation.get("order_ref")
                        )
                        .select_related("user", "kit_inventory")
                        .first()
                    )
                except Exception:
                    order_obj = None

            if order_obj:
                activation["order_created_at"] = (
                    _fmt_iso(getattr(order_obj, "created_at", None))
                    if hasattr(order_obj, "created_at")
                    else None
                )
                # Kit inventory -> kit model/serial/imei
                ki = getattr(order_obj, "kit_inventory", None)
                if ki:
                    activation["kit_serial"] = activation.get("kit_serial") or (
                        getattr(ki, "serial_number", None)
                        or getattr(ki, "kit_number", None)
                    )
                    activation["kit_model"] = getattr(
                        ki, "model_name", None
                    ) or getattr(ki, "model", None)
                    activation["kit_imei"] = getattr(ki, "imei", None)
                    activation["kit_stock_status"] = getattr(ki, "status", None)
                # Ensure client contact info from order is present
                if getattr(order_obj, "user", None):
                    activation["client_name"] = activation.get(
                        "client_name"
                    ) or getattr(order_obj.user, "full_name", None)
                    activation["client_phone"] = activation.get(
                        "client_phone"
                    ) or getattr(order_obj.user, "phone", None)

        except Exception:
            # best-effort enrichment; don't fail the page render
            pass

        # Prepare context for template: map data, order/client/subscription/kit/activation request metadata
        context = {
            "activation": activation,
            "activities": activities,
            "map_providers": map_providers,
        }
        return render(request, template_name, context)
    except Exception as e:
        return render(request, "tech/activation_detail.html", {"error": str(e)})


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_GET
def activation_kpis_api(request):
    """Return KPI cards for activations page.

    Query params:
      - technician_id (optional)
      - date_range (one of '24h','7d','30d') or start & end (YYYY-MM-DD)
    """
    try:
        from datetime import datetime, timedelta

        from django.core.cache import cache
        from django.utils import timezone

        from main.models import InstallationActivity, Subscription
        from tech.models import ActivationRequest

        tech_id = request.GET.get("technician_id")
        dr = request.GET.get("date_range")
        start = request.GET.get("start")
        end = request.GET.get("end")

        now = timezone.now()
        if dr == "24h":
            start_dt = now - timedelta(hours=24)
            end_dt = now
        elif dr == "7d":
            start_dt = now - timedelta(days=7)
            end_dt = now
        elif dr == "30d":
            start_dt = now - timedelta(days=30)
            end_dt = now
        elif start and end:
            try:
                start_dt = datetime.fromisoformat(start)
                end_dt = datetime.fromisoformat(end)
            except Exception:
                start_dt = None
                end_dt = None
        else:
            start_dt = None
            end_dt = None

        cache_key = f"activation_kpis:{tech_id}:{dr}:{start}:{end}"
        cached = cache.get(cache_key)
        if cached is not None:
            return JsonResponse({"success": True, "kpis": cached})

        # Build base filters
        subs_qs = Subscription.objects.all()
        reqs_qs = ActivationRequest.objects.all()
        acts_qs = InstallationActivity.objects.all()
        if tech_id:
            subs_qs = subs_qs.filter(assigned_technician_id=tech_id)
            reqs_qs = reqs_qs.filter(requested_by_id=tech_id)
            acts_qs = acts_qs.filter(assigned_to_id=tech_id)
        if start_dt:
            subs_qs = subs_qs.filter(started_at__gte=start_dt, started_at__lte=end_dt)
            reqs_qs = reqs_qs.filter(
                requested_at__gte=start_dt, requested_at__lte=end_dt
            )

        # KPIs
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        planned_today_qs = ActivationRequest.objects.filter(
            requested_at__gte=today_start, requested_at__lte=now
        )
        if tech_id:
            planned_today_qs = planned_today_qs.filter(requested_by_id=tech_id)
        planned_today_count = planned_today_qs.count()

        pending_subs = subs_qs.filter(status__iexact="pending")
        pending_reqs = reqs_qs.filter(status__iexact="pending")
        pending_count = pending_subs.count() + pending_reqs.count()

        in_progress_acts = acts_qs.filter(status__iexact="in_progress")
        in_progress_reqs = reqs_qs.filter(status__iexact="in_progress")
        in_progress_count = in_progress_acts.count() + in_progress_reqs.count()

        completed_subs = subs_qs.filter(status__iexact="active")
        completed_acts = acts_qs.filter(status__iexact="completed")
        completed_count = completed_subs.count() + completed_acts.count()

        kpis = {
            "planned_today": planned_today_count,
            "pending": pending_count,
            "in_progress": in_progress_count,
            "completed": completed_count,
        }

        cache.set(cache_key, kpis, 30)
        return JsonResponse({"success": True, "kpis": kpis})
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_POST
def confirm_activation(request, sub_id):
    """Confirm (activate) a pending subscription."""
    try:
        sub = Subscription.objects.select_related("user", "plan").get(id=sub_id)
        # Only allow confirming pending subscriptions
        if sub.status and sub.status.lower() != "pending":
            return JsonResponse(
                {"success": False, "message": "Subscription is not pending."},
                status=400,
            )

        # Activate
        sub.status = "active"
        from django.utils import timezone

        today = timezone.now().date()
        sub.started_at = today
        # Set next billing date based on cycle
        if sub.billing_cycle == "monthly":
            sub.next_billing_date = today + timedelta(days=30)
        elif sub.billing_cycle == "quarterly":
            sub.next_billing_date = today + timedelta(days=90)
        elif sub.billing_cycle == "yearly":
            sub.next_billing_date = today + timedelta(days=365)
        else:
            sub.next_billing_date = today + timedelta(days=30)

        sub.save()
        return JsonResponse({"success": True, "message": "Subscription activated."})
    except Subscription.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Subscription not found."}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_POST
def confirm_activation_request(request, req_id):
    """Confirm a technician-created ActivationRequest (mark status confirmed).

    req_id is integer id of ActivationRequest.
    """
    try:
        from tech.models import ActivationRequest

        ar = ActivationRequest.objects.get(id=req_id)
        if ar.status == "confirmed":
            return JsonResponse(
                {"success": False, "message": "Already confirmed."}, status=400
            )
        ar.status = "confirmed"
        ar.save()
        # Clear activity flag if set
        try:
            from main.models import InstallationActivity

            if getattr(ar, "requested_activity_id", None):
                ia = InstallationActivity.objects.filter(
                    id=ar.requested_activity_id
                ).first()
                if ia and getattr(ia, "activation_requested", False):
                    ia.activation_requested = False
                    ia.save(update_fields=["activation_requested"])
        except Exception:
            pass
        return JsonResponse(
            {"success": True, "message": "Activation request confirmed."}
        )
    except ActivationRequest.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Activation request not found."}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_POST
def cancel_activation_request(request, req_id):
    """Cancel (mark cancelled) a technician-created ActivationRequest."""
    try:
        from tech.models import ActivationRequest

        ar = ActivationRequest.objects.get(id=req_id)
        if ar.status == "cancelled":
            return JsonResponse(
                {"success": False, "message": "Already cancelled."}, status=400
            )
        ar.status = "cancelled"
        ar.save()
        # Clear activity flag if set
        try:
            from main.models import InstallationActivity

            if getattr(ar, "requested_activity_id", None):
                ia = InstallationActivity.objects.filter(
                    id=ar.requested_activity_id
                ).first()
                if ia and getattr(ia, "activation_requested", False):
                    ia.activation_requested = False
                    ia.save(update_fields=["activation_requested"])
        except Exception:
            pass
        return JsonResponse(
            {"success": True, "message": "Activation request cancelled."}
        )
    except ActivationRequest.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Activation request not found."}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_POST
def cancel_activation(request, sub_id):
    """Cancel (mark as cancelled) a pending subscription."""
    try:
        sub = Subscription.objects.get(id=sub_id)
        if sub.status and sub.status.lower() == "cancelled":
            return JsonResponse(
                {"success": False, "message": "Subscription already cancelled."},
                status=400,
            )

        sub.status = "cancelled"
        sub.ended_at = timezone.now().date()
        sub.save()
        return JsonResponse({"success": True, "message": "Subscription cancelled."})
    except Subscription.DoesNotExist:
        return JsonResponse(
            {"success": False, "message": "Subscription not found."}, status=404
        )
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin", "technician"])
@require_POST
def request_activation(request):
    """Create an ActivationRequest from a technician action (FE dashboard).

    Expected JSON body: { order_id, subscription_id (optional), plan_name, client_name, kit_serial, latitude, longitude, plus_code (optional) }
    """
    try:
        # TEMP DEBUG: log auth & cookie info to help diagnose unexpected 302 -> login redirects
        try:
            import logging

            logger = logging.getLogger(__name__)
            logger.info(
                "[request_activation debug] user: %s, is_authenticated: %s",
                getattr(request, "user", None),
                getattr(request.user, "is_authenticated", False),
            )
            logger.info(
                "[request_activation debug] request.COOKIES keys: %s",
                list(request.COOKIES.keys()),
            )
            logger.info(
                "[request_activation debug] request.headers Cookie: %s",
                request.headers.get("Cookie"),
            )
        except Exception:
            pass
        import json

        data = json.loads(request.body.decode("utf-8") or "{}")
        activity_id = data.get("activity_id")
        order_id = data.get("order_reference")
        subscription_id = data.get("subscription_id")
        plan_name = data.get("plan_name") or ""
        client_name = data.get("customer_name") or ""
        kit_serial = data.get("kit_serial") or ""
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        plus_code = data.get("plus_code") or ""

        # Import model lazily to avoid circular imports
        from main.models import InstallationActivity, Order, Subscription
        from tech.models import ActivationRequest

        # Verify technician is assigned to the activity (security)
        if not activity_id:
            return JsonResponse(
                {"success": False, "error": "Missing activity_id"}, status=400
            )

        if not InstallationActivity.objects.filter(
            id=activity_id, technician=request.user
        ).exists():
            return JsonResponse(
                {
                    "success": False,
                    "error": "Unauthorized to request activation for this activity",
                },
                status=403,
            )

        # Prevent duplicate activation requests and ensure atomic create + flag set
        order = None
        subscription = None
        # order_id may actually be an order_reference string coming from the frontend
        order_ref = (
            data.get("order_reference") or data.get("order_id") or data.get("order_pk")
        )
        if order_ref:
            # try integer PK first, otherwise match order_reference
            try:
                order = Order.objects.filter(pk=int(order_ref)).first()
            except Exception:
                order = Order.objects.filter(order_reference=str(order_ref)).first()

        if subscription_id:
            subscription = Subscription.objects.filter(pk=subscription_id).first()

        # If subscription not provided and we have an order, try to look up a subscription linked to that order
        if not subscription and order:
            subscription = Subscription.objects.filter(order=order).first()

        # If client did not send plus_code but latitude/longitude available, compute server-side
        if not plus_code and latitude is not None and longitude is not None:
            try:
                from openlocationcode import openlocationcode as olc

                plus_code = olc.encode(float(latitude), float(longitude))
            except Exception:
                plus_code = plus_code or ""

        with transaction.atomic():
            activity = (
                InstallationActivity.objects.select_for_update()
                .filter(id=activity_id)
                .first()
            )
            if not activity:
                return JsonResponse(
                    {"success": False, "error": "Installation activity not found"},
                    status=404,
                )

            # If flag set, try to return the existing ActivationRequest (if present)
            if getattr(activity, "activation_requested", False):
                existing = (
                    ActivationRequest.objects.filter(requested_activity_id=activity_id)
                    .exclude(status="cancelled")
                    .order_by("-id")
                    .first()
                )
                if existing:
                    # Return the existing activation data so the frontend can reconcile state
                    activation_payload = {
                        "id": existing.id,
                        "plan_name": existing.plan_name,
                        "client_name": existing.client_name,
                        "kit_serial": existing.kit_serial,
                        "plus_code": existing.plus_code,
                        "requested_at": (
                            existing.requested_at.isoformat()
                            if existing.requested_at
                            else None
                        ),
                        "status": existing.status,
                    }
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "Activation request already created for this activity.",
                            "activation": activation_payload,
                        },
                        status=409,
                    )
                else:
                    # Stale flag: clear and allow creation to proceed
                    try:
                        activity.activation_requested = False
                        activity.save(update_fields=["activation_requested"])
                    except Exception:
                        # non-fatal, continue
                        pass

            # Create ActivationRequest and set flag atomically
            ar = ActivationRequest.objects.create(
                subscription=subscription,
                order=order,
                requested_activity=activity,
                plan_name=plan_name,
                client_name=client_name,
                kit_serial=kit_serial,
                latitude=latitude,
                longitude=longitude,
                plus_code=plus_code,
                requested_by=request.user,
            )
            activity.activation_requested = True
            activity.save(update_fields=["activation_requested"])

        return JsonResponse(
            {
                "success": True,
                "activation": {
                    "id": ar.id,
                    "order_reference": ar.order.order_reference if ar.order else None,
                    "plan_name": ar.plan_name,
                    "client_name": ar.client_name,
                    "kit_serial": ar.kit_serial,
                    "plus_code": ar.plus_code,
                    "requested_at": (
                        ar.requested_at.isoformat() if ar.requested_at else None
                    ),
                    "status": ar.status,
                },
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)
