from __future__ import annotations

from django import template

register = template.Library()


@register.filter(name="add_class")
def add_class(bound_field, css_classes: str):
    """
    Add CSS classes to a Django BoundField's widget when rendering.

    Usage in templates:
        {{ form.field|add_class:"w-full form-control" }}
    """
    try:
        base = (bound_field.field.widget.attrs or {}).get("class", "").strip()
        merged = (f"{base} {css_classes}" if base else css_classes).strip()
        return bound_field.as_widget(attrs={"class": merged})
    except Exception:
        # Fallback: return the field unmodified if something unexpected occurs
        return bound_field
