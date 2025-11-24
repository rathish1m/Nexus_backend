from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task

from django.db import transaction
from django.utils import timezone

from main.models import InstallationActivity

from . import signals
from .models import Feedback, FeedbackReminderLog
from .notifications import notify_client_on_lock, send_feedback_reminder
from .services import build_diff, log_feedback_action

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    ignore_result=False,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def lock_expired_feedbacks(self):
    now = timezone.now()
    queryset = Feedback.objects.select_related("installation", "customer").filter(
        status__in=[Feedback.Status.SUBMITTED, Feedback.Status.EDITED],
        edit_until__isnull=False,
        edit_until__lte=now,
    )
    locked = 0
    for feedback in queryset:
        with transaction.atomic():
            before = Feedback.objects.get(pk=feedback.pk)
            feedback.status = Feedback.Status.LOCKED
            feedback.locked_at = now
            feedback.save(update_fields=["status", "locked_at", "updated_at"])
            diff = build_diff(
                before,
                feedback,
                ["status", "locked_at"],
            )
            log_feedback_action(
                feedback=feedback,
                actor=None,
                action="locked",
                changes=diff,
            )
        signals.feedback_locked.send(sender=Feedback, feedback=feedback, user=None)
        notify_client_on_lock(feedback)
        locked += 1
    logger.info("Auto-locked %s feedback(s)", locked)
    return {"locked": locked}


@shared_task(
    bind=True,
    ignore_result=False,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def send_feedback_reminders(self):
    from django.conf import settings

    cfg = getattr(settings, "FEEDBACK_SETTINGS", {})
    days = int(cfg.get("REMINDER_DAYS_AFTER_JOB", 3))
    if days <= 0:
        return {"reminded": 0}

    cutoff = timezone.now() - timedelta(days=days)

    installations = (
        InstallationActivity.objects.select_related("order", "order__user")
        .filter(
            completed_at__isnull=False,
            completed_at__lte=cutoff,
            feedback__isnull=True,
        )
        .exclude(feedback_reminder__isnull=False)
    )

    reminded = 0
    for installation in installations:
        order = installation.order
        if not order or not order.user or not order.user.email:
            continue
        try:
            send_feedback_reminder(installation)
            FeedbackReminderLog.objects.create(installation=installation)
            reminded += 1
        except Exception:
            logger.exception(
                "Failed to send feedback reminder for job %s", installation.pk
            )
    logger.info("Sent %s feedback reminder(s)", reminded)
    return {"reminded": reminded}
