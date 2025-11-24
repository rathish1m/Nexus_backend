#!/usr/bin/env python3
"""
Script pour créer des données de test pour les rapports d'installation
"""

import os
import sys
from datetime import timedelta

import django

# Configuration Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.utils import timezone

from main.models import InstallationActivity, Order, User


def create_test_data():
    print("=== Création de données de test ===")

    # Trouver un utilisateur technicien
    try:
        technician = User.objects.filter(is_staff=True).first()
        if not technician:
            print("❌ Aucun technicien trouvé")
            return
        print(f"✅ Technicien trouvé: {technician.username}")
    except Exception as e:
        print(f"❌ Erreur: {e}")
        return

    # Créer une commande de test s'il n'y en a pas
    try:
        customer = User.objects.filter(is_staff=False).first()
        if not customer:
            # Créer un client de test
            customer = User.objects.create_user(
                username="test_customer",
                email="customer@test.com",
                password="testpass123",
            )
            print(f"✅ Client de test créé: {customer.username}")
        else:
            print(f"✅ Client trouvé: {customer.username}")

        order = Order.objects.filter(user=customer).first()
        if not order:
            order = Order.objects.create(
                user=customer, total_amount=299.99, status="paid"
            )
            print(f"✅ Commande de test créée: ID={order.id}")
        else:
            print(f"✅ Commande trouvée: ID={order.id}")

    except Exception as e:
        print(f"❌ Erreur lors de la création de la commande: {e}")
        return

    # Créer une activité d'installation avec des données de test
    try:
        activity = InstallationActivity.objects.filter(technician=technician).first()
        if activity:
            print(f"✅ Activité existante trouvée: ID={activity.id}")
        else:
            activity = InstallationActivity.objects.create(
                order=order,
                technician=technician,
                status="submitted",  # Statut qui permet l'édition
                started_at=timezone.now() - timedelta(hours=2),
                completed_at=timezone.now() - timedelta(hours=1),
                submitted_at=timezone.now() - timedelta(minutes=30),
                edit_deadline=timezone.now()
                + timedelta(hours=23, minutes=30),  # 24h moins 30min
            )
            print(f"✅ Activité créée: ID={activity.id}")

        # Ajouter seulement des données de test basiques
        activity.site_address = "123 Test Street"
        activity.site_notes = "Test site"
        activity.dish_serial_number = "DISH123"
        activity.router_serial_number = "RTR123"
        activity.wifi_ssid = "TestNet"
        activity.wifi_password = "Pass123"

        activity.save()
        print(f"✅ Données de test ajoutées à l'activité ID={activity.id}")
        print(f"   Status: {activity.status}")
        print(f"   Peut être éditée: {activity.can_be_edited()}")
        print(f"   Temps restant: {activity.time_left_for_editing():.1f}h")

    except Exception as e:
        print(f"❌ Erreur lors de la création de l'activité: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    create_test_data()
