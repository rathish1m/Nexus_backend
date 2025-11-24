import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")

app = Celery("nexus_backend")

# Load config from Django settings (CELERY_BROKER_URL, etc.)
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks in installed apps
app.autodiscover_tasks()

# Ensure our tasks module is registered
app.conf.imports = tuple(
    {*(app.conf.imports or ()), "nexus_backend.celery_tasks.tasks"}
)


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")


CELERY_BEAT_SCHEDULE = {
    "check-flexpay-transactions-every-5m": {
        "task": "nexus_backend.celery_tasks.tasks.check_flexpay_transactions",
        "schedule": 150.0,  # seconds
        "options": {"queue": "default"},
    },
    "cancel-expired-orders-every-5m": {
        "task": "nexus_backend.celery_tasks.tasks.cancel_expired_orders",
        "schedule": 300.0,
        "options": {"queue": "default"},
    },
    "generate-renewal-orders-every-morning": {
        "task": "subscriptions.generate_renewal_orders_daily",
        "schedule": 300.0,
        "options": {"queue": "default"},
    },
    "lock-feedbacks-daily": {
        "task": "feedbacks.tasks.lock_expired_feedbacks",
        "schedule": crontab(minute=0, hour=2),
        "options": {"queue": "default"},
    },
    "feedback-reminder-daily": {
        "task": "feedbacks.tasks.send_feedback_reminders",
        "schedule": crontab(minute=30, hour=9),
        "options": {"queue": "default"},
    },
}
