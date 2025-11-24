"""
Centralized Role-Based Access Control (RBAC) System

This module provides a robust, reusable permission system for both
Django function-based views and Django REST Framework API views.

ARCHITECTURE:
- Single source of truth for role checking
- Decorator-based permissions for FBVs
- Class-based permissions for DRF
- Object-level permissions support

USAGE:
    # Function-based views
    from user.permissions import require_role, require_any_role

    @require_role('admin')
    def admin_only_view(request):
        pass

    @require_any_role(['admin', 'manager'])
    def manager_view(request):
        pass

    # DRF Views
    from user.permissions import HasRole, HasAnyRole

    class MyViewSet(viewsets.ModelViewSet):
        permission_classes = [IsAuthenticated, HasRole('admin')]

SECURITY CONSIDERATIONS:
- Always checks authentication first
- Superusers bypass role checks (privileged users)
- Case-insensitive role matching for flexibility
- Handles malformed data gracefully (no crashes)

Author: VirgoCoachman
Date: 2025-11-05
"""

import json
import logging
from functools import wraps
from typing import Iterable

from rest_framework import permissions

from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth.decorators import user_passes_test
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ============================================================================
# CORE ROLE CHECKING LOGIC - Single Source of Truth
# ============================================================================


def normalize_roles(user) -> set[str]:
    """
    Extract and normalize user roles to a set of lowercase strings.

    Handles multiple edge cases:
    - roles as list: ["Admin", "Manager"]
    - roles as JSON string: '["admin", "manager"]'
    - roles as comma-separated: "admin,manager"
    - roles as None or empty

    Args:
        user: Django user object with roles attribute

    Returns:
        Set of normalized (lowercase, stripped) role strings

    Examples:
        >>> user.roles = ["Admin", "Manager"]
        >>> normalize_roles(user)
        {'admin', 'manager'}
    """
    if not user or not user.is_authenticated:
        return set()

    roles = getattr(user, "roles", []) or []

    # Handle non-iterable types (int, dict, etc.) - convert to empty list
    if not isinstance(roles, (list, str)):
        roles = []

    # Handle JSON string
    if isinstance(roles, str):
        try:
            parsed = json.loads(roles)
            if isinstance(parsed, list):
                roles = parsed
            else:
                # Single role as string
                roles = [roles]
        except (json.JSONDecodeError, TypeError):
            # Comma-separated string fallback
            roles = [r.strip() for r in roles.split(",") if r.strip()]

    # Normalize to lowercase set
    return {str(r).strip().lower() for r in roles if r}


def user_has_role(user, role: str) -> bool:
    """
    Check if user has a specific role.

    Args:
        user: Django user object
        role: Role name to check (case-insensitive)

    Returns:
        True if user has the role, False otherwise

    Security:
        - Superusers always return True
        - Unauthenticated users always return False
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    user_roles = normalize_roles(user)
    return role.lower() in user_roles


def user_has_any_role(user, roles: Iterable[str]) -> bool:
    """
    Check if user has at least one of the specified roles.

    Args:
        user: Django user object
        roles: Iterable of role names

    Returns:
        True if user has any of the roles, False otherwise
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    user_roles = normalize_roles(user)
    required_roles = {r.lower() for r in roles}

    return bool(user_roles & required_roles)


def user_has_all_roles(user, roles: Iterable[str]) -> bool:
    """
    Check if user has all of the specified roles.

    Args:
        user: Django user object
        roles: Iterable of role names

    Returns:
        True if user has all roles, False otherwise
    """
    if not user or not user.is_authenticated:
        return False

    if user.is_superuser:
        return True

    user_roles = normalize_roles(user)
    required_roles = {r.lower() for r in roles}

    return required_roles.issubset(user_roles)


# ============================================================================
# FUNCTION-BASED VIEW DECORATORS
# ============================================================================


