from __future__ import annotations

from rest_framework.permissions import BasePermission

from django.utils.translation import gettext_lazy as _

STAFF_ROLES = {"support", "qa", "admin"}


def user_is_feedback_staff(user) -> bool:
    if not user.is_authenticated:
        return False
    if user.is_superuser or user.is_staff:
        return True
    user_roles = set(getattr(user, "roles", []) or [])
    return bool(STAFF_ROLES & user_roles)


class IsFeedbackOwner(BasePermission):
    message = _("You can only manage your own feedback.")

    def has_object_permission(self, request, view, obj) -> bool:
        return obj.customer_id == request.user.pk


class IsFeedbackStaff(BasePermission):
    message = _("This action is restricted to internal staff.")

    def has_permission(self, request, view) -> bool:
        return user_is_feedback_staff(request.user)

    def has_object_permission(self, request, view, obj) -> bool:
        return user_is_feedback_staff(request.user)
