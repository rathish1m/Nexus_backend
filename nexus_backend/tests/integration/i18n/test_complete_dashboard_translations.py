#!/usr/bin/env python3
"""
Test script pour vérifier toutes les traductions du dashboard client
"""

import pytest

from django.utils.translation import activate
from django.utils.translation import gettext as _


@pytest.mark.django_db
def test_all_dashboard_translations():
    """Test de toutes les traductions du dashboard client"""

    print("=== Test complet des traductions du dashboard client ===\n")

    # Toutes les nouvelles traductions ajoutées
    test_strings = [
        # Header
        "Welcome",
        # Billing cards
        "Unpaid Due",
        "Pay Now",
        "Account Credit",
        "View Ledger",
        "Net Due",
        "Details",
        "Account Credit Ledger",
        "Loading…",
        # Main order section
        "Start your order",
        "Starlink kit + plan in 3 quick steps",
        "Get started",
        # Dashboard main cards (previous session)
        "Your Subscription",
        "Billing",
        "Support",
        "Settings",
        "View Subscription",
        "Contact Support",
        "Manage Settings",
    ]

    # Test en français
    activate("fr")
    print("🇫🇷 FRANÇAIS:")
    for string in test_strings:
        translation = _(string)
        # Pour "Support", c'est le même mot en français, donc c'est OK
        is_translated = translation != string or string == "Support"
        status = "✅" if is_translated else "❌"
        print(f"  {status} '{string}' → '{translation}'")

    print()

    # Test en anglais
    activate("en")
    print("🇬🇧 ANGLAIS:")
    for string in test_strings:
        translation = _(string)
        status = "✅" if translation == string else "❌"
        print(f"  {status} '{string}' → '{translation}'")

    print("\n=== Test terminé ===")

    # Statistiques
    activate("fr")
    french_translated = sum(1 for s in test_strings if _(s) != s or s == "Support")
    total = len(test_strings)

    print("\n📊 Statistiques:")
    print(f"   Total des chaînes testées: {total}")
    print(f"   Traduites en français: {french_translated}")
    print(f"   Pourcentage de traduction: {(french_translated/total)*100:.1f}%")

    if french_translated == total:
        print("\n🎉 SUCCÈS: Toutes les traductions sont opérationnelles !")
    else:
        print(f"\n⚠️  ATTENTION: {total - french_translated} traduction(s) manquante(s)")


if __name__ == "__main__":
    test_all_dashboard_translations()
