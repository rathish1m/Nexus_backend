"""
Example Integration Tests
==========================

This file demonstrates best practices for writing integration tests
that test multiple components working together.

Run: pytest tests/integration/test_order_workflow_example.py -v
"""

from decimal import Decimal

import pytest

from django.contrib.auth import get_user_model

from main.factories import OrderFactory, UserFactory
from main.models import Order, PaymentAttempt

User = get_user_model()


@pytest.mark.integration
def test_complete_order_creation_workflow(authenticated_client, mock_flexpay, db):
    """Test complete workflow: create order → initiate payment → confirm"""
    # Step 1: Create order via API
    response = authenticated_client.post(
        "/api/orders/",
        {
            "subscription_plan": 1,
            "kit": 1,
            "latitude": -4.3217,
            "longitude": 15.3125,
        },
    )

    assert response.status_code == 201
    order_data = response.json()
    order_id = order_data["id"]

    # Verify order created
    order = Order.objects.get(id=order_id)
    assert order.status == "pending"

    # Step 2: Initiate payment
    response = authenticated_client.post(
        f"/api/orders/{order_id}/pay/", {"amount": 100.00, "payment_method": "flexpay"}
    )

    assert response.status_code == 200
    payment_data = response.json()

    # Verify payment created in FlexPay
    assert len(mock_flexpay.payments) == 1
    assert payment_data["status"] == "pending"

    # Step 3: Simulate payment success callback
    payment_id = payment_data["payment_id"]
    mock_flexpay.simulate_payment_success(payment_id)

    # Trigger webhook callback
    response = authenticated_client.post(
        "/api/payments/webhook/",
        {
            "payment_id": payment_id,
            "status": "completed",
            "transaction_id": "TXN-12345",
        },
    )

    assert response.status_code == 200

    # Verify order updated
    order.refresh_from_db()
    assert order.status == "confirmed"


@pytest.mark.integration
def test_order_cancellation_workflow(authenticated_client, mailoutbox, db):
    """Test order cancellation sends email notification"""
    # Arrange
    user = UserFactory()
    authenticated_client.force_login(user)
    order = OrderFactory(user=user, status="pending")

    # Act
    response = authenticated_client.post(
        f"/api/orders/{order.id}/cancel/", {"reason": "Customer changed mind"}
    )

    # Assert
    assert response.status_code == 200

    order.refresh_from_db()
    assert order.status == "cancelled"

    # Verify email sent
    assert len(mailoutbox) == 1
    assert mailoutbox[0].subject == "Order Cancelled"
    assert user.email in mailoutbox[0].to


@pytest.mark.integration
def test_payment_retry_with_exponential_backoff(authenticated_client, db):
    """Test payment retry logic with multiple attempts"""
    # Arrange
    user = UserFactory()
    authenticated_client.force_login(user)
    order = OrderFactory(user=user)

    # Start with a failed payment and an initial retry_count of 1 encoded in raw_payload
    payment = PaymentAttempt.objects.create(
        order=order,
        amount=Decimal("100.00"),
        amount_customer=Decimal("100.00"),
        currency="USD",
        status="failed",
        raw_payload={"retry_count": 1},
    )

    # First retry
    response = authenticated_client.post(f"/api/payments/{payment.id}/retry/")
    assert response.status_code == 200

    payment.refresh_from_db()
    assert payment.raw_payload.get("retry_count") == 2

    # Second retry
    response = authenticated_client.post(f"/api/payments/{payment.id}/retry/")
    assert response.status_code == 200

    payment.refresh_from_db()
    assert payment.raw_payload.get("retry_count") == 3

    # Third retry should fail (max attempts)
    response = authenticated_client.post(f"/api/payments/{payment.id}/retry/")
    assert response.status_code == 400
    assert "Maximum retry attempts" in response.json()["error"]


@pytest.mark.integration
@pytest.mark.slow
def test_order_statistics_dashboard(admin_client, db):
    """Test dashboard statistics calculation with multiple orders"""
    # Arrange - Create test data
    user1 = UserFactory()
    user2 = UserFactory()

    # Create orders with different statuses
    OrderFactory.create_batch(5, user=user1, status="completed")
    OrderFactory.create_batch(3, user=user2, status="pending")
    OrderFactory.create_batch(2, user=user1, status="cancelled")

    # Act
    response = admin_client.get("/api/dashboard/statistics/")

    # Assert
    assert response.status_code == 200
    stats = response.json()

    assert stats["total_orders"] == 10
    assert stats["completed_orders"] == 5
    assert stats["pending_orders"] == 3
    assert stats["cancelled_orders"] == 2
    assert stats["completion_rate"] == 50.0  # 5/10
