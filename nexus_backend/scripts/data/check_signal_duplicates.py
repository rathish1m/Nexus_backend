from site_survey.models import SiteSurveyChecklist

# Vérifier les questions dans la catégorie signal
print("Questions Signal Quality existantes:")
signal_items = SiteSurveyChecklist.objects.filter(category="signal").order_by(
    "display_order"
)

for item in signal_items:
    print(f"ID: {item.id}")
    print(f"Question: {item.question}")
    print(f"Type: {item.question_type}")
    print(f"Required: {item.is_required}")
    print(f"Display Order: {item.display_order}")
    print("---")

print(f"Total: {signal_items.count()} questions")

# Rechercher des questions similaires (potentiels doublons)
import difflib

signal_questions = list(signal_items.values_list("question", flat=True))
duplicates = []

for i, q1 in enumerate(signal_questions):
    for j, q2 in enumerate(signal_questions[i + 1 :], i + 1):
        similarity = difflib.SequenceMatcher(None, q1.lower(), q2.lower()).ratio()
        if similarity > 0.8:  # 80% de similarité
            duplicates.append((q1, q2, similarity))

if duplicates:
    print("\nDoublons potentiels détectés:")
    for q1, q2, sim in duplicates:
        print(f"Similarité {sim:.2%}: '{q1}' vs '{q2}'")
else:
    print("\nAucun doublon détecté.")
