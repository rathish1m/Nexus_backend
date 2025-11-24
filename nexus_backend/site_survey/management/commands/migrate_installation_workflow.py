"""
Management command to migrate existing InstallationActivity records to the new workflow
where installations are only created after survey approval.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import InstallationActivity
from site_survey.models import SiteSurvey


class Command(BaseCommand):
    help = "Migrate existing InstallationActivity records to align with new survey-first workflow"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be done without making changes",
        )
        parser.add_argument(
            "--auto-approve",
            action="store_true",
            help="Auto-approve surveys for existing installation activities",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        auto_approve = options["auto_approve"]

        self.stdout.write(
            self.style.SUCCESS("🔍 Analyzing existing InstallationActivity records...")
        )

        # Find InstallationActivity records without corresponding approved SiteSurvey
        installation_activities = (
            InstallationActivity.objects.select_related("order")
            .prefetch_related("order__site_survey")
            .all()
        )

        problematic_installations = []
        valid_installations = []

        for installation in installation_activities:
            order = installation.order

            # Check if there's a site survey for this order
            try:
                site_survey = order.site_survey
                if site_survey.status == "approved":
                    valid_installations.append((installation, site_survey))
                else:
                    problematic_installations.append((installation, site_survey))
            except SiteSurvey.DoesNotExist:
                # No site survey exists - this shouldn't happen with new workflow
                problematic_installations.append((installation, None))

        self.stdout.write("📊 Analysis results:")
        self.stdout.write(
            f"  ✅ Valid installations (with approved survey): {len(valid_installations)}"
        )
        self.stdout.write(
            f"  ⚠️  Problematic installations: {len(problematic_installations)}"
        )

        if not problematic_installations:
            self.stdout.write(
                self.style.SUCCESS(
                    "🎉 All installations are properly linked to approved surveys!"
                )
            )
            return

        self.stdout.write("\n📋 Problematic installations breakdown:")
        no_survey_count = 0
        unapproved_survey_count = 0

        for installation, survey in problematic_installations:
            if survey is None:
                no_survey_count += 1
            else:
                unapproved_survey_count += 1

        self.stdout.write(f"  🚫 No survey: {no_survey_count}")
        self.stdout.write(f"  ⏳ Unapproved survey: {unapproved_survey_count}")

        if dry_run:
            self.stdout.write(
                self.style.WARNING("\n🔍 DRY RUN MODE - No changes will be made")
            )
            self._show_detailed_analysis(problematic_installations)
            return

        # Process problematic installations
        self.stdout.write("\n🔧 Processing problematic installations...")

        with transaction.atomic():
            processed_count = 0

            for installation, survey in problematic_installations:
                order = installation.order

                if survey is None:
                    # Create a site survey for this order
                    survey = SiteSurvey.objects.create(
                        order=order,
                        survey_latitude=order.latitude,
                        survey_longitude=order.longitude,
                        survey_address=getattr(order, "address", ""),
                        status="scheduled",
                        overall_assessment="Migrated from existing installation - requires review",
                        installation_feasible=True,  # Assume true since installation was created
                    )
                    self.stdout.write(
                        f"  ✅ Created survey for order {order.order_reference}"
                    )

                if auto_approve and survey.status != "approved":
                    # Auto-approve the survey to match the existing installation
                    survey.status = "approved"
                    survey.approved_at = (
                        installation.order.created_at
                    )  # Use order creation time
                    survey.approval_notes = (
                        "Auto-approved during migration to new workflow"
                    )
                    survey.save()
                    self.stdout.write(
                        f"  ✅ Auto-approved survey for order {order.order_reference}"
                    )

                processed_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f"\n🎉 Successfully processed {processed_count} installations"
                )
            )

            if not auto_approve and unapproved_survey_count > 0:
                self.stdout.write(
                    self.style.WARNING(
                        f"\n⚠️  Note: {unapproved_survey_count} surveys still need manual approval. "
                        f"Use --auto-approve flag to automatically approve them."
                    )
                )

    def _show_detailed_analysis(self, problematic_installations):
        self.stdout.write("\n📋 Detailed analysis of problematic installations:")

        for installation, survey in problematic_installations[:10]:  # Show first 10
            order = installation.order
            status_desc = (
                "No survey" if survey is None else f"Survey status: {survey.status}"
            )
            self.stdout.write(
                f"  - Order: {order.order_reference} | Installation ID: {installation.id} | {status_desc}"
            )

        if len(problematic_installations) > 10:
            self.stdout.write(f"  ... and {len(problematic_installations) - 10} more")

        self.stdout.write("\n💡 Recommendations:")
        self.stdout.write(
            "  1. Run with --auto-approve to automatically approve surveys"
        )
        self.stdout.write(
            "  2. Or manually review and approve surveys in the admin interface"
        )
        self.stdout.write("  3. Remove --dry-run to apply changes")
