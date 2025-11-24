"""
Unit tests for main.models

Tests for Order, SubscriptionPlan, StarlinkKit, OrderLine and related models.
Focus on model fields, properties, methods, and string representations.

Coverage target: 95%+ for models
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from django.utils import timezone

from main.factories import (
    OrderFactory,
    StarlinkKitFactory,
    StarlinkKitInventoryFactory,
    SubscriptionPlanFactory,
    UserFactory,
)
from main.models import CompanyKYC, OrderLine, OTPVerification

# ============================================================================
# StarlinkKit Model Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestStarlinkKitModel:
    """Test StarlinkKit model fields, properties, and methods."""

    def test_starlink_kit_creation(self):
        """Test creating a StarlinkKit with required fields."""
        kit = StarlinkKitFactory(
            name="Standard V2",
            model="GEN2-001",
            kit_type="standard",
            base_price_usd=Decimal("599.00"),
        )

        assert kit.id is not None
        assert kit.name == "Standard V2"
        assert kit.model == "GEN2-001"
        assert kit.kit_type == "standard"
        assert kit.base_price_usd == Decimal("599.00")
        assert kit.is_active is True

    def test_starlink_kit_str_representation(self):
        """Test __str__ method returns expected format."""
        kit = StarlinkKitFactory(
            name="Mini Kit", kit_type="mini", base_price_usd=Decimal("299.00")
        )

        expected = "Mini Kit (mini) – $299.00"
        assert str(kit) == expected

    def test_starlink_kit_types(self):
        """Test kit type choices are valid."""
        standard_kit = StarlinkKitFactory(kit_type="standard")
        mini_kit = StarlinkKitFactory(kit_type="mini")

        assert standard_kit.kit_type == "standard"
        assert mini_kit.kit_type == "mini"

    def test_starlink_kit_unique_name(self):
        """Test kit name must be unique."""
        StarlinkKitFactory(name="Unique Kit")

        with pytest.raises(Exception):  # IntegrityError wrapped by Django
            StarlinkKitFactory(name="Unique Kit")

    def test_starlink_kit_base_price_decimal_places(self):
        """Test base_price_usd supports 2 decimal places."""
        kit = StarlinkKitFactory(base_price_usd=Decimal("599.99"))
        assert kit.base_price_usd == Decimal("599.99")

    def test_starlink_kit_is_active_default(self):
        """Test is_active defaults to True."""
        kit = StarlinkKitFactory()
        assert kit.is_active is True

    def test_starlink_kit_deactivation(self):
        """Test kit can be deactivated."""
        kit = StarlinkKitFactory(is_active=True)
        kit.is_active = False
        kit.save()

        kit.refresh_from_db()
        assert kit.is_active is False

    def test_starlink_kit_picture_optional(self):
        """Test picture field is optional."""
        kit = StarlinkKitFactory(picture=None)
        assert kit.picture.name == "" or kit.picture.name is None


# ============================================================================
# SubscriptionPlan Model Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestSubscriptionPlanModel:
    """Test SubscriptionPlan model fields, properties, and methods."""

    def test_subscription_plan_creation(self):
        """Test creating a SubscriptionPlan with required fields."""
        plan = SubscriptionPlanFactory(
            name="Unlimited Standard",
            site_type="fixed",
            plan_type="unlimited_standard",
            monthly_price_usd=Decimal("120.00"),
            standard_data_gb=None,  # Unlimited
        )

        assert plan.id is not None
        assert plan.name == "Unlimited Standard"
        assert plan.site_type == "fixed"
        assert plan.plan_type == "unlimited_standard"
        assert plan.monthly_price_usd == Decimal("120.00")
        assert plan.standard_data_gb is None  # Unlimited
        assert plan.is_active is True

    def test_subscription_plan_str_representation(self):
        """Test __str__ method returns expected format."""
        plan = SubscriptionPlanFactory(
            name="Business Plan",
            category_name="Standard Category",
            monthly_price_usd=Decimal("150.00"),
        )

        # Format: "{name} – {kit_type} – ${monthly_price_usd}"
        assert "Business Plan" in str(plan)
        assert "150.00" in str(plan) or "150" in str(plan)

    def test_subscription_plan_site_types(self):
        """Test site type choices are valid."""
        fixed_plan = SubscriptionPlanFactory(site_type="fixed")
        portable_plan = SubscriptionPlanFactory(site_type="portable")
        flexible_plan = SubscriptionPlanFactory(site_type="flexible")

        assert fixed_plan.site_type == "fixed"
        assert portable_plan.site_type == "portable"
        assert flexible_plan.site_type == "flexible"

    def test_subscription_plan_plan_types(self):
        """Test plan type choices are valid."""
        unlimited = SubscriptionPlanFactory(plan_type="unlimited_standard")
        limited = SubscriptionPlanFactory(plan_type="limited_standard")
        priority = SubscriptionPlanFactory(plan_type="unlimited_with_priority")

        assert unlimited.plan_type == "unlimited_standard"
        assert limited.plan_type == "limited_standard"
        assert priority.plan_type == "unlimited_with_priority"

    def test_subscription_plan_effective_price_property(self):
        """Test effective_price property returns monthly_price_usd."""
        plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("99.99"))
        assert plan.effective_price == Decimal("99.99")

    def test_subscription_plan_kit_type_property(self):
        """Test kit_type property inferred from category_name."""
        standard_plan = SubscriptionPlanFactory(category_name="Standard Category")
        mini_plan = SubscriptionPlanFactory(category_name="Mini Plans")

        assert standard_plan.kit_type == "standard"
        assert mini_plan.kit_type == "mini"

    def test_subscription_plan_unlimited_data(self):
        """Test unlimited data plan has null standard_data_gb."""
        unlimited_plan = SubscriptionPlanFactory(
            plan_type="unlimited_standard", standard_data_gb=None
        )
        assert unlimited_plan.standard_data_gb is None

    def test_subscription_plan_limited_data(self):
        """Test limited data plan has defined standard_data_gb."""
        limited_plan = SubscriptionPlanFactory(
            plan_type="limited_standard", standard_data_gb=50
        )
        assert limited_plan.standard_data_gb == 50

    def test_subscription_plan_priority_data(self):
        """Test plan with priority data allocation."""
        priority_plan = SubscriptionPlanFactory(
            plan_type="unlimited_with_priority", priority_data_gb=20
        )
        assert priority_plan.priority_data_gb == 20

    def test_subscription_plan_display_order(self):
        """Test display_order for sorting plans."""
        plan1 = SubscriptionPlanFactory(display_order=1)
        plan2 = SubscriptionPlanFactory(display_order=2)

        assert plan1.display_order < plan2.display_order

    def test_subscription_plan_validity_dates(self):
        """Test valid_from and valid_to dates."""
        today = timezone.now().date()
        future = today + timedelta(days=365)

        plan = SubscriptionPlanFactory(valid_from=today, valid_to=future)

        assert plan.valid_from == today
        assert plan.valid_to == future


# ============================================================================
# Order Model Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestOrderModel:
    """Test Order model fields, properties, and methods."""

    def test_order_creation(self):
        """Test creating an Order with required fields."""
        user = UserFactory()
        plan = SubscriptionPlanFactory()

        order = OrderFactory(
            user=user,
            plan=plan,
            total_price=Decimal("599.00"),
            status="pending_payment",
            payment_status="unpaid",
        )

        assert order.id is not None
        assert order.user == user
        assert order.plan == plan
        assert order.total_price == Decimal("599.00")
        assert order.status == "pending_payment"
        assert order.payment_status == "unpaid"
        assert order.created_at is not None

    def test_order_str_representation(self):
        """Test __str__ method returns expected format."""
        user = UserFactory(full_name="John Doe", email="john@example.com")
        order = OrderFactory(user=user)

        # Force order_reference generation
        order._ensure_reference()
        order.save()

        order_str = str(order)
        assert "Order" in order_str
        # Should contain either reference or ID
        assert order.order_reference in order_str or f"#{order.id}" in order_str

    def test_order_reference_generation(self):
        """Test order_reference is generated automatically."""
        order = OrderFactory()
        order._ensure_reference()
        order.save()

        assert order.order_reference is not None
        assert len(order.order_reference) > 0

    def test_order_status_choices(self):
        """Test order status transitions."""
        order = OrderFactory(status="pending_payment")
        assert order.status == "pending_payment"

        order.status = "awaiting_confirmation"
        order.save()
        assert order.status == "awaiting_confirmation"

        order.status = "fulfilled"
        order.save()
        assert order.status == "fulfilled"

    def test_order_payment_status_choices(self):
        """Test payment status transitions."""
        order = OrderFactory(payment_status="unpaid")
        assert order.payment_status == "unpaid"

        order.payment_status = "awaiting_confirmation"
        order.save()
        assert order.payment_status == "awaiting_confirmation"

        order.payment_status = "paid"
        order.save()
        assert order.payment_status == "paid"

    def test_order_is_tax_exempt_property(self):
        """Test is_tax_exempt property reads from user profile."""
        order = OrderFactory()
        # Default should be False (or handle None gracefully)
        assert order.is_tax_exempt is False

    def test_order_expires_at_iso_property(self):
        """Test expires_at_iso returns ISO format or None."""
        order = OrderFactory(expires_at=None)
        assert order.expires_at_iso is None

        now = timezone.now()
        order.expires_at = now
        order.save()

        assert order.expires_at_iso == now.isoformat()

    def test_order_is_expired_method(self):
        """Test is_expired() checks if order has expired."""
        # Order without expiry
        order = OrderFactory(expires_at=None)
        assert order.is_expired() is False

        # Order with future expiry
        future = timezone.now() + timedelta(hours=1)
        order.expires_at = future
        order.save()
        assert order.is_expired() is False

        # Order with past expiry
        past = timezone.now() - timedelta(hours=1)
        order.expires_at = past
        order.save()
        assert order.is_expired() is True

    def test_order_payment_hold_method(self):
        """Test start_subscription_payment_hold() extends payment time."""
        order = OrderFactory(status="pending_payment")
        order.start_subscription_payment_hold(days=7)

        order.refresh_from_db()
        assert order.status == "pending_payment"
        assert order.payment_hold_until is not None
        assert order.payment_hold_until > timezone.now()

    def test_order_with_kit_inventory(self):
        """Test order can be linked to kit inventory."""
        kit_inventory = StarlinkKitInventoryFactory()
        order = OrderFactory(kit_inventory=kit_inventory)

        assert order.kit_inventory == kit_inventory

    def test_order_with_sales_agent(self):
        """Test order can be assigned to sales agent."""
        sales_agent = UserFactory()
        order = OrderFactory(sales_agent=sales_agent)

        assert order.sales_agent == sales_agent

    def test_order_with_location_coordinates(self):
        """Test order can store GPS coordinates."""
        order = OrderFactory(latitude=45.5231, longitude=-122.6765)

        assert order.latitude == 45.5231
        assert order.longitude == -122.6765

    def test_order_renewal_flag(self):
        """Test is_subscription_renewal flag."""
        new_order = OrderFactory(is_subscription_renewal=False)
        renewal_order = OrderFactory(is_subscription_renewal=True)

        assert new_order.is_subscription_renewal is False
        assert renewal_order.is_subscription_renewal is True

    def test_order_cancellation(self):
        """Test order cancellation with reason."""
        order = OrderFactory(status="pending_payment")
        order.status = "cancelled"
        order.cancelled_reason = "Customer requested refund"
        order.save()

        order.refresh_from_db()
        assert order.status == "cancelled"
        assert order.cancelled_reason == "Customer requested refund"


# ============================================================================
# OrderLine Model Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestOrderLineModel:
    """Test OrderLine model fields, properties, and methods."""

    def test_orderline_creation(self):
        """Test creating an OrderLine with required fields."""
        order = OrderFactory()

        line = OrderLine.objects.create(
            order=order,
            kind="kit",
            description="Starlink Standard Kit",
            quantity=1,
            unit_price=Decimal("599.00"),
        )

        assert line.id is not None
        assert line.order == order
        assert line.kind == "kit"
        assert line.description == "Starlink Standard Kit"
        assert line.quantity == 1
        assert line.unit_price == Decimal("599.00")

    def test_orderline_automatic_line_total(self):
        """Test line_total is calculated automatically on save."""
        order = OrderFactory()

        line = OrderLine.objects.create(
            order=order,
            kind="plan",
            description="Monthly Subscription",
            quantity=3,
            unit_price=Decimal("120.00"),
        )

        # line_total should be quantity * unit_price
        expected_total = Decimal("360.00")  # 3 * 120.00
        assert line.line_total == expected_total

    def test_orderline_kind_choices(self):
        """Test OrderLine kind choices are valid."""
        order = OrderFactory()

        kit_line = OrderLine.objects.create(
            order=order, kind="kit", description="Kit", unit_price=Decimal("599.00")
        )
        plan_line = OrderLine.objects.create(
            order=order, kind="plan", description="Plan", unit_price=Decimal("120.00")
        )
        extra_line = OrderLine.objects.create(
            order=order,
            kind="extra",
            description="Installation",
            unit_price=Decimal("50.00"),
        )

        assert kit_line.kind == "kit"
        assert plan_line.kind == "plan"
        assert extra_line.kind == "extra"

    def test_orderline_zero_quantity(self):
        """Test OrderLine with zero quantity."""
        order = OrderFactory()

        line = OrderLine.objects.create(
            order=order,
            kind="adjust",
            description="Discount",
            quantity=0,
            unit_price=Decimal("-10.00"),
        )

        assert line.line_total == Decimal("0.00")

    def test_orderline_update_recalculates_total(self):
        """Test updating quantity/price recalculates line_total."""
        order = OrderFactory()

        line = OrderLine.objects.create(
            order=order,
            kind="extra",
            description="Shipping",
            quantity=1,
            unit_price=Decimal("25.00"),
        )

        assert line.line_total == Decimal("25.00")

        # Update quantity
        line.quantity = 2
        line.save()

        assert line.line_total == Decimal("50.00")

    def test_orderline_traceability_links(self):
        """Test optional traceability to kit_inventory, plan, extra_charge."""
        order = OrderFactory()
        kit_inventory = StarlinkKitInventoryFactory()
        plan = SubscriptionPlanFactory()

        line = OrderLine.objects.create(
            order=order,
            kind="kit",
            description="Kit with inventory",
            unit_price=Decimal("599.00"),
            kit_inventory=kit_inventory,
            plan=plan,
        )

        assert line.kit_inventory == kit_inventory
        assert line.plan == plan

    def test_orderline_related_to_order(self):
        """Test OrderLine is properly related to Order via foreign key."""
        order = OrderFactory()

        OrderLine.objects.create(
            order=order, kind="kit", description="Kit", unit_price=Decimal("599.00")
        )
        OrderLine.objects.create(
            order=order, kind="plan", description="Plan", unit_price=Decimal("120.00")
        )

        assert order.lines.count() == 2

    def test_orderline_decimal_precision(self):
        """Test OrderLine handles decimal precision correctly."""
        order = OrderFactory()

        line = OrderLine.objects.create(
            order=order,
            kind="extra",
            description="Precise charge",
            quantity=3,
            unit_price=Decimal("33.33"),
        )

        # 3 * 33.33 = 99.99
        assert line.line_total == Decimal("99.99")


# ============================================================================
# StarlinkKitInventory Model Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestStarlinkKitInventoryModel:
    """Test StarlinkKitInventory model."""

    def test_kit_inventory_creation(self):
        """Test creating a kit inventory item."""
        kit = StarlinkKitFactory()
        inventory = StarlinkKitInventoryFactory(
            kit=kit, serial_number="SN12345678", is_assigned=False
        )

        assert inventory.kit == kit
        assert inventory.serial_number == "SN12345678"
        assert inventory.is_assigned is False

    def test_kit_inventory_assignment(self):
        """Test kit inventory can be assigned."""
        inventory = StarlinkKitInventoryFactory(is_assigned=False)
        assert inventory.is_assigned is False

        inventory.is_assigned = True
        inventory.save()

        inventory.refresh_from_db()
        assert inventory.is_assigned is True

    def test_kit_inventory_unique_serial_number(self):
        """Test serial numbers are unique."""
        StarlinkKitInventoryFactory(serial_number="SN00000001")

        with pytest.raises(Exception):  # IntegrityError
            StarlinkKitInventoryFactory(serial_number="SN00000001")


# ============================================================================
# Integration Tests - Model Relationships
# ============================================================================


@pytest.mark.django_db
@pytest.mark.integration
class TestModelRelationships:
    """Test relationships between models."""

    def test_order_with_complete_setup(self):
        """Test creating an order with all related objects."""
        user = UserFactory()
        plan = SubscriptionPlanFactory()
        kit = StarlinkKitFactory()
        kit_inventory = StarlinkKitInventoryFactory(kit=kit)

        order = OrderFactory(user=user, plan=plan, kit_inventory=kit_inventory)

        # Add order lines
        OrderLine.objects.create(
            order=order,
            kind="kit",
            description=kit.name,
            quantity=1,
            unit_price=kit.base_price_usd,
            kit_inventory=kit_inventory,
        )

        OrderLine.objects.create(
            order=order,
            kind="plan",
            description=plan.name,
            quantity=1,
            unit_price=plan.monthly_price_usd,
            plan=plan,
        )

        assert order.lines.count() == 2
        assert order.user == user
        assert order.plan == plan
        assert order.kit_inventory == kit_inventory

    def test_cascade_delete_order_lines(self):
        """Test deleting order cascades to order lines."""
        order = OrderFactory()

        OrderLine.objects.create(
            order=order, kind="kit", description="Kit", unit_price=Decimal("599.00")
        )
        OrderLine.objects.create(
            order=order, kind="plan", description="Plan", unit_price=Decimal("120.00")
        )

        assert order.lines.count() == 2

        order_id = order.id
        order.delete()

        # Verify lines are deleted
        assert OrderLine.objects.filter(order_id=order_id).count() == 0

    def test_order_cancel_method_without_inventory(self):
        """Test Order.cancel() method without kit inventory."""
        order = OrderFactory(status="pending_payment")

        result = order.cancel(reason="Customer requested cancellation")

        order.refresh_from_db()
        assert order.status == "cancelled"
        assert order.cancelled_reason == "Customer requested cancellation"
        assert result["changed"] is True
        assert result["freed_inventory"] is False

    def test_order_cancel_method_with_inventory(self):
        """Test Order.cancel() method with kit inventory."""
        kit = StarlinkKitFactory()
        inventory = StarlinkKitInventoryFactory(kit=kit, is_assigned=True)
        order = OrderFactory(status="pending_payment", kit_inventory=inventory)
        inventory.assigned_to_order = order
        inventory.save()

        result = order.cancel(reason="Out of stock")

        order.refresh_from_db()
        inventory.refresh_from_db()

        assert order.status == "cancelled"
        assert order.cancelled_reason == "Out of stock"
        assert result["changed"] is True
        assert result["freed_inventory"] is True
        assert inventory.is_assigned is False
        assert inventory.assigned_to_order is None

    def test_order_cancel_method_idempotent(self):
        """Test Order.cancel() method is idempotent."""
        order = OrderFactory(status="cancelled", cancelled_reason="Already cancelled")

        result = order.cancel(reason="Trying to cancel again")

        order.refresh_from_db()
        assert order.status == "cancelled"
        assert result["changed"] is False
        assert result["freed_inventory"] is False


# ============================================================================
# OTP Model Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestOTPModel:
    """Test OTPVerification model functionality."""

    def test_otp_generation(self):
        """Test OTP generation creates 6-digit code."""
        user = UserFactory()
        otp = OTPVerification.objects.create(user=user)
        otp.generate_otp()

        assert otp.otp is not None
        assert len(otp.otp) == 6
        assert otp.otp.isdigit()
        assert otp.expires_at is not None
        assert otp.is_verified is False
        assert otp.attempt_count == 0

    def test_otp_is_expired_false(self):
        """Test OTP is not expired within validity period."""
        user = UserFactory()
        otp = OTPVerification.objects.create(user=user)
        otp.generate_otp()

        assert otp.is_expired() is False

    def test_otp_is_expired_true(self):
        """Test OTP is expired after validity period."""
        user = UserFactory()
        otp = OTPVerification.objects.create(user=user)
        otp.generate_otp()

        # Manually set expires_at to past
        otp.expires_at = timezone.now() - timedelta(hours=1)
        otp.save()

        assert otp.is_expired() is True

    def test_otp_verify_correct_code(self):
        """Test OTP verification with correct code."""
        user = UserFactory()
        otp = OTPVerification.objects.create(user=user)
        otp.generate_otp()

        correct_code = otp.otp
        success, message = otp.verify_otp(correct_code)

        assert success is True
        assert message == "OTP verified."
        assert otp.is_verified is True

    def test_otp_verify_incorrect_code(self):
        """Test OTP verification with incorrect code."""
        user = UserFactory()
        otp = OTPVerification.objects.create(user=user)
        otp.generate_otp()

        success, message = otp.verify_otp("000000")

        assert success is False
        assert message == "Invalid OTP."
        assert otp.attempt_count == 1

    def test_otp_verify_expired_code(self):
        """Test OTP verification fails for expired code."""
        user = UserFactory()
        otp = OTPVerification.objects.create(user=user)
        otp.generate_otp()

        correct_code = otp.otp
        otp.expires_at = timezone.now() - timedelta(hours=1)
        otp.save()

        success, message = otp.verify_otp(correct_code)

        assert success is False
        assert message == "OTP has expired."


# ============================================================================
# User Model Additional Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestUserAdditionalMethods:
    """Test User model additional methods."""

    def test_user_has_role_true(self):
        """Test user.has_role() returns True for assigned role."""
        user = UserFactory()
        user.roles = ["admin", "sales"]
        user.save()

        assert user.has_role("admin") is True
        assert user.has_role("sales") is True

    def test_user_has_role_false(self):
        """Test user.has_role() returns False for unassigned role."""
        user = UserFactory()
        user.roles = ["admin"]
        user.save()

        assert user.has_role("technician") is False

    def test_user_add_role(self):
        """Test user.add_role() adds new role."""
        user = UserFactory()
        user.roles = ["admin"]
        user.save()

        user.add_role("sales")
        user.refresh_from_db()

        assert "sales" in user.roles
        assert len(user.roles) == 2

    def test_user_add_role_duplicate(self):
        """Test user.add_role() doesn't duplicate existing role."""
        user = UserFactory()
        user.roles = ["admin"]
        user.save()

        user.add_role("admin")
        user.refresh_from_db()

        assert user.roles.count("admin") == 1

    def test_user_remove_role(self):
        """Test user.remove_role() removes role."""
        user = UserFactory()
        user.roles = ["admin", "sales", "technician"]
        user.save()

        user.remove_role("sales")
        user.refresh_from_db()

        assert "sales" not in user.roles
        assert len(user.roles) == 2

    def test_user_remove_role_not_present(self):
        """Test user.remove_role() handles non-existent role gracefully."""
        user = UserFactory()
        user.roles = ["admin"]
        user.save()

        user.remove_role("nonexistent")
        user.refresh_from_db()

        assert user.roles == ["admin"]


# ============================================================================
# Company KYC Status Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.unit
class TestCompanyKYCStatus:
    """Test CompanyKYC status methods."""

    def test_company_kyc_is_pending(self):
        """Test CompanyKYC.is_pending() method."""
        user = UserFactory()
        kyc = CompanyKYC.objects.create(user=user, status="pending")

        assert kyc.is_pending() is True
        assert kyc.is_approved() is False
        assert kyc.is_rejected() is False

    def test_company_kyc_is_approved(self):
        """Test CompanyKYC.is_approved() method."""
        user = UserFactory()
        kyc = CompanyKYC.objects.create(user=user, status="approved")

        assert kyc.is_approved() is True
        assert kyc.is_pending() is False
        assert kyc.is_rejected() is False

    def test_company_kyc_is_rejected(self):
        """Test CompanyKYC.is_rejected() method."""
        user = UserFactory()
        kyc = CompanyKYC.objects.create(user=user, status="rejected")

        assert kyc.is_rejected() is True
        assert kyc.is_pending() is False
        assert kyc.is_approved() is False
