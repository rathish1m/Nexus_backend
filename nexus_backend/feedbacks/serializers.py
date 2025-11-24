from __future__ import annotations

from typing import Any

from rest_framework import serializers

from django.conf import settings
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from main.models import InstallationActivity

from .models import Feedback, FeedbackAttachment, FeedbackAuditLog
from .permissions import user_is_feedback_staff
from .services import (
    build_diff,
    compute_edit_deadline,
    log_feedback_action,
    sanitize_markdown,
)


class FeedbackAuditSerializer(serializers.ModelSerializer):
    actor = serializers.StringRelatedField()

    class Meta:
        model = FeedbackAuditLog
        fields = ("id", "action", "changes", "actor", "created_at")


class FeedbackAttachmentSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True)
    url = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = FeedbackAttachment
        fields = (
            "id",
            "file",
            "filename",
            "content_type",
            "file_size",
            "uploaded_at",
            "url",
        )
        read_only_fields = (
            "filename",
            "content_type",
            "file_size",
            "uploaded_at",
            "url",
        )

    def validate_file(self, file):
        cfg = getattr(settings, "FEEDBACK_SETTINGS", {})
        max_size = cfg.get("MAX_ATTACHMENT_SIZE", 5 * 1024 * 1024)
        if file.size > max_size:
            raise serializers.ValidationError(_("File is too large."))
        allowed_types = set(cfg.get("ALLOWED_ATTACHMENT_TYPES", []))
        content_type = file.content_type or ""
        if allowed_types and content_type not in allowed_types:
            raise serializers.ValidationError(_("File type is not allowed."))
        return file

    def create(self, validated_data):
        file = validated_data.pop("file")
        feedback: Feedback = self.context["feedback"]
        user = self.context["request"].user
        attachment = FeedbackAttachment.objects.create(
            feedback=feedback,
            file=file,
            filename=file.name,
            content_type=file.content_type or "",
            file_size=file.size,
            uploaded_by=user,
        )
        log_feedback_action(
            feedback=feedback,
            actor=user,
            action="attachment_added",
            changes={"filename": attachment.filename},
        )
        return attachment

    def get_url(self, obj: FeedbackAttachment) -> str | None:
        try:
            return obj.file.url
        except Exception:
            return None