def require_role(
    role: str, login_url: str = "login_page", raise_exception: bool = True
):
    """
    Decorator to require a specific role for a view.

    Args:
        role: Required role name
        login_url: URL to redirect unauthenticated users
        raise_exception: If True (default), raise PermissionDenied (403) instead of redirect

    Usage:
        @require_role('admin')
        def admin_dashboard(request):
            pass
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if raise_exception:
                    raise PermissionDenied("Authentication required")
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse(login_url))

            has_permission = user_has_role(request.user, role)
            if not has_permission:
                logger.warning(
                    f"Access denied: User {request.user.email if request.user.is_authenticated else 'Anonymous'} "
                    f"attempted to access resource requiring role '{role}'"
                )
                if raise_exception:
                    raise PermissionDenied(f"Required role: {role}")
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse(login_url))

            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator


def require_any_role(
    roles: Iterable[str], login_url: str = "login_page", raise_exception: bool = True
):
    """
    Decorator to require at least one of the specified roles.

    Args:
        roles: List of acceptable roles
        login_url: URL to redirect unauthenticated users
        raise_exception: If True (default), raise PermissionDenied (403) instead of redirect

    Usage:
        @require_any_role(['admin', 'manager'])
        def management_view(request):
            pass
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if raise_exception:
                    raise PermissionDenied("Authentication required")
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse(login_url))

            has_permission = user_has_any_role(request.user, roles)
            if not has_permission:
                logger.warning(
                    f"Access denied: User {request.user.email if request.user.is_authenticated else 'Anonymous'} "
                    f"attempted to access resource requiring roles {list(roles)}"
                )
                if raise_exception:
                    raise PermissionDenied(f"Required roles: {list(roles)}")
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse(login_url))

            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator


def require_all_roles(roles: Iterable[str], login_url: str = "login_page"):
    """
    Decorator to require all of the specified roles.

    Args:
        roles: List of required roles (must have all)
        login_url: URL to redirect unauthenticated users

    Usage:
        @require_all_roles(['admin', 'finance'])
        def sensitive_finance_view(request):
            pass
    """

    def check_roles(user):
        has_permission = user_has_all_roles(user, roles)
        if not has_permission:
            logger.warning(
                f"Access denied: User {user.email if user.is_authenticated else 'Anonymous'} "
                f"requires ALL roles {list(roles)}"
            )
        return has_permission

    return user_passes_test(
        check_roles, login_url=login_url, redirect_field_name=REDIRECT_FIELD_NAME
    )


def require_customer_only(login_url: str = "login_page"):
    """
    Decorator to restrict access to customer role ONLY.
    Staff users are explicitly blocked.

    This is critical for client-facing views that should NEVER
    be accessed by backoffice staff, even if they have 'customer' role.

    Usage:
        @require_customer_only()
        def client_dashboard(request):
            pass
    """

    def check_customer(user):
        if not user.is_authenticated:
            return False

        # Explicitly block staff users
        if user.is_staff:
            logger.warning(
                f"Access denied: Staff user {user.email} attempted to access customer-only resource"
            )
            return False

        # Check for customer role
        has_customer_role = user_has_role(user, "customer")

        if not has_customer_role:
            logger.warning(f"Access denied: User {user.email} lacks 'customer' role")

        return has_customer_role

    return user_passes_test(
        check_customer, login_url=login_url, redirect_field_name=REDIRECT_FIELD_NAME
    )


