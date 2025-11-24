"""
Management command to load sample ExtraCharge data
"""

from django.core.management.base import BaseCommand

from site_survey.models import ExtraCharge


class Command(BaseCommand):
    help = "Load sample ExtraCharge data for testing"

    def add_arguments(self, parser):
        parser.add_argument(
            "--purge",
            action="store_true",
            help="Delete all existing ExtraCharge records before loading sample data",
        )

    def handle(self, *args, **options):
        self.stdout.write("Loading ExtraCharge sample data...")

        if options.get("purge"):
            # Clear existing data
            ExtraCharge.objects.all().delete()
            self.stdout.write(
                self.style.WARNING("All existing ExtraCharge records deleted.")
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    "Skipping deletion of existing ExtraCharge records. Use --purge to delete all before loading."
                )
            )

        # Sample data organized by cost_type
        extra_charges_data = [
            # Additional Equipment
            {
                "cost_type": "equipment",
                "item_name": "Starlink Ethernet Adapter",
                "description": "Official Starlink Ethernet adapter for wired connections",
                "unit_price": 25.00,
                "brand": "Starlink",
                "model": "ETH-ADT-GEN2",
                "specifications": {
                    "ports": 1,
                    "type": "Gigabit Ethernet",
                    "compatibility": "Gen 2 Starlink dishes",
                },
                "display_order": 1,
            },
            {
                "cost_type": "equipment",
                "item_name": "Starlink Pipe Adapter",
                "description": "Adapter for mounting Starlink dish on pipes",
                "unit_price": 35.00,
                "brand": "Starlink",
                "model": "PIPE-ADT",
                "specifications": {
                    "pipe_diameter": "1.5-3 inches",
                    "material": "Steel",
                    "weather_rating": "IP67",
                },
                "display_order": 2,
            },
            # Extra Cables
            {
                "cost_type": "cable",
                "item_name": "Starlink Cable Extension 75ft",
                "description": "Extension cable for Starlink dish connection",
                "unit_price": 75.00,
                "brand": "Starlink",
                "model": "CBL-EXT-75",
                "specifications": {
                    "length": "75 feet",
                    "type": "Proprietary Starlink cable",
                    "weather_rating": "Outdoor rated",
                },
                "display_order": 1,
            },
            {
                "cost_type": "cable",
                "item_name": "Ethernet Cable Cat6 - 100ft",
                "description": "Outdoor rated Cat6 ethernet cable",
                "unit_price": 45.00,
                "brand": "Generic",
                "model": "CAT6-OUT-100",
                "specifications": {
                    "length": "100 feet",
                    "type": "Cat6 UTP",
                    "rating": "Outdoor/Direct Burial",
                },
                "display_order": 2,
            },
            # Signal Extenders
            {
                "cost_type": "extender",
                "item_name": "WiFi Mesh Point",
                "description": "Mesh access point to extend WiFi coverage",
                "unit_price": 120.00,
                "brand": "Ubiquiti",
                "model": "U6-Lite",
                "specifications": {
                    "standards": "WiFi 6 (802.11ax)",
                    "coverage": "Up to 1500 sq ft",
                    "power": "PoE",
                },
                "display_order": 1,
            },
            # Router/Gateway
            {
                "cost_type": "router",
                "item_name": "Enterprise WiFi Router",
                "description": "High-performance router for large installations",
                "unit_price": 300.00,
                "brand": "Ubiquiti",
                "model": "Dream Machine",
                "specifications": {
                    "throughput": "3.5 Gbps",
                    "ports": "8x Gigabit",
                    "wifi": "WiFi 6",
                },
                "display_order": 1,
            },
            # Specialized Mounting
            {
                "cost_type": "mounting",
                "item_name": "Roof Penetration Mount",
                "description": "Professional roof mount with weatherproofing",
                "unit_price": 150.00,
                "brand": "Rohn",
                "model": "RM-ROOF-PRO",
                "specifications": {
                    "material": "Galvanized steel",
                    "mast_size": "1.25-2 inch",
                    "weatherproofing": "Included",
                },
                "display_order": 1,
            },
            {
                "cost_type": "mounting",
                "item_name": "Wall Mount Bracket",
                "description": "Heavy-duty wall mount for difficult installations",
                "unit_price": 85.00,
                "brand": "Generic",
                "model": "WM-HEAVY",
                "specifications": {
                    "load_capacity": "50 lbs",
                    "material": "Stainless steel",
                    "extension": "18 inches",
                },
                "display_order": 2,
            },
            # Additional Labor
            {
                "cost_type": "labor",
                "item_name": "Trenching Service (per foot)",
                "description": "Professional cable trenching service",
                "unit_price": 3.50,
                "brand": "",
                "model": "",
                "specifications": {
                    "depth": "18-24 inches",
                    "width": "4 inches",
                    "includes": "Backfill and restoration",
                },
                "display_order": 1,
            },
            {
                "cost_type": "labor",
                "item_name": "Attic/Crawlspace Run",
                "description": "Cable run through difficult access areas",
                "unit_price": 125.00,
                "brand": "",
                "model": "",
                "specifications": {
                    "includes": "Up to 100ft cable run",
                    "areas": "Attic, crawlspace, basement",
                    "difficulty": "Standard access",
                },
                "display_order": 2,
            },
            # Power Infrastructure
            {
                "cost_type": "power",
                "item_name": "Outdoor GFCI Outlet",
                "description": "Weather-resistant power outlet installation",
                "unit_price": 180.00,
                "brand": "Leviton",
                "model": "GFNT2-W",
                "specifications": {
                    "amperage": "20A",
                    "voltage": "120V",
                    "rating": "NEMA 4X",
                },
                "display_order": 1,
            },
            # Access Infrastructure
            {
                "cost_type": "access",
                "item_name": "Conduit Installation (per foot)",
                "description": "PVC conduit for cable protection",
                "unit_price": 2.25,
                "brand": "Schedule 40",
                "model": "PVC-1.25",
                "specifications": {
                    "diameter": "1.25 inches",
                    "material": "PVC Schedule 40",
                    "includes": "Fittings and cement",
                },
                "display_order": 1,
            },
            # Safety Equipment
            {
                "cost_type": "safety",
                "item_name": "Grounding Kit",
                "description": "Professional grounding system installation",
                "unit_price": 95.00,
                "brand": "Polyphaser",
                "model": "GRD-KIT-PRO",
                "specifications": {
                    "includes": "Ground rod, clamps, wire",
                    "compliance": "NEC Article 810",
                    "rod_length": "8 feet",
                },
                "display_order": 1,
            },
        ]

        # Create ExtraCharge objects
        for data in extra_charges_data:
            extra_charge = ExtraCharge.objects.create(**data)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Created: {extra_charge.get_cost_type_display()} - {extra_charge.item_name} (${extra_charge.unit_price})"
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully loaded {len(extra_charges_data)} ExtraCharge items!"
            )
        )
