import json
import logging
import re
from decimal import Decimal

import requests

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods, require_POST

from main.models import PaymentAttempt

# Import the models
from .models import SiteSurvey, SiteSurveyChecklist, SiteSurveyPhoto, SiteSurveyResponse

logger = logging.getLogger(__name__)

# Helper Functions


def _map_flexpay_error_to_user_message(gateway_message):
    """
    Map FlexPay gateway error messages to user-friendly, localized messages.
    This helps avoid exposing internal system details to users.
    """
    gateway_message_lower = str(gateway_message).lower()

    # Common FlexPay error patterns and their user-friendly mappings
    error_mappings = {
        "insufficient": _(
            "Insufficient funds. Please check your account balance and try again."
        ),
        "invalid phone": _(
            "Invalid phone number. Please check your mobile number and try again."
        ),
        "phone number": _(
            "Invalid phone number. Please check your mobile number and try again."
        ),
        "timeout": _("Payment request timed out. Please try again."),
        "network": _("Network error. Please check your connection and try again."),
        "declined": _(
            "Payment was declined. Please contact your mobile money provider."
        ),
        "blocked": _(
            "Account is temporarily blocked. Please contact your mobile money provider."
        ),
        "limit exceeded": _(
            "Transaction limit exceeded. Please try a smaller amount or contact your provider."
        ),
        "invalid amount": _("Invalid payment amount. Please try again."),
        "service unavailable": _(
            "Mobile money service is temporarily unavailable. Please try again later."
        ),
        "authentication failed": _("Authentication failed. Please try again."),
        "duplicate": _(
            "Duplicate transaction detected. Please wait a moment before trying again."
        ),
    }

    # Check for known error patterns
    for pattern, user_message in error_mappings.items():
        if pattern in gateway_message_lower:
            return user_message

    # Default fallback message for unknown errors
    return _(
        "Payment could not be processed at this time. Please try again or contact support."
    )


def _create_additional_billing_if_needed(survey):
    """
    Helper function to create additional billing when a survey is approved
    and has additional equipment costs. Returns the created billing object
    or None if no billing was created.
    """
    # Check if survey has additional costs and create billing if needed
    if survey.requires_additional_equipment and survey.additional_costs.exists():
        from .models import AdditionalBilling

        # Check if billing already exists
        if not hasattr(survey, "additional_billing"):
            # Calculate total from all additional costs
            total_amount = sum(
                cost.total_price for cost in survey.additional_costs.all()
            )

            # Create additional billing
            billing = AdditionalBilling.objects.create(
                survey=survey,
                order=survey.order,
                customer=survey.order.user,
                total_amount=total_amount,
                status="pending_approval",
            )

            # Send notification to customer about additional billing
            try:
                from .notifications import send_billing_notification

                notification_sent = send_billing_notification(billing)
                if not notification_sent:
                    print(
                        f"Warning: Failed to send billing notification for billing {billing.id}"
                    )
            except Exception as e:
                print(f"Error sending billing notification: {str(e)}")

            return billing

    return None


# Site Survey Views


@login_required
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def survey_dashboard_api(request):
    """API endpoint for survey data (called by JavaScript in template)"""
    surveys = SiteSurvey.objects.select_related(
        "order", "technician", "approved_by"
    ).all()

    # If user is a technician (not staff admin), filter to show only their assigned surveys
    if request.user.has_role("technician") and not request.user.is_superuser:
        surveys = surveys.filter(technician=request.user)

    # Filter by status
    status_filter = request.GET.get("status")
    if status_filter:
        surveys = surveys.filter(status=status_filter)

    # Convert to list of dictionaries for JSON response
    survey_data = []
    for survey in surveys:
        print(
            f"Survey {survey.id}: technician object = {survey.technician}"
        )  # Debug log

        technician_name = "Unassigned"
        if survey.technician:
            # Use full_name directly since get_full_name() might be empty
            technician_name = (
                survey.technician.full_name
                or survey.technician.email
                or f"User {survey.technician.id_user}"
            )
            print(
                f"Survey {survey.id}: technician.full_name = '{survey.technician.full_name}'"
            )

        survey_data.append(
            {
                "id": survey.id,
                "order_reference": survey.order.order_reference if survey.order else "",
                "technician": technician_name,
                "scheduled_at": (
                    survey.scheduled_date.strftime("%Y-%m-%d")
                    if survey.scheduled_date
                    else "—"
                ),
                "status": survey.status,
                "latitude": survey.survey_latitude,
                "longitude": survey.survey_longitude,
                "installation_feasible": survey.installation_feasible,
            }
        )
        print(
            f"Survey {survey.id}: final technician_name = '{technician_name}'"
        )  # Debug log

    return JsonResponse(
        {
            "surveys": survey_data,
            "status_choices": SiteSurvey.STATUS_CHOICES,
            "current_status": status_filter,
        }
    )


@login_required
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def survey_dashboard(request):
    """Dashboard for managing site surveys (admin view) or viewing assigned surveys (technician view)"""
    context = {
        "is_technician": request.user.has_role("technician")
        and not request.user.is_superuser,
        "user_role": (
            "technician"
            if request.user.has_role("technician") and not request.user.is_superuser
            else "admin"
        ),
    }
    return render(request, "site_survey/survey_dashboard.html", context)


