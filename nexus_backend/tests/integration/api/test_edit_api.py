#!/usr/bin/env python3
"""
Script de test pour vérifier l'API d'édition des rapports d'installation
"""

import pytest

from django.test import Client

from main.models import InstallationActivity, User


@pytest.mark.django_db
def test_edit_api():
    print("=== Test de l'API d'édition ===")

    # Créer un client de test
    client = Client()

    # Trouver un utilisateur technicien
    try:
        technician = User.objects.filter(is_staff=True).first()
        if not technician:
            print("❌ Aucun technicien trouvé")
            return
        print(f"✅ Technicien trouvé: {technician.username}")
    except Exception as e:
        print(f"❌ Erreur lors de la recherche d'un technicien: {e}")
        return

    # Trouver ou créer une activité d'installation
    try:
        activity = InstallationActivity.objects.filter(technician=technician).first()
        if not activity:
            print("❌ Aucune activité d'installation trouvée pour ce technicien")
            return
        print(f"✅ Activité trouvée: ID={activity.id}, Status={activity.status}")
        print(f"   Peut être éditée: {activity.can_be_edited()}")

        # Ajouter quelques données de test si l'activité est vide
        if not activity.site_address:
            activity.site_address = "123 Test Street"
            activity.dish_serial_number = "TEST12345"
            activity.router_serial_number = "ROUTER67890"
            activity.save()
            print("✅ Données de test ajoutées")

    except Exception as e:
        print(f"❌ Erreur lors de la recherche d'activité: {e}")
        return

    # Se connecter comme technicien
    try:
        client.force_login(technician)
        print("✅ Connecté comme technicien")
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return

    # Tester l'endpoint GET
    try:
        url = f"/fr/tech/api/installation-report/{activity.id}/data/"
        print(f"🔍 Test de l'URL: {url}")

        response = client.get(url)
        print(f"   Status code: {response.status_code}")

        if response.status_code == 200:
            data = response.json()
            print(f"   Success: {data.get('success')}")
            if data.get("success"):
                fields = data.get("data", {})
                print(f"   Nombre de champs: {len(fields)}")
                print("   Champs avec valeurs:")
                for key, value in fields.items():
                    if value:
                        print(f"     - {key}: {value}")
            else:
                print(f"   Erreur: {data.get('error')}")
        else:
            print(f"   Erreur HTTP: {response.content}")

    except Exception as e:
        print(f"❌ Erreur lors du test de l'API: {e}")


if __name__ == "__main__":
    test_edit_api()
