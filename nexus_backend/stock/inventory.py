import logging
from decimal import ROUND_HALF_UP, Decimal

from django.db import connections, transaction
from django.db.models import Count
from django.utils import timezone

from main.models import (
    Order,
    StarlinkKitInventory,
    StarlinkKitMovement,
    StockLocation,
    User,
)

# If these helpers live elsewhere, keep the imports and remove the stubs.
# from .pricing import price_order_from_lines
# from .geo import compute_local_expiry_from_coords, installation_fee_for_coords

logger = logging.getLogger(__name__)

# -------------------------------------------------------------------
# Tiny money helper (quantize like your model-side _qmoney)
# -------------------------------------------------------------------
ZERO = Decimal("0.00")


def _qmoney(x) -> Decimal:
    x = Decimal(str(x or "0"))
    return x.quantize(ZERO, rounding=ROUND_HALF_UP)


# -------------------------------------------------------------------
# DB feature helper: supports select_for_update(skip_locked=True)?
# -------------------------------------------------------------------
def db_supports_skip_locked(using: str = "default") -> bool:
    try:
        return bool(
            getattr(
                connections[using].features, "has_select_for_update_skip_locked", False
            )
        )
    except Exception:
        return False


# -------------------------------------------------------------------
# Canonical "available inventory" queryset (NO SIDE EFFECTS)
#   - has a current_location
#   - not scrapped
#   - not assigned
# -------------------------------------------------------------------
def available_inventory_qs(using: str = "default"):
    return (
        StarlinkKitInventory.objects.using(using)
        .filter(current_location__isnull=False)
        .exclude(status__iexact="scrapped")
        .filter(is_assigned=False)
    )


# -------------------------------------------------------------------
# Inventory service helpers (no location flip on reservation)
# -------------------------------------------------------------------
def reserve_inventory_for_order(
    *,
    inv: StarlinkKitInventory,
    order: Order,
    planned_lat: float | None,
    planned_lng: float | None,
    hold_hours: int,
    by: User | None,
    using: str = "default",
) -> None:
    """
    Logically reserve a kit for an order (no physical move).
    - Flip flags on inventory
    - Keep current_location as-is (warehouse/van)
    - Write one StarlinkKitMovement row for the reservation
    """
    inv.is_assigned = True
    inv.assigned_to_order = order
    inv.status = "assigned"
    inv.save(update_fields=["is_assigned", "assigned_to_order", "status"], using=using)

    StarlinkKitMovement.objects.using(using).create(
        inventory_item=inv,
        movement_type="assigned",
        order=order,
        location=(inv.current_location.code if inv.current_location else ""),
        note=(
            f"Reserved for order {order.order_reference or order.pk}; "
            f"planned install at {planned_lat},{planned_lng}; "
            f"hold {hold_hours}h"
        ),
        created_by=by if getattr(by, "pk", None) else None,
    )


def count_left_global(**filters):
    """
    Total available across everything. Optional filters:
    - kit_id, kit_type, region_id, location_id
    """
    qs = (
        StarlinkKitInventory.objects.available()
        .for_kit(filters.get("kit_id"))
        .for_kit_type(filters.get("kit_type"))
        .in_region(filters.get("region_id"))
        .at_location(filters.get("location_id"))
    )
    return qs.count()


def count_left_by_region(**filters):
    """
    Returns list of {region_id, region, quantity}
    """
    qs = (
        StarlinkKitInventory.objects.available()
        .for_kit(filters.get("kit_id"))
        .for_kit_type(filters.get("kit_type"))
    )
    if filters.get("location_id"):
        qs = qs.at_location(filters["location_id"])

    rows = (
        qs.values("current_location__region_id", "current_location__region__name")
        .annotate(quantity=Count("id"))
        .order_by("current_location__region__name")
    )
    return [
        {
            "region_id": r["current_location__region_id"],
            "region": r["current_location__region__name"],
            "quantity": int(r["quantity"] or 0),
        }
        for r in rows
    ]


