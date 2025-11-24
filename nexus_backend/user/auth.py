# auth_helpers.py
import json
import logging
from functools import wraps

from django.contrib.auth.decorators import user_passes_test
from django.shortcuts import redirect, resolve_url
from django.utils.http import url_has_allowed_host_and_scheme

logger = logging.getLogger(__name__)

# Where to send each role (URL **names**)
ROLE_REDIRECTS = {
    "admin": "dashboard_bi",
    "manager": "dashboard_bi",  # Use BI dashboard for managers
    "finance": "dashboard_bi",  # Finance users need access to financial reports and analytics
    "dispatcher": "dispatch_dashboard",
    # "technician": "tech_dashboard",
    "leadtechnician": "tech_dashboard",
    "technician": "fe_ops_dashboard",
    # "installer": "fe_ops_dashboard",
    "sales": "sales_dashboard",
    "support": "backoffice_feedback_list",  # Support users go directly to feedback management
    "compliance": "kyc_management",
}

# If a user has multiple roles, earlier ones win.
ROLE_PRIORITY = [
    "admin",
    "manager",
    "finance",
    "dispatcher",
    "leadtechnician",
    "installer",
    "sales",
    "support",
    "compliance",
]


def require_full_login(view_func):
    """
    Gate a view behind full login (with your 2FA flow).
    If user is not authenticated, remember the deep URL in session and send to login.
    After OTP verification, verify_2fa will bring them back here.
    """

    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if request.user.is_authenticated:
            return view_func(request, *args, **kwargs)

        path = request.get_full_path()
        if url_has_allowed_host_and_scheme(path, allowed_hosts={request.get_host()}):
            request.session["post_login_next"] = path

        return redirect("login_page")

    return _wrapped


def normalized_roles(user) -> list[str]:
    """Return user roles as a lowercase list, safely."""
    roles = getattr(user, "roles", []) or []
    if isinstance(roles, str):
        # tolerate comma-delimited or JSON-encoded strings
        try:
            parsed = json.loads(roles)
            if isinstance(parsed, list):
                roles = parsed
            else:
                roles = [roles]
        except Exception:
            roles = [r.strip() for r in roles.split(",") if r.strip()]
    return [str(r).strip().lower() for r in roles if r]


def has_role(user, role):
    """
    DEPRECATED: Use user.permissions.user_has_role instead.

    This function is maintained for backward compatibility but will be removed
    in a future version. Please migrate to the centralized permission system.

    See: user/permissions.py and RBAC_IMPLEMENTATION_GUIDE.md
    """
    import warnings

    warnings.warn(
        "has_role from user.auth is deprecated. Use user.permissions.user_has_role instead.",
        DeprecationWarning,
        stacklevel=2,
    )

    # Forward to new implementation for consistency
    from user.permissions import user_has_role as _new_implementation

    return _new_implementation(user, role)


# Legacy decorator - kept for backward compatibility
customer_nonstaff_required = user_passes_test(
    lambda u: (not u.is_staff) and has_role(u, "customer"), login_url="login_page"
)


def _safe_redirect(urlname_or_path: str, fallback_path: str = "/"):
    """
    Resolve a URL name or treat it as a path; fall back to a safe path if resolution fails.
    Accepts:
      - URL name (e.g., 'tech_main_dashboard')
      - Absolute path (e.g., '/tech/')
    """
    try:
        # resolve_url handles both names and absolute/relative paths
        target = resolve_url(urlname_or_path)
        return redirect(target)
    except Exception as e:
        logger.warning(
            "resolve_url failed for '%s': %s; falling back to '%s'",
            urlname_or_path,
            e,
            fallback_path,
        )
        try:
            return redirect(resolve_url(fallback_path))
        except Exception:
            # last-resort absolute root
            return redirect("/")


def role_redirect(user, default_urlname: str = "dashboard"):
    """
    Redirects user based on roles.

    Special case for 'customer' **only if** the user is *just* a customer (no other roles):
      - If KYC verified (approved) -> dashboard
      - Otherwise -> client_landing

    Otherwise, use ROLE_PRIORITY order among non-customer roles.

    Falls back to default_urlname, then '/'.
    """
    if not getattr(user, "is_authenticated", False):
        return _safe_redirect(default_urlname, "/")

    roles_set = set(normalized_roles(user))
    logger.info("role_redirect: normalized roles -> %s", roles_set)

    # --- Customer-only special case ---
    if roles_set == {"customer"}:
        kyc_status = (
            getattr(user, "get_kyc_status", lambda: "not_submitted")() or ""
        ).lower()
        logger.info("role_redirect: customer-only, KYC status=%s", kyc_status)
        if kyc_status == "approved":
            return _safe_redirect("dashboard", "/")
        else:
            return _safe_redirect("landing_page", "/client/landing/")

    # If the user has other roles (even if also 'customer'), route by priority
    for role in ROLE_PRIORITY:
        if role in roles_set:
            urlname = ROLE_REDIRECTS.get(role)
            if urlname:
                resp = _safe_redirect(urlname, "/")
                logger.info(
                    "role_redirect: matched role '%s' -> %s",
                    role,
                    getattr(resp, "url", ""),
                )
                return resp

    # Any roles mapped but not in priority list (future-proofing)
    for role in roles_set:
        urlname = ROLE_REDIRECTS.get(role)
        if urlname:
            resp = _safe_redirect(urlname, "/")
            logger.info(
                "role_redirect: fallback role '%s' -> %s",
                role,
                getattr(resp, "url", ""),
            )
            return resp

    # Final fallback
    logger.info("role_redirect: no role match; using default '%s'", default_urlname)
    return _safe_redirect(default_urlname, "/")
