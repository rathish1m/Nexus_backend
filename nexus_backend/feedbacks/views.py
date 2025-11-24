from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from feedbacks import signals
from feedbacks.notifications import (
    notify_client_on_lock,
    notify_client_on_staff_reply,
    notify_feedback_submitted,
)
from feedbacks.permissions import IsFeedbackStaff, user_is_feedback_staff
from feedbacks.serializers import FeedbackAttachmentSerializer, FeedbackSerializer
from feedbacks.services import build_diff, log_feedback_action, sanitize_markdown

from .models import Feedback, FeedbackAttachment


class FeedbackViewSet(
    mixins.RetrieveModelMixin,
    mixins.ListModelMixin,
    viewsets.GenericViewSet,
):
    queryset = (
        Feedback.objects.select_related(
            "installation",
            "installation__order",
            "customer",
        )
        .prefetch_related(
            "attachments",
            Prefetch("audit_logs"),
        )
        .all()
    )
    serializer_class = FeedbackSerializer
    permission_classes = [IsAuthenticated]

    def get_success_headers(self, data):
        """
        Minimal implementation to satisfy DRF create() semantics.

        We don't need a Location header for this API, so we simply
        return an empty dict instead of relying on mixins.CreateModelMixin.
        """
        return {}

    def get_queryset(self):
        qs = super().get_queryset()
        user = self.request.user
        if user_is_feedback_staff(user):
            # Optional filters
            params = self.request.query_params
            status_filter = params.get("status")
            if status_filter:
                qs = qs.filter(status=status_filter)
            job = params.get("job")
            if job:
                qs = qs.filter(installation_id=job)
            rating = params.get("rating")
            if rating and rating.isdigit():
                qs = qs.filter(rating=int(rating))
            search = params.get("q")
            if search:
                qs = qs.filter(
                    Q(installation__order__order_reference__icontains=search)
                    | Q(customer__email__icontains=search)
                    | Q(customer__full_name__icontains=search)
                )
            return qs
        # Only own feedback
        return qs.filter(customer=user)

    def get_permissions(self):
        if self.action in {"lock", "pin", "reply", "list"}:
            permission_classes = [IsAuthenticated, IsFeedbackStaff]
        elif self.action in {"retrieve"}:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        return [perm() for perm in permission_classes]

    def get_throttles(self):
        if self.action in {"create"}:
            self.throttle_scope = "feedback_mutation"
        elif self.action in {"attachments"}:
            self.throttle_scope = "feedback_attachment"
        elif self.action in {"lock", "pin", "reply"}:
            self.throttle_scope = "feedback_staff_action"
        return super().get_throttles()

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        feedback = serializer.save()
        created_flag = getattr(serializer, "_created", True)
        if created_flag and self.request.user == feedback.customer:
            notify_feedback_submitted(feedback)
            signals.feedback_submitted.send(
                sender=Feedback, feedback=feedback, user=self.request.user
            )
        headers = self.get_success_headers(serializer.data)
        return Response(
            self.get_serializer(feedback).data,
            status=status.HTTP_201_CREATED if created_flag else status.HTTP_200_OK,
            headers=headers,
        )

    @action(
        detail=False,
        methods=["get"],
        url_path="my",
        permission_classes=[IsAuthenticated],
    )
    def my_feedback(self, request, *args, **kwargs):
        job_id = request.query_params.get("job")
        if not job_id:
            return Response(
                {"detail": _("Query parameter `job` is required.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        feedback = (
            self.get_queryset()
            .filter(customer=request.user, installation_id=job_id)
            .first()
        )
        if not feedback:
            raise Http404(_("Feedback not found."))
        serializer = self.get_serializer(feedback)
        return Response(serializer.data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsFeedbackStaff],
        url_path="lock",
    )
    @transaction.atomic
    def lock(self, request, pk=None):
        feedback = self.get_object()
        if feedback.status == Feedback.Status.LOCKED:
            return Response({"detail": _("Already locked.")}, status=status.HTTP_200_OK)
        before = Feedback.objects.get(pk=feedback.pk)
        feedback.status = Feedback.Status.LOCKED
        feedback.locked_at = timezone.now()
        feedback.edit_until = feedback.locked_at
        feedback.save(update_fields=["status", "locked_at", "edit_until", "updated_at"])
        diff = build_diff(
            before,
            feedback,
            ["status", "locked_at", "edit_until"],
        )
        log_feedback_action(
            feedback=feedback,
            actor=request.user,
            action="locked",
            changes=diff,
        )
        signals.feedback_locked.send(
            sender=Feedback, feedback=feedback, user=request.user
        )
        notify_client_on_lock(feedback)
        return Response(self.get_serializer(feedback).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsFeedbackStaff],
        url_path="pin",
    )
    @transaction.atomic
    def pin(self, request, pk=None):
        feedback = self.get_object()
        before = Feedback.objects.get(pk=feedback.pk)
        pinned = request.data.get("pinned")
        pinned_value = True if pinned in (True, "true", "1", 1, "True") else False
        feedback.pinned = pinned_value
        feedback.save(update_fields=["pinned", "updated_at"])
        diff = build_diff(before, feedback, ["pinned"])
        if diff:
            log_feedback_action(
                feedback=feedback,
                actor=request.user,
                action="pinned",
                changes=diff,
            )
        return Response(self.get_serializer(feedback).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated, IsFeedbackStaff],
        url_path="reply",
    )
    @transaction.atomic
    def reply(self, request, pk=None):
        feedback = self.get_object()
        reply_text = (request.data.get("reply") or "").strip()
        if len(reply_text) > 1000:
            return Response(
                {"detail": _("Reply is too long (1000 characters max).")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        before = Feedback.objects.get(pk=feedback.pk)
        feedback.staff_reply = sanitize_markdown(reply_text)
        feedback.save(update_fields=["staff_reply", "updated_at"])
        diff = build_diff(before, feedback, ["staff_reply"])
        if diff:
            log_feedback_action(
                feedback=feedback,
                actor=request.user,
                action="reply",
                changes=diff,
            )
        signals.staff_replied.send(
            sender=Feedback, feedback=feedback, user=request.user
        )
        notify_client_on_staff_reply(feedback)
        return Response(self.get_serializer(feedback).data)

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[IsAuthenticated],
        url_path="attachments",
    )
    @transaction.atomic
    def attachments(self, request, pk=None):
        feedback = self.get_object()
        if feedback.customer_id != request.user.pk and not user_is_feedback_staff(
            request.user
        ):
            return Response(
                {"detail": _("Action not allowed.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        if feedback.is_locked and not user_is_feedback_staff(request.user):
            return Response(
                {"detail": _("Feedback is locked.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = FeedbackAttachmentSerializer(
            data=request.data,
            context={"feedback": feedback, "request": request},
        )
        serializer.is_valid(raise_exception=True)
        attachment = serializer.save()
        return Response(
            FeedbackAttachmentSerializer(attachment).data,
            status=status.HTTP_201_CREATED,
        )


class FeedbackAttachmentDetailView(viewsets.ViewSet):
    permission_classes = [IsAuthenticated]
    throttle_scope = "feedback_attachment"

    def destroy(self, request, pk=None):
        try:
            attachment = FeedbackAttachment.objects.select_related("feedback").get(
                pk=pk
            )
        except FeedbackAttachment.DoesNotExist as exc:
            raise Http404 from exc
        feedback = attachment.feedback
        if feedback.customer_id != request.user.pk and not user_is_feedback_staff(
            request.user
        ):
            return Response(
                {"detail": _("Action not allowed.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        if feedback.is_locked and not user_is_feedback_staff(request.user):
            return Response(
                {"detail": _("Feedback is locked.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        filename = attachment.filename
        attachment.delete()
        log_feedback_action(
            feedback=feedback,
            actor=request.user,
            action="attachment_deleted",
            changes={"filename": filename},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
