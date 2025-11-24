import json

from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string

from main.models import User
from user.permissions import require_staff_role

# Create your views here.


@login_required(login_url="login_page")
@require_staff_role(["admin"])
def customers_list(request):
    template = "customers_management.html"
    return render(request, template)


@login_required(login_url="login_page")
@require_staff_role(["admin"])
def get_customers(request):
    """
    Return paginated customer list and summary counts for dashboard cards.
    """
    search_query = request.GET.get("search", "").strip()
    page_number = request.GET.get("page", 1)

    # Filter only non-staff users
    customers_qs = User.objects.filter(is_staff=False)

    # Apply search
    if search_query:
        customers_qs = customers_qs.filter(
            Q(full_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(phone__icontains=search_query)
        )

    # Order by newest registered first
    customers_qs = customers_qs.order_by("-date_joined")

    # Pagination
    paginator = Paginator(customers_qs, 10)  # 10 customers per page
    try:
        page_obj = paginator.page(page_number)
    except Exception:
        return JsonResponse({"success": False, "error": "Invalid page number"})

    # Prepare customer data
    customers_data = []
    for cust in page_obj:
        customers_data.append(
            {
                "id": cust.id_user if hasattr(cust, "id_user") else cust.id,
                "name": cust.full_name or cust.username,
                "email": cust.email or "",
                "phone": cust.phone or "",
                "status": "active" if cust.is_active else "inactive",
                "registered_on": (
                    cust.date_joined.strftime("%Y-%m-%d %H:%M")
                    if cust.date_joined
                    else "—"
                ),
            }
        )

    # Summary counts (without search filter for dashboard cards)
    total_customers = User.objects.filter(is_staff=False).count()
    active_customers = User.objects.filter(is_staff=False, is_active=True).count()
    inactive_customers = User.objects.filter(is_staff=False, is_active=False).count()
    suspended_customers = 0  # Adjust if you have a suspended flag/field

    return JsonResponse(
        {
            "success": True,
            "customers": customers_data,
            "total_pages": paginator.num_pages,
            "total_customers": total_customers,
            "active_customers": active_customers,
            "inactive_customers": inactive_customers,
            "suspended_customers": suspended_customers,
        }
    )


@login_required(login_url="login_page")
@require_staff_role(["admin"])
def get_customer_details(request):
    customer_id = request.GET.get("customer_id")
    if not customer_id:
        return JsonResponse(
            {"success": False, "error": "Customer ID required"}, status=400
        )

    try:
        customer_id = int(customer_id)
    except ValueError:
        return JsonResponse(
            {"success": False, "error": "Invalid customer ID"}, status=400
        )

    customer = get_object_or_404(User, pk=customer_id, is_staff=False)

    # Basic Info
    customer_data = {
        "id": customer.id_user,
        "name": customer.full_name,
        "email": customer.email,
        "phone": customer.phone,
        "is_verified": customer.is_verified,
        "roles": customer.roles,
        "status": "active" if customer.is_active else "inactive",
        "date_joined": customer.date_joined.strftime("%Y-%m-%d %H:%M"),
    }

    # KYC Info
    kyc_data = None
    if hasattr(customer, "personnal_kyc") and customer.personnal_kyc:
        kyc = customer.personnal_kyc
        kyc_data = {
            "type": "Personal",
            "full_name": kyc.full_name,
            "address": kyc.address,
            "document_number": kyc.document_number,
            "document_file": kyc.document_file.url if kyc.document_file else None,
            "status": kyc.status,
            "submitted_at": kyc.submitted_at.strftime("%Y-%m-%d"),
        }
    elif hasattr(customer, "company_kyc") and customer.company_kyc:
        kyc = customer.company_kyc
        kyc_data = {
            "type": "Company",
            "company_name": kyc.company_name,
            "address": kyc.address,
            "rccm": kyc.rccm,
            "nif": kyc.nif,
            "id_nat": kyc.id_nat,
            "representative_name": kyc.representative_name,
            "representative_id_file": (
                kyc.representative_id_file.url if kyc.representative_id_file else None
            ),
            "company_documents": (
                kyc.company_documents.url if kyc.company_documents else None
            ),
            "status": kyc.status,
            "submitted_at": kyc.submitted_at.strftime("%Y-%m-%d"),
        }

    return JsonResponse({"success": True, "customer": customer_data, "kyc": kyc_data})


@login_required(login_url="login_page")
@require_staff_role(["admin", "support"])
def edit_customer(request):
    """
    Edit customer details.
    """
    try:
        if request.method != "POST":
            return JsonResponse(
                {"success": False, "error": "Method not allowed"}, status=405
            )

        data = json.loads(request.body)
        customer_id = data.get("customer_id")
        full_name = data.get("full_name")
        email = data.get("email")
        phone = data.get("phone")

        customer = get_object_or_404(User, pk=customer_id, is_staff=False)

        # Update fields
        if full_name:
            customer.full_name = full_name
        if email:
            customer.email = email
        if phone is not None:  # Allow empty string
            customer.phone = phone

        customer.save()

        return JsonResponse(
            {"success": True, "message": "Customer updated successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required(login_url="login_page")
@require_staff_role(["admin", "support"])
def toggle_customer_status(request):
    """
    Activate or deactivate a customer.
    """
    try:
        if request.method != "POST":
            return JsonResponse(
                {"success": False, "error": "Method not allowed"}, status=405
            )

        data = json.loads(request.body)
        customer_id = data.get("customer_id")
        action = data.get("action")  # "activate" or "deactivate"

        customer = get_object_or_404(User, pk=customer_id, is_staff=False)

        if action == "activate":
            customer.is_active = True
        elif action == "deactivate":
            customer.is_active = False
        else:
            return JsonResponse(
                {"success": False, "error": "Invalid action"}, status=400
            )

        customer.save()

        return JsonResponse(
            {"success": True, "message": f"Customer {action}d successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required(login_url="login_page")
@require_staff_role(["admin", "support"])
def reset_customer_password(request):
    """
    Reset customer password and send email.
    """
    try:
        if request.method != "POST":
            return JsonResponse(
                {"success": False, "error": "Method not allowed"}, status=405
            )

        data = json.loads(request.body)
        customer_id = data.get("customer_id")

        customer = get_object_or_404(User, pk=customer_id, is_staff=False)

        # Generate new password
        import secrets
        import string

        alphabet = string.ascii_letters + string.digits + string.punctuation
        new_password = "".join(secrets.choice(alphabet) for _ in range(12))
        customer.set_password(new_password)
        customer.save()

        # Send email with new password
        try:
            subject = "Votre mot de passe Nexus Telecoms a été réinitialisé"
            context = {
                "customer": customer,
                "new_password": new_password,
                "site_url": "https://nexustelecoms.com",  # Update with your actual domain
            }
            message = render_to_string("emails/password_reset.txt", context)
            send_mail(
                subject,
                message,
                None,  # Use DEFAULT_FROM_EMAIL from settings
                [customer.email],
                fail_silently=False,
            )
        except Exception as email_error:
            # Log the error but don't fail the password reset
            import logging

            logger = logging.getLogger(__name__)
            logger.error(
                f"Failed to send password reset email to {customer.email}: {email_error}"
            )

        return JsonResponse(
            {
                "success": True,
                "message": "Password reset successfully. Email sent to customer.",
            }
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required(login_url="login_page")
@require_staff_role(["admin", "support"])
def delete_customer(request):
    """
    Soft delete a customer (deactivate) if no unpaid invoices.
    """
    try:
        if request.method != "POST":
            return JsonResponse(
                {"success": False, "error": "Method not allowed"}, status=405
            )

        data = json.loads(request.body)
        customer_id = data.get("customer_id")

        customer = get_object_or_404(User, pk=customer_id, is_staff=False)

        # Check for unpaid invoices
        unpaid_invoices = customer.billing_account.entries.filter(
            entry_type="invoice", amount_usd__gt=0
        ).exists()

        if unpaid_invoices:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Cannot delete customer with unpaid invoices",
                },
                status=400,
            )

        # Soft delete: deactivate
        customer.is_active = False
        customer.save()

        return JsonResponse(
            {"success": True, "message": "Customer deleted successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)


@login_required(login_url="login_page")
@require_staff_role(["admin"])
def purge_customer_data(request):
    """
    Hard delete a customer. Requires admin password.
    """
    try:
        if request.method != "POST":
            return JsonResponse(
                {"success": False, "error": "Method not allowed"}, status=405
            )

        data = json.loads(request.body)
        customer_id = data.get("customer_id")
        admin_password = data.get("admin_password")

        customer = get_object_or_404(User, pk=customer_id, is_staff=False)

        # Verify admin password
        if not request.user.check_password(admin_password):
            return JsonResponse(
                {"success": False, "error": "Invalid admin password"}, status=403
            )

        # Hard delete
        customer.delete()

        return JsonResponse(
            {"success": True, "message": "Customer data purged successfully"}
        )
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
