#!/usr/bin/env python3

"""
Demonstration script for the new conditional installation logic

This script shows the two main flows:
1. Standard installation (without additional costs)
2. Installation with additional costs

Usage:
    python demo_new_installation_logic.py [--scenario standard|additional|both]
"""

import argparse
import os
from decimal import Decimal

import django

# Django configuration
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()


from main.models import (
    InstallationActivity,
    Order,
    StarlinkKitInventory,
    SubscriptionPlan,
    User,
)
from site_survey.models import AdditionalBilling, SiteSurvey, SurveyAdditionalCost


def create_demo_order():
    """Create a demonstration order"""
    # Get existing data
    user = User.objects.filter(is_staff=False).first()
    kit_inventory = StarlinkKitInventory.objects.filter(is_assigned=False).first()
    plan = SubscriptionPlan.objects.first()

    if not all([user, kit_inventory, plan]):
        print("❌ Insufficient data. Check that there are users, kits and plans.")
        return None, None

    # Create order with payment_status='paid'
    # Note: kit_inventory will be assigned automatically
    order = Order.objects.create(
        user=user,
        plan=plan,
        payment_status="paid",  # Triggers automatic SiteSurvey creation
        status="processing",
        latitude=45.5017,
        longitude=-73.5673,
    )

    # Get the automatically created survey
    try:
        survey = SiteSurvey.objects.get(order=order)
        print(f"✅ Order created: {order.order_reference}")
        print(f"✅ SiteSurvey automatically created: {survey.id}")
        return order, survey
    except SiteSurvey.DoesNotExist:
        print(f"❌ SiteSurvey not created for order {order.order_reference}")
        return order, None


def demo_scenario_standard():
    """Demonstration: Standard installation without additional costs"""
    print("\n" + "=" * 60)
    print("🧪 DEMONSTRATION: Standard Installation")
    print("=" * 60)

    order, survey = create_demo_order()
    if not order or not survey:
        return None

    print("\n📝 Step 1: Order paid")
    print(f"  - Order: {order.order_reference}")
    print(f"  - SiteSurvey automatically created: {survey.id}")
    print(
        f"  - InstallationActivity created: {InstallationActivity.objects.filter(order=order).exists()}"
    )

    print("\n📝 Step 2: Technician completes survey")
    print("  - Technical site assessment...")
    print("  - No additional equipment needed")

    # Configure survey as standard (no additional costs)
    survey.requires_additional_equipment = False
    survey.technician_notes = "Standard site. Cable run is acceptable, signal is good."
    survey.status = "approved"
    survey.save()

    print(f"  - Survey status: {survey.status}")
    print(f"  - Additional equipment required: {survey.requires_additional_equipment}")

    # Check that InstallationActivity is NOW created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    print(f"  - InstallationActivity created: {installation_exists} (should be True)")

    if installation_exists:
        installation = InstallationActivity.objects.get(order=order)
        print(f"  - Installation notes: {installation.notes}")
        print("\n🎉 SUCCESS: Installation automatically created after survey approval!")
        return "success"
    else:
        print("\n❌ ERROR: Installation was not created")
        return "error"