@login_required
# @user_passes_test(lambda u: u.is_staff, login_url="login_page")
def survey_detail(request, survey_id):
    """Detailed view of a site survey with approval functionality"""
    survey = get_object_or_404(
        SiteSurvey.objects.select_related(
            "order", "technician", "approved_by", "assigned_by"
        ).prefetch_related("responses", "photos"),
        id=survey_id,
    )

    if request.method == "POST":
        # Check if this is a JSON/AJAX request
        is_ajax = (
            request.content_type == "application/json"
            or request.headers.get("Content-Type") == "application/json"
        )

        if is_ajax:
            try:
                data = json.loads(request.body)
                action = data.get("action")

                if action == "approve":
                    # Check permissions
                    if not request.user.is_staff:
                        return JsonResponse(
                            {
                                "success": False,
                                "message": "You don't have permission to approve surveys",
                            },
                            status=403,
                        )

                    # Check if installation is feasible
                    if survey.installation_feasible is False:
                        return JsonResponse(
                            {
                                "success": False,
                                "message": "Cannot approve survey - technician marked installation as NOT feasible. Please reject instead.",
                            },
                            status=400,
                        )

                    survey.approved_by = request.user
                    survey.approved_at = timezone.now()
                    survey.status = "approved"
                    survey.approval_notes = data.get("approval_notes", "")
                    survey.save()  # This will trigger installation activity creation via the model's save method

                    # Create additional billing if needed
                    _create_additional_billing_if_needed(survey)

                    return JsonResponse(
                        {
                            "success": True,
                            "message": "Survey approved successfully and installation job created",
                        }
                    )

                elif action == "reject":
                    # Check permissions
                    if not request.user.is_staff:
                        return JsonResponse(
                            {
                                "success": False,
                                "message": "You don't have permission to reject surveys",
                            },
                            status=403,
                        )

                    survey.status = "rejected"
                    survey.rejection_reason = data.get("rejection_reason", "")
                    survey.save()

                    return JsonResponse(
                        {"success": True, "message": "Survey rejected successfully"}
                    )
                else:
                    return JsonResponse(
                        {"success": False, "message": "Invalid action"}, status=400
                    )

            except json.JSONDecodeError:
                return JsonResponse(
                    {"success": False, "message": "Invalid JSON data"}, status=400
                )
            except Exception as e:
                return JsonResponse(
                    {
                        "success": False,
                        "message": f"Error processing request: {str(e)}",
                    },
                    status=500,
                )
        else:
            # Handle regular form submission
            action = request.POST.get("action")

            if action == "approve":
                # Check if installation is feasible
                if survey.installation_feasible is False:
                    messages.error(
                        request,
                        "Cannot approve survey - technician marked installation as NOT feasible. Please reject instead.",
                    )
                    return redirect("site_survey:survey_detail", survey_id=survey.id)

                survey.approved_by = request.user
                survey.approved_at = timezone.now()
                survey.status = "approved"
                survey.approval_notes = request.POST.get("approval_notes", "")
                survey.save()  # This will trigger installation activity creation via the model's save method

                # Create additional billing if needed
                _create_additional_billing_if_needed(survey)

                messages.success(
                    request, "Survey approved successfully and installation job created"
                )

            elif action == "reject":
                survey.status = "rejected"
                survey.rejection_reason = request.POST.get("rejection_reason", "")
                survey.save()
                messages.success(request, "Survey rejected")

            return redirect("site_survey:survey_detail", survey_id=survey.id)

    # Calculate total additional costs
    total_additional_cost = sum(
        cost.total_price for cost in survey.additional_costs.all()
    )

    context = {
        "survey": survey,
        "checklist_items": SiteSurveyChecklist.objects.filter(is_active=True),
        "total_additional_cost": total_additional_cost,
    }
    return render(request, "site_survey/survey_detail.html", context)


@login_required
def technician_survey_list(request):
    """List of surveys assigned to the current technician"""
    if "technician" not in request.user.roles:
        messages.error(request, "Access denied")
        return redirect("login_page")

    surveys = (
        SiteSurvey.objects.filter(technician=request.user)
        .select_related("order")
        .order_by("-created_at")
    )

    context = {
        "surveys": surveys,
    }
    return render(request, "site_survey/technician_surveys.html", context)


@login_required
def conduct_survey(request, survey_id):
    """Interface for technician to conduct the survey"""
    survey = get_object_or_404(
        SiteSurvey.objects.select_related("order"),
        id=survey_id,
        technician=request.user,
        status__in=["scheduled", "in_progress"],
    )

    checklist_items = SiteSurveyChecklist.objects.filter(is_active=True)

    if request.method == "POST":
        # Update survey status
        survey.status = "in_progress"
        survey.save()

        # Save responses
        for item in checklist_items:
            response_text = request.POST.get(f"response_{item.id}")
            response_rating = request.POST.get(f"rating_{item.id}")
            response_choice = request.POST.get(f"choice_{item.id}")
            additional_notes = request.POST.get(f"notes_{item.id}")

            if response_text or response_rating or response_choice:
                SiteSurveyResponse.objects.update_or_create(
                    survey=survey,
                    checklist_item=item,
                    defaults={
                        "response_text": response_text or "",
                        "response_rating": (
                            int(response_rating) if response_rating else None
                        ),
                        "response_choice": response_choice or "",
                        "additional_notes": additional_notes or "",
                    },
                )

        # Save location info
        survey.survey_latitude = request.POST.get("latitude")
        survey.survey_longitude = request.POST.get("longitude")
        survey.survey_address = request.POST.get("address")
        survey.location_notes = request.POST.get("location_notes")
        survey.overall_assessment = request.POST.get("overall_assessment")
        survey.installation_feasible = request.POST.get("installation_feasible") == "on"
        survey.recommended_mounting = request.POST.get("recommended_mounting")

        # Mark as completed
        survey.status = "completed"
        survey.save()

        messages.success(request, "Survey completed successfully")
        return redirect("site_survey:technician_survey_list")

    # Get existing responses
    existing_responses = {
        response.checklist_item_id: response for response in survey.responses.all()
    }

    context = {
        "survey": survey,
        "checklist_items": checklist_items,
        "existing_responses": existing_responses,
    }
    return render(request, "site_survey/conduct_survey.html", context)


@login_required
@require_POST
def get_location(request):
    """Get current location using browser geolocation"""
    return JsonResponse({"status": "success"})


@login_required
@require_POST
def upload_survey_photos(request, survey_id):
    """Upload photos for a site survey"""
    try:
        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Check if user has permission to upload photos for this survey
        if hasattr(request.user, "has_role"):
            # If user is a technician, make sure they are assigned to this survey
            if (
                request.user.has_role("technician")
                and survey.technician != request.user
            ):
                return JsonResponse(
                    {
                        "success": False,
                        "message": "You are not authorized to upload photos for this survey",
                    },
                    status=403,
                )

        if "photos" not in request.FILES:
            return JsonResponse(
                {"success": False, "message": "No photos provided"}, status=400
            )

        photos = request.FILES.getlist("photos")
        photo_types = request.POST.getlist("photo_types")
        descriptions = request.POST.getlist("descriptions")
        latitudes = request.POST.getlist("latitudes")
        longitudes = request.POST.getlist("longitudes")

        # Validate that we have at least one photo
        if not photos:
            return JsonResponse(
                {"success": False, "message": "No valid photos found in the upload"},
                status=400,
            )

        uploaded_count = 0
        for i, photo in enumerate(photos):
            try:
                # Validate photo file
                if not photo.content_type.startswith("image/"):
                    continue  # Skip non-image files

                SiteSurveyPhoto.objects.create(
                    survey=survey,
                    photo=photo,
                    photo_type=photo_types[i] if i < len(photo_types) else "other",
                    description=descriptions[i] if i < len(descriptions) else "",
                    latitude=(
                        latitudes[i] if i < len(latitudes) and latitudes[i] else None
                    ),
                    longitude=(
                        longitudes[i] if i < len(longitudes) and longitudes[i] else None
                    ),
                )
                uploaded_count += 1
            except Exception as e:
                # Log the error but continue with other photos
                print(f"Error uploading photo {i}: {str(e)}")
                continue

        if uploaded_count == 0:
            return JsonResponse(
                {
                    "success": False,
                    "message": "No photos could be uploaded. Please check file formats.",
                },
                status=400,
            )

        return JsonResponse(
            {
                "success": True,
                "message": f"{uploaded_count} photo(s) uploaded successfully",
            }
        )

    except Exception as e:
        # Catch any unexpected errors and return proper JSON response
        print(f"Error in upload_survey_photos: {str(e)}")
        return JsonResponse(
            {"success": False, "message": f"Upload failed: {str(e)}"}, status=500
        )


