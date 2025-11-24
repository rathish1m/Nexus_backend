#!/usr/bin/env python
"""
Test rapide pour vérifier la persistance du champ Province
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from main.models import CompanySettings  # noqa: E402


def test_province_persistence():
    print("=" * 60)
    print("Test de persistance du champ Province")
    print("=" * 60)

    cs = CompanySettings.get()

    print("\n1. État actuel:")
    print(f"   Province: {cs.province}")

    # Sauvegarder une valeur
    print("\n2. Test de sauvegarde...")
    original = cs.province
    cs.province = "Haut-Katanga"
    cs.save()
    cs.refresh_from_db()

    if cs.province == "Haut-Katanga":
        print(f"   ✅ Sauvegarde réussie: {cs.province}")
    else:
        print(f"   ❌ Échec: attendu 'Haut-Katanga', obtenu '{cs.province}'")
        return

    # Vider le champ
    print("\n3. Test de vidage...")
    cs.province = ""
    cs.save()
    cs.refresh_from_db()

    if cs.province == "":
        print("   ✅ Vidage réussi: le champ est vide")
    else:
        print(f"   ❌ Échec: le champ contient '{cs.province}'")
        return

    # Restaurer
    print("\n4. Restauration...")
    cs.province = original
    cs.save()
    print(f"   Valeur restaurée: {cs.province}")

    print("\n" + "=" * 60)
    print("✅ Test terminé avec succès !")
    print("=" * 60)


if __name__ == "__main__":
    test_province_persistence()
