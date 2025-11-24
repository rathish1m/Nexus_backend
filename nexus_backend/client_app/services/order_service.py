from decimal import Decimal

from django.db import transaction

from client_app.serializers import serialize_order as serialize_order_payload
from client_app.services.installation_service import InstallationService
from client_app.services.utils.timezone_utils import get_expiry_time
from main.calculations import (
    determine_region_from_location,
    get_installation_fee_by_region,
)
from main.models import Order, OrderLine, StarlinkKit, Subscription, SubscriptionPlan

from .exceptions import OrderError
from .inventory_service import InventoryService


class OrderService:
    # Make OrderError available as a class attribute
    OrderError = OrderError

    @staticmethod
    def create_order(user, data):
        kit = StarlinkKit.objects.filter(id=data["kit_id"]).first()
        plan = SubscriptionPlan.objects.filter(id=data["plan_id"]).first()

        if not kit:
            raise OrderService.OrderError("Invalid kit selected.")
        if not plan:
            raise OrderService.OrderError("Invalid subscription plan.")
        if not data["lat"] or not data["lng"]:
            raise OrderService.OrderError("Installation address is required.")

        expires_at = get_expiry_time(data["lat"], data["lng"])
        install_fee = Decimal("0.00")
        if data.get("assisted"):
            region = determine_region_from_location(data["lat"], data["lng"])
            install_fee = get_installation_fee_by_region(region)

        # Determine plan price using kit_type compatibility
        try:
            kit_with_type = StarlinkKit.objects.filter(
                kit_type=plan.kit_type, is_active=True
            ).first()
            plan_price = (
                kit_with_type.base_price_usd if kit_with_type else kit.base_price_usd
            )
        except Exception:
            plan_price = Decimal("0.00")

        with transaction.atomic():
            # Assign inventory inside transaction to prevent race conditions
            assigned_inventory = InventoryService.assign_inventory(kit)

            order = Order.objects.create(
                user=user,
                plan=plan,
                kit_inventory=None,
                latitude=data["lat"],
                longitude=data["lng"],
                status="pending_payment",
                payment_status="unpaid",
                expires_at=expires_at,
                created_by=user,
            )

            # Create line items instead of storing per-order price fields
            OrderLine.objects.create(
                order=order,
                kind=OrderLine.Kind.KIT,
                description=kit.name,
                quantity=1,
                unit_price=kit.base_price_usd,
                kit_inventory=assigned_inventory,
            )
            OrderLine.objects.create(
                order=order,
                kind=OrderLine.Kind.PLAN,
                description=plan.name,
                quantity=1,
                unit_price=plan_price,
                plan=plan,
            )
            if install_fee and install_fee > 0:
                OrderLine.objects.create(
                    order=order,
                    kind=OrderLine.Kind.INSTALL,
                    description="Installation fee",
                    quantity=1,
                    unit_price=install_fee,
                )

            InventoryService.finalize_assignment(assigned_inventory, order)
            Subscription.objects.create(
                user=user, plan=plan, order=order, status="pending"
            )
            InventoryService.log_movement(
                assigned_inventory, order, data["lat"], data["lng"], user
            )

            if data.get("assisted"):
                InstallationService.schedule_installation(order)

        return order

    @staticmethod
    def serialize_order(order):
        return serialize_order_payload(order)
