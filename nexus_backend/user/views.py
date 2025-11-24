import json
import logging
import re
from os import environ

import phonenumbers

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from nexus_backend.settings import env

dev_mode = env.bool("DEVELOPMENT_MODE", default=True)


@csrf_exempt
@require_POST
def password_reset_request(request):
    email = request.POST.get("email", "").strip()
    if not email:
        return JsonResponse(
            {"success": False, "message": _("Please enter your email address.")},
            status=400,
        )
    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        # For security, do not reveal if email is not registered
        return JsonResponse(
            {
                "success": True,
                "message": _("If the account exists, an email has been sent."),
            }
        )

    token = default_token_generator.make_token(user)
    # Use URL-safe base64 encoding for the user's PK (Django's expected format)
    uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
    reset_url = request.build_absolute_uri(
        reverse("password_reset_confirm", kwargs={"uidb64": uidb64, "token": token})
    )
    logo_url = request.build_absolute_uri(settings.STATIC_URL + "images/logo/logo.png")
    subject = _("Password Reset")
    html_content = render_to_string(
        "email_password_reset.html",
        {
            "user": user,
            "reset_url": reset_url,
            "logo_url": logo_url,
        },
    )
    email_message = EmailMultiAlternatives(
        subject, "", settings.DEFAULT_FROM_EMAIL, [user.email]
    )
    email_message.attach_alternative(html_content, "text/html")
    email_message.send()
    return JsonResponse(
        {
            "success": True,
            "message": _("If the account exists, an email has been sent."),
        }
    )


from twilio.rest import Client

from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import FieldDoesNotExist
from django.db import transaction
from django.db.models import F
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_GET, require_POST

from geo_regions.models import Region
from main.calculations import generate_random_password
from main.models import OTPVerification, User, UserRole
from main.phonenumber import format_phone_number
from main.twilio_helpers import send_otp_sms
from user.auth import role_redirect
from user.permissions import require_staff_role

logger = logging.getLogger(__name__)


# --- Helper: pull & validate "next" and store it for after 2FA ---


def _stash_next(request):
    """
    Store a safe 'next' URL (deep link) in session so verify_2fa can return the user there.
    """
    candidate = (
        request.POST.get("next")
        or request.GET.get("next")
        or request.session.get("post_login_next")
    )
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}
    ):
        request.session["post_login_next"] = candidate
    else:
        # keep whatever is in session if already set, else clear
        request.session["post_login_next"] = request.session.get("post_login_next")


