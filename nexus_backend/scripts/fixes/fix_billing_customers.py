#!/usr/bin/env python
"""Fix billing customer assignment"""

import os

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from site_survey.models import AdditionalBilling


def fix_billing_customers():
    """Assign customers to billings from their associated surveys"""

    billings = AdditionalBilling.objects.all()

    print("\n=== Checking Billing Customer Assignments ===\n")

    for billing in billings:
        print(f"Billing ID: {billing.id}")
        print(f"  Reference: {billing.billing_reference}")
        print(f"  Current Customer: {billing.customer}")

        if billing.survey:
            survey_customer = (
                billing.survey.order.user if billing.survey.order else None
            )
            print(f"  Survey Customer: {survey_customer}")

            if not billing.customer and survey_customer:
                print(f"  ⚠️  FIXING: Assigning customer {survey_customer} to billing")
                billing.customer = survey_customer
                billing.save()
                print("  ✓ Fixed!")
            elif billing.customer != survey_customer and survey_customer:
                print("  ⚠️  WARNING: Customer mismatch!")
                print(f"     Billing customer: {billing.customer}")
                print(f"     Survey customer: {survey_customer}")
        else:
            print("  ⚠️  ERROR: No survey associated with this billing!")

        print("-" * 50)


if __name__ == "__main__":
    fix_billing_customers()
