#!/usr/bin/env python3

"""
Script pour nettoyer les questions de survey duplicées
Exécuter avec: python clean_duplicates.py
"""

import os

import django

# Configuration Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from site_survey.models import SiteSurveyChecklist


def clean_signal_duplicates():
    print("🔍 Vérification des questions Signal Quality...")

    # Rechercher toutes les questions signal
    signal_items = SiteSurveyChecklist.objects.filter(category="signal").order_by(
        "display_order"
    )

    print(f"📊 Trouvé {signal_items.count()} questions dans la catégorie 'signal':")
    for item in signal_items:
        print(
            f"  - ID: {item.id} | Question: '{item.question}' | Type: {item.question_type}"
        )

    # Rechercher des doublons potentiels
    questions = [item.question for item in signal_items]
    duplicates = []

    for i, q1 in enumerate(questions):
        for j, q2 in enumerate(questions[i + 1 :], i + 1):
            if "signal strength" in q1.lower() and "signal strength" in q2.lower():
                duplicates.append((signal_items[i], signal_items[j]))

    if duplicates:
        print("\n⚠️  Doublons détectés:")
        for item1, item2 in duplicates:
            print(f"  🔸 '{item1.question}' (ID: {item1.id})")
            print(f"  🔸 '{item2.question}' (ID: {item2.id})")

        print("\n🧹 Nettoyage des doublons...")

        # Supprimer toutes les questions signal
        deleted_count = signal_items.count()
        signal_items.delete()
        print(f"  ✅ Supprimé {deleted_count} questions signal existantes")

        # Recréer les questions correctes
        correct_questions = [
            {
                "category": "signal",
                "question": "Signal strength at the location",
                "question_type": "rating",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "signal",
                "question": "Are there any potential interference sources nearby?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "signal",
                "question": "Line of sight to satellites clear?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 3,
            },
        ]

        created_count = 0
        for question_data in correct_questions:
            item = SiteSurveyChecklist.objects.create(**question_data)
            created_count += 1
            print(f"  ✅ Créé: '{item.question}' (Type: {item.question_type})")

        print(
            f"\n🎉 Nettoyage terminé! {created_count} questions signal propres créées."
        )
    else:
        print("\n✅ Aucun doublon détecté.")

    # Afficher le résultat final
    print("\n📋 Questions Signal Quality finales:")
    final_signal_items = SiteSurveyChecklist.objects.filter(category="signal").order_by(
        "display_order"
    )
    for item in final_signal_items:
        print(f"  {item.display_order}. {item.question} ({item.question_type})")


if __name__ == "__main__":
    clean_signal_duplicates()
