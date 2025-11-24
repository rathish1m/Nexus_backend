"""
Management command to populate initial checklist data for site surveys
"""

from django.core.management.base import BaseCommand

from site_survey.models import SiteSurveyChecklist


class Command(BaseCommand):
    help = "Populate initial site survey checklist items"

    def handle(self, *args, **options):
        checklist_items = [
            {
                "category": "location",
                "question": "Is the installation location easily accessible?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "location",
                "question": "Are there any obstructions blocking the sky view?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "location",
                "question": "Describe the installation location",
                "question_type": "text",
                "is_required": False,
                "display_order": 3,
            },
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
                "category": "mounting",
                "question": "Preferred mounting type",
                "question_type": "multiple_choice",
                "choices": ["Roof Mount", "Pole Mount", "Wall Mount", "Ground Mount"],
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "mounting",
                "question": "Is the mounting surface structurally sound?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "technical",
                "question": "Distance from main electrical panel (meters)",
                "question_type": "text",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "technical",
                "question": "Is grounding available at the installation site?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "safety",
                "question": "Are there any safety concerns at the installation site?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "safety",
                "question": "Is the area free from power lines?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "environmental",
                "question": "Weather conditions during survey",
                "question_type": "multiple_choice",
                "choices": ["Clear", "Cloudy", "Rainy", "Windy", "Other"],
                "is_required": False,
                "display_order": 1,
            },
        ]

        created_count = 0
        for item_data in checklist_items:
            item, created = SiteSurveyChecklist.objects.get_or_create(
                category=item_data["category"],
                question=item_data["question"],
                defaults=item_data,
            )
            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created checklist item: {item.question}")
                )

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {created_count} checklist items")
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Total checklist items: {SiteSurveyChecklist.objects.count()}"
            )
        )