def count_left_by_location(**filters):
    """
    Returns list of {location_id, location, region_id, region, quantity}
    """
    qs = (
        StarlinkKitInventory.objects.available()
        .for_kit(filters.get("kit_id"))
        .for_kit_type(filters.get("kit_type"))
        .in_region(filters.get("region_id"))
    )

    rows = (
        qs.values(
            "current_location_id",
            "current_location__name",
            "current_location__region_id",
            "current_location__region__name",
        )
        .annotate(quantity=Count("id"))
        .order_by("current_location__name")
    )
    return [
        {
            "location_id": r["current_location_id"],
            "location": r["current_location__name"],
            "region_id": r["current_location__region_id"],
            "region": r["current_location__region__name"],
            "quantity": int(r["quantity"] or 0),
        }
        for r in rows
    ]


def count_left_by_kit_and_region(**filters):
    """
    Returns list of {kit_id, kit, kit_type, region_id, region, quantity}
    """
    qs = (
        StarlinkKitInventory.objects.available()
        .for_kit_type(filters.get("kit_type"))
        .in_region(filters.get("region_id"))
        .at_location(filters.get("location_id"))
    )

    rows = (
        qs.values(
            "kit_id",
            "kit__name",
            "kit__kit_type",
            "current_location__region_id",
            "current_location__region__name",
        )
        .annotate(quantity=Count("id"))
        .order_by("kit__name", "current_location__region__name")
    )
    return [
        {
            "kit_id": r["kit_id"],
            "kit": r["kit__name"] or "—",
            "kit_type": r["kit__kit_type"] or "",
            "region_id": r["current_location__region_id"],
            "region": r["current_location__region__name"],
            "quantity": int(r["quantity"] or 0),
        }
        for r in rows
    ]


def release_expired_reservations(now=None):
    now = now or timezone.now()
    stale = Order.objects.select_related("kit_inventory").filter(
        status="pending_payment", expires_at__lt=now, kit_inventory__isnull=False
    )

    released = 0
    for order in stale:
        with transaction.atomic():
            inv = StarlinkKitInventory.objects.select_for_update().get(
                pk=order.kit_inventory_id
            )
            inv.is_assigned = False
            inv.assigned_to_order = None
            inv.status = "available"
            inv.save(update_fields=["is_assigned", "assigned_to_order", "status"])

            StarlinkKitMovement.objects.create(
                inventory_item=inv,
                movement_type="adjusted",
                note=f"Auto-release reservation for expired order {order.order_reference}",
                order=order,
            )

            order.kit_inventory = None
            order.status = "failed"  # or keep pending; your choice
            order.save(update_fields=["kit_inventory", "status"])
            released += 1
    return released


def transfer_inventory(
    *,
    inv: StarlinkKitInventory,
    to_location: StockLocation | None,
    reason: str = "",
    order: Order | None = None,
    by: User | None = None,
    using: str = "default",
) -> None:
    """Physical/logistical move (warehouse → van, etc.)"""
    inv.current_location = to_location
    inv.save(update_fields=["current_location"], using=using)

    StarlinkKitMovement.objects.using(using).create(
        inventory_item=inv,
        movement_type="transferred",
        order=order,
        location=(to_location.code if to_location else ""),
        note=reason or f"Moved to {to_location}",
        created_by=by if getattr(by, "pk", None) else None,
    )


def release_reservation(
    *,
    inv: StarlinkKitInventory,
    order: Order,
    reason: str = "",
    by: User | None = None,
    using: str = "default",
) -> None:
    """
    Release a reserved kit back to available stock (before install).
    """
    inv.is_assigned = False
    inv.assigned_to_order = None
    inv.status = "available"
    inv.save(update_fields=["is_assigned", "assigned_to_order", "status"], using=using)

    StarlinkKitMovement.objects.using(using).create(
        inventory_item=inv,
        movement_type="adjusted",
        order=order,
        location=(inv.current_location.code if inv.current_location else ""),
        note=reason
        or f"Reservation released for order {order.order_reference or order.pk}",
        created_by=by if getattr(by, "pk", None) else None,
    )
