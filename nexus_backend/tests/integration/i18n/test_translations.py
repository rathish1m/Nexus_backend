#!/usr/bin/env python
"""
Test script to verify translation functionality for login page
"""

import pytest

from django.utils.translation import activate, gettext


@pytest.mark.django_db
def test_translations():
    print("Testing translations for login page...")

    # Test French translations
    print("\n=== FRENCH TRANSLATIONS ===")
    activate("fr")

    messages_to_test = [
        "Username and password are required.",
        "Invalid username or password.",
        "Your account is disabled. Please contact support.",
        "No phone number on file. Cannot deliver OTP.",
        "Your session has expired. Please login again.",
        "User not found.",
        "OTP session not found. Please login again.",
        "OTP expired. Please login again.",
        "Too many attempts. Please login again.",
        "Invalid OTP. Try again.",
        # Client app messages
        "File size must not exceed 10MB.",
        "Documents received — under review",
        "KYC Verification Required",
        "Start KYC",
        "Resubmit KYC",
        "Contact support",
        "Go to dashboard",
        "Government ID (passport or national ID)",
        "Selfie (liveness check)",
        "Address details",
    ]

    for message in messages_to_test:
        translated = gettext(message)
        print(f"EN: {message}")
        print(f"FR: {translated}")
        print("-" * 50)

    # Test English translations (fallback)
    print("\n=== ENGLISH TRANSLATIONS ===")
    activate("en")

    for message in messages_to_test:
        translated = gettext(message)
        print(f"EN: {message}")
        print(f"EN: {translated}")
        print("-" * 50)


if __name__ == "__main__":
    test_translations()
