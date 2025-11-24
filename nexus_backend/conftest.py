"""
conftest.py - Pytest Configuration
===================================

This file contains pytest configuration and shared fixtures for all tests.

Test Setup:
----------
- Django settings configuration
- Database setup (PostgreSQL with PostGIS)
- External service mocking (FlexPay, Twilio, AWS)
- Common fixtures for users, clients, authentication
- Time freezing utilities
- File upload helpers

Markers:
-------
- unit: Fast unit tests (< 100ms)
- integration: Integration tests (< 1s)
- e2e: End-to-end tests (< 5s)
- slow: Tests that take > 1s
- external: Tests requiring external services (mocked in CI)
- database: Tests requiring database access

Running Tests:
-------------
pytest                          # Run all tests
pytest -m unit                  # Run only unit tests
pytest -m "not slow"            # Skip slow tests
pytest -k test_order            # Run tests matching pattern
pytest --cov=. --cov-report=html # Run with coverage
"""

import os
import sys
from pathlib import Path

# Add project root to Python path
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Set environment variables
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
os.environ.setdefault("TESTING", "True")

# Import pytest plugins / shared fixtures
# Load the shared fixtures defined in tests/fixtures/__init__.py
pytest_plugins = ["tests.fixtures"]


def pytest_configure(config):
    """Configure pytest"""
    # Set test database settings
    from django.conf import settings

    # Use in-memory database for faster tests (optional)
    # settings.DATABASES['default'] = {
    #     'ENGINE': 'django.db.backends.sqlite3',
    #     'NAME': ':memory:',
    # }
    # Disable migrations for faster tests
    settings.MIGRATION_MODULES = {
        "main": None,
        "client_app": None,
        "backoffice": None,
        "sales": None,
        "billing_management": None,
        "orders": None,
        "user": None,
        "site_survey": None,
        "tech": None,
    }

    # Use simple password hasher for faster tests
    settings.PASSWORD_HASHERS = [
        "django.contrib.auth.hashers.MD5PasswordHasher",
    ]

    # Disable debug toolbar in tests
    settings.DEBUG_TOOLBAR_CONFIG = {
        "SHOW_TOOLBAR_CALLBACK": lambda request: False,
    }

    # Use local memory cache
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        }
    }

    # Use console email backend
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

    # Disable Celery eager mode for tests
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

    # Set media root to temp directory
    import tempfile

    settings.MEDIA_ROOT = tempfile.mkdtemp()

    # Mock external services by default
    settings.MOCK_EXTERNAL_SERVICES = True


def pytest_collection_modifyitems(config, items):
    """Modify test collection"""
    import pytest

    # Add markers based on test location
    for item in items:
        # Add 'database' marker to tests using db fixture
        if "db" in item.fixturenames:
            item.add_marker(pytest.mark.database)

        # Add 'slow' marker to integration and e2e tests
        if "integration" in str(item.fspath) or "e2e" in str(item.fspath):
            item.add_marker(pytest.mark.slow)

        # Add module markers based on directory
        parts = Path(item.fspath).parts
        if "billing_management" in parts:
            item.add_marker(pytest.mark.billing)
        elif "site_survey" in parts:
            item.add_marker(pytest.mark.survey)
        elif "tech" in parts:
            item.add_marker(pytest.mark.installation)


def pytest_report_header(config):
    """Add custom header to pytest output"""
    return [
        "NEXUS Telecoms Backend - Test Suite",
        f"Python version: {sys.version.split()[0]}",
        "Django test environment configured",
    ]
