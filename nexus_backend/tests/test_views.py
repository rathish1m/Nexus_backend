import json

import pytest

from django.urls import reverse

from main.factories import UserFactory


@pytest.mark.django_db
class TestClientAppViews:
    """Test cases for client_app views."""

    def test_dashboard_requires_login(self, client):
        """Test that dashboard requires authentication."""
        url = reverse("dashboard")
        response = client.get(url)
        assert response.status_code == 302  # Redirect to login

    def test_dashboard_authenticated(self, authenticated_client):
        """Test dashboard access for authenticated user."""
        url = reverse("dashboard")
        response = authenticated_client.get(url)
        assert response.status_code == 200
        assert "full_name" in response.context

    def test_get_checkout_options(self, staff_client):
        """Test checkout options endpoint."""
        url = reverse("get_checkout_options")
        response = staff_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "kits" in data
        assert "plans" in data

    def test_submit_order_invalid_kit(self, authenticated_client):
        """Test order submission with invalid kit."""
        url = reverse("submit_order")
        data = {
            "kit_type": "invalid",
            "subscription_plan": "1",
            "latitude": "-1.5",
            "longitude": "29.5",
        }
        response = authenticated_client.post(url, data)
        assert response.status_code == 400

    def test_submit_order_missing_location(self, authenticated_client):
        """Test order submission without location."""
        url = reverse("submit_order")
        data = {"kit_type": "1", "subscription_plan": "1"}
        response = authenticated_client.post(url, data)
        assert response.status_code == 400
        data = response.json()
        assert "Please select the installation address" in data["message"]


@pytest.mark.django_db
class TestKYCManagementViews:
    """Test cases for KYC management views."""

    def test_kyc_management_requires_staff(self, authenticated_client):
        """Test that KYC management requires staff status."""
        url = reverse("kyc_management")
        response = authenticated_client.get(url)
        assert response.status_code == 302  # Redirect to login or permission denied

    def test_kyc_management_staff_access(self, staff_client):
        """Test KYC management access for staff."""
        url = reverse("kyc_management")
        response = staff_client.get(url)
        assert response.status_code == 200

    def test_get_kyc_list(self, staff_client):
        """Test KYC list retrieval."""
        url = reverse("get_kyc")
        response = staff_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert "kycs" in data

    def test_update_kyc_status_invalid(self, staff_client):
        """Test KYC status update with invalid data."""
        url = reverse("update_kyc_status", kwargs={"user_id": 1})
        data = {"status": "invalid_status", "type": "personal"}
        response = staff_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )
        assert response.status_code == 400

    def test_update_kyc_status_valid(self, staff_client):
        """Test valid KYC status update."""
        user = UserFactory()
        url = reverse("update_kyc_status", kwargs={"user_id": user.id})
        data = {"status": "approved", "type": "personal"}
        response = staff_client.post(
            url, data=json.dumps(data), content_type="application/json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True


@pytest.mark.django_db
class TestOrderViews:
    """Test cases for order-related views."""

    def test_orders_list_requires_login(self, client):
        """Test that orders list requires authentication."""
        url = reverse("orders_list")
        response = client.get(url)
        assert response.status_code == 302

    def test_orders_list_authenticated(self, authenticated_client):
        """Test orders list for authenticated user."""
        url = reverse("orders_list")
        response = authenticated_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert "orders" in data

    def test_get_user_subscriptions(self, authenticated_client):
        """Test user subscriptions retrieval."""
        url = reverse("get_user_subscriptions")
        response = authenticated_client.get(url)
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "subscriptions" in data
