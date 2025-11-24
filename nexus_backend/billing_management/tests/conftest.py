"""
Pytest fixtures for billing_management tests.
"""

from decimal import Decimal

import pytest

from django.contrib.auth import get_user_model

from main.models import CompanySettings, Order

User = get_user_model()


@pytest.fixture
def user_factory(db):
    """Factory to create test users."""

    def _create_user(**kwargs):
        defaults = {
            "email": f"user_{kwargs.get('username', 'test')}@example.com",
            "username": kwargs.get("username", "testuser"),
            "password": "testpass123",
        }
        defaults.update(kwargs)
        return User.objects.create_user(**defaults)

    return _create_user


@pytest.fixture
def order_factory(db):
    """Factory to create test orders."""
    counter = 0

    def _create_order(**kwargs):
        nonlocal counter
        counter += 1
        defaults = {
            "order_reference": f"ORD-{counter:06d}",
            "total_price": Decimal("100.00"),
            "status": "confirmed",
        }
        defaults.update(kwargs)
        return Order.objects.create(**defaults)

    return _create_order


@pytest.fixture
def company_settings_factory(db):
    """Factory to create company settings."""

    def _create_company_settings(**kwargs):
        defaults = {
            "legal_name": "Test Company Ltd",
            "trade_name": "Test Corp",
            "city": "Test City",
            "country": "Test Country",
            "rccm": "TEST-RCCM-123",
            "vat_rate_percent": Decimal("16.00"),
            "excise_rate_percent": Decimal("10.00"),
        }
        defaults.update(kwargs)

        # Delete existing company settings (singleton pattern)
        CompanySettings.objects.all().delete()

        return CompanySettings.objects.create(**defaults)

    return _create_company_settings