def _is_ajax(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


# @anonymous_required
def login_page(request):
    logger.info("Rendering login page for anonymous user.")
    template = "login_page.html"
    return render(request, template)


def login_request(request):
    logger.info(f"Login request received via {request.method}.")
    if request.method != "POST":
        _stash_next(request)
        if _is_ajax(request):
            logger.warning("Login request received with GET via AJAX. 405.")
            return JsonResponse(
                {"success": False, "message": "Invalid request method."}, status=405
            )
        logger.info("Login request via GET. Redirecting to login page.")
        return redirect("login_page")

    username = (request.POST.get("username") or "").strip()
    password = (request.POST.get("password") or "").strip()
    _stash_next(request)

    def fail(message, status=400, redirect_to="login_page"):
        if _is_ajax(request):
            return JsonResponse({"success": False, "message": message}, status=status)
        messages.error(request, message)
        return redirect(redirect_to)

    if not username or not password:
        logger.warning("Login failed: Username or password not provided.")
        return fail("Username and password are required.", status=400)
        messages.error(request, _("Username and password are required."))
        return redirect("login_page")

    user = authenticate(request, username=username, password=password)
    if user is None:
        logger.warning(f"Login failed for '{username}': Invalid credentials.")
        return fail("Invalid username or password.", status=401)

    if not user.is_active:
        logger.warning(f"Login failed for '{username}': Account disabled.")
        return fail("Your account is disabled. Please contact support.", status=403)

    logger.info(f"User '{username}' authenticated. Starting 2FA flow.")

    # ---- Helpers ----------------------------------------------------------
    def normalize_phone_e164_drc(raw: str) -> str:
        """Normalize to E.164 for DRC if needed, preserving numbers already starting with '+'."""
        p = (raw or "").strip()
        if not p:
            return ""
        if p.startswith("+"):
            return p
        # Original code assumed DRC (+243); keep behavior:
        return f"+243{p}"

    def mask_phone(p: str) -> str:
        """Return a masked phone like +243 ** *** **56"""
        if not p or len(p) < 6:
            return "***"
        last = p[-2:]
        return f"{p[:4]} ** *** **{last}"

    # ----------------------------------------------------------------------

    # Clear previous unverified OTPs
    OTPVerification.objects.filter(user=user, is_verified=False).delete()

    # Create a fresh OTP challenge
    otp_instance = OTPVerification(user=user)
    otp_instance.generate_otp()  # sets otp, expiry, etc.
    challenge_id = str(otp_instance.pk)

    # Twilio config
    twilio_sid = environ.get("TWILIO_ACCOUNT_SID")
    twilio_token = environ.get("TWILIO_AUTH_TOKEN")
    twilio_phone = environ.get("TWILIO_PHONE_NUMBER")

    alpha_numeric = "NEXUS"
    # alpha_numeric = twilio_phone  # or branded sender if allowed by country/SMS rules

    phone = getattr(user, "phone", "") or ""
    if not phone:
        # No delivery method available; abort 2FA challenge
        otp_instance.delete()
        logger.error(f"OTP delivery failed for '{username}': No phone number.")
        return fail("No phone number on file. Cannot deliver OTP.", status=409)

    to_number = normalize_phone_e164_drc(phone)

    if dev_mode:
        print("OTP CODE:", otp_instance.otp)
        # Harden session & persist minimal 2FA state
        request.session.cycle_key()
        request.session["pre_2fa_user_id"] = user.pk
        request.session["2fa_pending"] = True
        request.session["2fa_challenge_id"] = challenge_id
        request.session["uid"] = user.id_user
        # (Optionally stash 'next' in session if you use it after verification)
        # request.session["post_login_next"] = request.session.get("next_url")

        verify_url = reverse("verify_2fa")  # fallback page (not used by modal flow)

        # === AJAX (modal) flow: tell frontend to open 2FA modal ===
        if _is_ajax(request):
            payload = {
                "twofa_required": True,
                "challenge_id": challenge_id,
                "method": "sms",
                "dest_masked": mask_phone(to_number),
            }
            # Optionally let UI show a soft note when SMS didn't send successfully:
            # payload["delivery_warning"] = not sms_sent
            return JsonResponse(payload, status=200)

        # === Non-AJAX fallback: go to a standalone 2FA page ===
        return redirect(verify_url)

    else:
        # Send OTP via Twilio (best-effort; continue to modal even if provider errors)
        sms_sent = False
        try:
            if not (twilio_sid and twilio_token and alpha_numeric):
                raise RuntimeError("Missing Twilio credentials or sender.")
            sms_body = f"Hi {user.get_full_name() or user.username}, your OTP code is: {otp_instance.otp}"
            logger.info(f"Sending OTP to '{username}' at ...{to_number[-4:]}")
            twilio_client = Client(twilio_sid, twilio_token)
            message = twilio_client.messages.create(
                body=sms_body, from_=alpha_numeric, to=to_number
            )
            sms_sent = bool(getattr(message, "sid", None))
            if sms_sent:
                logger.info(
                    f"[Twilio] SMS sent (SID: {message.sid}, Status: {message.status})"
                )
            else:
                logger.warning("[Twilio] SMS send returned no SID.")
        except Exception as e:
            logger.error(f"Twilio SMS sending failed for '{username}': {e}")

        # Harden session & persist minimal 2FA state
        request.session.cycle_key()
        request.session["pre_2fa_user_id"] = user.pk
        request.session["2fa_pending"] = True
        request.session["2fa_challenge_id"] = challenge_id
        request.session["uid"] = user.id_user
        # (Optionally stash 'next' in session if you use it after verification)
        # request.session["post_login_next"] = request.session.get("next_url")

        verify_url = reverse("verify_2fa")  # fallback page (not used by modal flow)

        # === AJAX (modal) flow: tell frontend to open 2FA modal ===
        if _is_ajax(request):
            payload = {
                "twofa_required": True,
                "challenge_id": challenge_id,
                "method": "sms",
                "dest_masked": mask_phone(to_number),
            }
            # Optionally let UI show a soft note when SMS didn't send successfully:
            # payload["delivery_warning"] = not sms_sent
            return JsonResponse(payload, status=200)

        # === Non-AJAX fallback: go to a standalone 2FA page ===
        return redirect(verify_url)


def logout_request(request):
    logout(request)
    return redirect("home_page")


def register(request):
    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        email = request.POST.get("email", "").strip()
        phone = request.POST.get("phone", "").strip()
        password = request.POST.get("password", "").strip()

        if not full_name or not email or not password:
            return JsonResponse(
                {"success": False, "message": "All fields are required."}
            )

        if User.objects.filter(email=email).exists():
            return JsonResponse(
                {"success": False, "message": "This email is already registered."}
            )

        cleaned_phone = format_phone_number(phone)
        if User.objects.filter(phone=cleaned_phone).exists():
            return JsonResponse(
                {
                    "success": False,
                    "message": "This phone number is already registered.",
                }
            )

        try:
            saving_user = User.objects.create_user(
                full_name=full_name,
                email=email,
                password=password,
                username=email,
                phone=cleaned_phone,
                roles=["customer"],
            )

            saving_user.is_active = False
            saving_user.save()

            otp_instance = OTPVerification.objects.create(user=saving_user)
            otp_instance.generate_otp()

            twilio_sid = environ.get("TWILIO_ACCOUNT_SID")
            twilio_token = environ.get("TWILIO_AUTH_TOKEN")
            twilio_phone = environ.get("TWILIO_PHONE_NUMBER")

            alpha_numeric = "NEXUS"

            if dev_mode:
                print("OTP CODE:", otp_instance.otp)
            else:
                try:
                    twilio_client = Client(twilio_sid, twilio_token)

                    sms_body = f"Hi {full_name}, your OTP code is: {otp_instance.otp}"
                    message = twilio_client.messages.create(
                        body=sms_body, from_=alpha_numeric, to=f"+{cleaned_phone}"
                    )

                    # Log or confirm it was queued
                    if message.sid:
                        print(
                            f"[Twilio] SMS successfully sent (SID: {message.sid}, Status: {message.status})"
                        )
                    else:
                        print("[Twilio] SMS sending failed: No SID returned")

                except Exception as e:
                    print(f"[Twilio Error] {str(e)}")

            request.session["uid"] = saving_user.id_user

            return JsonResponse(
                {
                    "success": True,
                    "message": "User registered. OTP sent.",
                    # 'otp': otp_instance.otp  # For dev only; remove in production
                }
            )
        except Exception:
            return JsonResponse(
                {"success": False, "message": str("This email is already registered.")}
            )

    return JsonResponse({"success": False, "message": "Invalid request method."})


def verify_otp(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Invalid request method."})

    uid = request.session.get("uid")
    if not uid:
        return JsonResponse(
            {"success": False, "message": "Session expired. Please register again."}
        )

    try:
        user = User.objects.get(id_user=uid)
        otp_entry = OTPVerification.objects.filter(user=user, is_verified=False).latest(
            "created_at"
        )
    except User.DoesNotExist:
        return JsonResponse({"success": False, "message": "User not found."})
    except OTPVerification.DoesNotExist:
        return JsonResponse(
            {
                "success": False,
                "message": "OTP session not found. Please register again.",
            }
        )

    otp_input = (request.POST.get("otp") or "").strip()

    # Expiry check (if model has expires_at)
    if hasattr(otp_entry, "expires_at") and now() > otp_entry.expires_at:
        otp_entry.delete()
        return JsonResponse(
            {"success": False, "message": "OTP expired. Please register again."}
        )

    # Validate OTP
    if otp_input != otp_entry.otp:
        if hasattr(otp_entry, "attempts"):
            otp_entry.attempts = (otp_entry.attempts or 0) + 1
            otp_entry.save(update_fields=["attempts"])
            if otp_entry.attempts >= 5:
                otp_entry.delete()
                return JsonResponse(
                    {
                        "success": False,
                        "message": "Too many attempts. Please register again.",
                    }
                )
        return JsonResponse({"success": False, "message": "Invalid OTP. Try again."})

    # Success → mark verified, activate, login
    if hasattr(otp_entry, "is_verified"):
        otp_entry.is_verified = True
        otp_entry.save(update_fields=["is_verified"])
    else:
        otp_entry.delete()

    user.is_active = True
    user.is_verified = True
    user.save(update_fields=["is_active", "is_verified"])

    login(request, user)

    # Clean session
    request.session.pop("uid", None)

    # Return a JSON redirect to dashboard
    return JsonResponse(
        {
            "success": True,
            "message": "Account verified successfully.",
            "redirect": reverse("dashboard"),  # <-- ensure this URL name exists
        }
    )


def verify_2fa(request):
    """
    Handles both:
      - GET: shows the 2FA page if session is valid
      - POST (AJAX or non-AJAX): verifies OTP and logs user in

    Compatible with the modal-based JS which posts to this URL and expects:
      { success: true, redirect_url: "<next>" }  on success
      { success: false, message: "<error>" }     on error
    """
    template = "verify_2fa.html"
    is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"

    logger.info("verify_2fa called - Method: %s, AJAX: %s", request.method, is_ajax)

    # --- GET -> show form (if session is valid) ---
    if request.method != "POST":
        if not request.session.get("pre_2fa_user_id"):
            logger.warning("verify_2fa GET without pre_2fa_user_id")
            messages.error(request, "Your session has expired. Please login again.")
            return redirect("login_page")
        return render(request, template)

    # --- POST -> check OTP ---
    # Accept multiple possible field names from the modal
    raw_otp = (
        (request.POST.get("otp") or "").strip()
        or (request.POST.get("code") or "").strip()
        or (request.POST.get("twofa_code") or "").strip()
    )
    # Keep only digits; front-end already enforces 6 digits but we’re defensive
    otp_input = re.sub(r"\D", "", raw_otp)[:8]  # cap just in case

    # Optional challenge id (hidden input). Accept both names.
    challenge_id = (request.POST.get("challenge_id") or "").strip() or (
        request.POST.get("twofa_challenge_id") or ""
    ).strip()

    user_id = request.session.get("pre_2fa_user_id")
    logger.info(
        "verify_2fa POST - OTP length: %s, User ID: %s, Challenge: %s",
        len(otp_input),
        user_id,
        challenge_id or "N/A",
    )

    # Basic session check
    if not user_id:
        logger.error("verify_2fa POST without pre_2fa_user_id")
        msg = "Session expired. Please login again."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("login_page")

    # Basic OTP format check
    if len(otp_input) < 6:
        msg = "Please enter the 6-digit code."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("verify_2fa")

    # Fetch user + pending OTP entry (prefer challenge_id when provided)
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        msg = "User not found."
        logger.error(msg)
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=404)
        messages.error(request, msg)
        return redirect("login_page")

    try:
        if challenge_id:
            otp_entry = OTPVerification.objects.filter(
                pk=challenge_id, user=user, is_verified=False
            ).latest("created_at")
        else:
            otp_entry = OTPVerification.objects.filter(
                user=user, is_verified=False
            ).latest("created_at")
        logger.info("OTP entry found; expires at: %s", otp_entry.expires_at)
    except OTPVerification.DoesNotExist:
        msg = "OTP session not found. Please login again."
        logger.error(msg)
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("login_page")

    # Expiry check
    if now() > otp_entry.expires_at:
        logger.warning("OTP expired for user %s", user.username)
        otp_entry.delete()
        msg = "OTP expired. Please login again."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("login_page")

    # Validate OTP
    if otp_input != otp_entry.otp:
        logger.warning("Invalid OTP for user %s", user.username)
        OTPVerification.objects.filter(pk=otp_entry.pk).update(
            attempt_count=F("attempt_count") + 1
        )
        otp_entry.refresh_from_db(fields=["attempt_count"])

        if otp_entry.attempt_count >= 5:
            logger.error(
                "Too many OTP attempts for user %s; deleting OTP", user.username
            )
            otp_entry.delete()
            msg = "Too many attempts. Please login again."
            if is_ajax:
                return JsonResponse({"success": False, "message": msg}, status=400)
            messages.error(request, msg)
            return redirect("login_page")

        msg = "Invalid OTP. Try again."
        if is_ajax:
            return JsonResponse({"success": False, "message": msg}, status=400)
        messages.error(request, msg)
        return redirect("verify_2fa")

    # --- Success ---
    otp_entry.is_verified = True
    otp_entry.save(update_fields=["is_verified"])

    # (Optional) clean other stale/pending OTPs for this user
    OTPVerification.objects.filter(user=user, is_verified=False).exclude(
        pk=otp_entry.pk
    ).delete()

    login(request, user)

    # cleanup 2FA flags
    request.session.pop("pre_2fa_user_id", None)
    request.session.pop("2fa_pending", None)

    # Prefer a safe deep-link if we stashed it
    next_url = request.session.pop("post_login_next", None)
    logger.info("verify_2fa: post_login_next=%s", next_url)

    if next_url and url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}
    ):
        if is_ajax:
            return JsonResponse(
                {
                    "success": True,
                    "message": "Account verified successfully.",
                    "redirect_url": next_url,
                }
            )
        return redirect(next_url)

    # Otherwise, role-based landing (default dashboard)
    resp = role_redirect(user, default_urlname="dashboard")
    final_url = getattr(resp, "url", "/")
    logger.info("verify_2fa: role_redirect -> %s", final_url)

    if is_ajax:
        return JsonResponse(
            {
                "success": True,
                "message": "Account verified successfully.",
                "redirect_url": final_url,
            }
        )
    return resp