def demo_scenario_additional():
    """Demonstration: Installation with additional costs"""
    print("\n" + "=" * 60)
    print("🧪 DEMONSTRATION: Installation with Additional Costs")
    print("=" * 60)

    order, survey = create_demo_order()
    if not order or not survey:
        return None

    print("\n📝 Step 1: Order paid")
    print(f"  - Order: {order.order_reference}")
    print(f"  - SiteSurvey automatically created: {survey.id}")

    print("\n📝 Step 2: Technician performs survey")
    print("  - Technical site assessment...")
    print("  - Additional equipment identified")

    # Add additional costs
    cost1 = SurveyAdditionalCost.objects.create(
        survey=survey,
        cost_type="cable",
        item_name="Ethernet Cable 50m",
        description="Additional cable for long distance",
        quantity=1,
        unit_price=Decimal("75.00"),
        total_cost=Decimal("75.00"),
    )

    cost2 = SurveyAdditionalCost.objects.create(
        survey=survey,
        cost_type="installation",
        item_name="Additional Support Pole",
        description="Extra pole needed for clear signal",
        quantity=1,
        unit_price=Decimal("150.00"),
        total_cost=Decimal("150.00"),
    )

    print(f"  - Cost 1: {cost1.item_name} - ${cost1.total_cost}")
    print(f"  - Cost 2: {cost2.item_name} - ${cost2.total_cost}")

    # Configure survey with additional costs
    survey.requires_additional_equipment = True
    survey.technician_notes = (
        "Site requires additional cable and support pole for optimal signal."
    )
    survey.status = "approved"
    survey.save()

    print("\n📝 Step 3: Survey approved with additional costs")
    print(f"  - Survey status: {survey.status}")
    print(f"  - Additional equipment required: {survey.requires_additional_equipment}")

    # Check that InstallationActivity is still NOT created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    print(f"  - InstallationActivity created: {installation_exists} (should be False)")

    print("\n📝 Step 4: Generate additional billing")

    # Create additional billing
    billing = AdditionalBilling.objects.create(
        survey=survey,
        status="pending_approval",
        total_amount=Decimal("225.00"),  # 75 + 150
        description="Additional equipment and installation costs identified during site survey",
        customer_notes="The technician identified the need for extra cable and a support pole to ensure optimal Starlink signal reception.",
    )

    print(f"  - Billing reference: {billing.billing_reference}")
    print(f"  - Total amount: ${billing.total_amount}")
    print(f"  - Status: {billing.status}")
    print(f"  - Customer notes: {billing.customer_notes}")

    # Check that InstallationActivity is still NOT created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    print(f"  - InstallationActivity created: {installation_exists} (should be False)")

    print("\n📝 Step 5: Customer approves additional costs")

    billing.status = "approved"
    billing.save()

    print(f"  - Status: {billing.status}")
    print(f"  - Customer notes: {billing.customer_notes}")

    # Check that InstallationActivity is still NOT created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    print(f"  - InstallationActivity created: {installation_exists} (should be False)")

    print("\n📝 Step 6: Customer pays the billing")

    billing.status = "paid"
    billing.payment_method = "mobile"
    billing.payment_reference = "DEMO123456789"
    billing.save()

    print(f"  - Status: {billing.status}")
    print(f"  - Payment method: {billing.payment_method}")
    print(f"  - Reference: {billing.payment_reference}")

    # Check that InstallationActivity is NOW created
    installation_exists = InstallationActivity.objects.filter(order=order).exists()
    print(f"  - InstallationActivity created: {installation_exists} (should be True)")

    if installation_exists:
        installation = InstallationActivity.objects.get(order=order)
        print(f"  - Installation notes: {installation.notes}")
        print("\n🎉 SUCCESS: Installation created after additional costs payment!")
        return "success"
    else:
        print("\n❌ ERROR: Installation was not created after payment")
        return "error"


def demo_both_scenarios():
    """Demonstration: Both scenarios"""
    print("\n" + "=" * 80)
    print("🚀 COMPLETE DEMONSTRATION: New Conditional Installation Logic")
    print("=" * 80)

    # Scenario 1: Standard
    result1 = demo_scenario_standard()

    # Separator
    print("\n" + "-" * 80)

    # Scenario 2: Additional costs
    result2 = demo_scenario_additional()

    # Final summary
    print("\n" + "=" * 80)
    print("📊 DEMONSTRATION SUMMARY")
    print("=" * 80)
    print(
        f"Scenario A (Standard): {'✅ SUCCESS' if result1 == 'success' else '❌ ERROR'}"
    )
    print(
        f"Scenario B (Additional costs): {'✅ SUCCESS' if result2 == 'success' else '❌ ERROR'}"
    )

    if result1 == "success" and result2 == "success":
        print("\n🎉 ALL SCENARIOS COMPLETED SUCCESSFULLY!")
        print("   The new conditional installation logic works perfectly.")
    else:
        print("\n⚠️  Some scenarios failed. Check the implementation.")

    return result1, result2


def main():
    """Main demonstration script"""
    parser = argparse.ArgumentParser(description="Demonstrate new installation logic")
    parser.add_argument(
        "--scenario",
        choices=["standard", "additional", "both"],
        default="both",
        help="Scenario to demonstrate",
    )

    args = parser.parse_args()

    if args.scenario == "standard":
        demo_scenario_standard()
    elif args.scenario == "additional":
        demo_scenario_additional()
    else:
        demo_both_scenarios()


if __name__ == "__main__":
    main()
