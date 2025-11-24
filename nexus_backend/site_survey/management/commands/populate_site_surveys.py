import os
import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import Order, SubscriptionPlan
from site_survey.models import SiteSurvey, SiteSurveyChecklist, SiteSurveyResponse

User = get_user_model()


class Command(BaseCommand):
    help = "Populate the database with sample site surveys for testing CRUD operations"

    def add_arguments(self, parser):
        parser.add_argument(
            "--surveys",
            type=int,
            default=10,
            help="Number of site surveys to create (default: 10)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Clear existing site surveys before creating new ones",
        )

    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write("Clearing existing site surveys...")
            SiteSurvey.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Cleared existing site surveys"))

        num_surveys = options["surveys"]

        # First, ensure we have some checklist items
        self.create_checklist_items()

        # Then create sample orders if needed
        self.create_sample_orders()

        # Finally create site surveys
        self.create_site_surveys(num_surveys)

        self.stdout.write(
            self.style.SUCCESS(f"Successfully created {num_surveys} site surveys")
        )

    def create_checklist_items(self):
        """Create sample checklist items if they don't exist"""
        checklist_data = [
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
                "category": "signal",
                "question": "Rate the expected signal quality (1-5)",
                "question_type": "rating",
                "is_required": True,
                "display_order": 3,
            },
            {
                "category": "mounting",
                "question": "What is the recommended mounting option?",
                "question_type": "multiple_choice",
                "choices": ["Roof Mount", "Ground Mount", "Pole Mount", "Wall Mount"],
                "is_required": True,
                "display_order": 4,
            },
            {
                "category": "safety",
                "question": "Are there any safety concerns at the site?",
                "question_type": "text",
                "is_required": False,
                "display_order": 5,
            },
            {
                "category": "technical",
                "question": "Is power available within 30m of the proposed location?",
                "question_type": "yes_no",
                "is_required": True,
                "display_order": 6,
            },
            {
                "category": "environmental",
                "question": "Rate the weather protection level (1-5)",
                "question_type": "rating",
                "is_required": True,
                "display_order": 7,
            },
            {
                "category": "technical",
                "question": "Additional technical observations",
                "question_type": "text",
                "is_required": False,
                "display_order": 8,
            },
        ]

        created_count = 0
        for item_data in checklist_data:
            checklist_item, created = SiteSurveyChecklist.objects.get_or_create(
                category=item_data["category"],
                question=item_data["question"],
                defaults=item_data,
            )
            if created:
                created_count += 1

        if created_count > 0:
            self.stdout.write(f"Created {created_count} checklist items")

    def create_sample_orders(self):
        """Create sample orders if we don't have enough"""
        existing_orders = Order.objects.count()
        if existing_orders < 20:
            # Get or create a sample user
            admin_user, created = User.objects.get_or_create(
                username="site_survey_admin",
                defaults={
                    "email": "admin@nexus.com",
                    "first_name": "Site Survey",
                    "last_name": "Admin",
                    "is_staff": True,
                    "is_superuser": True,
                },
            )
            if created:
                admin_password = os.getenv("TEST_ADMIN_PASSWORD", "admin123_dev_only")
                admin_user.set_password(admin_password)
                admin_user.save()
                self.stdout.write(
                    "Created admin user for site surveys with password from env"
                )

            # Get or create subscription plans
            plan, created = SubscriptionPlan.objects.get_or_create(
                name="Standard Plan",
                defaults={
                    "standard_data_gb": 250,
                    "monthly_price_usd": Decimal("99.99"),
                    "is_active": True,
                    "plan_type": "limited_standard",
                    "category_name": "Standard Category",
                },
            )

            # Create sample orders
            orders_to_create = 20 - existing_orders
            for i in range(orders_to_create):
                order = Order.objects.create(
                    user=admin_user,
                    plan=plan,
                    latitude=-4.3000 + random.uniform(-0.5, 0.5),
                    longitude=15.3000 + random.uniform(-0.5, 0.5),
                    total_price=Decimal("1500.00"),
                    payment_method="mobile",
                    payment_status="paid",
                    status="fulfilled",
                    order_reference=f"ORD-{timezone.now().year}-{1000 + i}",
                )

            self.stdout.write(f"Created {orders_to_create} sample orders")

    def create_site_surveys(self, num_surveys):
        """Create sample site surveys"""
        # Get available orders without site surveys
        orders_without_surveys = Order.objects.filter(site_survey__isnull=True)[
            :num_surveys
        ]

        if len(orders_without_surveys) < num_surveys:
            self.stdout.write(
                self.style.WARNING(
                    f"Only {len(orders_without_surveys)} orders available without site surveys"
                )
            )

        # Get technicians (staff users)
        technicians = list(User.objects.filter(is_staff=True))
        if not technicians:
            # Create a sample technician
            technician = User.objects.create_user(
                username="technician1",
                email="tech1@nexus.com",
                first_name="John",
                last_name="Technician",
                is_staff=True,
            )
            tech_password = os.getenv("TEST_TECH_PASSWORD", "tech123_dev_only")
            technician.set_password(tech_password)
            technician.save()
            technicians = [technician]
            self.stdout.write("Created sample technician with password from env")

        # Get checklist items
        checklist_items = list(SiteSurveyChecklist.objects.all())

        statuses = [
            "scheduled",
            "in_progress",
            "completed",
            "requires_approval",
            "approved",
        ]
        mounting_options = ["Roof Mount", "Ground Mount", "Pole Mount", "Wall Mount"]

        # Sample addresses in Kinshasa area
        sample_addresses = [
            "Commune de Gombe, Avenue de la Paix, Kinshasa",
            "Bandalungwa, Rue Kasa-Vubu, Kinshasa",
            "Kalamu, Boulevard du 30 Juin, Kinshasa",
            "Ngaliema, Avenue des Cliniques, Kinshasa",
            "Kintambo, Rue Colonel Lukusa, Kinshasa",
            "Limete, Avenue de la Liberation, Kinshasa",
            "Matete, Rue de la Victoire, Kinshasa",
            "Lingwala, Avenue Tombalbaye, Kinshasa",
        ]

        for i, order in enumerate(orders_without_surveys):
            # Random survey data
            status = random.choice(statuses)
            technician = random.choice(technicians)

            # Create base survey data
            survey_data = {
                "order": order,
                "technician": technician,
                "assigned_by": technician,  # For simplicity, technician assigns themselves
                "assigned_at": timezone.now() - timedelta(days=random.randint(1, 30)),
                "scheduled_date": timezone.now().date()
                + timedelta(days=random.randint(-10, 10)),
                "status": status,
                "survey_latitude": (
                    order.latitude + random.uniform(-0.01, 0.01)
                    if order.latitude
                    else None
                ),
                "survey_longitude": (
                    order.longitude + random.uniform(-0.01, 0.01)
                    if order.longitude
                    else None
                ),
                "survey_address": random.choice(sample_addresses),
                "location_notes": f"Survey location notes for order {order.order_reference}",
                "installation_feasible": random.choice([True, False, None]),
                "recommended_mounting": random.choice(mounting_options),
            }

            # Add status-specific fields
            if status in ["in_progress", "completed", "requires_approval", "approved"]:
                survey_data["started_at"] = survey_data["assigned_at"] + timedelta(
                    hours=random.randint(1, 48)
                )

            if status in ["completed", "requires_approval", "approved"]:
                survey_data["completed_at"] = survey_data["started_at"] + timedelta(
                    hours=random.randint(1, 8)
                )
                survey_data["submitted_for_approval_at"] = survey_data["completed_at"]
                survey_data["overall_assessment"] = (
                    f"Detailed assessment for {order.order_reference}. "
                    + random.choice(
                        [
                            "Site is excellent for Starlink installation.",
                            "Site has minor obstacles but installation is feasible.",
                            "Site requires additional mounting equipment.",
                            "Perfect line of sight to southern sky.",
                        ]
                    )
                )

            if status == "approved":
                survey_data["approved_by"] = technician
                survey_data["approved_at"] = survey_data[
                    "submitted_for_approval_at"
                ] + timedelta(hours=random.randint(1, 24))
                survey_data["approval_notes"] = (
                    "Survey approved. Proceed with installation."
                )

            # Create the survey
            survey = SiteSurvey.objects.create(**survey_data)

            # Create responses for completed surveys
            if (
                status in ["completed", "requires_approval", "approved"]
                and checklist_items
            ):
                for checklist_item in checklist_items:
                    response_data = {"survey": survey, "checklist_item": checklist_item}

                    if checklist_item.question_type == "yes_no":
                        response_data["response_text"] = random.choice(["Yes", "No"])
                    elif checklist_item.question_type == "rating":
                        response_data["response_rating"] = random.randint(1, 5)
                    elif checklist_item.question_type == "multiple_choice":
                        if checklist_item.choices:
                            response_data["response_choice"] = random.choice(
                                checklist_item.choices
                            )
                    elif checklist_item.question_type == "text":
                        if random.choice([True, False]):  # 50% chance of text response
                            response_data["response_text"] = (
                                f"Sample response for {checklist_item.question}"
                            )

                    if random.choice([True, False]):  # 50% chance of additional notes
                        response_data["additional_notes"] = (
                            "Additional technician notes"
                        )

                    SiteSurveyResponse.objects.create(**response_data)

            self.stdout.write(
                f"Created site survey {i+1}/{len(orders_without_surveys)} - Status: {status}"
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {len(orders_without_surveys)} site surveys"
            )
        )