class FeedbackSerializer(serializers.ModelSerializer):
    job_id = serializers.IntegerField(write_only=True)
    job = serializers.IntegerField(source="installation_id", read_only=True)
    editable_until = serializers.DateTimeField(source="edit_until", read_only=True)
    job_reference = serializers.SerializerMethodField()
    can_edit = serializers.SerializerMethodField()
    attachments = FeedbackAttachmentSerializer(many=True, read_only=True)
    audit_logs = FeedbackAuditSerializer(many=True, read_only=True)

    class Meta:
        model = Feedback
        fields = (
            "id",
            "job_id",
            "job_reference",
            "customer",
            "job",
            "rating",
            "comment",
            "sanitized_comment",
            "is_public",
            "status",
            "editable_until",
            "created_at",
            "updated_at",
            "pinned",
            "internal_flag",
            "staff_reply",
            "moderation_note",
            "can_edit",
            "attachments",
            "audit_logs",
        )
        read_only_fields = (
            "id",
            "customer",
            "status",
            "editable_until",
            "created_at",
            "updated_at",
            "pinned",
            "internal_flag",
            "staff_reply",
            "moderation_note",
            "sanitized_comment",
            "audit_logs",
        )

    def get_job_reference(self, obj: Feedback) -> str:
        order = getattr(obj.installation, "order", None)
        return getattr(order, "order_reference", "") if order else ""

    def get_can_edit(self, obj: Feedback) -> bool:
        request = self.context.get("request")
        if not request or not request.user.is_authenticated:
            return False
        if user_is_feedback_staff(request.user):
            return True
        if obj.customer_id != request.user.pk:
            return False
        if obj.status not in (Feedback.Status.SUBMITTED, Feedback.Status.EDITED):
            return False
        if obj.edit_until and timezone.now() >= obj.edit_until:
            return False
        return True

    def validate_job_id(self, job_id: int) -> int:
        try:
            installation = InstallationActivity.objects.select_related("order").get(
                pk=job_id
            )
        except InstallationActivity.DoesNotExist as exc:
            raise serializers.ValidationError(_("Installation not found.")) from exc

        request = self.context["request"]
        user_pk = request.user.pk
        if installation.order.user_id != user_pk and not user_is_feedback_staff(
            request.user
        ):
            raise serializers.ValidationError(
                _("You can only create feedback for your own installations.")
            )
        self.context["installation"] = installation
        return job_id

    def validate_comment(self, value: str) -> str:
        value = value or ""
        if len(value) > 2000:
            raise serializers.ValidationError(
                _("Comment exceeds the maximum length of 2000 characters.")
            )
        return value

    def create(self, validated_data: dict[str, Any]) -> Feedback:
        request = self.context["request"]
        installation: InstallationActivity = self.context["installation"]
        comment = validated_data.get("comment", "")
        sanitized = sanitize_markdown(comment)
        rating = validated_data["rating"]
        now = timezone.now()
        feedback, created = Feedback.objects.select_for_update().get_or_create(
            installation=installation,
            defaults={
                "customer": installation.order.user,
                "rating": rating,
                "comment": comment,
                "sanitized_comment": sanitized,
                "status": Feedback.Status.SUBMITTED,
                "created_by": request.user,
            },
        )
        self._created = created

        if created:
            edit_until = compute_edit_deadline(
                installation.completed_at or now, submitted_at=now
            )
            feedback.edit_until = edit_until
            feedback.save(update_fields=["edit_until"])
            log_feedback_action(
                feedback=feedback,
                actor=request.user,
                action="created",
                changes={
                    "rating": rating,
                    "comment": sanitized,
                },
            )
            self.instance = feedback
            return feedback

        # Update existing feedback (idempotent create)
        old_snapshot = Feedback.objects.get(pk=feedback.pk)
        if feedback.customer_id != request.user.pk and not user_is_feedback_staff(
            request.user
        ):
            raise serializers.ValidationError(_("Action not allowed."))
        if feedback.status not in (
            Feedback.Status.SUBMITTED,
            Feedback.Status.EDITED,
        ):
            raise serializers.ValidationError(_("Feedback is locked."))
        if (
            feedback.edit_until
            and not user_is_feedback_staff(request.user)
            and now >= feedback.edit_until
        ):
            raise serializers.ValidationError(_("The editing window has expired."))

        feedback.rating = rating
        feedback.comment = comment
        feedback.sanitized_comment = sanitized
        feedback.status = (
            Feedback.Status.EDITED
            if not user_is_feedback_staff(request.user)
            else feedback.status
        )
        if not feedback.edit_until:
            feedback.edit_until = compute_edit_deadline(
                installation.completed_at or now, submitted_at=feedback.created_at
            )
        feedback.save()

        diff = build_diff(
            old_snapshot,
            feedback,
            ["rating", "comment", "sanitized_comment", "status"],
        )
        if diff:
            log_feedback_action(
                feedback=feedback,
                actor=request.user,
                action="updated",
                changes=diff,
            )
        self._created = False
        self.instance = feedback
        return feedback

    def update(self, instance: Feedback, validated_data: dict[str, Any]) -> Feedback:
        # Staff-only moderate update
        request = self.context["request"]
        old_snapshot = Feedback.objects.get(pk=instance.pk)
        for field in ("rating", "comment", "is_public", "internal_flag"):
            if field in validated_data:
                setattr(instance, field, validated_data[field])
        if "comment" in validated_data:
            instance.sanitized_comment = sanitize_markdown(instance.comment)
        instance.save()
        diff = build_diff(
            old_snapshot,
            instance,
            ["rating", "comment", "sanitized_comment", "is_public", "internal_flag"],
        )
        if diff:
            log_feedback_action(
                feedback=instance,
                actor=request.user,
                action="moderated",
                changes=diff,
            )
        self.instance = instance
        return instance
