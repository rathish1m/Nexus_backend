"""
Test fixtures for site_survey tests
"""

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from main.models import Order, SubscriptionPlan, User
from site_survey.models import SiteSurvey


@pytest.fixture
def api_client():
    """Provide REST framework API client for API tests"""
    return APIClient()


@pytest.fixture
def survey_factory(db):
    """Factory function to create SiteSurvey objects for testing"""

    def _create_survey(**kwargs):
        # Create necessary related objects if they don't exist
        if "order" not in kwargs:
            # Create a unique user for each survey to avoid conflicts
            import uuid

            unique_id = str(uuid.uuid4())[:8]

            user = User.objects.create_user(
                username=f"test_user_{unique_id}",
                email=f"test_{unique_id}@example.com",
                full_name=f"Test User {unique_id}",
            )

            # Create a subscription plan
            plan, _ = SubscriptionPlan.objects.get_or_create(
                name="Test Plan",
                defaults={
                    "monthly_price_usd": Decimal("50.00"),
                    "standard_data_gb": 100,
                },
            )

            # Create a unique order for this survey
            # Ensure the order doesn't already have a survey
            # Create order with payment_status='pending' to avoid auto-creation of SiteSurvey
            order = Order.objects.create(
                user=user,
                plan=plan,
                order_reference=f"TEST_{unique_id}",
                latitude=51.5074,
                longitude=-0.1278,
                payment_status="pending",  # This won't trigger SiteSurvey creation
            )
            kwargs["order"] = order

        if "technician" not in kwargs:
            # Create a unique technician for each test to avoid conflicts
            import uuid

            tech_id = str(uuid.uuid4())[:8]
            technician = User.objects.create_user(
                username=f"test_technician_{tech_id}",
                email=f"tech_{tech_id}@example.com",
                full_name=f"Test Technician {tech_id}",
                is_staff=True,
            )
            kwargs["technician"] = technician

        # Set default values
        defaults = {
            "status": "scheduled",
            "assigned_at": None,
            "started_at": None,
            "completed_at": None,
        }
        defaults.update(kwargs)

        return SiteSurvey.objects.create(**defaults)

    return _create_survey
