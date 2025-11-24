from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import FeedbackAttachmentDetailView, FeedbackViewSet

router = DefaultRouter()
router.register("", FeedbackViewSet, basename="feedbacks")


feedback_attachment = FeedbackAttachmentDetailView.as_view({"delete": "destroy"})

urlpatterns = [
    path("", include(router.urls)),
    path(
        "attachments/<int:pk>/",
        feedback_attachment,
        name="feedbacks-attachment-detail",
    ),
]
