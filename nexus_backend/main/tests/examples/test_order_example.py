"""
Example Unit Tests for Order Model
===================================

This file demonstrates best practices for writing unit tests.

Run: pytest main/tests/examples/test_order_example.py -v
"""

from datetime import datetime

import pytest
from freezegun import freeze_time

from main.factories import OrderFactory, UserFactory
from main.models import Order

# ============================================================================
# BASIC UNIT TESTS
# ============================================================================


@pytest.mark.unit
def test_order_creation_with_defaults(db):
    """Test creating an order with default values"""
    # Arrange
    user = UserFactory()

    # Act
    order = Order.objects.create(user=user)

    # Assert
    assert order.user == user
    assert order.status == "pending_payment"
    assert order.created_at is not None


@pytest.mark.unit
def test_order_factory_creation(db):
    """Test using Factory Boy to create test data"""
    # Act
    order = OrderFactory(status="completed")

    # Assert
    assert order.status == "completed"
    assert order.user is not None
    assert order.created_at is not None


# ============================================================================
# RELATIONSHIP TESTS
# ============================================================================


@pytest.mark.unit
def test_order_belongs_to_user(db):
    """Test order-user relationship"""
    # Arrange
    user = UserFactory()

    # Act
    order1 = OrderFactory(user=user)
    order2 = OrderFactory(user=user)

    # Assert
    assert order1.user == user
    assert order2.user == user
    assert user.kit_orders.count() == 2


# ============================================================================
# METHOD TESTS
# ============================================================================


@pytest.mark.unit
def test_order_str_representation(db):
    """Test order string representation"""
    # Arrange
    order = OrderFactory(id=123)

    # Act
    result = str(order)

    # Assert
    assert "Order" in result
    assert "by" in result


# ============================================================================
# TIME-BASED TESTS
# ============================================================================


@pytest.mark.unit
def test_order_created_at_timestamp(db):
    """Test that created_at is set automatically"""
    # Arrange & Act
    with freeze_time("2024-01-01 12:00:00"):
        order = OrderFactory()

    # Assert
    assert order.created_at.year == 2024
    assert order.created_at.month == 1
    assert order.created_at.day == 1


# ============================================================================
# EDGE CASE TESTS
# ============================================================================


@pytest.mark.unit
def test_order_creation_with_missing_required_field(db):
    """Test that creating order without required field raises error"""
    # Act & Assert
    with pytest.raises(Exception):  # Should raise IntegrityError or similar
        Order.objects.create(subscription_plan_id=1)


# ============================================================================
# MULTIPLE ASSERTIONS (when related)
# ============================================================================


@pytest.mark.unit
def test_order_complete_workflow(db):
    """Test complete order workflow from pending to completed"""
    # Arrange
    order = OrderFactory(status="pending")

    # Act - Step 1: Confirm
    order.status = "confirmed"
    order.save()

    # Assert - Step 1
    assert order.status == "confirmed"

    # Act - Step 2: Complete
    order.status = "completed"
    order.completed_at = datetime.now()
    order.save()

    # Assert - Step 2
    assert order.status == "completed"
    assert order.completed_at is not None