@login_required(login_url="login_page")
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
@require_POST
def assign_to_technician(request):
    """
    Assign a technician to a site survey.
    Expects POST data: survey_id, technician_id, scheduled_date
    """
    try:
        data = json.loads(request.body)
        survey_id = data.get("survey_id")
        technician_id = data.get("technician_id")
        scheduled_date = data.get("scheduled_date")

        if not (survey_id and technician_id and scheduled_date):
            return JsonResponse(
                {"success": False, "message": "Missing required fields."}, status=400
            )

        # Get survey and technician
        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Import User from main.models
        from main.models import User

        technician = get_object_or_404(User, id_user=technician_id)

        # Assign technician to site survey
        survey.technician = technician
        survey.assigned_by = request.user
        survey.assigned_at = timezone.now()

        # Convert string date to date object
        from datetime import datetime

        survey.scheduled_date = datetime.strptime(scheduled_date, "%Y-%m-%d").date()
        survey.save()

        print(
            f"Survey {survey.id} assigned to technician {technician.full_name} (ID: {technician.id_user})"
        )  # Debug log

        return JsonResponse(
            {
                "success": True,
                "message": f"Technician {technician.full_name} assigned successfully to site survey for order {survey.order.order_reference}.",
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def start_site_survey(request):
    """
    Start a site survey - change status to in_progress and set started_at
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            survey_id = data.get("survey_id")

            if not survey_id:
                return JsonResponse(
                    {"success": False, "message": "Survey ID is required."}, status=400
                )

            survey = get_object_or_404(SiteSurvey, id=survey_id)

            # Check if user is the assigned technician or admin
            if survey.technician != request.user and not request.user.is_superuser:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "You are not authorized to start this survey.",
                    },
                    status=403,
                )

            # Update survey status
            survey.status = "in_progress"
            survey.started_at = timezone.now()
            survey.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Site survey for order {survey.order.order_reference} has been started.",
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    return JsonResponse(
        {"success": False, "message": "Invalid request method."}, status=405
    )


@login_required
def get_survey_checklist(request, survey_id):
    """
    Get the checklist for a specific survey
    """
    try:
        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Check if user is the assigned technician or admin
        if survey.technician != request.user and not request.user.is_superuser:
            return JsonResponse(
                {
                    "success": False,
                    "message": "You are not authorized to view this survey.",
                },
                status=403,
            )

        # Get all active checklist items
        checklist_items = SiteSurveyChecklist.objects.filter(is_active=True).order_by(
            "category", "display_order"
        )

        # Get existing responses for this survey
        existing_responses = {
            resp.checklist_item_id: resp
            for resp in SiteSurveyResponse.objects.filter(survey=survey)
        }

        # Organize checklist by category
        checklist_data = {}
        for item in checklist_items:
            if item.category not in checklist_data:
                checklist_data[item.category] = {
                    "name": item.get_category_display(),
                    "items": [],
                }

            existing_response = existing_responses.get(item.id)

            # Get the appropriate response value based on question type
            response_value = None
            response_notes = None

            if existing_response:
                response_notes = existing_response.additional_notes
                if item.question_type == "rating":
                    response_value = existing_response.response_rating
                elif item.question_type in ["yes_no", "multiple_choice"]:
                    response_value = existing_response.response_choice
                else:  # text type
                    response_value = existing_response.response_text

            checklist_data[item.category]["items"].append(
                {
                    "id": item.id,
                    "question": item.question,
                    "question_type": item.question_type,
                    "choices": item.choices,
                    "is_required": item.is_required,
                    "response": {"value": response_value, "notes": response_notes},
                }
            )

        return JsonResponse(
            {
                "success": True,
                "survey": {
                    "id": survey.id,
                    "order_reference": survey.order.order_reference,
                    "status": survey.status,
                    "started_at": (
                        survey.started_at.isoformat() if survey.started_at else None
                    ),
                },
                "checklist": checklist_data,
                "final_assessment": {
                    "installation_feasible": survey.installation_feasible,
                    "recommended_mounting": survey.recommended_mounting,
                    "overall_assessment": survey.overall_assessment,
                    "requires_additional_equipment": survey.requires_additional_equipment,
                    "cost_justification": survey.cost_justification,
                    "estimated_additional_cost": survey.estimated_additional_cost,
                },
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def save_survey_response(request):
    """
    Save survey checklist responses
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            survey_id = data.get("survey_id")
            responses = data.get("responses", [])
            final_assessment = data.get("final_assessment", {})
            additional_costs_data = data.get("additional_costs", {})

            if not survey_id:
                return JsonResponse(
                    {"success": False, "message": "Survey ID is required."}, status=400
                )

            survey = get_object_or_404(SiteSurvey, id=survey_id)

            # Check if user is the assigned technician or admin
            if survey.technician != request.user and not request.user.is_superuser:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "You are not authorized to modify this survey.",
                    },
                    status=403,
                )

            # Save final assessment fields if provided
            if final_assessment:
                update_fields = {}

                if (
                    "installation_feasible" in final_assessment
                    and final_assessment["installation_feasible"]
                ):
                    update_fields["installation_feasible"] = (
                        final_assessment["installation_feasible"] == "true"
                    )

                if (
                    "recommended_mounting" in final_assessment
                    and final_assessment["recommended_mounting"]
                ):
                    update_fields["recommended_mounting"] = final_assessment[
                        "recommended_mounting"
                    ]

                if (
                    "overall_assessment" in final_assessment
                    and final_assessment["overall_assessment"]
                ):
                    update_fields["overall_assessment"] = final_assessment[
                        "overall_assessment"
                    ]

                if (
                    "requires_additional_equipment" in final_assessment
                    and final_assessment["requires_additional_equipment"]
                ):
                    update_fields["requires_additional_equipment"] = (
                        final_assessment["requires_additional_equipment"] == "true"
                    )

                if (
                    "cost_justification" in final_assessment
                    and final_assessment["cost_justification"]
                ):
                    update_fields["cost_justification"] = final_assessment[
                        "cost_justification"
                    ]

                # Update survey fields
                for field, value in update_fields.items():
                    setattr(survey, field, value)

                if update_fields:
                    survey.save()

            # Synchronize additional costs if provided
            if additional_costs_data and "costs" in additional_costs_data:
                # Get current cost IDs from frontend
                frontend_cost_ids = {
                    cost.get("id")
                    for cost in additional_costs_data["costs"]
                    if cost.get("id")
                }

                # Get current cost IDs from database
                db_cost_ids = set(survey.additional_costs.values_list("id", flat=True))

                # Remove costs that are in database but not in frontend (deleted locally)
                costs_to_remove = db_cost_ids - frontend_cost_ids
                if costs_to_remove:
                    survey.additional_costs.filter(id__in=costs_to_remove).delete()

                # Update estimated additional cost
                if "estimated_total" in additional_costs_data:
                    survey.estimated_additional_cost = Decimal(
                        str(additional_costs_data["estimated_total"])
                    )
                    survey.save()

            # Save each response
            for response_data in responses:
                checklist_item_id = response_data.get("checklist_item_id")
                response_value = response_data.get("response_value")
                notes = response_data.get("notes", "")

                if not checklist_item_id:
                    continue

                checklist_item = get_object_or_404(
                    SiteSurveyChecklist, id=checklist_item_id
                )

                # Determine which field to update based on question type
                defaults = {"additional_notes": notes}

                if checklist_item.question_type == "rating":
                    defaults["response_rating"] = (
                        int(response_value) if response_value else None
                    )
                    defaults["response_text"] = ""
                    defaults["response_choice"] = ""
                elif checklist_item.question_type in ["yes_no", "multiple_choice"]:
                    defaults["response_choice"] = response_value
                    defaults["response_rating"] = None
                    defaults["response_text"] = ""
                else:  # text type
                    defaults["response_text"] = response_value
                    defaults["response_rating"] = None
                    defaults["response_choice"] = ""

                # Update or create response
                response_obj, created = SiteSurveyResponse.objects.update_or_create(
                    survey=survey, checklist_item=checklist_item, defaults=defaults
                )

            return JsonResponse(
                {"success": True, "message": "Survey responses saved successfully."}
            )

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    return JsonResponse(
        {"success": False, "message": "Invalid request method."}, status=405
    )