# def verify_2fa(request):
#     template = "verify_2fa.html"
#     is_ajax = request.headers.get("X-Requested-With") == "XMLHttpRequest"
#
#     logger.info("verify_2fa called - Method: %s, AJAX: %s", request.method, is_ajax)
#
#     # GET -> show form
#     if request.method != "POST":
#         if not request.session.get("pre_2fa_user_id"):
#             logger.warning("verify_2fa GET without pre_2fa_user_id")
#             messages.error(request, "Your session has expired. Please login again.")
#             return redirect("login_page")
#         return render(request, template)
#
#     # POST -> check OTP
#     otp_input = (request.POST.get("otp") or "").strip()
#     user_id = request.session.get("pre_2fa_user_id")
#
#     logger.info("verify_2fa POST - OTP length: %s, User ID: %s", len(otp_input), user_id)
#
#     if not user_id:
#         logger.error("verify_2fa POST without pre_2fa_user_id")
#         if is_ajax:
#             return JsonResponse(
#                 {"success": False, "message": "Session expired. Please login again."},
#                 status=400,
#             )
#         messages.error(request, "Session expired. Please login again.")
#         return redirect("login_page")
#
#     try:
#         user = User.objects.get(pk=user_id)
#         otp_entry = OTPVerification.objects.filter(user=user, is_verified=False).latest("created_at")
#         logger.info("OTP entry found; expires at: %s", otp_entry.expires_at)
#     except User.DoesNotExist:
#         msg = "User not found."
#         logger.error(msg)
#         if is_ajax:
#             return JsonResponse({"success": False, "message": msg}, status=404)
#         messages.error(request, msg)
#         return redirect("login_page")
#     except OTPVerification.DoesNotExist:
#         msg = "OTP session not found. Please login again."
#         logger.error(msg)
#         if is_ajax:
#             return JsonResponse({"success": False, "message": msg}, status=400)
#         messages.error(request, msg)
#         return redirect("login_page")
#
#     # Expiry check
#     current_time = now()
#     if current_time > otp_entry.expires_at:
#         logger.warning("OTP expired for user %s", user.username)
#         otp_entry.delete()
#         msg = "OTP expired. Please login again."
#         if is_ajax:
#             return JsonResponse({"success": False, "message": msg}, status=400)
#         messages.error(request, msg)
#         return redirect("login_page")
#
#     # Validate OTP
#     if otp_input != otp_entry.otp:
#         logger.warning("Invalid OTP for user %s", user.username)
#         OTPVerification.objects.filter(pk=otp_entry.pk).update(attempt_count=F("attempt_count") + 1)
#         otp_entry.refresh_from_db(fields=["attempt_count"])
#         if otp_entry.attempt_count >= 5:
#             logger.error("Too many OTP attempts for user %s; deleting OTP", user.username)
#             otp_entry.delete()
#             msg = "Too many attempts. Please login again."
#             if is_ajax:
#                 return JsonResponse({"success": False, "message": msg}, status=400)
#             messages.error(request, msg)
#             return redirect("login_page")
#
#         msg = "Invalid OTP. Try again."
#         if is_ajax:
#             return JsonResponse({"success": False, "message": msg}, status=400)
#         messages.error(request, msg)
#         return redirect("verify_2fa")
#
#     # Success
#     otp_entry.is_verified = True
#     otp_entry.save(update_fields=["is_verified"])
#     login(request, user)
#
#     # cleanup 2FA flags
#     request.session.pop("pre_2fa_user_id", None)
#     request.session.pop("2fa_pending", None)
#
#     # 1) Prefer a safe deep-link if we stashed it
#     next_url = request.session.pop("post_login_next", None)
#     logger.info("verify_2fa: post_login_next=%s", next_url)
#
#     if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
#         if is_ajax:
#             return JsonResponse({"success": True, "message": "Account verified successfully.", "redirect": next_url})
#         return redirect(next_url)
#
#     # 2) Otherwise, role-based
#     resp = role_redirect(user, default_urlname="dashboard")
#     final_url = getattr(resp, "url", "/")
#     logger.info("verify_2fa: role_redirect -> %s", final_url)
#
#     if is_ajax:
#         return JsonResponse({"success": True, "message": "Account verified successfully.", "redirect": final_url})
#     return resp


