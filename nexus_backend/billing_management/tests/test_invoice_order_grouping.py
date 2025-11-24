"""
TDD tests for invoice order grouping functionality.
Tests that invoice lines are grouped by order with per-order tax calculations.
"""

from datetime import timedelta
from decimal import Decimal

import pytest

from django.utils import timezone

from billing_management.services.invoice_grouping import group_invoice_lines_by_order
from main.models import Invoice, InvoiceLine, InvoiceOrder


@pytest.mark.django_db
@pytest.mark.unit
class TestInvoiceOrderGrouping:
    """Test grouping invoice lines by order with tax calculations."""

    def test_single_order_invoice_shows_order_reference(
        self, user_factory, order_factory
    ):
        """Une facture avec 1 commande affiche le numéro de commande."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-ABC123")
        invoice = Invoice.objects.create(
            user=user,
            number="INV/2025/001",
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )
        InvoiceOrder.objects.create(
            invoice=invoice, order=order, amount_excl_tax=Decimal("100.00")
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Test Item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        assert len(result["order_groups"]) == 1
        assert result["order_groups"][0]["order_ref"] == "ORD-ABC123"
        assert result["order_groups"][0]["order"] == order

    def test_multi_order_invoice_groups_lines_correctly(
        self, user_factory, order_factory
    ):
        """Une facture consolidée groupe les lignes par commande."""
        # Arrange
        user = user_factory()
        order1 = order_factory(user=user, order_reference="ORD-001")
        order2 = order_factory(user=user, order_reference="ORD-002")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        # Order 1 has 2 lines
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order1,
            description="Kit",
            quantity=Decimal("1.00"),
            unit_price=Decimal("599.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order1,
            description="Installation",
            quantity=Decimal("1.00"),
            unit_price=Decimal("120.00"),
        )

        # Order 2 has 1 line
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order2,
            description="Monthly Plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        assert len(result["order_groups"]) == 2
        assert len(result["order_groups"][0]["lines"]) == 2  # Order 1 has 2 lines
        assert len(result["order_groups"][1]["lines"]) == 1  # Order 2 has 1 line

    def test_order_group_calculates_subtotal_correctly(
        self, user_factory, order_factory
    ):
        """Le sous-total par commande est la somme des line_total."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-123")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("0.00"),
        )

        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Item 1",
            quantity=Decimal("2.00"),
            unit_price=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Item 2",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        # 2*100 + 1*50 = 250.00
        assert result["order_groups"][0]["subtotal"] == Decimal("250.00")

    def test_order_group_calculates_vat_per_order(self, user_factory, order_factory):
        """La VAT est calculée par commande sur (subtotal + excise)."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-VAT")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        # Subscription plan: excise applies
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Subscription Plan",
            kind="plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        group = result["order_groups"][0]
        # Subtotal: 100.00
        # Excise (10% on plan): 10.00
        # Taxable after excise: 110.00
        # VAT (16% on 110.00): 17.60
        assert group["subtotal"] == Decimal("100.00")
        assert group["excise_amount"] == Decimal("10.00")
        assert group["vat_amount"] == Decimal("17.60")

    def test_order_group_calculates_excise_per_order(self, user_factory, order_factory):
        """L'Excise est calculée SEULEMENT sur les lignes de type 'plan'."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-EXC")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("0.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        # Subscription plan: $1000 (excise applies)
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Premium Plan",
            kind="plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("1000.00"),
            line_total=Decimal("1000.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        group = result["order_groups"][0]
        # Excise: 1000.00 * 10% = 100.00
        assert group["excise_amount"] == Decimal("100.00")

    def test_excise_only_on_subscription_plans(self, user_factory, order_factory):
        """L'Excise s'applique SEULEMENT sur kind='plan', pas sur les autres items."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-MIXED")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        # Kit: $55 (NO excise)
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Mini Kit",
            kind="item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("55.00"),
            line_total=Decimal("55.00"),
        )

        # Plan: $85 (YES excise)
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Limited Fast",
            kind="plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("85.00"),
            line_total=Decimal("85.00"),
        )

        # Installation: $120 (NO excise)
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Installation fee",
            kind="item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("120.00"),
            line_total=Decimal("120.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        group = result["order_groups"][0]
        # Subtotal: 55 + 85 + 120 = 260.00
        # Excise: 10% of plan only ($85) = 8.50
        # VAT base: 260 + 8.50 = 268.50
        # VAT: 16% of 268.50 = 42.96
        # Total TTC: 260 + 8.50 + 42.96 = 311.46
        assert group["subtotal"] == Decimal("260.00")
        assert group["excise_amount"] == Decimal("8.50")
        assert group["vat_amount"] == Decimal("42.96")
        assert group["total_ttc"] == Decimal("311.46")

    def test_order_group_total_ttc_includes_all_taxes(
        self, user_factory, order_factory
    ):
        """Le total TTC inclut subtotal + excise + VAT."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-TTC")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Monthly Plan",
            kind="plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        group = result["order_groups"][0]
        # Subtotal: 100.00
        # Excise (10% on plan): 10.00
        # VAT (16% on 110.00): 17.60
        # Total TTC: 100.00 + 10.00 + 17.60 = 127.60
        assert group["total_ttc"] == Decimal("127.60")

    def test_grand_total_sums_all_order_ttc(self, user_factory, order_factory):
        """Le grand total est la somme des totaux TTC de toutes les commandes."""
        # Arrange
        user = user_factory()
        order1 = order_factory(user=user, order_reference="ORD-001")
        order2 = order_factory(user=user, order_reference="ORD-002")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        # Order 1: plan = 100.00
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order1,
            description="Basic Plan",
            kind="plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            line_total=Decimal("100.00"),
        )

        # Order 2: plan = 200.00
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order2,
            description="Premium Plan",
            kind="plan",
            quantity=Decimal("1.00"),
            unit_price=Decimal("200.00"),
            line_total=Decimal("200.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        # Order 1 TTC: 100 + 10 (excise) + 17.60 (VAT) = 127.60
        # Order 2 TTC: 200 + 20 (excise) + 35.20 (VAT) = 255.20
        # Grand Total: 127.60 + 255.20 = 382.80
        assert result["grouped_grand_total"] == Decimal("382.80")

    def test_order_groups_sorted_by_creation_date(self, user_factory, order_factory):
        """Les commandes sont triées par created_at (chronologique)."""
        # Arrange
        user = user_factory()
        now = timezone.now()

        # Create orders with different creation times
        order1 = order_factory(user=user, order_reference="ORD-LATE")
        order1.created_at = now + timedelta(hours=2)
        order1.save()

        order2 = order_factory(user=user, order_reference="ORD-EARLY")
        order2.created_at = now
        order2.save()

        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("0.00"),
        )

        # Add lines in reverse order
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order1,
            description="Late order",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order2,
            description="Early order",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert - should be sorted by created_at
        assert result["order_groups"][0]["order_ref"] == "ORD-EARLY"
        assert result["order_groups"][1]["order_ref"] == "ORD-LATE"

    def test_order_with_no_excise_rate(self, user_factory, order_factory):
        """Une commande sans excise (None) doit avoir excise_amount = 0."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-NO-EXC")
        invoice = Invoice.objects.create(
            user=user, vat_rate_percent=Decimal("16.00"), excise_rate_percent=None
        )

        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Service",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        group = result["order_groups"][0]
        assert group["excise_amount"] == Decimal("0.00")
        # VAT calculated on subtotal only (no excise)
        assert group["vat_amount"] == Decimal("16.00")  # 16% of 100

    def test_empty_invoice_returns_empty_groups(self, user_factory):
        """Une facture sans lignes retourne des groupes vides."""
        # Arrange
        user = user_factory()
        invoice = Invoice.objects.create(user=user)

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        assert result["order_groups"] == []
        assert result["grouped_grand_total"] == Decimal("0.00")

    def test_lines_without_order_are_skipped(self, user_factory):
        """Les lignes sans Order (taxes, ajustements) sont ignorées."""
        # Arrange
        user = user_factory()
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("0.00"),
        )

        # Line without order (e.g., tax adjustment)
        InvoiceLine.objects.create(
            invoice=invoice,
            order=None,
            description="Tax adjustment",
            quantity=Decimal("1.00"),
            unit_price=Decimal("10.00"),
            kind="tax",
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        assert result["order_groups"] == []
        assert result["grouped_grand_total"] == Decimal("0.00")

    def test_multiple_lines_same_order_grouped_together(
        self, user_factory, order_factory
    ):
        """Plusieurs lignes de la même commande sont groupées ensemble."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-MULTI")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("0.00"),
        )

        # Create 3 lines for same order
        for i in range(3):
            InvoiceLine.objects.create(
                invoice=invoice,
                order=order,
                description=f"Item {i+1}",
                quantity=Decimal("1.00"),
                unit_price=Decimal("10.00"),
            )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        assert len(result["order_groups"]) == 1
        assert len(result["order_groups"][0]["lines"]) == 3
        assert result["order_groups"][0]["subtotal"] == Decimal("30.00")

    def test_order_date_is_included_in_group(self, user_factory, order_factory):
        """La date de création de la commande est incluse dans le groupe."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-DATE")
        invoice = Invoice.objects.create(user=user)

        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        assert result["order_groups"][0]["order_date"] == order.created_at

    def test_decimal_precision_in_tax_calculations(self, user_factory, order_factory):
        """Les calculs de taxes respectent la précision décimale (2 chiffres)."""
        # Arrange
        user = user_factory()
        order = order_factory(user=user, order_reference="ORD-PRECISION")
        invoice = Invoice.objects.create(
            user=user,
            vat_rate_percent=Decimal("16.00"),
            excise_rate_percent=Decimal("10.00"),
        )

        # Amount that creates rounding scenarios
        InvoiceLine.objects.create(
            invoice=invoice,
            order=order,
            description="Item",
            quantity=Decimal("1.00"),
            unit_price=Decimal("33.33"),
            kind="plan",
        )

        # Act
        result = group_invoice_lines_by_order(invoice)

        # Assert
        group = result["order_groups"][0]
        # Subtotal: 33.33
        # Excise (10%): 3.33
        # Taxable: 36.66
        # VAT (16%): 5.87 (rounded from 5.8656)
        # Total: 42.53
        assert group["subtotal"] == Decimal("33.33")
        assert group["excise_amount"] == Decimal("3.33")
        assert group["vat_amount"] == Decimal("5.87")
        assert group["total_ttc"] == Decimal("42.53")
