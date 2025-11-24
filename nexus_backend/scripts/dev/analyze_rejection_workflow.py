#!/usr/bin/env python
"""
Analyse du Workflow après Rejet de Site Survey
"""

import os

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from site_survey.models import SiteSurvey


def analyze_rejection_workflow():
    print("=== ANALYSE DU WORKFLOW APRÈS REJET DE SITE SURVEY ===\n")

    # 1. Trouver les surveys rejetés
    rejected_surveys = SiteSurvey.objects.filter(status="rejected")
    print(f"📊 Total des surveys rejetés: {rejected_surveys.count()}")

    if rejected_surveys.exists():
        print("\n🔍 Détails des surveys rejetés:")
        for survey in rejected_surveys[:5]:  # Afficher les 5 premiers
            print(f"- Survey {survey.id}:")
            print(f"  Order: {survey.order.order_reference if survey.order else 'N/A'}")
            print(
                f"  Technician: {survey.technician.full_name if survey.technician else 'N/A'}"
            )
            print(f"  Rejection Reason: {survey.rejection_reason or 'Pas spécifié'}")
            print(f"  Created: {survey.created_at.strftime('%Y-%m-%d %H:%M')}")
            print()

    print("=== WORKFLOW ACTUEL ===")
    print("1. ✅ Admin rejette le survey avec une raison")
    print("2. ✅ Status changé vers 'rejected'")
    print("3. ✅ Raison de rejet sauvegardée dans rejection_reason")
    print("4. ❌ AUCUNE notification automatique au technician")
    print("5. ❌ AUCUNE notification au client")
    print("6. ❌ AUCUNE action de suivi définie")

    print("\n=== PROBLÈMES IDENTIFIÉS ===")
    print("❌ Le technician n'est pas informé du rejet")
    print("❌ Le client n'est pas au courant de l'état du survey")
    print("❌ Aucun processus de replanification")
    print("❌ Pas de tracking des actions post-rejet")

    print("\n=== WORKFLOW RECOMMANDÉ ===")
    print("1. ✅ Admin rejette le survey (ACTUEL)")
    print("2. 🔄 NOTIFICATION au technician (EMAIL/SMS)")
    print("3. 🔄 NOTIFICATION au client (EMAIL/SMS)")
    print("4. 🔄 OPTION de replanification automatique")
    print("5. 🔄 CRÉATION d'une nouvelle survey ou modification")
    print("6. 🔄 SUIVI et escalation si nécessaire")

    print("\n=== ACTIONS RECOMMANDÉES ===")
    print("📧 1. Implémenter notifications email/SMS pour:")
    print("   - Technician: 'Survey rejeté - action requise'")
    print("   - Client: 'Survey en cours de révision'")
    print("   - Admin: Rapport de suivi")

    print("\n🔄 2. Options de workflow post-rejet:")
    print("   - OPTION A: Replanifier avec le même technician")
    print("   - OPTION B: Assigner à un autre technician")
    print("   - OPTION C: Escalader vers un superviseur")
    print("   - OPTION D: Annuler la commande")

    print("\n📋 3. Interface de gestion des rejets:")
    print("   - Dashboard pour suivre les surveys rejetés")
    print("   - Actions rapides de replanification")
    print("   - Historique des rejets par technician")
    print("   - KPIs de qualité des surveys")

    print("\n🎯 4. Prochaines étapes d'implémentation:")
    print("   a) Ajouter système de notification")
    print("   b) Créer workflow de replanification")
    print("   c) Interface de gestion des rejets")
    print("   d) Métriques et rapports")


if __name__ == "__main__":
    analyze_rejection_workflow()