@login_required(login_url="login_page")
@require_staff_role(["admin"])
@require_GET
def users_management(request):
    """
    Renders the Users Management page with:
      - regions: Region queryset (id, name) for both modals
      - roles: list of dicts shaped like {"id": "<role>", "name": "<Role>"}
      - assigned_order_count: active staff users
      - dispatched_order: inactive staff users
      - total_dispatched: total staff users
    """
    User = get_user_model()

    # Regions for selects
    regions = Region.objects.all().only("id", "name").order_by("name")

    # Your 8 system roles (as id/name to match {{ group.id }} / {{ group.name }} style)
    role_strings = [
        "admin",
        "manager",
        "dispatcher",
        "leadtechnician",
        "technician",
        "sales",
        "support",
        "compliance",
    ]
    roles = [{"id": r, "name": r.capitalize()} for r in role_strings]

    # Summary cards
    assigned_order_count = User.objects.filter(is_staff=True, is_active=True).count()
    dispatched_order = User.objects.filter(is_staff=True, is_active=False).count()
    total_dispatched = User.objects.filter(is_staff=True).count()

    context = {
        "regions": regions,
        "roles": roles,
        "assigned_order_count": assigned_order_count,
        "dispatched_order": dispatched_order,
        "total_dispatched": total_dispatched,
    }
    return render(request, "users_management_page.html", context)


