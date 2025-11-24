from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import StarlinkKitInventory, StarlinkKitMovement


class Command(BaseCommand):
    help = "Clear all Starlink inventory items and their associated movements"

    def add_arguments(self, parser):
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Confirm the deletion of all inventory data",
        )

    def handle(self, *args, **options):
        if not options["confirm"]:
            self.stdout.write(
                self.style.WARNING(
                    "This command will DELETE ALL Starlink inventory items and movements.\n"
                    "Use --confirm to proceed with the deletion."
                )
            )
            return

        self.stdout.write("Clearing Starlink inventory data...")

        # Get counts before deletion
        inventory_count = StarlinkKitInventory.objects.count()
        movement_count = StarlinkKitMovement.objects.count()

        self.stdout.write(
            f"Found {inventory_count} inventory items and {movement_count} movements"
        )

        # Use transaction to ensure data integrity
        with transaction.atomic():
            # Delete movements first (due to foreign key constraints)
            movements_deleted = StarlinkKitMovement.objects.all().delete()
            self.stdout.write(f"Deleted {movements_deleted[0]} movement records")

            # Then delete inventory items
            inventory_deleted = StarlinkKitInventory.objects.all().delete()
            self.stdout.write(f"Deleted {inventory_deleted[0]} inventory items")

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully cleared all Starlink inventory data: "
                f"{inventory_count} items and {movement_count} movements removed"
            )
        )
