"""
Service for grouping invoice lines by order with tax calculations.

This module provides functionality to group invoice lines by their associated
orders and calculate per-order taxes and totals.
"""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Dict


def group_invoice_lines_by_order(invoice) -> Dict[str, Any]:
    """
    Group invoice lines by their associated order and calculate per-order totals.

    Args:
        invoice: Invoice instance with related invoice_lines

    Returns:
        Dictionary containing:
        - order_groups: List of dicts, each containing:
            - order: Order instance
            - order_ref: Order reference string
            - order_date: Order creation date
            - lines: List of InvoiceLine instances for this order
            - subtotal: Sum of line totals (excluding taxes)
            - excise_amount: Calculated excise tax for this order
            - vat_amount: Calculated VAT for this order
            - total_ttc: Total including all taxes (subtotal + excise + vat)
        - grouped_grand_total: Sum of all order total_ttc values

    Notes:
        - Only includes orders that have non-tax lines
        - Tax lines (kind='VAT' or kind='Excise') are excluded from grouping
        - Orders are sorted chronologically by created_at
        - Uses snapshotted tax rates from invoice.vat_rate_percent and invoice.excise_rate_percent
        - Handles lines without order association (edge case)

        Tax Calculation Logic:
        - Excise (10%): Applied ONLY to subscription plan lines (kind='plan')
        - VAT (16%): Applied to total including excise (subtotal + excise)
        - Total TTC = subtotal + excise + vat
    """
    # Get all invoice lines with their order (excluding tax lines)
    lines = invoice.lines.select_related("order").exclude(kind__in=["VAT", "Excise"])

    # Group lines by order
    order_map = defaultdict(list)
    for line in lines:
        if line.order:
            order_map[line.order.id].append(line)

    # Build order groups with calculations
    order_groups = []
    grouped_grand_total = Decimal("0.00")

    # Get tax rates from invoice (snapshotted)
    vat_rate = (
        invoice.vat_rate_percent / Decimal("100")
        if invoice.vat_rate_percent
        else Decimal("0.00")
    )
    excise_rate = (
        invoice.excise_rate_percent / Decimal("100")
        if invoice.excise_rate_percent
        else Decimal("0.00")
    )

    # Sort orders by creation date (chronological)
    orders = sorted(
        [line.order for line in lines if line.order], key=lambda o: o.created_at
    )

    # Remove duplicates while preserving order
    seen = set()
    unique_orders = []
    for order in orders:
        if order.id not in seen:
            seen.add(order.id)
            unique_orders.append(order)

    def _q(x: Decimal) -> Decimal:
        return (x or Decimal("0.00")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    for order in unique_orders:
        order_lines = order_map[order.id]

        # Calculate subtotal (sum of line totals)
        subtotal = sum((line.line_total or Decimal("0.00")) for line in order_lines)
        subtotal = _q(subtotal)

        # Calculate taxes for this order
        # IMPORTANT: Excise applies ONLY to subscription plan lines (kind='plan')
        # Step 1: Calculate excise on subscription plans only
        subscription_amount = sum(
            (line.line_total or Decimal("0.00"))
            for line in order_lines
            if (getattr(line, "kind", "") or "").lower() == "plan"
        )
        excise_amount = _q(subscription_amount * excise_rate)

        # Step 2: Calculate VAT on (subtotal + excise)
        # VAT applies to everything including excise
        base_for_vat = subtotal + excise_amount
        vat_amount = _q(base_for_vat * vat_rate)

        # Calculate total TTC (all taxes included)
        total_ttc = _q(subtotal + excise_amount + vat_amount)

        order_group = {
            "order": order,
            "order_ref": order.order_reference,
            "order_date": order.created_at,
            "lines": order_lines,
            "subtotal": subtotal,
            "excise_amount": excise_amount,
            "vat_amount": vat_amount,
            "total_ttc": total_ttc,
        }

        order_groups.append(order_group)
        grouped_grand_total += total_ttc

    return {
        "order_groups": order_groups,
        "grouped_grand_total": grouped_grand_total,
    }
