from __future__ import annotations

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from nexus_backend.storage_backend import PrivateMediaStorage

User = settings.AUTH_USER_MODEL


class Feedback(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        EDITED = "edited", "Edited"
        LOCKED = "locked", "Locked"
        DELETED = "deleted", "Deleted"

    installation = models.OneToOneField(
        "main.InstallationActivity",
        on_delete=models.CASCADE,
        related_name="feedback",
    )
    customer = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="feedbacks"
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    comment = models.TextField(blank=True, default="")
    sanitized_comment = models.TextField(blank=True, default="")
    is_public = models.BooleanField(default=False)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT
    )
    edit_until = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedbacks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    internal_flag = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)
    staff_reply = models.TextField(blank=True, default="")
    moderation_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["installation", "customer"]),
            models.Index(fields=["status"]),
            models.Index(fields=["created_at"]),
        ]

    def __str__(self) -> str:
        return f"Feedback #{self.pk or 'new'} for job {self.installation_id}"

    @property
    def is_locked(self) -> bool:
        if self.status == self.Status.LOCKED:
            return True
        if self.edit_until and timezone.now() >= self.edit_until:
            return True
        return False


def _feedback_attachment_path(instance: "FeedbackAttachment", filename: str) -> str:
    return f"feedbacks/{instance.feedback_id}/{filename}"


class FeedbackAttachment(models.Model):
    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name="attachments"
    )
    file = models.FileField(
        upload_to=_feedback_attachment_path,
        storage=PrivateMediaStorage()
        if getattr(settings, "USE_SPACES", False)
        else None,
    )
    filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="feedback_attachments"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self) -> str:
        return f"Attachment {self.filename} for feedback {self.feedback_id}"


class FeedbackAuditLog(models.Model):
    ACTION_CHOICES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("locked", "Locked"),
        ("pinned", "Pinned"),
        ("reply", "Staff Reply"),
        ("moderated", "Moderated"),
        ("attachment_added", "Attachment Added"),
        ("attachment_deleted", "Attachment Deleted"),
    ]

    feedback = models.ForeignKey(
        Feedback, on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="feedback_audit_entries",
    )
    action = models.CharField(max_length=64, choices=ACTION_CHOICES)
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Audit({self.feedback_id}, {self.action})"


class FeedbackReminderLog(models.Model):
    installation = models.OneToOneField(
        "main.InstallationActivity",
        on_delete=models.CASCADE,
        related_name="feedback_reminder",
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    reminder_count = models.PositiveSmallIntegerField(default=1)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self) -> str:
        return f"Reminder for job {self.installation_id} ({self.reminder_count})"
