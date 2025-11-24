from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Optional, Tuple

from django.db import transaction

from main.models import AccountEntry, RegionSalesDefault
from main.services.region_resolver import resolve_region_from_coords

if TYPE_CHECKING:  # pragma: no cover
    from geo_regions.models import Region


RegionResult = Tuple[Optional["Region"], str]


def _resolve_region_for_order(order) -> RegionResult:
    if order is None:
        return None, "manual"

    # Use order coordinates if available
    region, tag = resolve_region_from_coords(order.latitude, order.longitude)
    if region:
        return region, tag

    last_tag = tag

    # Fallback to installation activity coordinates
    installation = getattr(order, "installation_activity", None)
    if installation:
        region, tag = resolve_region_from_coords(
            installation.site_latitude, installation.site_longitude
        )
        if region:
            return region, tag
        if tag not in {"no_coords"}:
            last_tag = tag

    # Fallback to stock location region
    inventory = getattr(order, "kit_inventory", None)
    if inventory and getattr(inventory, "current_location", None):
        location_region = getattr(inventory.current_location, "region", None)
        if location_region:
            return location_region, "from_stock_location"

    # Manual override on the order itself
    if order.region_id:
        return order.region, "manual"

    return None, last_tag


def resolve_region_from_context(order=None, subscription=None) -> RegionResult:
    order_candidates = []
    if order is not None:
        order_candidates.append(order)
    if (
        subscription is not None
        and getattr(subscription, "order", None) is not None
        and subscription.order not in order_candidates
    ):
        order_candidates.append(subscription.order)

    last_tag = "manual"
    for candidate in order_candidates:
        region, tag = _resolve_region_for_order(candidate)
        if region:
            return region, tag
        last_tag = tag

    if subscription and subscription.region_id:
        return subscription.region, "manual"

    return None, last_tag


def resolve_sales_agent(order=None, subscription=None, region=None):
    if order and order.sales_agent_id:
        return order.sales_agent, "order"
    if subscription and subscription.sales_agent_id:
        return subscription.sales_agent, "subscription"
    if region:
        default = (
            RegionSalesDefault.objects.filter(region=region, is_primary=True)
            .select_related("agent")
            .first()
        )
        if default and default.agent:
            return default.agent, "region_default"
    return None, "manual"


@transaction.atomic
def create_entry(
    *,
    account,
    entry_type: str,
    amount_usd: Decimal,
    description: str = "",
    order=None,
    subscription=None,
    payment=None,
    period_start=None,
    period_end=None,
    external_ref: str = "",
    region_override=None,
    sales_agent_override=None,
    snapshot_source: Optional[str] = None,
    **extra,
):
    region = region_override
    source = snapshot_source

    if region is None:
        region, auto_source = resolve_region_from_context(
            order=order, subscription=subscription
        )
        source = source or auto_source

    if region_override is not None and snapshot_source is None:
        source = source or "manual_override"

    sales_agent = sales_agent_override
    if sales_agent is None:
        sales_agent, agent_source = resolve_sales_agent(order, subscription, region)
        if sales_agent and source is None:
            source = agent_source

    if source is None:
        source = "manual" if region is None else "auto"

    entry = AccountEntry.objects.create(
        account=account,
        entry_type=entry_type,
        amount_usd=amount_usd,
        description=description,
        order=order,
        subscription=subscription,
        payment=payment,
        period_start=period_start,
        period_end=period_end,
        external_ref=external_ref,
        region_snapshot=region,
        sales_agent_snapshot=sales_agent,
        snapshot_source=source,
        **extra,
    )
    return entry


__all__ = ["create_entry", "resolve_region_from_context", "resolve_sales_agent"]