def _only_digits(s: str) -> str:
    return re.sub(r"\D+", "", s or "")


@login_required(login_url="login_page")
@require_staff_role(["admin"])
@require_POST
def staff_creation(request):
    try:
        data = request.POST if request.method == "POST" else json.loads(request.body)

        full_name = (data.get("full_name") or "").strip()
        email = (data.get("email") or "").strip().lower()

        # Accept either phone_local (digits) or phone (may be E.164 or digits)
        phone_local = (data.get("phone_local") or "").strip()
        phone_raw = (data.get("phone") or "").strip()
        region_id = (data.get("region_id") or "").strip()
        password = data.get("password") or ""
        confirm_password = data.get("confirm_password") or ""

        # roles from <select multiple> or CSV/string
        roles = (
            data.getlist("roles") if hasattr(data, "getlist") else data.get("roles", [])
        )
        if isinstance(roles, str):
            roles = [r.strip() for r in roles.split(",") if r.strip()]

        submitted_data = {
            "full_name": full_name,
            "email": email,
            "region_id": region_id,
            "roles": roles,
        }

        # -------- Phone normalization: force +243 if local digits --------
        raw_input = (phone_local or phone_raw or "").strip()
        if not raw_input:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Phone number is required.",
                    "data": submitted_data,
                },
                status=400,
            )

        if raw_input.startswith("+"):
            candidate = raw_input
        else:
            digits = _only_digits(raw_input)
            # If user typed 243XXXXXXXXX w/o '+'
            if digits.startswith("243"):
                candidate = f"+{digits}"
            else:
                candidate = f"+243{digits.lstrip('0')}"

        try:
            parsed = phonenumbers.parse(candidate, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("invalid")
            phone_e164 = phonenumbers.format_number(
                parsed, phonenumbers.PhoneNumberFormat.E164
            )
        except Exception:
            return JsonResponse(
                {
                    "success": False,
                    "message": "Invalid phone number format.",
                    "data": submitted_data,
                },
                status=400,
            )

        # -------- Field validation --------
        if not all([full_name, email, password, confirm_password]):
            return JsonResponse(
                {
                    "success": False,
                    "error": "All required fields must be filled.",
                    "data": submitted_data,
                },
                status=400,
            )

        if password != confirm_password:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Passwords do not match.",
                    "data": submitted_data,
                },
                status=400,
            )

        if User.objects.filter(email=email).exists():
            return JsonResponse(
                {
                    "success": False,
                    "error": "A user with this email already exists.",
                    "data": submitted_data,
                },
                status=400,
            )

        # -------- Create user (atomic) --------
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                full_name=full_name,
                phone=phone_e164,
                password=password,
                is_verified=True,
                is_staff=True,
                roles=roles,
            )

            # --- Conditionally set region ONLY if User has such a field ---
            if region_id:
                try:
                    # Does the User model actually have a concrete 'region' field?
                    user._meta.get_field("region")  # raises FieldDoesNotExist if absent
                    # If present, assign Region FK
                    try:
                        region = Region.objects.get(id=region_id)
                        setattr(user, "region", region)
                        user.save(update_fields=["region"])
                    except Region.DoesNotExist:
                        return JsonResponse(
                            {
                                "success": False,
                                "error": "Selected region does not exist.",
                                "data": submitted_data,
                            },
                            status=400,
                        )
                except FieldDoesNotExist:
                    # No region field on User → just ignore silently (or log)
                    # print("[Users] 'region' field not present on User; skipping assignment.")
                    pass

            # -------- SMS with Twilio (best-effort) --------
            twilio_sid = environ.get("TWILIO_ACCOUNT_SID")
            twilio_token = environ.get("TWILIO_AUTH_TOKEN")
            twilio_phone = environ.get("TWILIO_PHONE_NUMBER")

            alpha_numeric = "NEXUS"

            if dev_mode:
                return JsonResponse(
                    {"success": True, "message": "User created successfully."}
                )
            else:
                if twilio_sid and twilio_token and twilio_phone:
                    try:
                        client = Client(twilio_sid, twilio_token)
                        sms_body = f"Hi {full_name}, your password is: {password}"
                        message = client.messages.create(
                            body=sms_body, from_=alpha_numeric, to=phone_e164
                        )
                        if message.sid:
                            print(
                                f"[Twilio] SMS sent (SID: {message.sid}, Status: {message.status})"
                            )
                    except Exception as e:
                        # Non-fatal: user is created; just log
                        print(f"[Twilio Error] {e}")
                else:
                    print("[Twilio] Missing credentials; SMS not sent.")

        return JsonResponse({"success": True, "message": "User created successfully."})

    except Exception as e:
        import traceback

        print(traceback.format_exc())
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin"])
@require_GET
def get_roles_region(request):
    regions = [
        {"value": region.id, "label": region.name} for region in Region.objects.all()
    ]
    roles = [{"value": role.value, "label": role.label} for role in UserRole]
    return JsonResponse({"roles": roles, "regions": regions}, safe=False)


