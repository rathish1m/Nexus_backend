"""
RBAC Security Tests for Dashboard BI
=====================================

Tests to verify Role-Based Access Control for the BI Dashboard.

Run: pytest backoffice/tests/test_dashboard_bi_rbac.py -v
"""

import pytest

from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

User = get_user_model()


@pytest.mark.django_db
class TestDashboardBIRBAC:
    """RBAC security tests for dashboard_bi"""

    def test_unauthenticated_user_redirected(self):
        """Unauthenticated users should be redirected to login"""
        client = Client()
        response = client.get(reverse("dashboard_bi"))

        # Should redirect to login page
        assert response.status_code == 302
        assert "login_page" in response.url

    def test_customer_user_blocked_from_dashboard_bi(self):
        """Customer users should be blocked from BI dashboard"""
        # Create a customer user (non-staff)
        customer = User.objects.create_user(
            username="customer@test.com",
            email="customer@test.com",
            password="testpass123",
            full_name="Customer User",
            is_staff=False,
            roles=["customer"],
        )

        client = Client()
        client.force_login(customer)
        response = client.get(reverse("dashboard_bi"))

        # Should be forbidden (403) or redirected
        assert response.status_code in [302, 403]

    def test_staff_user_allowed_to_dashboard_bi(self):
        """Staff users with appropriate roles should have access to BI dashboard"""
        # Create a finance staff user (finance role has access)
        staff = User.objects.create_user(
            username="finance@test.com",
            email="finance@test.com",
            password="testpass123",
            full_name="Finance User",
            is_staff=True,
            roles=["finance"],
        )

        client = Client()
        client.force_login(staff)
        response = client.get(reverse("dashboard_bi"))

        # Should be allowed
        assert response.status_code == 200

    def test_admin_user_allowed_to_dashboard_bi(self):
        """Admin users should have access to BI dashboard"""
        # Create an admin user
        admin = User.objects.create_superuser(
            username="admin@test.com",
            email="admin@test.com",
            password="testpass123",
            full_name="Admin User",
        )

        client = Client()
        client.force_login(admin)
        response = client.get(reverse("dashboard_bi"))

        # Should be allowed
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "role,expected_access",
        [
            ("customer", False),
            ("staff", False),  # Generic 'staff' role doesn't have BI access
            ("finance", True),  # Finance role has BI access
            ("admin", True),
            ("manager", True),
        ],
    )
    def test_role_based_access(self, role, expected_access):
        """Test access based on different user roles"""
        # Create user with specific role
        user = User.objects.create_user(
            username=f"{role}@test.com",
            email=f"{role}@test.com",
            password="testpass123",
            full_name=f"{role.title()} User",
            is_staff=(role != "customer"),
            roles=[role],
        )

        client = Client()
        client.force_login(user)
        response = client.get(reverse("dashboard_bi"))

        if expected_access:
            assert response.status_code == 200, f"{role} should have access"
        else:
            assert response.status_code in [302, 403], f"{role} should be blocked"