@login_required
def submit_survey(request):
    """
    Submit completed survey for review
    """
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            survey_id = data.get("survey_id")
            overall_assessment = data.get("overall_assessment", "")
            installation_feasible = data.get("installation_feasible")
            recommended_mounting = data.get("recommended_mounting", "")

            # Additional costs data
            requires_additional_equipment = data.get(
                "requires_additional_equipment", False
            )
            estimated_additional_cost = data.get("estimated_additional_cost", 0)
            cost_justification = data.get("cost_justification", "")

            if not survey_id:
                return JsonResponse(
                    {"success": False, "message": "Survey ID is required."}, status=400
                )

            survey = get_object_or_404(SiteSurvey, id=survey_id)

            # Check if user is the assigned technician or admin
            if survey.technician != request.user and not request.user.is_superuser:
                return JsonResponse(
                    {
                        "success": False,
                        "message": "You are not authorized to submit this survey.",
                    },
                    status=403,
                )

            # Validate required fields
            errors = {}
            if not overall_assessment or overall_assessment.strip() == "":
                errors["overall_assessment"] = (
                    "Veuillez fournir une évaluation globale."
                )

            if errors:
                return JsonResponse({"success": False, "errors": errors}, status=400)

            # Update survey with final details
            survey.status = "completed"
            survey.completed_at = timezone.now()
            survey.overall_assessment = overall_assessment
            survey.installation_feasible = installation_feasible
            survey.recommended_mounting = recommended_mounting
            survey.submitted_for_approval_at = timezone.now()

            # Update additional costs information
            survey.requires_additional_equipment = requires_additional_equipment
            survey.estimated_additional_cost = estimated_additional_cost
            survey.cost_justification = cost_justification

            survey.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": f"Survey for order {survey.order.order_reference} has been submitted for review.",
                }
            )

        except Exception as e:
            return JsonResponse({"success": False, "message": str(e)}, status=500)

    return JsonResponse(
        {"success": False, "message": "Invalid request method."}, status=405
    )


# Additional Billing Management Views


