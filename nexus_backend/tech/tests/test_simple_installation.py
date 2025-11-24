#!/usr/bin/env python3
# ruff: noqa: E402


"""
Test simple pour vérifier la logique de création d'InstallationActivity
"""

import os

import pytest

import django

# Configuration Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()


from django.utils import timezone

from main.models import InstallationActivity
from site_survey.models import SiteSurvey


@pytest.mark.django_db
def test_simple_logic():
    print("🧪 Test simple de la logique d'installation")
    print("=" * 50)

    # Test avec un survey existant
    print("🔍 Cherche un survey existant...")

    surveys = SiteSurvey.objects.all()[:2]

    if not surveys:
        print("❌ Aucun survey trouvé. Créez d'abord des données de test.")
        return

    for i, survey in enumerate(surveys, 1):
        print(f"\n🧪 Test {i}: Survey ID {survey.id}")
        print(f"📄 Commande: {survey.order.order_reference}")
        print(f"📊 Status: {survey.status}")
        print(f"💰 Coûts additionnels requis: {survey.requires_additional_equipment}")

        # Vérifier l'état actuel
        installation_exists = InstallationActivity.objects.filter(
            order=survey.order
        ).exists()
        print(f"🔍 InstallationActivity existe: {installation_exists}")

        # Tester la méthode can_create_installation
        can_create = survey.can_create_installation()
        print(f"🤔 Peut créer installation: {can_create}")

        if survey.status != "approved":
            print("📝 Approbation du survey...")
            survey.status = "approved"
            survey.approved_at = timezone.now()
            survey.save()

            # Vérifier si installation a été créée
            installation_exists_after = InstallationActivity.objects.filter(
                order=survey.order
            ).exists()
            print(
                f"🔍 InstallationActivity après approbation: {installation_exists_after}"
            )

            if installation_exists_after and not installation_exists:
                installation = InstallationActivity.objects.get(order=survey.order)
                print(f"✅ Installation créée: {installation.notes}")
            elif survey.requires_additional_equipment:
                print("💰 Coûts additionnels requis - installation pas encore créée")

                # Vérifier s'il y a une facturation additionnelle
                if hasattr(survey, "additional_billing"):
                    billing = survey.additional_billing
                    print(
                        f"🧾 Facturation: {billing.billing_reference}, Status: {billing.status}"
                    )

                    if billing.status != "paid":
                        print("💳 Simulation du paiement...")
                        billing.status = "paid"
                        billing.save()

                        # Vérifier si installation a été créée maintenant
                        installation_exists_final = InstallationActivity.objects.filter(
                            order=survey.order
                        ).exists()
                        print(
                            f"🔍 InstallationActivity après paiement: {installation_exists_final}"
                        )

                        if installation_exists_final and not installation_exists:
                            installation = InstallationActivity.objects.get(
                                order=survey.order
                            )
                            print(
                                f"✅ Installation créée après paiement: {installation.notes}"
                            )
                else:
                    print("⚠️  Pas de facturation additionnelle trouvée")

        print("-" * 30)

    print("\n✅ Test terminé!")


if __name__ == "__main__":
    test_simple_logic()
