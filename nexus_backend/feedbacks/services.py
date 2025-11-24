from __future__ import annotations

import datetime
from collections.abc import Iterable
from decimal import Decimal
from typing import Any, Dict, Optional

import bleach

from django.conf import settings
from django.utils import timezone

from .models import Feedback, FeedbackAuditLog


def feedback_settings() -> dict[str, Any]:
    return getattr(settings, "FEEDBACK_SETTINGS", {})


def sanitize_markdown(raw_comment: str) -> str:
    cfg = feedback_settings()
    allowed_tags = cfg.get("SANITIZE_ALLOWED_TAGS", [])
    allowed_attrs = cfg.get("SANITIZE_ALLOWED_ATTRIBUTES", {})
    cleaned = bleach.clean(
        raw_comment or "",
        tags=allowed_tags,
        attributes=allowed_attrs,
        strip=True,
    )
    return cleaned.strip()


def compute_edit_deadline(
    completion_ts,
    *,
    submitted_at=None,
) -> Optional[timezone.datetime]:
    cfg = feedback_settings()
    base = cfg.get("EDIT_WINDOW_BASE", "completion").lower()
    days = int(cfg.get("DEFAULT_EDIT_WINDOW_DAYS", 7))
    base_ts = completion_ts
    if base == "submission" and submitted_at:
        base_ts = submitted_at
    if not base_ts:
        return None
    return base_ts + timezone.timedelta(days=days)


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime.datetime):
        if timezone.is_naive(value):
            value = timezone.make_aware(value, timezone.get_current_timezone())
        return timezone.localtime(value).isoformat()
    if isinstance(value, datetime.date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def build_diff(
    before: Feedback, after: Feedback, fields: Iterable[str]
) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    for field in fields:
        old_value = getattr(before, field, None)
        new_value = getattr(after, field, None)
        if old_value != new_value:
            delta[field] = {
                "from": _serialize_value(old_value),
                "to": _serialize_value(new_value),
            }
    return delta


def log_feedback_action(
    *,
    feedback: Feedback,
    actor,
    action: str,
    changes: Optional[Dict[str, Any]] = None,
) -> FeedbackAuditLog:
    return FeedbackAuditLog.objects.create(
        feedback=feedback,
        actor=actor,
        action=action,
        changes=changes or {},
    )
