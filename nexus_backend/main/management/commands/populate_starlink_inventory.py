from django.core.management.base import BaseCommand
from django.utils import timezone

from main.models import StarlinkKit, StarlinkKitInventory, StarlinkKitMovement


class Command(BaseCommand):
    help = "Populate StarlinkKitInventory with sample data"

    def handle(self, *args, **options):
        self.stdout.write("Populating Starlink inventory data...")

        # Get all StarlinkKits and ensure they have correct kit_types
        kits_to_populate = [
            ("Kit Standard", "standard", 99),
            ("Kit Mini", "mini", 50),
        ]

        total_inventory_created = 0

        for kit_name, correct_kit_type, quantity in kits_to_populate:
            try:
                kit = StarlinkKit.objects.get(name=kit_name)

                # Fix kit_type if incorrect
                if kit.kit_type != correct_kit_type:
                    kit.kit_type = correct_kit_type
                    kit.save()
                    self.stdout.write(
                        f"Fixed kit_type for {kit_name} to '{correct_kit_type}'"
                    )

                # Create inventory items
                inventory_count = 0
                prefix = "STD" if correct_kit_type == "standard" else "MINI"
                new_inventory_items = []
                updated_inventory_items = []

                for i in range(1, quantity + 1):
                    kit_number = f"{prefix}-{i:04d}"
                    serial_number = f"SN-{prefix}-{i:06d}"

                    # Check if inventory item already exists
                    existing = StarlinkKitInventory.objects.filter(
                        kit_number=kit_number
                    ).first()
                    if existing:
                        # Ensure it's not assigned and linked to correct kit
                        if existing.is_assigned or existing.kit != kit:
                            existing.is_assigned = False
                            existing.kit = kit
                            existing.serial_number = serial_number
                            existing.model = correct_kit_type.capitalize()
                            existing.firmware_version = "1.0.0"
                            existing.save()
                            updated_inventory_items.append(existing)
                        inventory_count += 1
                    else:
                        # Create new inventory item
                        new_item = StarlinkKitInventory.objects.create(
                            kit_number=kit_number,
                            serial_number=serial_number,
                            model=correct_kit_type.capitalize(),
                            firmware_version="1.0.0",
                            kit=kit,
                            is_assigned=False,
                        )
                        new_inventory_items.append(new_item)
                        inventory_count += 1

                # Create "received" movements for new and updated inventory items
                items_needing_movements = new_inventory_items + updated_inventory_items
                if items_needing_movements:
                    movement_records = []
                    for item in items_needing_movements:
                        # Check if a "received" movement already exists for this item
                        existing_movement = StarlinkKitMovement.objects.filter(
                            inventory_item=item, movement_type="received"
                        ).first()

                        if not existing_movement:
                            movement = StarlinkKitMovement(
                                inventory_item=item,
                                movement_type="received",
                                timestamp=timezone.now(),
                                location="Warehouse - Populated via management command",
                                note=f"Initial stock population for {kit_name}",
                            )
                            movement_records.append(movement)

                    # Bulk create movements
                    if movement_records:
                        StarlinkKitMovement.objects.bulk_create(movement_records)
                        self.stdout.write(
                            f"Created {len(movement_records)} 'received' movements for {kit_name}"
                        )

                self.stdout.write(
                    f"Created/updated {inventory_count} inventory items for {kit_name}"
                )

                # Verify the count
                actual_count = StarlinkKitInventory.objects.filter(
                    kit=kit, is_assigned=False
                ).count()
                self.stdout.write(
                    f"Verified {actual_count} available inventory items for {kit_name}"
                )

                total_inventory_created += inventory_count

            except StarlinkKit.DoesNotExist:
                self.stdout.write(
                    self.style.WARNING(f"Kit '{kit_name}' not found. Skipping.")
                )

        # Count total movements created
        total_movements_created = StarlinkKitMovement.objects.filter(
            movement_type="received", note__icontains="Initial stock population"
        ).count()

        self.stdout.write(
            self.style.SUCCESS(
                f"Successfully created {total_inventory_created} total Starlink inventory items "
                f"and {total_movements_created} corresponding 'received' movements"
            )
        )
