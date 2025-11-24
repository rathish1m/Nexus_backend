from django.core.management.base import BaseCommand

from site_survey.models import (
    SiteSurvey,
    SiteSurveyChecklist,
    SiteSurveyPhoto,
    SiteSurveyResponse,
)


class Command(BaseCommand):
    help = "Clear all site survey data from the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force", action="store_true", help="Force deletion without confirmation"
        )
        parser.add_argument(
            "--keep-checklist",
            action="store_true",
            help="Keep checklist items, only delete surveys and responses",
        )

    def handle(self, *args, **options):
        if not options["force"]:
            confirm = input(
                "This will delete all site survey data. Are you sure? (yes/no): "
            )
            if confirm.lower() not in ["yes", "y"]:
                self.stdout.write("Operation cancelled.")
                return

        # Count existing data
        surveys_count = SiteSurvey.objects.count()
        responses_count = SiteSurveyResponse.objects.count()
        photos_count = SiteSurveyPhoto.objects.count()
        checklist_count = SiteSurveyChecklist.objects.count()

        # Delete in order (respecting foreign keys)
        SiteSurveyPhoto.objects.all().delete()
        SiteSurveyResponse.objects.all().delete()
        SiteSurvey.objects.all().delete()

        if not options["keep_checklist"]:
            SiteSurveyChecklist.objects.all().delete()

        # Report what was deleted
        self.stdout.write(self.style.SUCCESS("Deleted:"))
        self.stdout.write(f"  - {surveys_count} site surveys")
        self.stdout.write(f"  - {responses_count} survey responses")
        self.stdout.write(f"  - {photos_count} survey photos")

        if not options["keep_checklist"]:
            self.stdout.write(f"  - {checklist_count} checklist items")
        else:
            self.stdout.write(f"  - Kept {checklist_count} checklist items")

        self.stdout.write(self.style.SUCCESS("Site survey data cleared successfully"))
