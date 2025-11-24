#!/usr/bin/env python3
# ruff: noqa: E402


"""
Script to test a complete order creation scenario with our new logic
"""

import os

import django

# Django configuration
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from decimal import Decimal

import pytest

from main.models import (
    InstallationActivity,
    Order,
    StarlinkKitInventory,
    SubscriptionPlan,
    User,
)
from site_survey.models import AdditionalBilling, SiteSurvey, SurveyAdditionalCost


@pytest.mark.django_db
def test_full_workflow():
    print("🧪 Testing complete workflow")
    print("=" * 60)

    # Get existing data
    try:
        user = User.objects.filter(is_staff=False).first()
        if not user:
            print("❌ No client user found")
            return

        kit_inventory = StarlinkKitInventory.objects.filter(is_assigned=False).first()
        if not kit_inventory:
            print("❌ No available kit found")
            return

        plan = SubscriptionPlan.objects.first()
        if not plan:
            print("❌ No plan found")
            return

        print(f"👤 Client: {user.username}")
        print(f"📦 Kit: {kit_inventory.kit.name}")
        print(f"📋 Plan: {plan.name}")

    except Exception as e:
        print(f"❌ Error retrieving data: {e}")
        return

    # Step 1: Create an order with payment_status='paid'
    print("\n📝 Step 1: Creating paid order...")

    order = Order.objects.create(
        user=user,
        plan=plan,
        payment_status="paid",  # This should trigger SiteSurvey creation
        status="processing",
        latitude=45.5017,
        longitude=-73.5673,
    )

    print(f"✅ Order created: {order.order_reference}")

    # Step 2: Verify SiteSurvey was created automatically
    print("\n📝 Step 2: Checking automatic SiteSurvey creation...")

    try:
        survey = SiteSurvey.objects.get(order=order)
        print(f"✅ SiteSurvey automatically created: {survey.id}")
    except SiteSurvey.DoesNotExist:
        print("❌ SiteSurvey was not created!")
        return

    # Step 3: Verify InstallationActivity was NOT created yet
    print("\n📝 Step 3: Checking InstallationActivity (should NOT exist yet)...")

    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    if installation_exists:
        print("❌ InstallationActivity should NOT exist yet!")
        return
    else:
        print("✅ InstallationActivity correctly NOT created yet")


@pytest.mark.django_db
def test_scenario_a():
    """Test Scenario A: Standard installation without additional costs"""
    print("\n🔄 SCENARIO A: Standard Installation")
    print("-" * 50)

    # Use the base workflow to create order and survey
    user = User.objects.filter(is_staff=False).first()
    _kit_inventory = StarlinkKitInventory.objects.filter(is_assigned=False).first()
    plan = SubscriptionPlan.objects.first()

    order = Order.objects.create(
        user=user,
        plan=plan,
        payment_status="paid",
        status="processing",
        latitude=45.5017,
        longitude=-73.5673,
    )

    survey = SiteSurvey.objects.get(order=order)

    # Configure survey as standard (no additional equipment)
    survey.requires_additional_equipment = False
    survey.technician_notes = "Standard site. No additional equipment needed."
    survey.status = "approved"
    survey.save()

    print("✅ Survey approved without additional costs")

    # Check that InstallationActivity is now created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    if installation_exists:
        installation = InstallationActivity.objects.get(order=order)
        print(f"✅ InstallationActivity created: {installation.id}")
        print(f"   Notes: {installation.notes}")
        return "success"
    else:
        print("❌ InstallationActivity was not created after survey approval!")
        return "error"


@pytest.mark.django_db
def test_scenario_b():
    """Test Scenario B: Installation with additional costs"""
    print("\n🔄 SCENARIO B: Installation with Additional Costs")
    print("-" * 50)

    # Use the base workflow to create order and survey
    user = User.objects.filter(is_staff=False).first()
    if not user:
        # Create a test user if none exists
        user = User.objects.create_user(
            username="test_user", email="test@example.com", full_name="Test User"
        )

    _kit_inventory = StarlinkKitInventory.objects.filter(is_assigned=False).first()
    plan = SubscriptionPlan.objects.first()

    order = Order.objects.create(
        user=user,
        plan=plan,
        payment_status="paid",
        status="processing",
        latitude=45.5017,
        longitude=-73.5673,
    )

    survey = SiteSurvey.objects.get(order=order)

    # Create ExtraCharge objects for testing
    from site_survey.models import ExtraCharge

    cable_charge, _ = ExtraCharge.objects.get_or_create(
        item_name="Extra Cable 100m",
        defaults={
            "cost_type": "cable",
            "description": "Long cable run needed",
            "unit_price": Decimal("120.00"),
        },
    )

    mounting_charge, _ = ExtraCharge.objects.get_or_create(
        item_name="Wall Mount Kit",
        defaults={
            "cost_type": "mounting",
            "description": "Heavy-duty wall mounting",
            "unit_price": Decimal("85.00"),
        },
    )

    # Add additional costs
    cost1 = SurveyAdditionalCost.objects.create(
        survey=survey,
        extra_charge=cable_charge,
        quantity=1,
        justification="Long cable run needed for optimal placement",
    )

    print(f"✅ Additional cost added: {cost1.item_name} - ${cost1.total_price}")

    # Configure survey with additional equipment requirement
    survey.requires_additional_equipment = True
    survey.technician_notes = "Site requires additional cable for proper installation."
    survey.status = "approved"
    survey.save()

    print("✅ Survey approved with additional equipment requirement")

    # Check that InstallationActivity is NOT yet created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    if installation_exists:
        print("❌ InstallationActivity should NOT exist before billing payment!")
        return "error"

    print("✅ InstallationActivity correctly NOT created yet")

    # Create additional billing
    billing = AdditionalBilling.objects.create(
        survey=survey,
        order=survey.order,
        customer=survey.order.user,
        status="pending_approval",
    )

    print(f"✅ Additional billing created: {billing.billing_reference}")

    # Customer approves and pays
    billing.status = "approved"
    billing.save()

    billing.status = "paid"
    billing.payment_method = "mobile"
    billing.payment_reference = "TEST123456"
    billing.save()

    print("✅ Additional billing paid")

    # Check that InstallationActivity is NOW created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    if installation_exists:
        installation = InstallationActivity.objects.get(order=order)
        print(f"✅ InstallationActivity created after payment: {installation.id}")
        print(f"   Notes: {installation.notes}")
        return "success"
    else:
        print("❌ InstallationActivity was not created after billing payment!")
        return "error"


def run_all_tests():
    """Run all workflow tests"""
    print("🚀 COMPREHENSIVE WORKFLOW TESTING")
    print("=" * 80)

    # Basic workflow test
    test_full_workflow()

    # Scenario A test
    result_a = test_scenario_a()

    # Scenario B test
    result_b = test_scenario_b()

    # Final summary
    print("\n📊 TEST RESULTS SUMMARY")
    print("=" * 50)
    print(
        f"Scenario A (Standard): {'✅ SUCCESS' if result_a == 'success' else '❌ FAILED'}"
    )
    print(
        f"Scenario B (Additional costs): {'✅ SUCCESS' if result_b == 'success' else '❌ FAILED'}"
    )

    if result_a == "success" and result_b == "success":
        print("\n🎉 ALL TESTS PASSED! New installation logic works perfectly.")
    else:
        print("\n⚠️  Some tests failed. Check implementation.")

    return result_a, result_b


if __name__ == "__main__":
    run_all_tests()
