"""
Shared Test Fixtures
====================

This module provides pytest fixtures shared across all test modules.

Available Fixtures:
------------------
- db: Database access fixture
- client: Django test client
- api_client: DRF API client
- authenticated_client: Client with authenticated user
- admin_client: Client with admin user
- mock_flexpay: Mocked FlexPay API
- mock_twilio: Mocked Twilio API
- mock_s3: Mocked AWS S3/Spaces
- freeze_time: Time freezing utility

Usage:
-----
def test_example(authenticated_client, mock_flexpay):
    response = authenticated_client.get('/api/orders/')
    assert response.status_code == 200
"""

from datetime import datetime, timedelta

import pytest
from freezegun import freeze_time as freezegun_freeze_time
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model
from django.test import Client

from main.models import PersonalKYC
from tests.mocks.aws import AWSS3Mock
from tests.mocks.flexpay import FlexPayMock
from tests.mocks.twilio import TwilioMock

User = get_user_model()


# ============================================================================
# DATABASE FIXTURES
# ============================================================================


@pytest.fixture
def db_access(db):
    """Explicit database access fixture"""
    return db


# ============================================================================
# CLIENT FIXTURES
# ============================================================================


@pytest.fixture
def client():
    """Django test client"""
    return Client()


@pytest.fixture
def api_client():
    """DRF API client"""
    return APIClient()


@pytest.fixture
def user(db):
    """Create regular user"""
    user = User.objects.create_user(
        username="testuser",
        email="testuser@nexus.test",
        password="TestPass123!",
        first_name="Test",
        last_name="User",
    )
    # Assign application-level role using JSON roles field
    if hasattr(user, "roles"):
        # Customer-facing role for client portal
        user.roles = ["customer"]
        user.save(update_fields=["roles"])
    return user


@pytest.fixture
def admin_user(db):
    """Create admin user"""
    return User.objects.create_superuser(
        username="admin",
        email="admin@nexus.test",
        password="AdminPass123!",
        first_name="Admin",
        last_name="User",
    )


@pytest.fixture
def staff_user(db):
    """Create staff user"""
    user = User.objects.create_user(
        username="staffuser",
        email="staff@nexus.test",
        password="StaffPass123!",
        first_name="Staff",
        last_name="User",
    )
    user.is_staff = True
    if hasattr(user, "roles"):
        # Grant admin/compliance roles so require_staff_role checks pass in tests
        user.roles = ["admin", "compliance"]
    user.save()
    return user


@pytest.fixture
def authenticated_client(client, user):
    """Client with authenticated regular user"""
    client.force_login(user)
    # Ensure KYC is approved so customer portal views (dashboard, etc.)
    # allow full access in tests.
    PersonalKYC.objects.get_or_create(user=user, defaults={"status": "approved"})
    return client


@pytest.fixture
def admin_client(client, admin_user):
    """Client with authenticated admin user"""
    client.force_login(admin_user)
    return client


@pytest.fixture
def staff_client(client, staff_user):
    """Client with authenticated staff user"""
    client.force_login(staff_user)
    return client


@pytest.fixture
def authenticated_api_client(api_client, user):
    """API client with authenticated regular user"""
    api_client.force_authenticate(user=user)
    return api_client


@pytest.fixture
def admin_api_client(api_client, admin_user):
    """API client with authenticated admin user"""
    api_client.force_authenticate(user=admin_user)
    return api_client


# ============================================================================
# EXTERNAL SERVICE MOCKS
# ============================================================================


@pytest.fixture
def mock_flexpay(responses):
    """Mock FlexPay payment gateway"""
    mock = FlexPayMock()
    mock.register_responses(responses)
    return mock


@pytest.fixture
def mock_twilio(monkeypatch):
    """Mock Twilio SMS service"""
    mock = TwilioMock()
    # Patch Twilio client initialization
    monkeypatch.setattr("twilio.rest.Client", lambda *args, **kwargs: mock)
    return mock


@pytest.fixture
def mock_s3(monkeypatch):
    """Mock AWS S3/DigitalOcean Spaces"""
    mock = AWSS3Mock()
    # Patch boto3 client initialization
    monkeypatch.setattr(
        "boto3.client", lambda service, **kwargs: mock if service == "s3" else None
    )
    return mock


# ============================================================================
# TIME FIXTURES
# ============================================================================


@pytest.fixture
def freeze_time():
    """Freeze time utility"""

    def _freeze(time_to_freeze=None):
        if time_to_freeze is None:
            time_to_freeze = datetime.now()
        return freezegun_freeze_time(time_to_freeze)

    return _freeze


@pytest.fixture
def now():
    """Current datetime fixture"""
    return datetime.now()


@pytest.fixture
def today():
    """Current date fixture"""
    return datetime.now().date()


@pytest.fixture
def tomorrow():
    """Tomorrow's date fixture"""
    return (datetime.now() + timedelta(days=1)).date()


@pytest.fixture
def yesterday():
    """Yesterday's date fixture"""
    return (datetime.now() - timedelta(days=1)).date()


# ============================================================================
# CLEANUP FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def reset_mocks():
    """Auto-reset all mocks after each test"""
    yield
    # Reset happens automatically via fixture scope


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Django cache after each test"""
    from django.core.cache import cache

    yield
    cache.clear()


# ============================================================================
# SETTINGS FIXTURES
# ============================================================================


@pytest.fixture
def settings_with_debug(settings):
    """Settings with DEBUG=True"""
    settings.DEBUG = True
    return settings


@pytest.fixture
def settings_no_debug(settings):
    """Settings with DEBUG=False"""
    settings.DEBUG = False
    return settings


# ============================================================================
# EMAIL FIXTURES
# ============================================================================


@pytest.fixture
def mailoutbox(settings):
    """Access to sent emails"""
    from django.core import mail

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    return mail.outbox


# ============================================================================
# FILE UPLOAD FIXTURES
# ============================================================================


@pytest.fixture
def sample_image():
    """Create sample image for testing file uploads"""
    import io

    from PIL import Image

    image = Image.new("RGB", (100, 100), color="red")
    image_file = io.BytesIO()
    image.save(image_file, format="PNG")
    image_file.seek(0)
    image_file.name = "test_image.png"
    return image_file


@pytest.fixture
def sample_pdf():
    """Create sample PDF for testing document uploads"""
    import io

    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    pdf.drawString(100, 750, "Test PDF Document")
    pdf.save()
    buffer.seek(0)
    buffer.name = "test_document.pdf"
    return buffer