def require_staff_role(
    roles: Iterable[str] = None,
    login_url: str = "login_page",
    raise_exception: bool = False,
):
    """
    Decorator for backoffice views requiring is_staff=True AND specific role(s).

    This provides defense in depth:
    1. User must be marked as staff (is_staff=True)
    2. User must have at least one of the specified roles

    Args:
        roles: List of acceptable staff roles. If None, any staff user is allowed.
        login_url: URL to redirect unauthenticated users
        raise_exception: If True, raise PermissionDenied (403); if False (default), redirect

    Usage:
        @require_staff_role(['admin', 'manager'])
        def backoffice_view(request):
            pass

        # For API views, use raise_exception=True to get HTTP 403 responses
        @require_staff_role(['admin'], raise_exception=True)
        def api_view(request):
            pass
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if raise_exception:
                    raise PermissionDenied("Authentication required")
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse(login_url))

            # Must be staff
            if not request.user.is_staff and not request.user.is_superuser:
                logger.warning(
                    f"Access denied: Non-staff user {request.user.email} attempted to access backoffice"
                )
                if raise_exception:
                    raise PermissionDenied("Staff access required")
                from django.shortcuts import redirect
                from django.urls import reverse

                return redirect(reverse(login_url))

            # If no specific roles required, any staff is ok
            if roles is None:
                return view_func(request, *args, **kwargs)

            # Check specific roles
            has_permission = user_has_any_role(request.user, roles)

            if not has_permission:
                logger.warning(
                    f"Access denied: Staff user {request.user.email} lacks required roles {list(roles)}"
                )
                if raise_exception:
                    raise PermissionDenied(f"Required roles: {list(roles)}")
                from django.http import HttpResponseForbidden
                from django.shortcuts import redirect

                return HttpResponseForbidden("Insufficient permissions")

            return view_func(request, *args, **kwargs)

        return wrapped_view

    return decorator


# ============================================================================
# DJANGO REST FRAMEWORK PERMISSIONS
# ============================================================================


class HasRole(permissions.BasePermission):
    """
    DRF permission to check if user has a specific role.

    Usage:
        class MyViewSet(viewsets.ModelViewSet):
            permission_classes = [IsAuthenticated, HasRole]
            required_role = 'admin'

    Or with custom role:
        permission_classes = [IsAuthenticated, HasRole]

        def get_permissions(self):
            return [perm() for perm in self.permission_classes]

        def check_permissions(self, request):
            for permission in self.get_permissions():
                if isinstance(permission, HasRole):
                    permission.required_role = 'manager'
                if not permission.has_permission(request, self):
                    self.permission_denied(request, message=getattr(permission, 'message', None))
    """

    message = _("You do not have the required role to access this resource.")
    required_role = None  # Must be set by view or overridden

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        role = getattr(view, "required_role", self.required_role)

        if role is None:
            logger.error(
                f"HasRole permission used without required_role on {view.__class__.__name__}"
            )
            return False

        return user_has_role(request.user, role)


class HasAnyRole(permissions.BasePermission):
    """
    DRF permission to check if user has any of the specified roles.

    Usage:
        class MyViewSet(viewsets.ModelViewSet):
            permission_classes = [IsAuthenticated, HasAnyRole]
            required_roles = ['admin', 'manager']
    """

    message = _("You do not have any of the required roles to access this resource.")
    required_roles = None  # Must be set by view

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        roles = getattr(view, "required_roles", self.required_roles)

        if roles is None:
            logger.error(
                f"HasAnyRole permission used without required_roles on {view.__class__.__name__}"
            )
            return False

        return user_has_any_role(request.user, roles)


class IsCustomerOnly(permissions.BasePermission):
    """
    DRF permission to ensure user is a customer and NOT staff.

    Usage:
        class ClientOrderViewSet(viewsets.ModelViewSet):
            permission_classes = [IsAuthenticated, IsCustomerOnly]
    """

    message = _("This resource is only accessible to customers.")

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        # Block staff
        if request.user.is_staff:
            logger.warning(
                f"Access denied: Staff user {request.user.email} attempted customer-only API"
            )
            return False

        return user_has_role(request.user, "customer")


class IsStaffWithRole(permissions.BasePermission):
    """
    DRF permission requiring is_staff=True AND specific role(s).

    Usage:
        class BackofficeViewSet(viewsets.ModelViewSet):
            permission_classes = [IsAuthenticated, IsStaffWithRole]
            required_staff_roles = ['admin', 'dispatcher']
    """

    message = _("This resource requires staff privileges with specific roles.")
    required_staff_roles = None

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False

        if not request.user.is_staff and not request.user.is_superuser:
            return False

        roles = getattr(view, "required_staff_roles", self.required_staff_roles)

        if roles is None:
            # If no specific roles, any staff is OK
            return True

        return user_has_any_role(request.user, roles)


# ============================================================================
# BACKWARD COMPATIBILITY
# ============================================================================

# Alias old function for backward compatibility
has_role = user_has_role
