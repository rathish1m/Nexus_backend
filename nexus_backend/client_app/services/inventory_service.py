from django.utils import timezone

from main.models import StarlinkKitInventory, StarlinkKitMovement

from .exceptions import OrderError


class InventoryService:
    @staticmethod
    def assign_inventory(kit):
        # Use select_for_update to lock the inventory item during selection
        # This prevents race conditions where multiple orders try to assign the same item
        inventory = (
            StarlinkKitInventory.objects.select_for_update()
            .filter(kit=kit, is_assigned=False)
            .first()
        )
        if not inventory:
            raise OrderError("No available inventory for the selected kit.")
        return inventory

    @staticmethod
    def finalize_assignment(inventory, order):
        # Check if inventory is already assigned to another order
        if inventory.assigned_to_order and inventory.assigned_to_order != order:
            raise OrderError(
                "This inventory item is already assigned to another order."
            )

        # Mark inventory as assigned
        inventory.is_assigned = True
        inventory.assigned_to_order = order
        inventory.save()

        # Assign inventory to order
        order.kit_inventory = inventory
        order.save(update_fields=["kit_inventory"])

    @staticmethod
    def log_movement(inventory, order, lat, lng, user):
        StarlinkKitMovement.objects.create(
            inventory_item=inventory,
            movement_type="assigned",
            timestamp=timezone.now(),
            location=f"{lat},{lng}",
            note="Order placed – kit reserved for 1 hour",
            order=order,
            created_by=user,
        )
