from datetime import timedelta

import pytest
from rest_framework.test import APIClient

from django.utils import timezone

from feedbacks.models import Feedback
from main.factories import (
    InstallationActivityFactory,
    OrderFactory,
    StaffUserFactory,
    UserFactory,
)


@pytest.mark.django_db
def test_client_can_submit_feedback(settings):
    settings.FEEDBACK_SETTINGS["DEFAULT_EDIT_WINDOW_DAYS"] = 7
    user = UserFactory()
    order = OrderFactory(user=user)
    installation = InstallationActivityFactory(
        order=order,
        completed_at=timezone.now() - timedelta(days=1),
        status="completed",
    )

    client = APIClient()
    client.force_authenticate(user=user)

    payload = {"job_id": installation.id, "rating": 5, "comment": "Service impeccable"}
    response = client.post("/api/feedbacks/", payload, format="json")

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "submitted"
    assert body["rating"] == 5
    assert body["editable_until"] is not None
    feedback = Feedback.objects.get(installation=installation)
    assert feedback.customer == user


@pytest.mark.django_db
def test_client_cannot_submit_feedback_for_other_job():
    owner = UserFactory()
    other_user = UserFactory()
    order = OrderFactory(user=owner)
    installation = InstallationActivityFactory(order=order)

    client = APIClient()
    client.force_authenticate(user=other_user)

    response = client.post(
        "/api/feedbacks/",
        {"job_id": installation.id, "rating": 4, "comment": "Test"},
        format="json",
    )

    assert response.status_code == 400
    assert Feedback.objects.count() == 0


@pytest.mark.django_db
def test_staff_can_lock_feedback():
    customer = UserFactory()
    order = OrderFactory(user=customer)
    installation = InstallationActivityFactory(order=order)
    feedback = Feedback.objects.create(
        installation=installation,
        customer=customer,
        rating=4,
        comment="OK",
        sanitized_comment="OK",
        status=Feedback.Status.SUBMITTED,
        edit_until=timezone.now() + timedelta(days=1),
    )

    staff = StaffUserFactory()
    staff.roles = ["support"]
    staff.save()

    client = APIClient()
    client.force_authenticate(user=staff)

    response = client.post(f"/api/feedbacks/{feedback.pk}/lock/", {}, format="json")

    assert response.status_code == 200
    feedback.refresh_from_db()
    assert feedback.status == Feedback.Status.LOCKED
    assert feedback.locked_at is not None


@pytest.mark.django_db
def test_my_feedback_endpoint_returns_feedback():
    user = UserFactory()
    order = OrderFactory(user=user)
    installation = InstallationActivityFactory(order=order)
    Feedback.objects.create(
        installation=installation,
        customer=user,
        rating=5,
        comment="Great",
        sanitized_comment="Great",
        status=Feedback.Status.SUBMITTED,
        edit_until=timezone.now() + timedelta(days=7),
    )

    client = APIClient()
    client.force_authenticate(user=user)
    response = client.get(f"/api/feedbacks/my/?job={installation.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["rating"] == 5
    assert data["job"] == installation.id
