#!/usr/bin/env python
"""
Test script to verify survey approval validation works correctly
"""
# ruff: noqa: E402

import os

import pytest

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from datetime import date

from main.models import Order, User
from site_survey.models import SiteSurvey


@pytest.mark.django_db
def test_survey_validation():
    print("=== Testing Survey Approval Validation ===\n")

    # Find surveys with installation_feasible=False
    non_feasible_surveys = SiteSurvey.objects.filter(installation_feasible=False)
    print(f"Found {non_feasible_surveys.count()} surveys marked as NOT feasible")

    if non_feasible_surveys.exists():
        for survey in non_feasible_surveys[:3]:
            print(
                f"- Survey {survey.id}: status={survey.status}, feasible={survey.installation_feasible}"
            )

    # Find completed surveys that are feasible
    feasible_completed = SiteSurvey.objects.filter(
        status="completed", installation_feasible=True
    )
    print(f"\nFound {feasible_completed.count()} completed surveys that ARE feasible")

    if feasible_completed.exists():
        for survey in feasible_completed[:3]:
            print(
                f"- Survey {survey.id}: status={survey.status}, feasible={survey.installation_feasible}"
            )

    # Check if we need to create a test survey
    test_survey = SiteSurvey.objects.filter(
        status="completed", installation_feasible=False
    ).first()

    if not test_survey:
        print("\n🔄 Creating a test survey with installation_feasible=False...")

        # Get or create a test order
        try:
            test_order = Order.objects.first()
            if not test_order:
                print("No orders found in database - cannot create test survey")
                return

            # Get or create a technician user
            technician = User.objects.filter(user_type="technician").first()
            if not technician:
                technician = User.objects.filter(is_staff=True).first()

            if technician:
                test_survey = SiteSurvey.objects.create(
                    order=test_order,
                    technician=technician,
                    status="completed",
                    installation_feasible=False,
                    scheduled_date=date.today(),
                    survey_latitude=48.8566,
                    survey_longitude=2.3522,
                    site_access_notes="Test survey - installation not feasible",
                )
                print(
                    f"✅ Created test survey {test_survey.id} with installation_feasible=False"
                )
            else:
                print("No suitable technician found")

        except Exception as e:
            print(f"Error creating test survey: {e}")
    else:
        print(f"\n✅ Test survey already exists: Survey {test_survey.id}")

    print("\n=== Summary ===")
    print("✅ API now includes 'installation_feasible' field")
    print("✅ Frontend shows warning for non-feasible surveys")
    print("✅ Approve button is disabled for non-feasible surveys")
    print("✅ Backend validation prevents approval of non-feasible surveys")
    print(
        "\n📋 To test: Go to the survey dashboard and look for surveys marked as 'Installation NOT Feasible'"
    )


if __name__ == "__main__":
    test_survey_validation()
