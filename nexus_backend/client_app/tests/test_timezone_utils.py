import pytest
from datetime import timedelta

from django.utils import timezone

from client_app.services.utils.timezone_utils import get_expiry_time


@pytest.mark.django_db
def test_get_expiry_time_returns_future_datetime_for_valid_coords(monkeypatch):
    """
    For valid coordinates where a timezone name is found, get_expiry_time should
    return a timezone-aware datetime approximately one hour in the future.
    """

    class DummyTF:
        def timezone_at(self, lng, lat):
            # Return a known timezone regardless of input for determinism
            return "UTC"

    # Freeze "now" to make the test deterministic
    fixed_now = timezone.now()

    monkeypatch.setattr(
        "client_app.services.utils.timezone_utils.TimezoneFinder",
        lambda: DummyTF(),
    )
    monkeypatch.setattr(
        "client_app.services.utils.timezone_utils.timezone.now",
        lambda: fixed_now,
    )

    expires_at = get_expiry_time(lat=0.0, lng=0.0)

    assert expires_at.tzinfo is not None
    assert expires_at == timezone.localtime(
        fixed_now, timezone.get_current_timezone()
    ) + timedelta(hours=1)


@pytest.mark.django_db
def test_get_expiry_time_falls_back_when_timezone_not_found(monkeypatch):
    """
    When TimezoneFinder returns None, get_expiry_time should fall back to
    timezone.now() + 1 hour.
    """

    class DummyTF:
        def timezone_at(self, lng, lat):
            return None

    fixed_now = timezone.now()

    monkeypatch.setattr(
        "client_app.services.utils.timezone_utils.TimezoneFinder",
        lambda: DummyTF(),
    )
    monkeypatch.setattr(
        "client_app.services.utils.timezone_utils.timezone.now",
        lambda: fixed_now,
    )

    expires_at = get_expiry_time(lat=0.0, lng=0.0)

    assert expires_at.tzinfo is not None
    assert expires_at == fixed_now + timedelta(hours=1)
