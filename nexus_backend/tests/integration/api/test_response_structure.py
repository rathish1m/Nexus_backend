#!/usr/bin/env python3
"""
Script de test pour vérifier la structure des modèles SiteSurveyResponse
"""

import pytest

from site_survey.models import SiteSurveyChecklist, SiteSurveyResponse


@pytest.mark.django_db
def test_response_fields():
    print("🔍 Vérification de la structure du modèle SiteSurveyResponse...")

    # Obtenir tous les champs du modèle
    fields = SiteSurveyResponse._meta.fields
    field_names = [field.name for field in fields]

    print("📊 Champs disponibles dans SiteSurveyResponse:")
    for field in fields:
        print(f"  - {field.name}: {field.__class__.__name__}")

    # Vérifier les champs requis
    required_fields = [
        "survey",
        "checklist_item",
        "response_text",
        "response_rating",
        "response_choice",
        "additional_notes",
    ]
    print("\n✅ Vérification des champs requis:")

    for field_name in required_fields:
        if field_name in field_names:
            print(f"  ✅ {field_name} - Présent")
        else:
            print(f"  ❌ {field_name} - Manquant")

    # Tester avec une question de checklist existante
    print("\n🧪 Test de création d'une réponse...")

    checklist_items = SiteSurveyChecklist.objects.all()[:3]
    if checklist_items:
        print("📋 Questions de test disponibles:")
        for item in checklist_items:
            print(
                f"  - ID: {item.id} | Type: {item.question_type} | Question: '{item.question}'"
            )
    else:
        print(
            "⚠️  Aucune question de checklist trouvée. Exécutez d'abord populate_checklist."
        )


if __name__ == "__main__":
    test_response_fields()
