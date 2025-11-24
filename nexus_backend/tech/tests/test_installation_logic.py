#!/usr/bin/env python3
# ruff: noqa: E402


"""
Test script for the new installation creation logic
Vérifier que les InstallationActivity sont créées au bon moment
"""

import os

import pytest

import django

# Configuration Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from decimal import Decimal

from django.utils import timezone

from main.models import InstallationActivity, Order, StarlinkKit, User
from site_survey.models import AdditionalBilling, SiteSurvey, SurveyAdditionalCost


@pytest.mark.django_db
def test_installation_creation_logic():
    print("🧪 Test de la nouvelle logique de création d'InstallationActivity")
    print("=" * 60)

    # Créer un utilisateur test
    try:
        user = User.objects.get(username="testuser")
    except User.DoesNotExist:
        user = User.objects.create_user(
            username="testuser",
            email="test@example.com",
            first_name="Test",
            last_name="User",
            password="testpass123",
        )

    # Créer un kit Starlink test
    try:
        kit = StarlinkKit.objects.first()
        if not kit:
            kit = StarlinkKit.objects.create(
                name="Test Kit",
                model="TEST-MODEL",
                base_price_usd=Decimal("500.00"),
                description="Kit de test",
                kit_type="standard",
            )
    except Exception:  # noqa: E722
        kit = StarlinkKit.objects.create(
            name="Test Kit",
            model="TEST-MODEL",
            base_price_usd=Decimal("500.00"),
            description="Kit de test",
            kit_type="standard",
        )

    print(f"👤 Utilisateur test: {user.email}")
    print(f"📦 Kit test: {kit.name}")

    # Create kit inventory first
    from main.models import StarlinkKitInventory

    kit_inventory = StarlinkKitInventory.objects.create(
        kit=kit, serial_number="TEST123", status="available"
    )

    # Test 1: Survey sans coûts additionnels
    print("\n🧪 Test 1: Survey sans coûts additionnels")
    print("-" * 40)

    # Créer une commande
    order1 = Order.objects.create(
        user=user,
        kit_inventory=kit_inventory,
        plan=None,  # Optional
        payment_status="paid",  # Ceci devrait créer automatiquement un SiteSurvey
        status="processing",
    )

    print(f"📄 Commande créée: {order1.order_reference}")

    # Vérifier que SiteSurvey a été créé mais pas InstallationActivity
    try:
        survey1 = SiteSurvey.objects.get(order=order1)
        print(f"✅ SiteSurvey créé: ID {survey1.id}, Status: {survey1.status}")
    except SiteSurvey.DoesNotExist:
        print("❌ SiteSurvey pas créé!")
        return

    # Vérifier qu'InstallationActivity n'existe pas encore
    installation_exists = InstallationActivity.objects.filter(order=order1).exists()
    print(f"🔍 InstallationActivity existe: {installation_exists} (devrait être False)")

    # Approuver le survey (sans coûts additionnels)
    survey1.status = "approved"
    survey1.requires_additional_equipment = False
    survey1.save()

    print("✅ Survey approuvé (sans coûts additionnels)")

    # Vérifier qu'InstallationActivity a été créée
    installation_exists = InstallationActivity.objects.filter(order=order1).exists()
    print(
        f"🔍 InstallationActivity créée après approbation: {installation_exists} (devrait être True)"
    )

    if installation_exists:
        installation1 = InstallationActivity.objects.get(order=order1)
        print(f"📋 Notes installation: {installation1.notes}")

    # Test 2: Survey avec coûts additionnels
    print("\n🧪 Test 2: Survey avec coûts additionnels")
    print("-" * 40)

    # Create another kit inventory
    kit_inventory2 = StarlinkKitInventory.objects.create(
        kit=kit, serial_number="TEST456", status="available"
    )

    # Créer une autre commande
    order2 = Order.objects.create(
        user=user,
        kit_inventory=kit_inventory2,
        payment_status="paid",
        status="processing",
    )

    print(f"📄 Commande créée: {order2.order_reference}")

    # Récupérer le survey automatiquement créé
    survey2 = SiteSurvey.objects.get(order=order2)
    print(f"✅ SiteSurvey créé: ID {survey2.id}")

    # Ajouter des coûts additionnels - d'abord créer l'ExtraCharge
    from site_survey.models import ExtraCharge

    extra_charge, _ = ExtraCharge.objects.get_or_create(
        item_name="Cable extra 50m",
        defaults={
            "cost_type": "cable",
            "description": "Cable supplémentaire nécessaire",
            "unit_price": Decimal("75.00"),
        },
    )

    # Puis créer le SurveyAdditionalCost avec la relation ExtraCharge
    additional_cost = SurveyAdditionalCost.objects.create(
        survey=survey2,
        extra_charge=extra_charge,
        quantity=1,
        justification="Distance importante entre kit et maison",
    )

    print(
        f"💰 Coût additionnel ajouté: {additional_cost.item_name} - ${additional_cost.total_price}"
    )

    # Marquer le survey comme nécessitant des coûts additionnels
    survey2.requires_additional_equipment = True
    survey2.estimated_additional_cost = additional_cost.total_price
    survey2.cost_justification = "Cable supplémentaire requis"
    survey2.save()

    # Approuver le survey (avec coûts additionnels)
    survey2.status = "approved"
    survey2.save()

    print("✅ Survey approuvé (avec coûts additionnels)")

    # Vérifier qu'InstallationActivity n'est PAS créée
    installation_exists = InstallationActivity.objects.filter(order=order2).exists()
    print(
        f"🔍 InstallationActivity créée après approbation: {installation_exists} (devrait être False)"
    )

    # Créer la facturation additionnelle
    billing = AdditionalBilling.objects.create(
        survey=survey2,
        order=order2,
        customer=user,
        status="pending_approval",
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )

    print(f"🧾 Facturation additionnelle créée: {billing.billing_reference}")
    print(f"💰 Montant total: ${billing.total_amount}")

    # Vérifier qu'InstallationActivity n'est toujours pas créée
    installation_exists = InstallationActivity.objects.filter(order=order2).exists()
    print(
        f"🔍 InstallationActivity après création billing: {installation_exists} (devrait être False)"
    )

    # Approuver la facturation
    billing.status = "approved"
    billing.save()

    print("✅ Facturation approuvée par le client")

    # Vérifier qu'InstallationActivity n'est toujours pas créée
    installation_exists = InstallationActivity.objects.filter(order=order2).exists()
    print(
        f"🔍 InstallationActivity après approbation billing: {installation_exists} (devrait être False)"
    )

    # Marquer la facturation comme payée
    billing.status = "paid"
    billing.save()

    print("💳 Facturation payée")

    # Vérifier qu'InstallationActivity est maintenant créée
    installation_exists = InstallationActivity.objects.filter(order=order2).exists()
    print(
        f"🔍 InstallationActivity après paiement: {installation_exists} (devrait être True)"
    )

    if installation_exists:
        installation2 = InstallationActivity.objects.get(order=order2)
        print(f"📋 Notes installation: {installation2.notes}")

    print("\n🎉 Tests terminés!")
    print("=" * 60)

    # Résumé
    print("📊 Résumé des tests:")
    print(
        f"  - Survey sans coûts additionnels: {'✅ RÉUSSI' if InstallationActivity.objects.filter(order=order1).exists() else '❌ ÉCHOUÉ'}"
    )
    print(
        f"  - Survey avec coûts additionnels: {'✅ RÉUSSI' if InstallationActivity.objects.filter(order=order2).exists() else '❌ ÉCHOUÉ'}"
    )

    # Nettoyage (optionnel)
    print("\n🧹 Nettoyage des données de test...")
    InstallationActivity.objects.filter(order__in=[order1, order2]).delete()
    AdditionalBilling.objects.filter(order__in=[order1, order2]).delete()
    SurveyAdditionalCost.objects.filter(survey__order__in=[order1, order2]).delete()
    SiteSurvey.objects.filter(order__in=[order1, order2]).delete()
    Order.objects.filter(id__in=[order1.id, order2.id]).delete()

    print("✅ Nettoyage terminé")


if __name__ == "__main__":
    test_installation_creation_logic()
