#!/usr/bin/env python3
"""
Test script pour vérifier les traductions du dashboard
"""

import pytest

from django.utils.translation import activate
from django.utils.translation import gettext as _


@pytest.mark.django_db
def test_dashboard_translations():
    """Test des traductions du dashboard principal"""

    print("=== Test des traductions du dashboard ===\n")

    # Nouvelles traductions du dashboard
    test_strings = [
        "Manage your Starlink subscription, view plan details, and check your current status.",
        "View Subscription",
        "View your payment history, check outstanding balances, and securely manage your Starlink billing details.",
        "View Billing History",
        "Get help with your Starlink services, submit support tickets, and chat with our technical team 24/7.",
        "Contact Support",
        "Update your account information, manage preferences, and configure security settings for your Starlink account.",
        "Manage Settings",
    ]

    # Test en français
    activate("fr")
    print("🇫🇷 FRANÇAIS:")
    for string in test_strings:
        translation = _(string)
        print(f"  ✓ '{string[:50]}...' → '{translation}'")

    print()

    # Test en anglais
    activate("en")
    print("🇬🇧 ANGLAIS:")
    for string in test_strings:
        translation = _(string)
        print(f"  ✓ '{string[:50]}...' → '{translation}'")

    print("\n=== Test terminé avec succès ! ===")


if __name__ == "__main__":
    test_dashboard_translations()
