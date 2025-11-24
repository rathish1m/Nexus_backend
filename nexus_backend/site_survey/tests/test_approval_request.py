#!/usr/bin/env python
"""Test script to simulate billing approval POST request"""

import json
import os

import pytest

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from site_survey.models import AdditionalBilling
from site_survey.views import customer_billing_approval

User = get_user_model()


@pytest.mark.django_db
def test_approval_request():
    """Simulate a POST request to approve billing"""
    # ruff: noqa: E402

    # Get a pending billing
    billing = AdditionalBilling.objects.filter(status="pending_approval").first()

    if not billing:
        print("No pending billings found")
        return

    print("\n=== Testing Billing Approval ===")
    print(f"Billing ID: {billing.id}")
    print(f"Customer: {billing.customer}")
    print(f"Customer ID: {billing.customer.id if billing.customer else 'None'}")
    print(f"Status: {billing.status}")
    print(f"Can be approved: {billing.can_be_approved()}")

    # Create a mock request
    factory = RequestFactory()

    request_data = {"action": "approve", "customer_notes": "Test approval from script"}

    request = factory.post(
        f"/site-survey/billing/approval/{billing.id}/",
        data=json.dumps(request_data),
        content_type="application/json",
    )

    # Set the user to the billing's customer
    request.user = billing.customer

    print(f"\nRequest user: {request.user}")
    print(f"Request user == billing.customer: {request.user == billing.customer}")

    # Call the view
    print("\nCalling view...")
    try:
        response = customer_billing_approval(request, billing.id)
        print(f"Response status: {response.status_code}")

        response_data = json.loads(response.content)
        print(f"Response data: {json.dumps(response_data, indent=2)}")

        # Check the billing status after
        billing.refresh_from_db()
        print(f"\nBilling status after: {billing.status}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_approval_request()