@login_required(login_url="login_page")
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def get_users_data(request):
    users = User.objects.filter(
        is_staff=True
    ).select_related()  # Add 'region' if region is a FK

    data = []
    for index, user in enumerate(users, start=1):
        region_name = getattr(user, "region", None)
        region_label = region_name.name if region_name else "N/A"

        data.append(
            {
                "index": index,
                "full_name": user.full_name,
                "email": user.email,
                "phone": user.phone or "",
                "region": region_label,
                "roles": (
                    ", ".join(user.roles)
                    if isinstance(user.roles, list)
                    else str(user.roles)
                ),
                "last_login": (
                    user.last_login.strftime("%Y-%m-%d %H:%M")
                    if user.last_login
                    else "Never"
                ),
                "is_active": user.is_active,
            }
        )

    return JsonResponse({"users": data})


@login_required(login_url="login_page")
@require_staff_role(["admin"])
@require_POST
def reset_user_password(request):
    try:
        data = json.loads(request.body)
        email = data.get("email")

        if not email:
            return JsonResponse(
                {"success": False, "error": "Email is required."}, status=400
            )

        user = User.objects.get(email=email)

        if not user.phone or not user.phone.startswith("+243"):
            return JsonResponse(
                {
                    "success": False,
                    "error": "User has no valid phone number to send SMS.",
                },
                status=400,
            )

        new_password = generate_random_password()
        user.set_password(new_password)
        user.save()

        full_name = user.full_name
        phone = user.phone

        twilio_sid = environ.get("TWILIO_ACCOUNT_SID")
        twilio_token = environ.get("TWILIO_AUTH_TOKEN")
        twilio_phone = environ.get("TWILIO_PHONE_NUMBER")

        # Try to send SMS via Twilio
        sms_sent = False
        if twilio_sid and twilio_token and twilio_phone:
            try:
                twilio_client = Client(twilio_sid, twilio_token)
                sms_body = (
                    f"Hi {full_name}, your password has been reset to : {new_password}"
                )
                message = twilio_client.messages.create(
                    body=sms_body, from_=twilio_phone, to=phone
                )
                if message.sid:
                    print(f"[Twilio] SMS sent successfully (SID: {message.sid})")
                    sms_sent = True
                else:
                    print("[Twilio] SMS sending failed: No SID returned")
            except Exception as e:
                print(f"[Twilio Error] Failed to send SMS: {str(e)}")
                # Don't fail the entire operation if SMS fails
                sms_sent = False
        else:
            print("[Twilio] SMS credentials not configured - skipping SMS")

        message = "Password reset successfully."
        if sms_sent:
            message += " New password sent via SMS."
        else:
            message += " Please share the new password with the user."

        return JsonResponse(
            {
                "success": True,
                "new_password": new_password,
                "message": message,
                "sms_sent": sms_sent,
            }
        )

    except User.DoesNotExist:
        return JsonResponse({"success": False, "error": "User not found."}, status=404)
    except Exception as e:
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin"])
@require_POST
def edit_user(request):
    try:
        data = request.POST if request.method == "POST" else json.loads(request.body)

        email = data.get("email")
        full_name = data.get("full_name")
        phone = data.get("phone")
        region_id = data.get("region_id")

        # Handle roles input (from multi-select or JSON string)
        roles = (
            data.getlist("roles") if hasattr(data, "getlist") else data.get("roles", [])
        )
        if isinstance(roles, str):
            roles = [role.strip() for role in roles.split(",") if role.strip()]

        # Preserve submitted data for error response
        submitted_data = {
            "email": email,
            "full_name": full_name,
            "phone": phone,
            "region_id": region_id,
            "roles": roles,
        }

        # Validate required fields
        if not all([email, full_name]):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Email and full name are required.",
                    "data": submitted_data,
                },
                status=400,
            )

        # Get the user to edit
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse(
                {
                    "success": False,
                    "error": "User not found.",
                    "data": submitted_data,
                },
                status=404,
            )

        # Validate and format phone number if provided
        if phone:
            try:
                parsed = phonenumbers.parse(phone, None)
                if not phonenumbers.is_valid_number(parsed):
                    raise ValueError("Invalid phone number")
                phone = phonenumbers.format_number(
                    parsed, phonenumbers.PhoneNumberFormat.E164
                )
            except Exception:
                return JsonResponse(
                    {"success": False, "message": "Invalid phone number format."}
                )

        # Update user fields
        user.full_name = full_name
        if phone:
            user.phone = phone
        if roles:
            user.roles = roles
        user.save()

        # Update region if provided
        if region_id:
            try:
                region = Region.objects.get(id=region_id)
                user.region = region
                user.save()
            except Region.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "Selected region does not exist.",
                        "data": submitted_data,
                    },
                    status=400,
                )

        return JsonResponse({"success": True, "message": "User updated successfully."})
    except Exception as e:
        import traceback

        print(traceback.format_exc())
        return JsonResponse({"success": False, "error": str(e)}, status=500)


