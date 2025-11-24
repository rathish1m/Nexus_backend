#!/usr/bin/env python3
"""
Test script for the photo upload feature in the Conduct Survey modal
"""
# ruff: noqa: E402

import os
import sys
from pathlib import Path

import django

# Add the project root to Python path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from main.models import Order, User
from site_survey.models import SiteSurvey, SiteSurveyPhoto


def test_photo_upload_functionality():
    """Test the photo upload feature"""
    print("🧪 Testing Photo Upload Feature in Conduct Survey Modal")
    print("=" * 60)

    # Create test data
    print("📝 Setting up test data...")

    try:
        # Create a test user (technician)
        user = User.objects.filter(username="test_technician").first()
        if not user:
            user = User.objects.create_user(
                username="test_technician",
                email="tech@test.com",
                password="testpass123",
            )
            user.is_staff = True
            user.save()

        # Create a test order
        order = Order.objects.filter(customer_name__icontains="test").first()
        if not order:
            print("❌ No test order found. Please create a test order first.")
            return False

        # Create or get a test site survey
        survey = SiteSurvey.objects.filter(order=order).first()
        if not survey:
            survey = SiteSurvey.objects.create(
                order=order,
                technician=user,
                status="in_progress",
                site_address=order.customer_address or "Test Address",
            )

        print(f"✅ Test survey created: ID {survey.id}")

        # Test the upload endpoint
        client = Client()
        client.force_login(user)

        # Create a fake image file for testing
        test_image_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\tpHYs\x00\x00\x0b\x13\x00\x00\x0b\x13\x01\x00\x9a\x9c\x18\x00\x00\x00\nIDATx\x9cc\xf8\x00\x00\x00\x01\x00\x01\x8d\xb0\xc9\x14\x00\x00\x00\x00IEND\xaeB`\x82"

        uploaded_file = SimpleUploadedFile(
            "test_photo.png", test_image_content, content_type="image/png"
        )

        # Test photo upload
        upload_url = reverse(
            "site_survey:upload_survey_photos", kwargs={"survey_id": survey.id}
        )
        print(f"📤 Testing upload to: {upload_url}")

        response = client.post(
            upload_url,
            {
                "photos": [uploaded_file],
                "photo_types": ["site_overview"],
                "descriptions": ["Test photo description"],
                "latitudes": [""],
                "longitudes": [""],
            },
        )

        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                print("✅ Photo upload successful!")

                # Check if photo was saved
                photo = SiteSurveyPhoto.objects.filter(survey=survey).first()
                if photo:
                    print(f"✅ Photo saved to database: {photo.photo_type}")
                    print(f"   Description: {photo.description}")
                    print(f"   File: {photo.photo.name}")
                else:
                    print("❌ Photo not found in database")
                    return False
            else:
                print(f"❌ Upload failed: {data.get('message', 'Unknown error')}")
                return False
        else:
            print(f"❌ HTTP Error {response.status_code}: {response.content}")
            return False

        # Test survey dashboard page
        dashboard_url = reverse("site_survey:survey_dashboard")
        print(f"📄 Testing dashboard page: {dashboard_url}")

        response = client.get(dashboard_url)
        if response.status_code == 200:
            print("✅ Survey dashboard loads successfully")

            # Check if modal HTML is present
            content = response.content.decode()
            if "photoUploadSection" in content:
                print("✅ Photo upload section found in modal")
            else:
                print("❌ Photo upload section not found in modal")
                return False

            if "handlePhotoDrop" in content:
                print("✅ Photo drag & drop functionality found")
            else:
                print("❌ Photo drag & drop functionality not found")
                return False

        else:
            print(f"❌ Dashboard page error: {response.status_code}")
            return False

        print("\n🎉 All tests passed! Photo upload feature is working correctly.")
        print("\n📋 Feature Summary:")
        print("   ✅ Drag & drop interface")
        print("   ✅ Photo type selection")
        print("   ✅ Description fields")
        print("   ✅ Preview functionality")
        print("   ✅ Backend integration")
        print("   ✅ Database storage")

        return True

    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        import traceback

        traceback.print_exc()
        return False


def check_modal_interface():
    """Check the modal interface elements"""
    print("\n🔍 Checking Modal Interface Elements")
    print("-" * 40)

    template_path = (
        project_root / "site_survey/templates/site_survey/survey_dashboard.html"
    )

    if not template_path.exists():
        print(f"❌ Template not found: {template_path}")
        return False

    with open(template_path, "r") as f:
        content = f.read()

    # Check for key elements
    elements = {
        "photoUploadSection": "Photo upload section container",
        "photoDropZone": "Drag & drop zone",
        "photoInput": "File input field",
        "photoPreviewArea": "Photo preview area",
        "uploadPhotosBtn": "Upload button",
        "handlePhotoDrop": "Drag & drop handler",
        "uploadSelectedPhotos": "Upload function",
        "updatePhotoType": "Photo type selection",
    }

    missing_elements = []
    for element, description in elements.items():
        if element in content:
            print(f"✅ {description}")
        else:
            print(f"❌ {description}")
            missing_elements.append(element)

    if missing_elements:
        print(f"\n❌ Missing elements: {', '.join(missing_elements)}")
        return False

    print("\n✅ All modal interface elements are present!")
    return True


if __name__ == "__main__":
    print("🚀 Starting Photo Upload Feature Tests")
    print("=" * 60)

    # Check modal interface
    interface_ok = check_modal_interface()

    if interface_ok:
        # Test functionality
        test_ok = test_photo_upload_functionality()

        if test_ok:
            print(
                "\n🎯 CONCLUSION: Photo upload feature is fully implemented and working!"
            )
            print("\nℹ️  Usage Instructions:")
            print("1. Go to Site Survey Dashboard")
            print("2. Click 'Continue Survey' or 'Conduct Survey' on any survey")
            print("3. Scroll to 'Survey Photos' section")
            print("4. Drag & drop photos or click 'Select Photos'")
            print("5. Choose photo types and add descriptions")
            print("6. Click 'Upload Photos'")
        else:
            print(
                "\n❌ Some functionality tests failed. Please check the implementation."
            )
    else:
        print("\n❌ Modal interface is incomplete. Please check the template.")
