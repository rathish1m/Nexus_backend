from decimal import Decimal

from django.core.management.base import BaseCommand

from main.models import SubscriptionPlan

# Note: SubscriptionPlan pricing has been updated to use monthly_price_usd (same for all regions)
# Regional pricing is now handled by the InstallationFee model


class Command(BaseCommand):
    help = "Populate SubscriptionPlan with Starlink pricing data"

    def handle(self, *args, **options):
        self.stdout.write("Populating Starlink pricing data...")

        # === STANDARD KIT PLANS ===

        # Fixed Site with Unlimited Data
        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data",
            category_name="Standard Kit",
            plan_type="unlimited_standard",
            defaults={
                "monthly_price_usd": Decimal("120.00"),
                "category_description": "Fixed Site with Unlimited Data - Residential",
                "starlink_plan_code": "FIXED_UNLIMITED_STANDARD",
                "display_order": 1,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 40GB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("120.00"),
                "priority_data_gb": 40,
                "category_description": "Fixed Site with Unlimited Data + 40GB Priority",
                "starlink_plan_code": "FIXED_UNLIMITED_40GB_PRIORITY",
                "display_order": 2,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 1 TB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("175.00"),
                "priority_data_gb": 1000,  # 1 TB = 1000 GB
                "category_description": "Fixed Site with Unlimited Data + 1 TB Priority",
                "starlink_plan_code": "FIXED_UNLIMITED_1TB_PRIORITY",
                "display_order": 3,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 2 TB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("340.00"),
                "priority_data_gb": 2000,  # 2 TB = 2000 GB
                "additional_priority_rate": Decimal("0.33"),
                "category_description": "Fixed Site with Unlimited Data + 2 TB Priority",
                "starlink_plan_code": "FIXED_UNLIMITED_2TB_PRIORITY",
                "display_order": 4,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 6 TB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("1020.00"),
                "priority_data_gb": 6000,  # 6 TB = 6000 GB
                "additional_priority_rate": Decimal("0.33"),
                "category_description": "Fixed Site with Unlimited Data + 6 TB Priority",
                "starlink_plan_code": "FIXED_UNLIMITED_6TB_PRIORITY",
                "display_order": 5,
            },
        )

        # Portable Site with Unlimited Data
        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 50GB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("476.00"),
                "priority_data_gb": 50,
                "additional_priority_rate": Decimal("3.80"),
                "category_description": "Portable Site with Unlimited Data + 50GB Priority",
                "starlink_plan_code": "PORTABLE_UNLIMITED_50GB_PRIORITY",
                "display_order": 6,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 1 TB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("1899.00"),
                "priority_data_gb": 1000,
                "additional_priority_rate": Decimal("3.80"),
                "category_description": "Portable Site with Unlimited Data + 1 TB Priority",
                "starlink_plan_code": "PORTABLE_UNLIMITED_1TB_PRIORITY",
                "display_order": 7,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited Standard Data + 5 TB Priority Data",
            category_name="Standard Kit",
            plan_type="unlimited_with_priority",
            defaults={
                "monthly_price_usd": Decimal("9499.00"),
                "priority_data_gb": 5000,
                "additional_priority_rate": Decimal("3.80"),
                "category_description": "Portable Site with Unlimited Data + 5 TB Priority",
                "starlink_plan_code": "PORTABLE_UNLIMITED_5TB_PRIORITY",
                "display_order": 8,
            },
        )

        # Flexible Site with Limited Data
        plans_flexible = [
            ("Limited Standard Plan with 25GB", 25, Decimal("39.00")),
            ("Limited Pro Plan with 55 GB", 55, Decimal("45.00")),
            ("Limited Elite Plan with 120 GB", 120, Decimal("69.00")),
            ("Limited Advanced Plan with 320 GB", 320, Decimal("105.00")),
            ("Limited Ultra Plan with 450 GB", 450, Decimal("129.00")),
            ("Limited Mega Plan with 650 GB", 650, Decimal("185.00")),
        ]

        for i, (name, data_gb, price) in enumerate(plans_flexible, 9):
            SubscriptionPlan.objects.get_or_create(
                name=name,
                category_name="Standard Kit",
                plan_type="limited_standard",
                defaults={
                    "monthly_price_usd": price,
                    "standard_data_gb": data_gb,
                    "additional_priority_rate": Decimal("0.25"),
                    "category_description": f"Flexible Site with {data_gb}GB Limited Data",
                    "starlink_plan_code": f"FLEXIBLE_LIMITED_{data_gb}GB",
                    "display_order": i,
                },
            )

        # === MINI KIT PLANS ===

        # Fixed Site with Unlimited Data
        SubscriptionPlan.objects.get_or_create(
            name="Unlimited data - Residential Lite",
            category_name="Mini Kit",
            plan_type="unlimited_standard",
            defaults={
                "monthly_price_usd": Decimal("30.00"),
                "category_description": "Mini Kit - Fixed Site Unlimited Data Lite",
                "starlink_plan_code": "MINI_FIXED_UNLIMITED_LITE",
                "display_order": 15,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Unlimited data - Residential Pro",
            category_name="Mini Kit",
            plan_type="unlimited_standard",
            defaults={
                "monthly_price_usd": Decimal("50.00"),
                "category_description": "Mini Kit - Fixed Site Unlimited Data Pro",
                "starlink_plan_code": "MINI_FIXED_UNLIMITED_PRO",
                "display_order": 16,
            },
        )

        # Flexible Site with Limited Data (Mini)
        plans_mini_flexible = [
            ("Limited Standard Plan with 25GB", 25, Decimal("39.00")),
            ("Limited Pro Plan with 55 GB", 55, Decimal("45.00")),
            ("Limited Elite Plan with 120 GB", 120, Decimal("69.00")),
            ("Limited Advanced Plan with 320 GB", 320, Decimal("105.00")),
            ("Limited Ultra Plan with 450 GB", 450, Decimal("129.00")),
            ("Limited Mega Plan with 650 GB", 650, Decimal("185.00")),
        ]

        for i, (name, data_gb, price) in enumerate(plans_mini_flexible, 17):
            SubscriptionPlan.objects.get_or_create(
                name=name,
                category_name="Mini Kit",
                plan_type="limited_standard",
                defaults={
                    "monthly_price_usd": price,
                    "standard_data_gb": data_gb,
                    "additional_priority_rate": Decimal("0.25"),
                    "category_description": f"Mini Kit - Flexible Site with {data_gb}GB Limited Data",
                    "starlink_plan_code": f"MINI_FLEXIBLE_LIMITED_{data_gb}GB",
                    "display_order": i,
                },
            )

        # === SMART PLANS ===
        SubscriptionPlan.objects.get_or_create(
            name="Smart Education Impact Plan",
            category_name="Standard Kit",
            plan_type="smart_education",
            defaults={
                "monthly_price_usd": Decimal("123.00"),
                "priority_data_gb": 2000,
                "category_description": "Smart Education Impact - Unlimited + 2TB Priority",
                "starlink_plan_code": "SMART_EDUCATION_2TB",
                "display_order": 23,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Smart Health / Community Impact Plan",
            category_name="Standard Kit",
            plan_type="smart_health",
            defaults={
                "monthly_price_usd": Decimal("123.00"),
                "priority_data_gb": 2000,
                "category_description": "Smart Health Impact - Unlimited + 2TB Priority",
                "starlink_plan_code": "SMART_HEALTH_2TB",
                "display_order": 24,
            },
        )

        SubscriptionPlan.objects.get_or_create(
            name="Smart Health / Community Impact Plan (3TB)",
            category_name="Standard Kit",
            plan_type="smart_health",
            defaults={
                "monthly_price_usd": Decimal("191.00"),
                "priority_data_gb": 3000,
                "category_description": "Smart Health Impact - Unlimited + 3TB Priority",
                "starlink_plan_code": "SMART_HEALTH_3TB",
                "display_order": 25,
            },
        )

        # === OTHER CHARGES ===
        # Note: Extra charges are now handled by the ExtraCharge model
        # These SubscriptionPlan entries for charges have been removed

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully populated {SubscriptionPlan.objects.count()} Starlink pricing plans"
            )
        )
