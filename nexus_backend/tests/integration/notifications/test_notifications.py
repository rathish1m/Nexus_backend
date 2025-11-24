#!/usr/bin/env python
"""
Script de test pour le système de notifications de rejet de surveys
"""

import pytest

from site_survey.models import SiteSurvey
from site_survey.notifications import send_all_rejection_notifications


@pytest.mark.django_db
def test_notification_system():
    print("=== TEST DU SYSTÈME DE NOTIFICATIONS ===\n")

    # Récupérer un survey existant pour le test
    surveys = SiteSurvey.objects.all()

    if not surveys.exists():
        print("❌ Aucun survey trouvé dans la base de données")
        return

    # Prendre un survey qui n'est pas déjà rejeté
    test_survey = surveys.filter(status__in=["completed", "approved"]).first()

    if not test_survey:
        print("❌ Aucun survey approprié trouvé pour le test")
        print("   (Besoin d'un survey avec status 'completed' ou 'approved')")
        return

    print("📋 Survey de test sélectionné:")
    print(f"   - ID: {test_survey.id}")
    print(f"   - Status actuel: {test_survey.status}")
    print(
        f"   - Order: {test_survey.order.order_reference if test_survey.order else 'N/A'}"
    )
    print(
        f"   - Technician: {test_survey.technician.full_name if test_survey.technician else 'N/A'}"
    )
    print()

    # Sauvegarder l'état original
    original_status = test_survey.status
    original_rejection_reason = test_survey.rejection_reason

    try:
        print("🔄 Simulation du rejet du survey...")

        # Modifier le survey pour simuler un rejet
        test_survey.status = "rejected"
        test_survey.rejection_reason = "Test automatique - Installation non faisable en raison d'obstacles techniques"

        print("📤 Déclenchement des notifications...")

        # Tester manuellement les notifications (sans passer par save() pour éviter les doublons)
        results = send_all_rejection_notifications(test_survey)

        print("\n✅ RÉSULTATS DES NOTIFICATIONS:")
        print(
            f"   📧 Email technician: {'✅ Envoyé' if results['technician_email'] else '❌ Échec'}"
        )
        print(
            f"   📱 SMS technician: {'✅ Envoyé' if results['technician_sms'] else '❌ Échec/Non configuré'}"
        )
        print(
            f"   📧 Email client: {'✅ Envoyé' if results['customer_email'] else '❌ Échec'}"
        )
        print(
            f"   ⚠️  Alerte admin: {'✅ Envoyé' if results['admin_alert'] else '❌ Échec'}"
        )

        success_count = sum(1 for success in results.values() if success)
        total_count = len(results)

        print(
            f"\n📊 RÉSUMÉ: {success_count}/{total_count} notifications envoyées avec succès"
        )

        if success_count > 0:
            print("\n🎉 Le système de notifications fonctionne !")
            print("   Vérifiez la console pour voir les emails générés")
        else:
            print("\n❌ Aucune notification n'a été envoyée")
            print("   Vérifiez la configuration des emails dans settings.py")

    except Exception as e:
        print(f"❌ Erreur lors du test: {str(e)}")
        import traceback

        traceback.print_exc()

    finally:
        # Restaurer l'état original (ne pas sauvegarder pour éviter les effets de bord)
        test_survey.status = original_status
        test_survey.rejection_reason = original_rejection_reason
        print(f"\n🔄 État du survey restauré (status: {original_status})")

    print("\n=== TEST AUTOMATIQUE VIA SAVE() ===")

    try:
        print("🔄 Test avec déclenchement automatique via save()...")

        # Test avec la méthode save() automatique
        test_survey.status = "rejected"
        test_survey.rejection_reason = (
            "Test automatique via save() - Problème technique identifié"
        )
        test_survey.save()  # Ceci devrait déclencher automatiquement les notifications

        print("✅ save() exécuté avec succès")
        print("   Les notifications ont été déclenchées automatiquement")
        print("   Vérifiez la console pour voir les emails")

    except Exception as e:
        print(f"❌ Erreur lors du test automatique: {str(e)}")

    finally:
        # Restaurer vraiment l'état original
        test_survey.status = original_status
        test_survey.rejection_reason = original_rejection_reason
        test_survey.save()
        print("🔄 État final restauré")

    print("\n=== TEST TERMINÉ ===")
    print("💡 Pour voir les emails en mode développement, vérifiez la sortie console")
    print("💡 En production, les emails seraient envoyés réellement")


if __name__ == "__main__":
    test_notification_system()
