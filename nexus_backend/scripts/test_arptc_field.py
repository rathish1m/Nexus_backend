#!/usr/bin/env python
"""
Script de test manuel pour vérifier que le champ ARPTC License
peut être sauvegardé et affiché correctement.
"""

import os

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from main.models import CompanySettings


def test_arptc_field():
    print("=" * 60)
    print("Test du champ ARPTC License")
    print("=" * 60)

    # Récupérer les paramètres de l'entreprise
    cs = CompanySettings.get()

    print("\n1. État actuel de la base de données:")
    print(f"   RCCM: {cs.rccm}")
    print(f"   Id.Nat: {cs.id_nat}")
    print(f"   NIF: {cs.nif}")
    print(f"   ARPTC License: {cs.arptc_license}")

    # Tester la sauvegarde d'une valeur
    print("\n2. Test de sauvegarde d'une valeur ARPTC...")
    original_value = cs.arptc_license
    test_value = "ARPTC-TEST-12345"
    cs.arptc_license = test_value
    cs.save()
    cs.refresh_from_db()

    if cs.arptc_license == test_value:
        print(f"   ✅ Sauvegarde réussie: {cs.arptc_license}")
    else:
        print(f"   ❌ Échec: attendu '{test_value}', obtenu '{cs.arptc_license}'")

    # Tester le vidage du champ
    print("\n3. Test de vidage du champ...")
    cs.arptc_license = ""
    cs.save()
    cs.refresh_from_db()

    if cs.arptc_license == "":
        print("   ✅ Vidage réussi: le champ est maintenant vide")
    else:
        print(f"   ❌ Échec: le champ contient encore '{cs.arptc_license}'")

    # Restaurer la valeur originale
    print("\n4. Restauration de la valeur originale...")
    cs.arptc_license = original_value
    cs.save()
    cs.refresh_from_db()
    print(f"   Valeur restaurée: {cs.arptc_license}")

    print("\n" + "=" * 60)
    print("Test terminé avec succès !")
    print("=" * 60)


if __name__ == "__main__":
    test_arptc_field()
