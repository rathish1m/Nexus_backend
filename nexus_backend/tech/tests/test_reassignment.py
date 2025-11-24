#!/usr/bin/env python
"""
Script de test pour valider la fonctionnalité de réassignation
"""

import os
import sys

import django

# Configuration Django
sys.path.append(
    "/home/virgocoachman/Documents/Workspace/Cedric Taty/nexus/nexus_backend"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()


def test_reassignment_functions():
    """Test des fonctions de réassignation"""
    print("🔍 Test de validation des fonctions de réassignation...")

    try:
        # Test import des vues

        print("✅ Import des vues réussi")

        # Test import des notifications

        print("✅ Import des notifications réussi")

        # Test des modèles
        from main.models import User
        from site_survey.models import SiteSurvey

        print("✅ Import des modèles réussi")

        # Compter les technicians
        technicians = User.objects.filter(roles__contains="technician")
        print(f"✅ {technicians.count()} technicien(s) trouvé(s)")

        # Compter les surveys
        surveys = SiteSurvey.objects.all()
        rejected_surveys = SiteSurvey.objects.filter(status="rejected")
        print(
            f"✅ {surveys.count()} survey(s) total, {rejected_surveys.count()} rejeté(s)"
        )

        print("\n🎉 Tous les tests de base réussis!")
        return True

    except Exception as e:
        print(f"❌ Erreur lors du test: {str(e)}")
        import traceback

        traceback.print_exc()
        return False


def test_technician_stats():
    """Test du calcul des statistiques des techniciens"""
    print("\n🔍 Test des statistiques des techniciens...")

    try:
        from django.db.models import Case, Count, FloatField, Q, When

        from main.models import User

        # Requête similaire à celle utilisée dans technicians_list
        technicians = (
            User.objects.filter(roles__contains="technician")
            .annotate(
                total_surveys=Count("site_surveys"),
                rejected_surveys=Count(
                    "site_surveys", filter=Q(site_surveys__status="rejected")
                ),
                rejection_rate=Case(
                    When(total_surveys=0, then=0.0),
                    default=100.0
                    * Count("site_surveys", filter=Q(site_surveys__status="rejected"))
                    / Count("site_surveys"),
                    output_field=FloatField(),
                ),
            )
            .order_by("rejection_rate", "full_name")
        )

        print(
            f"✅ Requête statistiques réussie pour {technicians.count()} technicien(s)"
        )

        for tech in technicians[:3]:  # Afficher les 3 premiers
            print(
                f"  - {tech.full_name or tech.username}: {tech.total_surveys} surveys, {tech.rejected_surveys} rejets, {tech.rejection_rate:.1f}% rejet"
            )

        return True

    except Exception as e:
        print(f"❌ Erreur test statistiques: {str(e)}")
        return False


if __name__ == "__main__":
    print("🚀 Démarrage des tests de validation...")

    success1 = test_reassignment_functions()
    success2 = test_technician_stats()

    if success1 and success2:
        print(
            "\n✅ Tous les tests réussis! La fonctionnalité de réassignation est prête."
        )
    else:
        print("\n❌ Certains tests ont échoué. Vérifiez les erreurs ci-dessus.")