@login_required(login_url="login_page")
@require_staff_role(["admin"])
@require_GET
def get_user_details(request):
    email = request.GET.get("email")
    if not email:
        return JsonResponse({"error": "Email is required."}, status=400)

    try:
        user = User.objects.get(email=email)
        region_name = getattr(user, "region", None)
        region_data = (
            {
                "id": region_name.id if region_name else None,
                "name": region_name.name if region_name else "",
            }
            if region_name
            else None
        )

        user_data = {
            "full_name": user.full_name,
            "email": user.email,
            "phone": user.phone or "",
            "region": region_data,
            "roles": user.roles if isinstance(user.roles, list) else [],
        }
        return JsonResponse({"success": True, "user": user_data})
    except User.DoesNotExist:
        return JsonResponse({"error": "User not found."}, status=404)
    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


def _get_pending_user(request):
    """Return the user being verified (logged-in or stored in session)."""
    if request.user.is_authenticated:
        return request.user
    uid = request.session.get("uid")
    if not uid:
        return None
    try:
        return User.objects.get(pk=uid)
    except User.DoesNotExist:
        return None


# If send_otp_sms is in another module, import it from there instead:
# from apps.notifications.sms import send_otp_sms
# Here we assume it's in the same module/file.


def _send_otp(user, code: str) -> bool:
    """
    Send the OTP to the user's phone using Twilio.
    Falls back to logging if no phone is available or send fails.

    Returns:
        True if the SMS was queued successfully, False otherwise.
    """
    full_name = (
        getattr(user, "full_name", "") or getattr(user, "username", "") or "Customer"
    ).strip()
    phone = (getattr(user, "phone", "") or "").strip()

    if not phone:
        print(f"[OTP] No phone number on file for user {user}. Skipping SMS.")
        print(f"[OTP] (Info) Code for {user.email or 'no-email'} is: {code}")
        return False

    ok, info = send_otp_sms(
        full_name=full_name,
        cleaned_phone=phone,  # accepts with or without leading '+'
        otp_code=code,
        alpha_sender="NEXUS",  # use your approved alphanumeric sender if supported
    )

    if ok:
        print(f"[OTP] SMS queued to {phone} (SID: {info})")
        return True

    print(f"[OTP] SMS failed for {phone}: {info}")
    # Optional: email fallback could go here
    # send_otp_email(user.email, code)  # implement if needed
    return False


@require_POST
def resend_otp(request):
    """
    Create a fresh OTP for the pending user and send it.
    Returns JSON {success, message}.
    """
    user = _get_pending_user(request)
    if not user:
        return JsonResponse(
            {"success": False, "message": "No verification session found."},
            status=400,
        )

    # Create & generate a new OTP
    otp_obj = OTPVerification.objects.create(user=user)
    otp_obj.generate_otp()  # sets otp, expires_at, etc.

    # Deliver it (implement your provider inside _send_otp)
    _send_otp(user, otp_obj.otp)

    return JsonResponse({"success": True, "message": "A new code was sent."})
