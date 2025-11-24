from django.contrib import admin

from .models import Feedback, FeedbackAttachment, FeedbackAuditLog


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "installation",
        "customer",
        "rating",
        "status",
        "pinned",
        "internal_flag",
        "edit_until",
        "updated_at",
    )
    list_filter = ("status", "pinned", "internal_flag", "created_at")
    search_fields = (
        "installation__order__order_reference",
        "customer__email",
        "customer__full_name",
    )
    readonly_fields = ("created_at", "updated_at", "locked_at")


@admin.register(FeedbackAttachment)
class FeedbackAttachmentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "feedback",
        "filename",
        "content_type",
        "file_size",
        "uploaded_at",
    )
    search_fields = ("filename", "feedback__installation__order__order_reference")


@admin.register(FeedbackAuditLog)
class FeedbackAuditLogAdmin(admin.ModelAdmin):
    list_display = ("id", "feedback", "action", "actor", "created_at")
    search_fields = (
        "feedback__installation__order__order_reference",
        "action",
        "actor__email",
    )
    list_filter = ("action", "created_at")
