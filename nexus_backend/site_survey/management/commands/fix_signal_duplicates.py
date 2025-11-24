"""
Script pour nettoyer et corriger les questions de checklist duplicées
"""

from django.core.management.base import BaseCommand

from site_survey.models import SiteSurveyChecklist


class Command(BaseCommand):
    help = "Clean and fix duplicate survey checklist questions"

    def handle(self, *args, **options):
        # 1. Supprimer tous les éléments de la catégorie signal pour éviter les doublons
        signal_items = SiteSurveyChecklist.objects.filter(category="signal")
        deleted_count = signal_items.count()
        signal_items.delete()

        self.stdout.write(
            self.style.WARNING(f"Deleted {deleted_count} existing signal questions")
        )

        # 2. Recréer les questions signal correctes
        correct_signal_questions = [
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
            {
                "category": "signal",
                "question": "Weather conditions affecting signal",
                "question_type": "multiple_choice",
                "choices": ["Clear", "Cloudy", "Rain", "Snow", "Heavy winds"],
                "is_required": False,
                "display_order": 4,
            },
        ]

        created_count = 0
        for item_data in correct_signal_questions:
            item = SiteSurveyChecklist.objects.create(**item_data)
            created_count += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created: {item.question} (Type: {item.question_type})"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {created_count} clean signal questions"
            )
        )

        # 3. Afficher toutes les questions signal pour vérification
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("Current Signal Quality questions:"))

        signal_items = SiteSurveyChecklist.objects.filter(category="signal").order_by(
            "display_order"
        )
        for item in signal_items:
            self.stdout.write(
                f"  {item.display_order}. {item.question} ({item.question_type})"
            )

        self.stdout.write("=" * 50)
