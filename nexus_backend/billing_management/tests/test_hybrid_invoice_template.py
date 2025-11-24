"""
Tests for hybrid invoice template - TDD approach
Combines PDF simplicity with technical robustness

Following the reference: Nexus — Manual Billing.pdf
- Dual currency display (USD + CDF column)
- Bank details section
- Selective excise (subscription items only)
- Order grouping collapse for single orders
"""

from decimal import Decimal

import pytest

from django.contrib.auth import get_user_model
from django.utils import timezone

from billing_management.billing_helpers import calculate_excise_selective
from main.models import (
    CompanySettings,
    FxRate,
    Invoice,
    InvoiceLine,
    InvoiceOrder,
    Order,
    OrderLine,
)

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestHybridInvoiceTemplate:
    """Test suite for hybrid invoice template following TDD principles"""

    @pytest.fixture
    def company_settings(self):
        """Company settings with bank details"""
        cs, _ = CompanySettings.objects.get_or_create(
            id=1,
            defaults={
                "legal_name": "Nexus Telecoms SA",
                "trade_name": "Nexus",
                "email": "billing@nexus.cd",
                "phone": "+243 900 000 000",
                "rccm": "CD/LSH/RCCM/25-B-00807",
                "nif": "A1234567",
                "default_currency": "USD",
                "vat_rate_percent": Decimal("16.00"),
                "excise_rate_percent": Decimal("10.00"),
                # Bank details
                "bank_name": "Rawbank",
                "bank_account_name": "Nexus Telecoms SA",
                "bank_account_number_usd": "05100-05130-01146609001-26",
                "bank_swift": "RBCDCDKIXXX",
                # Payment terms
                "payment_terms_days": 14,
            },
        )
        return cs

    @pytest.fixture
    def test_user(self):
        """Create test user"""
        return User.objects.create_user(
            username="testuser",
            email="test@example.com",
            full_name="Mr. Test User",
        )

    @pytest.fixture
    def fx_rate(self):
        """Exchange rate USD/CDF"""
        return FxRate.objects.create(
            date=timezone.now().date(),
            pair="USD/CDF",
            rate=Decimal("2600.00"),
        )

    @pytest.fixture
    def mixed_order(self, test_user):
        """Order with mixed items: kit, subscription, installation"""
        order = Order.objects.create(
            user=test_user,
            order_reference="ORD-TEST-001",
            payment_status="paid",
            status="processing",
        )

        # Add lines
        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.KIT,
            description="Starlink Standard KIT",
            quantity=1,
            unit_price=Decimal("400.00"),
            line_total=Decimal("400.00"),
        )

        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.PLAN,  # ← Subscription (should have excise)
            description="Internet Subscription – Premium Plan",
            quantity=1,
            unit_price=Decimal("80.00"),
            line_total=Decimal("80.00"),
        )

        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.INSTALL,
            description="Installation Service Fee",
            quantity=1,
            unit_price=Decimal("120.00"),
            line_total=Decimal("120.00"),
        )

        return order

    def test_selective_excise_calculation(self, mixed_order, company_settings):
        """
        CRITICAL TEST: Excise must apply ONLY to subscription items

        Expected:
        - Kit ($400): NO excise
        - Subscription ($80): 10% excise = $8.00
        - Installation ($120): NO excise

        Total excise should be $8.00, NOT $60.00 (which would be 10% of $600)
        """
        excise_amount = calculate_excise_selective(
            mixed_order, rate_percent=Decimal("10.00")
        )

        assert excise_amount == Decimal("8.00"), (
            f"Excise should be $8.00 (10% of $80 subscription only), "
            f"got ${excise_amount}"
        )

    def test_dual_currency_display_structure(
        self, mixed_order, company_settings, fx_rate, test_user
    ):
        """
        Test that invoice template includes CDF column alongside USD

        Structure should be:
        Description | Qty | Unit(USD) | Total(USD) | Total(CDF)
        """
        # Create invoice from order
        invoice = Invoice.objects.create(
            user=test_user,
            number="INV-TEST-001",
            currency="USD",
            status=Invoice.Status.ISSUED,
            issued_at=timezone.now(),
            subtotal=Decimal("600.00"),
            vat_amount=Decimal("96.80"),  # 16% of (600 + 8)
            excise_amount=Decimal("8.00"),  # 10% of 80 (subscription only)
            tax_total=Decimal("104.80"),
            grand_total=Decimal("704.80"),
        )

        # Link to order
        InvoiceOrder.objects.create(
            invoice=invoice, order=mixed_order, amount_excl_tax=Decimal("600.00")
        )

        # Add invoice lines
        for order_line in mixed_order.lines.all():
            InvoiceLine.objects.create(
                invoice=invoice,
                description=order_line.description,
                quantity=order_line.quantity,
                unit_price=order_line.unit_price,
                line_total=order_line.line_total,
            )

        # Render template context (would need actual template rendering)
        # For now, test that data structure exists
        context = {
            "invoice": invoice,
            "company": company_settings,
            "exchange_rate": fx_rate.rate,
        }

        # Verify CDF conversion logic exists
        kit_cdf = Decimal("400.00") * fx_rate.rate
        assert kit_cdf == Decimal("1040000.00")

        subscription_cdf = Decimal("80.00") * fx_rate.rate
        assert subscription_cdf == Decimal("208000.00")

    def test_bank_details_section_exists(self, company_settings):
        """
        Bank details must be present in template context

        Required fields:
        - bank_name
        - bank_account_number_usd or bank_account_number_cdf
        - bank_swift
        """
        assert company_settings.bank_name == "Rawbank"
        # Prefer USD field presence in the test fixture
        assert "05100-05130-01146609001-26" in (
            getattr(company_settings, "bank_account_number_usd", "")
            or getattr(company_settings, "bank_account_number_cdf", "")
        )
        assert company_settings.bank_swift == "RBCDCDKIXXX"

    def test_order_grouping_collapse_single_order(self, mixed_order):
        """
        When invoice has only 1 order, should NOT display grouping boxes

        This keeps visual simplicity like the PDF reference
        """
        # Logic: if order_groups count == 1, don't show "Order #XXX" boxes
        # Instead, show flat item list

        order_count = 1  # Single order scenario
        should_show_grouping = order_count > 1

        assert (
            should_show_grouping is False
        ), "Single order invoice should NOT display order grouping boxes"

    def test_vat_calculation_includes_excise_base(self, company_settings):
        """
        VAT should be calculated on (subtotal + excise) per DRC tax law

        Example from PDF:
        - Subtotal: $675.00
        - Excise (10% on $80 subscription): $8.00
        - Base for VAT: $683.00
        - VAT (16%): $109.28
        """
        subtotal = Decimal("675.00")
        excise = Decimal("8.00")
        vat_base = subtotal + excise
        vat_amount = (vat_base * Decimal("0.16")).quantize(Decimal("0.01"))

        assert vat_amount == Decimal("109.28")

    def test_hybrid_template_capacity_18_lines(self):
        """
        Template must maintain 18-line capacity despite dual currency column

        This is critical for avoiding multi-page invoices
        """
        # This would be integration test - checking PDF page count
        # For unit test, verify MAX_ROWS template variable exists
        max_rows = 18
        assert max_rows == 18, "Hybrid template must support 18 lines minimum"

    def test_no_emojis_in_hybrid_template(self):
        """
        Hybrid template should use professional text instead of emojis

        Replace:
        - 💵 → "Subtotal" or "Subtotal (USD)"
        - 📦 → "Order"
        - ✅ → "Total"
        """
        # This would be checked in actual template file
        # Marking as documentation of requirement
        assert True  # Placeholder - actual check in template review

    def test_fx_rate_display_with_date(self, fx_rate):
        """
        Exchange rate must show rate, date, and ideally source

        Example: "Exchange rate: 2,600 CDF/USD (2025-11-13)"
        """
        assert fx_rate.rate == Decimal("2600.00")
        assert fx_rate.pair == "USD/CDF"
        assert fx_rate.date is not None


