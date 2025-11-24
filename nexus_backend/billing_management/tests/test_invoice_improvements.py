"""
TDD Tests for Invoice Template Improvements

Test-Driven Development approach to ensure:
1. NIF is displayed in invoice header
2. Tax percentages are shown (e.g., "Excise(10%)", "VAT(16%)")
3. Currency is displayed in "Total Due", "Unit Price", and "Line Total"

Following RED-GREEN-REFACTOR methodology:
- RED: Write tests that fail (feature not implemented yet)
- GREEN: Implement minimal code to pass tests
- REFACTOR: Improve code while keeping tests passing
"""

import os

from django.conf import settings
from django.test import SimpleTestCase


class InvoiceTemplateImprovementsTests(SimpleTestCase):
    """
    Test suite for invoice template improvements.

    Uses SimpleTestCase to avoid database dependencies - we're only
    checking template content for required elements.
    """

    def setUp(self):
        """Setup template path for tests."""
        self.template_path = os.path.join(
            settings.BASE_DIR,
            "billing_management",
            "templates",
            "invoices",
            "inv_templates.html",
        )
        self.consolidated_template_path = os.path.join(
            settings.BASE_DIR,
            "billing_management",
            "templates",
            "invoices",
            "consolidated_inv_templates.html",
        )

    def test_template_file_exists(self):
        """Test that the invoice template file exists."""
        self.assertTrue(
            os.path.exists(self.template_path),
            f"Invoice template should exist at {self.template_path}",
        )

    def test_consolidated_template_file_exists(self):
        """Test that the consolidated invoice template file exists."""
        self.assertTrue(
            os.path.exists(self.consolidated_template_path),
            f"Consolidated invoice template should exist at {self.consolidated_template_path}",
        )

    def test_nif_is_displayed_in_company_info(self):
        """
        Test that NIF (Tax Identification Number) is displayed in company info section.

        The NIF should be shown on a separate line from RCCM and Id.Nat in the company header.
        Format expected: "{% if company.nif %}NIF: {{ company.nif }}{% endif %}"
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for NIF conditional display
        self.assertTrue(
            "company.nif" in content,
            "Template should reference company.nif for display",
        )

        # Check that NIF label is present
        self.assertTrue(
            "NIF:" in content or "NIF :" in content,
            "Template should have 'NIF:' label for Tax ID",
        )

    def test_nif_and_arptc_on_separate_line(self):
        """
        Test that NIF and ARPTC license are on a separate line from RCCM and Id.Nat.

        RCCM and Id.Nat should be on one <p> tag, NIF and ARPTC on another <p> tag.
        This improves readability of company legal information.
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check that there are separate paragraphs for RCCM/Id.Nat and NIF/ARPTC
        # We look for the pattern where RCCM and Id.Nat are together,
        # followed by a closing </p> and then a new <p> with NIF
        import re

        # Pattern: RCCM and Id.Nat in one <p>, closed, then new <p> with NIF
        pattern = r"<p>.*company\.rccm.*company\.id_nat.*</p>\s*<p>.*company\.nif"

        self.assertIsNotNone(
            re.search(pattern, content, re.DOTALL),
            "NIF should be on a separate line (in a separate <p> tag) from RCCM and Id.Nat",
        )

        # Check for ARPTC license reference
        self.assertTrue(
            "company.arptc_license" in content,
            "Template should reference company.arptc_license for display",
        )

    def test_excise_tax_shows_percentage(self):
        """
        Test that Excise tax line shows the percentage rate.

        Expected format: "Excise(10%)" or "Excise (10%)" with template logic
        This provides transparency about the tax rate being applied.
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should have logic to display percentage for Excise
        # Looking for: Excise with % symbol and rate variable reference
        has_excise_with_percent = (
            "Excise" in content
            and "%" in content
            and (
                "excise_rate_percent" in content
                or "invoice.excise_rate_percent" in content
            )
        )

        self.assertTrue(
            has_excise_with_percent,
            "Template should show Excise with percentage variable, e.g., 'Excise ({{ invoice.excise_rate_percent }}%)'",
        )

    def test_vat_shows_percentage(self):
        """
        Test that VAT line shows the percentage rate.

        Expected format: "VAT(16%)" or "VAT (16%)" with template logic
        This provides transparency about the tax rate being applied.
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should have logic to display percentage for VAT
        has_vat_with_percent = (
            "VAT" in content
            and "%" in content
            and ("vat_rate_percent" in content or "invoice.vat_rate_percent" in content)
        )

        self.assertTrue(
            has_vat_with_percent,
            "Template should show VAT with percentage variable, e.g., 'VAT ({{ invoice.vat_rate_percent }}%)'",
        )

    def test_total_due_shows_currency(self):
        """
        Test that "Total Due" label includes the currency.

        Expected format: "Total Due (USD)" or "Total Due (CDF)"
        This clarifies which currency the total is in.
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should have "Total Due" with currency variable
        self.assertTrue(
            "Total Due" in content, "Template should have 'Total Due' label"
        )

        # Check for currency in Total Due context
        # Looking for pattern like: Total Due ({{ invoice.currency }})
        has_currency_in_total = (
            "Total Due (" in content or "Total Due(" in content
        ) and "invoice.currency" in content

        self.assertTrue(
            has_currency_in_total,
            "Template should show 'Total Due' with currency, e.g., 'Total Due (USD)'",
        )

    def test_unit_price_column_shows_currency(self):
        """
        Test that "Unit Price" column header includes the currency.

        Expected format: "Unit Price (USD)" or "Unit Price (CDF)"
        This clarifies the currency for prices in the items table.
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should have "Unit Price" with currency
        self.assertTrue(
            "Unit Price" in content, "Template should have 'Unit Price' column"
        )

        # Check for currency in Unit Price header
        has_currency_in_unit_price = (
            "Unit Price (" in content or "Unit Price(" in content
        )

        self.assertTrue(
            has_currency_in_unit_price,
            "Template should show 'Unit Price' with currency, e.g., 'Unit Price (USD)'",
        )

    def test_line_total_column_shows_currency(self):
        """
        Test that "Line Total" column header includes the currency.

        Expected format: "Line Total (USD)" or "Line Total (CDF)"
        This clarifies the currency for line totals in the items table.
        """
        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Should have "Line Total" with currency
        self.assertTrue(
            "Line Total" in content, "Template should have 'Line Total' column"
        )

        # Check for currency in Line Total header
        has_currency_in_line_total = (
            "Line Total (" in content or "Line Total(" in content
        )

        self.assertTrue(
            has_currency_in_line_total,
            "Template should show 'Line Total' with currency, e.g., 'Line Total (USD)'",
        )

    # Consolidated invoice template tests

    def test_consolidated_nif_is_displayed(self):
        """Test that NIF is displayed in consolidated invoice template."""
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            "company.nif" in content and ("NIF:" in content or "NIF :" in content),
            "Consolidated template should display NIF",
        )

    def test_consolidated_nif_and_arptc_on_separate_line(self):
        """
        Test that NIF and ARPTC are on a separate line in consolidated invoice.

        Same structure as regular invoice: RCCM/Id.Nat on one line, NIF/ARPTC on another.
        """
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        import re

        # Pattern: RCCM and Id.Nat in one <p>, closed, then new <p> with NIF
        pattern = r"<p>.*company\.rccm.*company\.id_nat.*</p>\s*<p>.*company\.nif"

        self.assertIsNotNone(
            re.search(pattern, content, re.DOTALL),
            "Consolidated template: NIF should be on a separate line from RCCM and Id.Nat",
        )

        # Check for ARPTC license reference
        self.assertTrue(
            "company.arptc_license" in content,
            "Consolidated template should reference company.arptc_license",
        )

    def test_consolidated_excise_shows_percentage(self):
        """Test that Excise shows percentage in consolidated invoice."""
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        has_excise_with_percent = (
            "Excise" in content
            and "%" in content
            and (
                "excise_rate_percent" in content
                or "consolidated.excise_rate_percent" in content
            )
        )

        self.assertTrue(
            has_excise_with_percent,
            "Consolidated template should show Excise with percentage variable",
        )

    def test_consolidated_vat_shows_percentage(self):
        """Test that VAT shows percentage in consolidated invoice."""
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        has_vat_with_percent = (
            "VAT" in content
            and "%" in content
            and (
                "vat_rate_percent" in content
                or "consolidated.vat_rate_percent" in content
            )
        )

        self.assertTrue(
            has_vat_with_percent,
            "Consolidated template should show VAT with percentage variable",
        )

    def test_consolidated_total_due_shows_currency(self):
        """Test that Total Due shows currency in consolidated invoice."""
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        has_currency_in_total = "Total Due" in content and (
            "consolidated.currency" in content
        )

        self.assertTrue(
            has_currency_in_total,
            "Consolidated template should show 'Total Due' with currency variable",
        )

    def test_consolidated_unit_price_shows_currency(self):
        """Test that Unit Price shows currency in consolidated invoice."""
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            "Unit Price" in content
            and ("Unit Price (" in content or "Unit Price(" in content),
            "Consolidated template should show 'Unit Price' with currency",
        )

    def test_consolidated_line_total_shows_currency(self):
        """Test that Line Total shows currency in consolidated invoice."""
        with open(self.consolidated_template_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(
            "Line Total" in content
            and ("Line Total (" in content or "Line Total(" in content),
            "Consolidated template should show 'Line Total' with currency",
        )
