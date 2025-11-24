#!/usr/bin/env python
"""Test script to verify billing approval functionality"""

import os

import pytest

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.contrib.auth import get_user_model

from site_survey.models import AdditionalBilling

User = get_user_model()


@pytest.mark.django_db
def test_billing_approval():
    """Test the billing approval process"""
    # ruff: noqa: E402

    # Get all pending billings
    pending_billings = AdditionalBilling.objects.filter(status="pending_approval")

    print("\n=== Billing Approval Test ===")
    print(f"Found {pending_billings.count()} pending billings\n")

    for billing in pending_billings:
        print(f"Billing ID: {billing.id}")
        print(f"Reference: {billing.billing_reference}")
        print(f"Customer: {billing.customer.get_full_name()}")
        print(f"Status: {billing.status}")
        print(f"Can be approved: {billing.can_be_approved()}")
        print(f"Is expired: {billing.is_expired()}")
        print(f"Expires at: {billing.expires_at}")
        print(f"Subtotal: ${billing.subtotal}")
        print(f"Tax amount: ${billing.tax_amount}")
        print(f"Total: ${billing.total_amount}")

        # Test tax breakdown
        print("\nTax Breakdown:")
        tax_breakdown = billing.get_tax_breakdown()
        if tax_breakdown:
            for tax in tax_breakdown:
                print(
                    f"  - {tax['description']} ({tax['percentage']}%): ${tax['amount']}"
                )
        else:
            print("  No taxes applied")

        print("-" * 50 + "\n")


if __name__ == "__main__":
    test_billing_approval()