@login_required
def get_available_extra_charges(request):
    """Get all available predefined extra charges for dropdown"""
    try:
        from .models import ExtraCharge

        # Get only active extra charges, ordered by category and display order
        extra_charges = ExtraCharge.objects.filter(is_active=True).order_by(
            "cost_type", "display_order", "item_name"
        )

        charges_data = []
        for charge in extra_charges:
            charges_data.append(
                {
                    "id": charge.id,
                    "cost_type": charge.cost_type,
                    "cost_type_display": charge.get_cost_type_display(),
                    "item_name": charge.item_name,
                    "description": charge.description,
                    "brand": charge.brand,
                    "model": charge.model,
                    "unit_price": float(charge.unit_price),
                    "specifications": charge.specifications,
                    "display_name": f"{charge.item_name}"
                    + (f" - {charge.brand}" if charge.brand else "")
                    + (f" {charge.model}" if charge.model else ""),
                }
            )

        return JsonResponse({"success": True, "extra_charges": charges_data})

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
@require_POST
def add_additional_cost(request):
    """Add additional cost item to a survey using predefined ExtraCharge"""
    try:
        data = json.loads(request.body)
        survey_id = data.get("survey_id")
        extra_charge_id = data.get("extra_charge_id")

        # Get survey and verify permission
        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Only technician assigned to survey or admin can add costs
        if not (request.user == survey.technician or request.user.is_staff):
            return JsonResponse(
                {"success": False, "message": "Not authorized"}, status=403
            )

        # Import the models here to avoid circular import
        from .models import ExtraCharge, SurveyAdditionalCost

        # Get the predefined extra charge
        extra_charge = get_object_or_404(
            ExtraCharge, id=extra_charge_id, is_active=True
        )

        # Create additional cost using predefined charge
        additional_cost = SurveyAdditionalCost.objects.create(
            survey=survey,
            extra_charge=extra_charge,
            quantity=int(data.get("quantity", 1)),
            is_required=data.get("is_required", True),
            justification=data.get("justification", ""),
        )

        # Update survey's estimated additional cost
        total_additional = sum(
            cost.total_price for cost in survey.additional_costs.all()
        )
        survey.estimated_additional_cost = total_additional
        survey.requires_additional_equipment = True
        survey.save()

        return JsonResponse(
            {
                "success": True,
                "cost_id": additional_cost.id,
                "total_price": float(additional_cost.total_price),
                "survey_total": float(total_additional),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def get_additional_costs(request, survey_id):
    """Get all additional costs for a survey"""
    try:
        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Import the model here to avoid circular import

        costs = survey.additional_costs.all()
        costs_data = []

        for cost in costs:
            costs_data.append(
                {
                    "id": cost.id,
                    "cost_type": cost.cost_type,
                    "cost_type_display": cost.get_cost_type_display(),
                    "item_name": cost.item_name,
                    "description": cost.description,
                    "quantity": cost.quantity,
                    "unit_price": float(cost.unit_price),
                    "total_price": float(cost.total_price),
                    "is_required": cost.is_required,
                    "justification": cost.justification,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "costs": costs_data,
                "total_additional_cost": float(survey.estimated_additional_cost or 0),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
@require_POST
def generate_additional_billing(request):
    """Generate additional billing after survey completion"""
    try:
        data = json.loads(request.body)
        survey_id = data.get("survey_id")

        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Only admin or manager can generate billing
        if not (request.user.is_staff or request.user.has_role("manager")):
            return JsonResponse(
                {"success": False, "message": "Not authorized"}, status=403
            )

        # Check if survey is completed and has additional costs
        if survey.status != "completed":
            return JsonResponse(
                {"success": False, "message": "Survey not completed"}, status=400
            )

        if not survey.requires_additional_equipment:
            return JsonResponse(
                {"success": False, "message": "No additional costs identified"},
                status=400,
            )

        # Import the model here to avoid circular import
        from .models import AdditionalBilling

        # Check if billing already exists
        if hasattr(survey, "additional_billing"):
            return JsonResponse(
                {"success": False, "message": "Billing already exists"}, status=400
            )

        # Create additional billing
        billing = AdditionalBilling.objects.create(
            survey=survey,
            order=survey.order,
            customer=survey.order.user,
            expires_at=timezone.now() + timezone.timedelta(days=7),  # 7 days to respond
        )

        # Send notification to customer about additional billing
        try:
            from .notifications import send_billing_notification

            notification_sent = send_billing_notification(billing)
            if not notification_sent:
                print(
                    f"Warning: Failed to send billing notification for billing {billing.id}"
                )
        except Exception as e:
            print(f"Error sending billing notification: {str(e)}")

        return JsonResponse(
            {
                "success": True,
                "billing_reference": billing.billing_reference,
                "total_amount": float(billing.total_amount),
                "expires_at": billing.expires_at.isoformat(),
            }
        )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
@require_http_methods(["GET", "POST"])
def customer_billing_approval(request, billing_id):
    """Customer interface to approve/reject additional billing"""
    logger = logging.getLogger(__name__)

    try:
        # Import the model here to avoid circular import
        from .models import AdditionalBilling

        billing = get_object_or_404(AdditionalBilling, id=billing_id)

        # Get user and customer IDs safely
        user_id = getattr(request.user, "id", getattr(request.user, "pk", None))
        user_username = getattr(request.user, "username", str(request.user))
        customer_id = (
            getattr(billing.customer, "id", getattr(billing.customer, "pk", None))
            if billing.customer
            else None
        )
        customer_username = (
            getattr(billing.customer, "username", str(billing.customer))
            if billing.customer
            else "None"
        )

        logger.info(
            f"Billing approval access - Billing: {billing_id}, User: {user_id} ({user_username}), Customer: {customer_id} ({customer_username})"
        )

        # Check if billing has a customer assigned
        if not billing.customer:
            logger.error(f"Billing {billing_id} has no customer assigned")
            return JsonResponse(
                {"success": False, "message": "This billing has no customer assigned"},
                status=400,
            )

        # Only the customer can approve their billing (or staff for testing)
        if user_id != customer_id and not request.user.is_staff:
            logger.warning(
                f"Unauthorized access attempt - User: {user_id} ({user_username}), Customer: {customer_id} ({customer_username})"
            )
            return JsonResponse(
                {
                    "success": False,
                    "message": f"Not authorized. You are {user_username}, but this billing belongs to {customer_username}",
                },
                status=403,
            )

        if request.method == "GET":
            # Check if this is an API request or template request
            if request.headers.get(
                "Content-Type"
            ) == "application/json" or request.GET.get("api"):
                # Return billing details for customer review
                try:
                    cost_breakdown = []
                    for cost in billing.get_cost_breakdown():
                        cost_breakdown.append(
                            {
                                "item_name": (
                                    cost.extra_charge.item_name
                                    if cost.extra_charge
                                    else "Unknown Item"
                                ),
                                "description": (
                                    cost.extra_charge.description
                                    if cost.extra_charge
                                    else ""
                                ),
                                "quantity": cost.quantity,
                                "unit_price": float(cost.unit_price),
                                "total_price": float(cost.total_price),
                                "justification": cost.justification,
                            }
                        )

                    tax_breakdown = billing.get_tax_breakdown()
                    logger.info(
                        f"Tax breakdown for billing {billing_id}: {tax_breakdown}"
                    )

                    return JsonResponse(
                        {
                            "success": True,
                            "billing": {
                                "billing_reference": billing.billing_reference,
                                "subtotal": float(billing.subtotal),
                                "tax_amount": float(billing.tax_amount),
                                "tax_breakdown": tax_breakdown,
                                "total_amount": float(billing.total_amount),
                                "status": billing.status,
                                "expires_at": (
                                    billing.expires_at.isoformat()
                                    if billing.expires_at
                                    else None
                                ),
                                "cost_breakdown": cost_breakdown,
                                "can_be_approved": billing.can_be_approved(),
                                "is_expired": billing.is_expired(),
                            },
                        }
                    )
                except Exception as e:
                    logger.exception(
                        f"Error getting billing details for {billing_id}: {str(e)}"
                    )
                    return JsonResponse(
                        {
                            "success": False,
                            "message": f"Error loading billing details: {str(e)}",
                        },
                        status=500,
                    )
            else:
                # Render template
                return render(
                    request,
                    "site_survey/customer_billing_approval.html",
                    {"billing_id": billing_id, "billing": billing},
                )

        elif request.method == "POST":
            # Process customer approval/rejection
            try:
                data = json.loads(request.body)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON in billing approval: {e}")
                return JsonResponse(
                    {"success": False, "message": "Invalid request format"}, status=400
                )

            action = data.get("action")  # 'approve' or 'reject'
            customer_notes = data.get("customer_notes", "")

            logger.info(
                f"Billing approval request - ID: {billing_id}, Action: {action}, User: {request.user}"
            )

            if not billing.can_be_approved():
                logger.warning(
                    f"Billing {billing_id} cannot be approved - Status: {billing.status}, Expired: {billing.is_expired()}"
                )
                return JsonResponse(
                    {"success": False, "message": "Billing cannot be approved"},
                    status=400,
                )

            if action == "approve":
                billing.status = "approved"
                billing.customer_notes = customer_notes
                billing.save()
                billing.ensure_invoice_entry()
                logger.info(f"Billing {billing_id} approved by {request.user}")

                # Redirect to payment process
                return JsonResponse(
                    {
                        "success": True,
                        "message": "Additional billing approved",
                        "redirect_to_payment": True,
                        "payment_url": f"/site-survey/billing/payment/{billing.id}/",
                    }
                )

            elif action == "reject":
                billing.status = "rejected"
                billing.customer_notes = customer_notes or "Rejected by customer"
                billing.save()
                logger.info(f"Billing {billing_id} rejected by {request.user}")

                return JsonResponse(
                    {"success": True, "message": "Additional billing rejected"}
                )

            else:
                logger.warning(f"Invalid action '{action}' for billing {billing_id}")
                return JsonResponse(
                    {"success": False, "message": "Invalid action"}, status=400
                )

    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.exception(
            f"Error in billing approval for billing_id {billing_id}: {str(e)}"
        )
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def billing_management_dashboard(request):
    """Dashboard for managing additional billings (admin view)"""
    if not (request.user.is_staff or request.user.has_role("manager")):
        return JsonResponse({"success": False, "message": "Not authorized"}, status=403)

    # Import the model here to avoid circular import
    from .models import AdditionalBilling

    billings = AdditionalBilling.objects.select_related(
        "survey", "order", "customer"
    ).all()

    # Filter by status if specified
    status_filter = request.GET.get("status")
    if status_filter:
        billings = billings.filter(status=status_filter)

    billings_data = []
    for billing in billings:
        billings_data.append(
            {
                "id": billing.id,
                "billing_reference": billing.billing_reference,
                "order_reference": billing.order.order_reference,
                "customer_name": billing.customer.full_name,
                "total_amount": float(billing.total_amount),
                "status": billing.status,
                "status_display": billing.get_status_display(),
                "created_at": billing.created_at.isoformat(),
                "expires_at": (
                    billing.expires_at.isoformat() if billing.expires_at else None
                ),
                "is_expired": billing.is_expired(),
            }
        )

    return JsonResponse({"success": True, "billings": billings_data})


@login_required
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def technicians_list(request):
    """API endpoint to get list of technicians with their rejection rates"""
    from django.db.models import Case, Count, FloatField, Q, When

    from main.models import User

    try:
        # Get technicians with their rejection statistics
        technicians = (
            User.objects.filter(roles__contains="technician")
            .annotate(
                total_surveys=Count("site_surveys"),
                rejected_surveys=Count(
                    "site_surveys", filter=Q(site_surveys__status="rejected")
                ),
                rejection_rate=Case(
                    When(total_surveys=0, then=0.0),
                    default=100.0
                    * Count("site_surveys", filter=Q(site_surveys__status="rejected"))
                    / Count("site_surveys"),
                    output_field=FloatField(),
                ),
            )
            .order_by("rejection_rate", "full_name")
        )

        technicians_data = []
        for tech in technicians:
            technicians_data.append(
                {
                    "id": tech.id_user,
                    "username": tech.username,
                    "full_name": tech.full_name
                    or f"{tech.first_name} {tech.last_name}".strip(),
                    "email": tech.email,
                    "total_surveys": tech.total_surveys,
                    "rejected_surveys": tech.rejected_surveys,
                    "rejection_rate": (
                        round(tech.rejection_rate, 1) if tech.rejection_rate else 0.0
                    ),
                }
            )

        return JsonResponse({"success": True, "technicians": technicians_data})

    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Error loading technicians: {str(e)}"},
            status=500,
        )


@login_required
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def reassign_survey(request):
    """Reassign a rejected survey to another technician for counter-expertise"""
    if request.method != "POST":
        return JsonResponse(
            {"success": False, "message": "POST method required"}, status=405
        )

    try:
        data = json.loads(request.body)
        survey_id = data.get("survey_id")
        new_technician_id = data.get("new_technician_id")
        reason = data.get("reason", "").strip()

        if not all([survey_id, new_technician_id, reason]):
            return JsonResponse(
                {
                    "success": False,
                    "message": "Survey ID, new technician, and reason are required",
                },
                status=400,
            )

        # Get the survey
        survey = get_object_or_404(SiteSurvey, id=survey_id)

        # Verify survey is rejected
        if survey.status != "rejected":
            return JsonResponse(
                {
                    "success": False,
                    "message": "Only rejected surveys can be reassigned",
                },
                status=400,
            )

        # Get the new technician
        from main.models import User

        new_technician = get_object_or_404(User, id_user=new_technician_id)

        if not new_technician.has_role("technician"):
            return JsonResponse(
                {"success": False, "message": "Selected user is not a technician"},
                status=400,
            )

        # Check if it's the same technician
        if survey.technician and survey.technician.id_user == new_technician_id:
            return JsonResponse(
                {"success": False, "message": "Cannot reassign to the same technician"},
                status=400,
            )

        # Store previous technician for notifications
        previous_technician = survey.technician

        # Create reassignment history entry
        reassignment_data = {
            "previous_technician": (
                previous_technician.full_name if previous_technician else "Unknown"
            ),
            "previous_technician_id": (
                previous_technician.id_user if previous_technician else None
            ),
            "new_technician": new_technician.full_name or new_technician.username,
            "new_technician_id": new_technician.id_user,
            "reason": reason,
            "reassigned_by": request.user.full_name or request.user.username,
            "reassigned_at": timezone.now().isoformat(),
        }

        # Update the survey
        survey.technician = new_technician
        survey.status = "scheduled"  # Reset to scheduled for re-evaluation
        survey.rejection_reason = f"REASSIGNED FOR COUNTER-EXPERTISE: {reason}\n\nOriginal rejection: {survey.rejection_reason or 'No reason provided'}"

        # Add reassignment history to a notes field or create a separate tracking
        if hasattr(survey, "admin_notes") and survey.admin_notes:
            survey.admin_notes += f"\n\nREASSIGNMENT ({timezone.now().strftime('%Y-%m-%d %H:%M')}): {reason}"
        else:
            # If no admin_notes field, add to rejection_reason
            survey.rejection_reason += (
                f"\n\nREASSIGNMENT HISTORY: {json.dumps(reassignment_data)}"
            )

        # Set new scheduled date to tomorrow
        survey.scheduled_date = timezone.now().date() + timezone.timedelta(days=1)
        survey.save()

        # Send notifications
        try:
            from .notifications import send_reassignment_notifications

            send_reassignment_notifications(
                survey, previous_technician, new_technician, reason, request.user
            )
        except ImportError:
            # If notifications not available, log it
            print(f"Reassignment notifications not sent for survey {survey_id}")

        return JsonResponse(
            {
                "success": True,
                "message": f"Survey reassigned to {new_technician.full_name or new_technician.username} for counter-expertise",
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "message": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "message": f"Error reassigning survey: {str(e)}"},
            status=500,
        )


def _normalize_cd_phone(raw: str) -> str:
    """
    Normalize DR Congo numbers to the format 243XXXXXXXXX (12 digits).
    Accepts:
      - 9-digit local numbers: XXXXXXXXX      -> 243XXXXXXXXX
      - 0-prefixed local:      0XXXXXXXXX     -> 243XXXXXXXXX
      - Already normalized:    243XXXXXXXXX   -> 243XXXXXXXXX
      - +243XXXXXXXXX          -> 243XXXXXXXXX
    Returns:
      - '243XXXXXXXXX' if recognized; otherwise returns the digits-only string (may be empty).
    """
    digits = re.sub(r"\D", "", (raw or "").strip())

    # +243XXXXXXXXX -> 243XXXXXXXXX
    if digits.startswith("243") and len(digits) == 12:
        return digits

    # 0XXXXXXXXX -> 243XXXXXXXXX
    if len(digits) == 10 and digits.startswith("0"):
        return "243" + digits[1:]

    # 9 local digits -> 243XXXXXXXXX
    if len(digits) == 9:
        return "243" + digits

    # Fallback: return whatever digits we have (caller/gateway can decide)
    return digits


def _map_flexpay_error_to_user_message(msg: str) -> str:
    """Graceful fallback if you don’t have a central mapper."""
    base = (msg or "").lower()
    if "solde" in base or "insufficient" in base:
        return _("Insufficient balance. Please ensure your wallet has enough funds.")
    if "invalid" in base or "format" in base:
        return _("Invalid input. Please double-check the information and try again.")
    if "phone" in base:
        return _("The phone number appears invalid. Use 0XXXXXXXXX or 243XXXXXXXXX.")
    if "timeout" in base:
        return _("The payment service timed out. Please try again.")
    return _("Payment could not be initiated at the moment. Please try again later.")


@login_required(login_url="login_page")
@require_http_methods(["GET", "POST"])
def billing_payment(request, billing_id):
    """
    Customer payment interface for AdditionalBilling (mobile money + card).
    - Authorizes the billing's customer
    - For GET: renders methods
    - For POST: calls FlexPay and records a PaymentAttempt when FlexPay returns success (code == "0")
    """
    from main.models import PaymentMethod
    from nexus_backend.settings import (
        FLEXPAY_API_KEY,
        FLEXPAY_CARD_URL,
        FLEXPAY_MERCHANT_ID,
        FLEXPAY_MOBILE_URL,
    )

    from .models import AdditionalBilling  # adjust if nested differently

    try:
        billing = get_object_or_404(AdditionalBilling, id=billing_id)

        # Only the owner can access
        if request.user != billing.customer:
            return JsonResponse(
                {"success": False, "message": _("Not authorized")}, status=403
            )

        # Must be approved to pay
        if billing.status != "approved":
            return JsonResponse(
                {"success": False, "message": _("Billing not approved for payment")},
                status=400,
            )

        if request.method == "GET":
            methods = PaymentMethod.objects.filter(enabled=True)
            return render(
                request,
                "site_survey/billing_payment.html",
                {"billing": billing, "payment_methods": methods},
            )

        # ----- POST: initiate payment -----
        try:
            data = json.loads(request.body or "{}")
        except json.JSONDecodeError:
            return JsonResponse(
                {"success": False, "message": _("Invalid JSON.")}, status=400
            )

        payment_method = (data.get("payment_method") or "").strip()
        payment_reference = (data.get("payment_reference") or "").strip()
        phone_number = (data.get("phone_number") or "").strip()
        email = (data.get("email") or "").strip()

        normalized_phone = ""

        # Validate enabled payment method
        try:
            _selected_pm = PaymentMethod.objects.get(name=payment_method, enabled=True)
        except PaymentMethod.DoesNotExist:
            return JsonResponse(
                {"success": False, "message": _("Invalid payment method")}, status=400
            )

        method_key = payment_method.lower()

        # Field validation per method
        if "mobile" in method_key or "momo" in method_key:
            normalized_phone = _normalize_cd_phone(phone_number)
            if not normalized_phone:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _(
                            "Invalid phone number. Use 0XXXXXXXXX or 243XXXXXXXXX."
                        ),
                    },
                    status=400,
                )
        elif "card" in method_key or "credit" in method_key:
            if not email:
                return JsonResponse(
                    {
                        "success": False,
                        "message": _("Email address is required for card payments"),
                    },
                    status=400,
                )
        else:
            if not payment_reference:
                return JsonResponse(
                    {"success": False, "message": _("Payment reference is required")},
                    status=400,
                )

        # Common values
        amount_str = str(billing.total_amount or "0.00")
        reference = billing.billing_reference  # what FlexPay will see
        payment_for = "additional_billing"  # classify attempts

        # -------------------- MOBILE MONEY VIA FLEXPAY --------------------
        if "mobile" in method_key or "momo" in method_key:
            payload = {
                "merchant": FLEXPAY_MERCHANT_ID,
                "type": "1",  # Mobile Money
                "phone": normalized_phone,
                "reference": reference,
                "amount": amount_str,
                "currency": "USD",
                "callbackUrl": request.build_absolute_uri(
                    reverse("flexpay_callback_mobile")
                ),
            }
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {FLEXPAY_API_KEY}",
            }
            flexpay_url = FLEXPAY_MOBILE_URL

            try:
                resp = requests.post(
                    flexpay_url, json=payload, headers=headers, timeout=30
                )
            except requests.RequestException:
                logger.exception(
                    "FlexPay mobile request error for billing %s", billing.id
                )
                return JsonResponse(
                    {
                        "success": False,
                        "message": _(
                            "Payment service is temporarily unavailable. Please try again later."
                        ),
                    },
                    status=502,
                )

            # Parse response safely
            try:
                fp = resp.json()
            except ValueError:
                fp = {}

            # FlexPay contract: consider HTTP 200, then check code == "0"
            if resp.status_code == 200:
                code = str(fp.get("code", "")).strip()
                order_number = fp.get("orderNumber") or fp.get("order_number")
                trans_id = fp.get("transid")

                if code == "0" and order_number:
                    # Record PaymentAttempt (pending)
                    try:
                        with transaction.atomic():
                            attempt, created = PaymentAttempt.objects.get_or_create(
                                order=None,  # No Order here; tie by reference
                                order_number=str(order_number),
                                defaults={
                                    "code": code,
                                    "reference": reference,
                                    "amount": billing.total_amount or None,
                                    "amount_customer": billing.total_amount or None,
                                    "currency": "USD",
                                    "status": "pending",
                                    "payment_type": "mobile",
                                    "payment_for": payment_for,
                                    "transaction_time": timezone.now(),
                                    "raw_payload": {
                                        "request": payload,
                                        "response": fp,
                                        "billing_id": billing.id,
                                    },
                                    # If you added a FK to AdditionalBilling on PaymentAttempt:
                                    # "billing": billing,
                                },
                            )
                            if not created and attempt.status != "completed":
                                attempt.code = code
                                attempt.reference = reference
                                attempt.amount = billing.total_amount or attempt.amount
                                attempt.amount_customer = (
                                    billing.total_amount or attempt.amount_customer
                                )
                                attempt.currency = "USD"
                                attempt.status = "pending"
                                attempt.payment_type = "mobile"
                                attempt.payment_for = payment_for
                                attempt.transaction_time = timezone.now()
                                attempt.raw_payload = {
                                    "request": payload,
                                    "response": fp,
                                    "billing_id": billing.id,
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

                            # Put billing into processing/awaiting confirmation
                            if billing.status != "processing":
                                billing.status = "processing"
                                billing.payment_method = payment_method
                                # store a useful ref; prefer FlexPay transid or orderNumber
                                billing.payment_reference = trans_id or order_number
                                billing.save(
                                    update_fields=[
                                        "status",
                                        "payment_method",
                                        "payment_reference",
                                    ]
                                )
                    except IntegrityError:
                        pass

                    return JsonResponse(
                        {
                            "success": True,
                            "message": fp.get("message")
                            or _(
                                "Mobile money payment initiated. Please check your phone to complete the payment."
                            ),
                            "transaction_id": trans_id,
                            "order_number": order_number,
                            "code": code,
                        },
                        status=200,
                    )

                # Non-success code from FlexPay
                user_msg = _map_flexpay_error_to_user_message(fp.get("message", ""))
                logger.warning(
                    "FlexPay mobile non-success for billing %s: %s", billing.id, fp
                )
                return JsonResponse({"success": False, "message": user_msg}, status=400)

            # HTTP error from FlexPay
            logger.error(
                "FlexPay mobile HTTP %s for billing %s: %s",
                resp.status_code,
                billing.id,
                resp.text[:500],
            )
            return JsonResponse(
                {"success": False, "message": _("Payment gateway error")}, status=502
            )

        # -------------------- CARD VIA FLEXPAY --------------------
        if "card" in method_key or "credit" in method_key:
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {FLEXPAY_API_KEY}",
            }
            card_url = FLEXPAY_CARD_URL

            # Per your working card view: include bearer inside JSON and snake_case keys
            payload = {
                "authorization": f"Bearer {FLEXPAY_API_KEY}",
                "merchant": FLEXPAY_MERCHANT_ID,
                "reference": reference,
                "amount": amount_str,
                "currency": "USD",
                "description": payment_for,
                "callback_url": "https://flexpaie.com",
                "approve_url": "https://flexpaie.com",
                "cancel_url": "https://flexpaie.com",
                "decline_url": "https://flexpaie.com",
                # "email": email,  # uncomment if FlexPay supports email for card init
            }

            try:
                resp = requests.post(
                    card_url, json=payload, headers=headers, timeout=30
                )
            except requests.RequestException:
                logger.exception(
                    "FlexPay card request error for billing %s", billing.id
                )
                return JsonResponse(
                    {
                        "success": False,
                        "message": _(
                            "Payment service is temporarily unavailable. Please try again later."
                        ),
                    },
                    status=502,
                )

            try:
                fp = resp.json()
            except ValueError:
                fp = {}

            if not (200 <= resp.status_code < 300):
                logger.error(
                    "FlexPay (card) HTTP %s for billing %s: %s",
                    resp.status_code,
                    billing.id,
                    resp.text[:500],
                )
                return JsonResponse(
                    {"success": False, "message": _("Payment gateway error")},
                    status=502,
                )

            code = str(fp.get("code", "")).strip()
            order_number = fp.get("orderNumber") or fp.get("order_number")
            redirect_url = fp.get("url")

            if code == "0" and order_number:
                # Record a PENDING attempt (awaiting 3DS/card completion)
                try:
                    with transaction.atomic():
                        attempt, created = PaymentAttempt.objects.get_or_create(
                            order=None,
                            order_number=str(order_number),
                            defaults={
                                "code": code,
                                "reference": reference,
                                "amount": billing.total_amount or None,
                                "amount_customer": billing.total_amount or None,
                                "currency": "USD",
                                "status": "pending",
                                "payment_type": "card",
                                "payment_for": payment_for,
                                "transaction_time": timezone.now(),
                                "raw_payload": {
                                    "request": {**payload, "email": email},
                                    "response": fp,
                                    "billing_id": billing.id,
                                },
                                # If you added FK:
                                # "billing": billing,
                            },
                        )
                        if not created and attempt.status != "completed":
                            attempt.code = code
                            attempt.reference = reference
                            attempt.amount = billing.total_amount or attempt.amount
                            attempt.amount_customer = (
                                billing.total_amount or attempt.amount_customer
                            )
                            attempt.currency = "USD"
                            attempt.status = "pending"
                            attempt.payment_type = "card"
                            attempt.payment_for = payment_for
                            attempt.transaction_time = timezone.now()
                            attempt.raw_payload = {
                                "request": {**payload, "email": email},
                                "response": fp,
                                "billing_id": billing.id,
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

                        # Move billing to awaiting confirmation while user completes card flow
                        if billing.status != "processing":
                            billing.status = "processing"
                            billing.payment_method = payment_method
                            billing.payment_reference = order_number
                            billing.save(
                                update_fields=[
                                    "status",
                                    "payment_method",
                                    "payment_reference",
                                ]
                            )
                except IntegrityError:
                    pass

                # Return the redirect URL (frontend will open in a new window)
                if redirect_url:
                    print("REDIRECT OK", redirect_url)
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
                        "message": _(
                            "Payment initiated but no redirect URL was returned."
                        ),
                        "order_number": order_number,
                        "code": code,
                    },
                    status=200,
                )

            # Non-success from FlexPay
            logger.warning(
                "FlexPay (card) non-success for billing %s: %s", billing.id, fp
            )
            return JsonResponse(
                {
                    "success": False,
                    "message": fp.get("message", _("Payment initialization failed")),
                },
                status=400,
            )

        # # -------------------- OTHER / MANUAL METHODS --------------------
        # # If you truly want to mark paid here, keep; otherwise set 'processing' and wait for proof/upload.
        # billing.status = "paid"
        # billing.payment_method = payment_method
        # billing.payment_reference = payment_reference
        # billing.save(update_fields=["status", "payment_method", "payment_reference"])

        # Optional: send confirmation
        try:
            from .notifications import send_payment_confirmation

            send_payment_confirmation(billing)
        except Exception as e:
            logger.warning(
                "Payment confirmation notification failed for billing %s: %s",
                billing.id,
                e,
            )

        return JsonResponse(
            {
                "success": True,
                "message": _("Payment processed successfully"),
                "installation_created": True,
            },
            status=200,
        )

    except Exception as e:
        logger.exception("billing_payment fatal error for billing %s", billing_id)
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required
def simulate_payment_processing(request, billing_id):
    """Simulate payment processing for testing purposes"""
    try:
        from .models import AdditionalBilling

        billing = get_object_or_404(AdditionalBilling, id=billing_id)

        # Only the customer can process their payment
        if request.user != billing.customer:
            return JsonResponse(
                {"success": False, "message": "Not authorized"}, status=403
            )

        if billing.status != "approved":
            return JsonResponse(
                {"success": False, "message": "Billing not approved"}, status=400
            )

        # Simulate payment processing
        import random
        import time

        # Simulate processing delay
        time.sleep(1)

        # 95% success rate for simulation
        if random.random() < 0.95:
            billing.status = "paid"
            billing.payment_method = "credit_card"
            billing.payment_reference = f"SIM{random.randint(100000, 999999)}"
            billing.save()

            return JsonResponse(
                {
                    "success": True,
                    "message": "Payment processed successfully",
                    "payment_reference": billing.payment_reference,
                }
            )
        else:
            return JsonResponse(
                {"success": False, "message": "Payment failed. Please try again."}
            )

    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)
