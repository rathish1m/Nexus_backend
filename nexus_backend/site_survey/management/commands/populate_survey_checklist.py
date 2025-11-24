from django.core.management.base import BaseCommand

from site_survey.models import SiteSurveyChecklist


class Command(BaseCommand):
    help = "Populate predefined site survey checklist items"

    def handle(self, *args, **options):
        checklist_items = [
            # Location & Access
            {
                "category": "location",
                "question": "Is the site easily accessible by vehicle?",
                "question_type": "yes_no",
                "display_order": 1,
            },
            {
                "category": "location",
                "question": "Are there any access restrictions (gates, security, permits required)?",
                "question_type": "text",
                "display_order": 2,
            },
            {
                "category": "location",
                "question": "Is there adequate space for equipment and personnel?",
                "question_type": "yes_no",
                "display_order": 3,
            },
            # Signal Quality
            {
                "category": "signal",
                "question": "Rate the line of sight to the sky (1-5, where 5 is excellent)",
                "question_type": "rating",
                "display_order": 1,
            },
            {
                "category": "signal",
                "question": "Are there any major obstructions (tall trees, buildings, power lines)?",
                "question_type": "text",
                "display_order": 2,
            },
            {
                "category": "signal",
                "question": "Is the location free from significant signal interference sources?",
                "question_type": "yes_no",
                "display_order": 3,
            },
            # Mounting Options
            {
                "category": "mounting",
                "question": "What is the preferred mounting location?",
                "question_type": "multiple_choice",
                "choices": ["Roof", "Wall", "Pole", "Ground", "Chimney", "Other"],
                "display_order": 1,
            },
            {
                "category": "mounting",
                "question": "Is the proposed mounting surface structurally sound?",
                "question_type": "yes_no",
                "display_order": 2,
            },
            {
                "category": "mounting",
                "question": "Is there clear access to the mounting location?",
                "question_type": "yes_no",
                "display_order": 3,
            },
            # Safety Considerations
            {
                "category": "safety",
                "question": "Are there any electrical hazards in the vicinity?",
                "question_type": "text",
                "display_order": 1,
            },
            {
                "category": "safety",
                "question": "Is the work area free from fall hazards?",
                "question_type": "yes_no",
                "display_order": 2,
            },
            {
                "category": "safety",
                "question": "Are there adequate safety measures available (ladders, harnesses, etc.)?",
                "question_type": "text",
                "display_order": 3,
            },
            # Technical Requirements
            {
                "category": "technical",
                "question": "Is there a power source available within 30 meters?",
                "question_type": "yes_no",
                "display_order": 1,
            },
            {
                "category": "technical",
                "question": "Is there adequate cable routing from mounting location to power/equipment area?",
                "question_type": "text",
                "display_order": 2,
            },
            {
                "category": "technical",
                "question": "Are there any equipment placement restrictions?",
                "question_type": "text",
                "display_order": 3,
            },
            # Environmental Factors
            {
                "category": "environmental",
                "question": "Rate the weather exposure at the proposed location (1-5, where 5 is very exposed)",
                "question_type": "rating",
                "display_order": 1,
            },
            {
                "category": "environmental",
                "question": "Are there any environmental concerns (wildlife, vegetation, water sources)?",
                "question_type": "text",
                "display_order": 2,
            },
            {
                "category": "environmental",
                "question": "Is the location prone to extreme weather conditions?",
                "question_type": "text",
                "display_order": 3,
            },
        ]

        for item_data in checklist_items:
            SiteSurveyChecklist.objects.get_or_create(
                question=item_data["question"], defaults=item_data
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {len(checklist_items)} checklist items"
            )
        )
