from django.apps import AppConfig


class FeedbacksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "feedbacks"
    verbose_name = "Client Feedback"

    def ready(self) -> None:
        # Import signal handlers
        from . import signals  # noqa: F401
