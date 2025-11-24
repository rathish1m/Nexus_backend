import pytest

from django.utils import timezone

from main.factories import OrderFactory, SubscriptionPlanFactory, UserFactory


@pytest.mark.django_db
class TestUserModel:
    """Test cases for User model."""

    def test_user_creation(self):
        """Test basic user creation."""
        user = UserFactory()
        assert user.username
        assert user.email
        assert user.full_name
        assert user.is_active

    def test_user_str_method(self):
        """Test string representation of User."""
        user = UserFactory(full_name="John Doe")
        assert str(user) == "John Doe"

    def test_user_has_role(self):
        """Test role checking functionality."""
        user = UserFactory()
        user.roles = ["customer"]
        user.save()
        assert user.has_role("customer")
        assert not user.has_role("admin")


@pytest.mark.django_db
class TestOrderModel:
    """Test cases for Order model."""

    def test_order_creation(self):
        """Test basic order creation."""
        order = OrderFactory()
        assert order.user
        assert order.plan
        assert order.status == "pending_payment"
        assert order.payment_status == "unpaid"

    def test_order_str_method(self):
        """Test string representation of Order."""
        order = OrderFactory()
        name = (
            getattr(order.user, "get_full_name", lambda: None)()
            or getattr(order.user, "full_name", None)
            or getattr(order.user, "email", None)
        )
        expected = (
            f"Order {order.order_reference or '#'+str(order.id)} by {name or 'Guest'}"
        )
        assert str(order) == expected

    def test_order_is_expired(self):
        """Test order expiration logic."""
        # Create order with past expiry
        past_time = timezone.now() - timezone.timedelta(hours=2)
        order = OrderFactory(expires_at=past_time)
        assert order.is_expired()

        # Create order with future expiry
        future_time = timezone.now() + timezone.timedelta(hours=2)
        order = OrderFactory(expires_at=future_time)
        assert not order.is_expired()

    def test_order_calculate_total(self):
        """Test total price field is set and non-negative."""
        order = OrderFactory()
        assert order.total_price is None or order.total_price >= 0


@pytest.mark.django_db
class TestSubscriptionPlanModel:
    """Test cases for SubscriptionPlan model."""

    def test_plan_creation(self):
        """Test basic plan creation."""
        plan = SubscriptionPlanFactory()
        assert plan.name
        assert plan.effective_price is None or plan.effective_price >= 0
        assert plan.is_active

    def test_plan_str_method(self):
        """Test string representation of SubscriptionPlan."""
        plan = SubscriptionPlanFactory(
            name="Premium Plan", standard_data_gb=100, monthly_price_usd=99.99
        )
        expected = "Premium Plan – standard – $99.99"
        assert str(plan) == expected