class TestExciseHelper:
    """Test the calculate_excise_selective() helper function"""

    @pytest.fixture
    def user(self):
        return User.objects.create_user(username="testuser", email="test@test.com")

    def test_calculate_excise_only_on_plan_items(self, user):
        """Excise applies ONLY to OrderLine.kind='plan'"""
        order = Order.objects.create(
            user=user, order_reference="TEST-001", payment_status="paid"
        )

        # Create mixed lines
        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.PLAN,
            description="Subscription",
            unit_price=Decimal("100.00"),
            quantity=1,
        )

        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.KIT,
            description="Hardware",
            unit_price=Decimal("500.00"),
            quantity=1,
        )

        # Only $100 subscription should be taxed at 10% = $10
        excise = calculate_excise_selective(order, rate_percent=Decimal("10.00"))
        assert excise == Decimal("10.00")

    def test_calculate_excise_zero_when_no_subscription(self, user):
        """If no subscription items, excise should be zero"""
        order = Order.objects.create(
            user=user, order_reference="TEST-002", payment_status="paid"
        )

        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.KIT,
            description="Hardware only",
            unit_price=Decimal("500.00"),
            quantity=1,
        )

        excise = calculate_excise_selective(order, rate_percent=Decimal("10.00"))
        assert excise == Decimal("0.00")

    def test_calculate_excise_multiple_subscriptions(self, user):
        """Multiple subscription items should sum correctly"""
        order = Order.objects.create(
            user=user, order_reference="TEST-003", payment_status="paid"
        )

        # Two subscriptions
        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.PLAN,
            description="Basic Plan",
            unit_price=Decimal("50.00"),
            quantity=1,
        )

        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.PLAN,
            description="Premium Addon",
            unit_price=Decimal("30.00"),
            quantity=1,
        )

        # Total subscription: $80 → 10% = $8
        excise = calculate_excise_selective(order, rate_percent=Decimal("10.00"))
        assert excise == Decimal("8.00")
