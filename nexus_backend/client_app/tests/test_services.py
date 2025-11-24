import pytest
from decimal import Decimal
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

from client_app.services.order_service import OrderService
from client_app.services.inventory_service import InventoryService
from main.factories import (
    OrderFactory,
    StarlinkKitFactory,
    StarlinkKitInventoryFactory,
    SubscriptionPlanFactory,
    UserFactory,
)
from main.models import StarlinkKitMovement, Subscription


@pytest.mark.django_db
def test_create_order_success(monkeypatch):
    user = UserFactory()

    kit = StarlinkKitFactory(base_price_usd=Decimal("100.00"), kit_type="standard")
    plan = SubscriptionPlanFactory(
        category_name="Standard Category", monthly_price_usd=Decimal("50.00")
    )
    # Make sure there is available inventory for this kit
    StarlinkKitInventoryFactory(kit=kit, is_assigned=False)

    fixed_expiry = timezone.now() + timedelta(hours=1)

    # Patch get_expiry_time so the test is deterministic
    def fake_get_expiry_time(lat, lng):
        return fixed_expiry

    monkeypatch.setattr(
        "client_app.services.order_service.get_expiry_time",
        fake_get_expiry_time,
    )

    data = {
        "kit_id": kit.id,
        "plan_id": plan.id,
        "lat": -4.3,
        "lng": 15.3,
        "assisted": False,
    }

    order = OrderService.create_order(user, data)

    assert order.user == user
    assert order.plan == plan
    assert order.kit_inventory is not None
    assert order.status == "pending_payment"
    assert order.payment_status == "unpaid"
    assert order.expires_at == fixed_expiry

    # Lines should reflect kit, plan, and (no) install fee
    kit_line = order.lines.filter(kind="kit").first()
    plan_line = order.lines.filter(kind="plan").first()
    install_line = order.lines.filter(kind="install").first()

    assert kit_line is not None
    assert kit_line.unit_price == kit.base_price_usd
    assert plan_line is not None
    assert plan_line.unit_price == kit.base_price_usd
    assert install_line is None

    # Subscription should be created and linked
    assert Subscription.objects.filter(
        user=user, plan=plan, order=order, status="pending"
    ).exists()

    # Inventory should be marked as assigned and linked to the order
    inventory = order.kit_inventory
    inventory.refresh_from_db()
    assert inventory.is_assigned
    assert inventory.assigned_to_order == order

    # A movement log should exist for this assignment
    assert StarlinkKitMovement.objects.filter(
        inventory_item=inventory, order=order, movement_type="assigned"
    ).exists()


@pytest.mark.django_db
def test_create_order_with_assisted_install_creates_install_line(monkeypatch):
    user = UserFactory()

    kit = StarlinkKitFactory(base_price_usd=Decimal("100.00"), kit_type="standard")
    plan = SubscriptionPlanFactory(
        category_name="Standard Category", monthly_price_usd=Decimal("50.00")
    )
    StarlinkKitInventoryFactory(kit=kit, is_assigned=False)

    fixed_expiry = timezone.now() + timedelta(hours=1)

    def fake_get_expiry_time(lat, lng):
        return fixed_expiry

    def fake_determine_region(lat, lng):
        return "KIN"

    def fake_install_fee(region):
        assert region == "KIN"
        return Decimal("10.00")

    monkeypatch.setattr(
        "client_app.services.order_service.get_expiry_time",
        fake_get_expiry_time,
    )
    monkeypatch.setattr(
        "client_app.services.order_service.determine_region_from_location",
        fake_determine_region,
    )
    monkeypatch.setattr(
        "client_app.services.order_service.get_installation_fee_by_region",
        fake_install_fee,
    )
    # Avoid hitting real InstallationService.schedule_installation (which depends on
    # SiteSurvey fields that may not match the current schema) – we only care that
    # assisted orders create the proper INSTALL line.
    monkeypatch.setattr(
        "client_app.services.order_service.InstallationService.schedule_installation",
        lambda order: None,
    )

    data = {
        "kit_id": kit.id,
        "plan_id": plan.id,
        "lat": -4.3,
        "lng": 15.3,
        "assisted": True,
    }

    order = OrderService.create_order(user, data)

    assert order.expires_at == fixed_expiry

    kit_line = order.lines.filter(kind="kit").first()
    plan_line = order.lines.filter(kind="plan").first()
    install_line = order.lines.filter(kind="install").first()

    assert kit_line is not None
    assert plan_line is not None
    assert install_line is not None
    assert install_line.unit_price == Decimal("10.00")


