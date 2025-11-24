"""
Management command to load sample SiteSurveyChecklist data
"""

from django.core.management.base import BaseCommand

from site_survey.models import SiteSurveyChecklist


class Command(BaseCommand):
    help = "Load sample SiteSurveyChecklist data for testing"

    def handle(self, *args, **options):
        self.stdout.write("Loading SiteSurveyChecklist sample data...")

        # Clear existing data
        SiteSurveyChecklist.objects.all().delete()

        # Sample checklist items
        checklist_items = [
            {
                "category": "location",
                "question": "Is the installation site easily accessible?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "location",
                "question": "Are there any access restrictions (gates, security, etc.)?",
                "question_type": "text",
                "is_required": False,
                "display_order": 2,
            },
            {
                "category": "technical",
                "question": "Is power available within 100ft of dish location?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "technical",
                "question": "What is the distance to nearest power source?",
                "question_type": "text",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "signal",
                "question": "Is there clear line of sight to the sky?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 1,
            },
            {
                "category": "signal",
                "question": "Are there any potential obstructions?",
                "question_type": "text",
                "is_required": False,
                "display_order": 2,
            },
            {
                "category": "mounting",
                "question": "What is the best mounting location?",
                "question_type": "multiple_choice",
                "choices": ["Roof", "Ground", "Wall", "Pole", "Other"],
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
                "question": "What is the best cable routing path?",
                "question_type": "text",
                "is_required": True,
                "display_order": 3,
            },
            {
                "category": "technical",
                "question": "Will cable routing require drilling or trenching?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 4,
            },
            {
                "category": "environmental",
                "question": "Are there any environmental concerns?",
                "question_type": "text",
                "is_required": False,
                "display_order": 1,
            },
            {
                "category": "safety",
                "question": "Are there any safety hazards at the site?",
                "question_type": "text",
                "is_required": False,
                "display_order": 1,
            },
            {
                "category": "safety",
                "question": "Will specialized safety equipment be required?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 2,
            },
            {
                "category": "technical",
                "question": "Rate the overall installation difficulty (1=Easy, 5=Very Difficult)",
                "question_type": "rating",
                "is_required": True,
                "display_order": 5,
            },
            {
                "category": "location",
                "question": "Customer specific installation preferences",
                "question_type": "text",
                "is_required": False,
                "display_order": 3,
            },
        ]

        # Create SiteSurveyChecklist objects
        for data in checklist_items:
            checklist_item = SiteSurveyChecklist.objects.create(**data)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created: {checklist_item.get_category_display()} - {checklist_item.question[:50]}..."
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully loaded {len(checklist_items)} SiteSurveyChecklist items!"
            )
        )
