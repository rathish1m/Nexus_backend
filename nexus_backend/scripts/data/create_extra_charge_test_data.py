#!/usr/bin/env python
import os
import sys
from pathlib import Path

import django

# Setup Django environment
sys.path.append(str(Path(__file__).resolve().parent / "nexus_backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from decimal import Decimal

from site_survey.models import ExtraCharge


def create_test_data():
    """Create test data for ExtraCharge model"""

    charges = [
        {
            "cost_type": "cable",
            "item_name": "CAT6 Ethernet Cable (50m)",
            "description": "High quality CAT6 cable for long distance connections",
            "unit_price": Decimal("45.00"),
            "brand": "Belkin",
            "model": "CAT6-50M",
            "display_order": 1,
        },
        {
            "cost_type": "mounting",
            "item_name": "Wall Mount Bracket",
            "description": "Heavy-duty wall mounting bracket for outdoor installation",
            "unit_price": Decimal("35.00"),
            "brand": "Starlink",
            "model": "WMB-001",
            "display_order": 2,
        },
        {
            "cost_type": "equipment",
            "item_name": "Power Adapter Extension",
            "description": "12V power adapter with 10m extension cable",
            "unit_price": Decimal("65.00"),
            "brand": "Generic",
            "model": "PA-EXT-10M",
            "display_order": 3,
        },
        {
            "cost_type": "safety",
            "item_name": "Lightning Protection Kit",
            "description": "Surge protector and grounding kit for lightning protection",
            "unit_price": Decimal("85.00"),
            "brand": "SurgeProtec",
            "model": "LP-KIT-01",
            "display_order": 4,
        },
        {
            "cost_type": "extender",
            "item_name": "WiFi Range Extender",
            "description": "High-power WiFi extender for large coverage areas",
            "unit_price": Decimal("120.00"),
            "brand": "Netgear",
            "model": "EX8000",
            "display_order": 5,
        },
        {
            "cost_type": "router",
            "item_name": "Mesh Router System",
            "description": "Professional mesh router system for enterprise use",
            "unit_price": Decimal("250.00"),
            "brand": "Ubiquiti",
            "model": "UDM-Pro",
            "display_order": 6,
        },
    ]

    created_count = 0
    existing_count = 0

    for charge_data in charges:
        charge, created = ExtraCharge.objects.get_or_create(
            item_name=charge_data["item_name"], defaults=charge_data
        )
        if created:
            print(f"✓ Created: {charge.item_name} - ${charge.unit_price}")
            created_count += 1
        else:
            print(f"- Already exists: {charge.item_name}")
            existing_count += 1

    print("\nSummary:")
    print(f"- Created: {created_count} items")
    print(f"- Existing: {existing_count} items")
    print(f"- Total ExtraCharge items: {ExtraCharge.objects.count()}")


if __name__ == "__main__":
    create_test_data()