@pytest.mark.django_db
def test_create_order_no_inventory():
    """Simulez l'absence d'inventaire disponible"""
    user = get_user_model().objects.create_user(
        username="test", email="test@example.com", full_name="Test User"
    )
    data = {
        "kit_id": 999,  # Non-existent kit
        "plan_id": 999,  # Non-existent plan
        "lat": 45.5017,
        "lng": -73.5673,
        "assisted": False,
    }
    with pytest.raises(OrderService.OrderError):
        OrderService.create_order(user, data)


@pytest.mark.django_db
def test_create_order_missing_plan():
    """Simulez l'absence de plan"""
    user = get_user_model().objects.create_user(
        username="test", email="test@example.com", full_name="Test User"
    )
    data = {
        "kit_id": 1,
        "plan_id": 999,  # Non-existent plan
        "lat": 45.5017,
        "lng": -73.5673,
        "assisted": False,
    }
    with pytest.raises(OrderService.OrderError):
        OrderService.create_order(user, data)


@pytest.mark.django_db
def test_create_order_invalid_location():
    """Simulez une latitude/longitude manquante"""
    user = get_user_model().objects.create_user(
        username="test", email="test@example.com", full_name="Test User"
    )
    data = {
        "kit_id": 1,
        "plan_id": 1,
        "lat": None,  # Missing latitude
        "lng": None,  # Missing longitude
        "assisted": False,
    }
    with pytest.raises(OrderService.OrderError):
        OrderService.create_order(user, data)


@pytest.mark.django_db
def test_assign_inventory_returns_available_item():
    kit = StarlinkKitFactory()
    available = StarlinkKitInventoryFactory(kit=kit, is_assigned=False)

    assigned = InventoryService.assign_inventory(kit)

    assert assigned.pk == available.pk


@pytest.mark.django_db
def test_assign_inventory_raises_when_none_available():
    kit = StarlinkKitFactory()

    with pytest.raises(OrderService.OrderError):
        InventoryService.assign_inventory(kit)


@pytest.mark.django_db
def test_finalize_assignment_marks_inventory_and_order():
    kit = StarlinkKitFactory()
    inventory = StarlinkKitInventoryFactory(kit=kit, is_assigned=False)
    order = OrderFactory()

    InventoryService.finalize_assignment(inventory, order)

    inventory.refresh_from_db()
    order.refresh_from_db()
    assert inventory.is_assigned
    assert inventory.assigned_to_order == order
    assert order.kit_inventory == inventory


@pytest.mark.django_db
def test_finalize_assignment_raises_if_already_assigned_to_other_order():
    kit = StarlinkKitFactory()
    inventory = StarlinkKitInventoryFactory(kit=kit, is_assigned=True)
    first_order = OrderFactory()
    second_order = OrderFactory()

    inventory.assigned_to_order = first_order
    inventory.save()

    with pytest.raises(OrderService.OrderError):
        InventoryService.finalize_assignment(inventory, second_order)


@pytest.mark.django_db
def test_log_movement_creates_record():
    user = UserFactory()
    kit = StarlinkKitFactory()
    inventory = StarlinkKitInventoryFactory(kit=kit, is_assigned=False)
    order = OrderFactory()

    InventoryService.log_movement(inventory, order, -4.3, 15.3, user)

    movement = StarlinkKitMovement.objects.filter(
        inventory_item=inventory, order=order
    ).first()
    assert movement is not None
    assert movement.movement_type == "assigned"
    assert movement.location == "-4.3,15.3"
    assert movement.created_by == user
