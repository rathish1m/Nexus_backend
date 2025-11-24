from django import template

register = template.Library()


@register.filter
def has_role(user, role):
    """Return True if the user has the given role (case-insensitive)."""
    if not user.is_authenticated:
        return False
    roles = getattr(user, "roles", []) or []
    roles = [str(r).lower() for r in roles]
    return role.lower() in roles
