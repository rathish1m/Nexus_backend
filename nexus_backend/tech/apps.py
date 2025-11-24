from django.apps import AppConfig


class TechConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tech"

    def ready(self):
        # import signals to register receivers
        try:
            from . import signals  # noqa: F401
        except Exception:
            pass
