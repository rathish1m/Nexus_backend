from __future__ import annotations

import logging
from typing import Iterable

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils import timezone

from .models import Feedback

logger = logging.getLogger(__name__)


def _get_recipients() -> Iterable[str]:
    cfg = getattr(settings, "FEEDBACK_SETTINGS", {})
    recipients = cfg.get("NOTIFY_RECIPIENTS") or settings.ADMIN_NOTIFICATION_EMAILS
    return [r for r in recipients if r]


def notify_feedback_submitted(feedback: Feedback) -> None:
    recipients = list(_get_recipients())
    if not recipients:
        return
    try:
        order = getattr(feedback.installation, "order", None)
        subject = f"[Nexus] New customer feedback for job {order.order_reference if order else feedback.installation_id}"
        context = {
            "feedback": feedback,
            "order": order,
            "submitted_at": timezone.localtime(feedback.created_at),
            "site_url": settings.SITE_URL.rstrip("/"),
        }
        body = render_to_string("emails/feedback_submitted.txt", context)
        send_mail(
            subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True
        )
    except Exception:
        logger.exception("Failed to send feedback submitted notification")


def notify_client_on_staff_reply(feedback: Feedback) -> None:
    cfg = getattr(settings, "FEEDBACK_SETTINGS", {})
    if not cfg.get("ENABLE_STAFF_REPLY_EMAIL"):
        return
    if not feedback.customer or not feedback.customer.email:
        return
    try:
        order = getattr(feedback.installation, "order", None)
        subject = "Nexus team replied to your feedback"
        context = {
            "feedback": feedback,
            "order": order,
            "reply_at": timezone.localtime(feedback.updated_at),
            "site_url": settings.SITE_URL.rstrip("/"),
        }
        body = render_to_string("emails/feedback_staff_reply.txt", context)
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [feedback.customer.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send feedback reply notification")


def notify_client_on_lock(feedback: Feedback) -> None:
    cfg = getattr(settings, "FEEDBACK_SETTINGS", {})
    if not cfg.get("ENABLE_LOCK_EMAIL"):
        return
    if not feedback.customer or not feedback.customer.email:
        return
    order = getattr(feedback.installation, "order", None)
    subject = "Your feedback is now locked"
    context = {
        "feedback": feedback,
        "order": order,
        "locked_at": timezone.localtime(feedback.locked_at or feedback.updated_at),
        "site_url": settings.SITE_URL.rstrip("/"),
    }
    body = render_to_string("emails/feedback_locked.txt", context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [feedback.customer.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send feedback lock notification")


def send_feedback_reminder(installation) -> None:
    order = getattr(installation, "order", None)
    if not order or not order.user or not order.user.email:
        return
    context = {
        "order": order,
        "installation": installation,
        "deadline": installation.completed_at,
        "feedback_url": f"{settings.SITE_URL.rstrip('/')}/client/feedbacks/{installation.pk}/",
        "site_url": settings.SITE_URL.rstrip("/"),
    }
    subject = "We would love to hear your feedback"
    body = render_to_string("emails/feedback_reminder.txt", context)
    try:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            [order.user.email],
            fail_silently=True,
        )
    except Exception:
        logger.exception("Failed to send feedback reminder")
