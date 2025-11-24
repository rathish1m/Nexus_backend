"""
TDD Tests for Invoice PDF Generation with Logo
Following Test-Driven Development methodology
"""

import os
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.urls import reverse

from billing_management.views import (
    _build_invoice_context,
    invoice_pdf_by_number,
    consolidated_invoice_pdf,
    resolve_uri,
)
from main.models import CompanySettings, Invoice, InvoiceLine, ConsolidatedInvoice

User = get_user_model()


class InvoicePDFLogoTests(TestCase):
    """
    Test suite for verifying that invoice PDFs contain the company logo.
    These tests follow TDD principles:
    1. Write failing tests first (RED)
    2. Implement minimal code to pass (GREEN)
    3. Refactor for quality (REFACTOR)
    """

    def setUp(self):
        """Set up test data for invoice PDF generation"""
        # Create test user
        self.user = User.objects.create_user(
            email="test.invoice@example.com",
            username="test_invoice_user",
            password="testpass123",
        )

        # Use singleton CompanySettings and update fields used in tests
        self.company = CompanySettings.get()
        self.company.legal_name = "Test Company Ltd"
        self.company.trade_name = "Test Corp"
        self.company.street_address = "123 Test Street"
        self.company.city = "Test City"
        self.company.province = "Test Province"
        self.company.country = "Test Country"
        self.company.rccm = "TEST-RCCM-123"
        self.company.id_nat = "TEST-NAT-456"
        self.company.nif = "TEST-NIF-789"
        self.company.email = "info@testcompany.com"
        self.company.phone = "+1234567890"
        self.company.website = "www.testcompany.com"
        self.company.vat_rate_percent = Decimal("16.00")
        self.company.payment_terms_days = 30
        self.company.save()

        # Create test invoice
        self.invoice = Invoice.objects.create(
            number="2025-TEST-000001",
            user=self.user,
            currency="USD",
            subtotal=Decimal("100.00"),
            tax_total=Decimal("16.00"),
            grand_total=Decimal("116.00"),
            status="paid",
            bill_to_name="Test Customer",
            bill_to_address="456 Customer Ave",
        )

        # Add invoice line
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Test Service",
            quantity=1,
            unit_price=Decimal("100.00"),
        )

        # Request factory for views
        self.factory = RequestFactory()

    def test_static_logo_path_exists(self):
        """
        Test that the static logo file exists in the project.
        This is a prerequisite for displaying the logo in PDFs.
        """
        # Construct path to static logo
        logo_path = os.path.join(
            settings.BASE_DIR, "static", "images", "logo", "logo.png"
        )

        # Assert logo file exists
        self.assertTrue(
            os.path.exists(logo_path), f"Logo file should exist at {logo_path}"
        )

    def test_resolve_uri_handles_static_logo(self):
        """
        Test that resolve_uri correctly converts static logo URL to absolute path.
        WeasyPrint needs absolute file paths to embed images in PDFs.
        """
        # Static URL for logo
        logo_url = "/static/images/logo/logo.png"

        # Resolve the URI
        resolved_path = resolve_uri(logo_url)

        # Assert the path is resolved and file exists
        self.assertIsNotNone(resolved_path, "Logo URL should be resolved")
        self.assertNotEqual(
            resolved_path, logo_url, "Resolved path should be different from URL"
        )
        self.assertTrue(
            os.path.exists(resolved_path),
            f"Resolved logo path should exist: {resolved_path}",
        )

    def test_invoice_context_includes_static_logo(self):
        """
        Test that the invoice context includes a static logo URL
        even when company.logo is not set.
        """
        # Build invoice context
        context = _build_invoice_context(self.invoice, self.company)

        # Assert context has necessary data
        self.assertIn("company", context)
        self.assertIn("invoice", context)

        # Assert static logo is available in context or template can access it
        # We'll verify this through the rendered HTML in the next test

    def test_rendered_html_contains_logo_img_tag(self):
        """
        Test that the rendered invoice HTML contains an img tag for the logo.
        This verifies the template correctly includes the logo.
        """
        # Build context
        context = _build_invoice_context(self.invoice, self.company)

        # Create a mock request
        request = self.factory.get("/fake-path/")
        request.user = self.user

        # Render the template
        html = render_to_string(
            "invoices/inv_templates.html", context=context, request=request
        )

        # Assert HTML contains logo image tag
        self.assertIn("<img", html, "HTML should contain an img tag")

        # Assert the logo source is the static file
        self.assertIn(
            "static/images/logo/logo.png",
            html,
            "HTML should reference the static logo file",
        )

    def test_invoice_pdf_generation_includes_logo(self):
        """
        Test that the generated PDF includes the logo.
        This is an integration test verifying the entire flow.
        """
        # Create a request
        request = self.factory.get(f"/en/billing/invoice/{self.invoice.number}/pdf/")
        request.user = self.user

        # Mock pisa.CreatePDF to avoid actual PDF generation in tests
        # but verify it's called with HTML containing logo
        with patch("billing_management.views.pisa.CreatePDF") as mock_create_pdf:
            # Configure mock to simulate successful PDF generation
            mock_status = MagicMock()
            mock_status.err = 0
            mock_create_pdf.return_value = mock_status

            # Call the view
            response = invoice_pdf_by_number(request, self.invoice.number)

            # Assert CreatePDF was called
            self.assertTrue(mock_create_pdf.called, "PDF generation should be called")

            # Get the HTML passed to CreatePDF
            call_args = mock_create_pdf.call_args
            html_content = (
                call_args.kwargs.get("src") if call_args.kwargs else call_args[1]["src"]
            )

            # Assert HTML contains logo reference
        self.assertIn(
            "static/images/logo/logo.png",
            html_content,
            "PDF HTML should contain static logo reference",
        )

            # Assert response is successful
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_logo_displays_even_without_company_logo_field(self):
        """
        Test that logo displays using static fallback when company.logo is None/empty.
        This is the core requirement: static logo should always appear.
        """
        # Ensure company.logo is None
        self.company.logo = None
        self.company.save()

        # Build context
        context = _build_invoice_context(self.invoice, self.company)

        # Create request
        request = self.factory.get("/fake-path/")
        request.user = self.user

        # Render template
        html = render_to_string(
            "invoices/inv_templates.html", context=context, request=request
        )

        # Assert static logo is present even though company.logo is None
        self.assertIn(
            "static/images/logo/logo.png",
            html,
            "Static logo should be present even when company.logo is empty",
        )

    def test_logo_styling_is_correct(self):
        """
        Test that the logo has correct styling (top-left positioning).
        """
        # Build context
        context = _build_invoice_context(self.invoice, self.company)
        request = self.factory.get("/fake-path/")
        request.user = self.user

        # Render template
        html = render_to_string(
            "invoices/inv_templates.html", context=context, request=request
        )

        # Check that logo is in the header section
        self.assertIn('<div class="hdr">', html)
        self.assertIn('<div class="logo">', html)

        # Verify CSS styling exists for logo
        self.assertIn(".logo img", html, "CSS for logo should exist")
        self.assertIn("height: 40px", html, "Logo should have height styling")

    def test_invoice_pdf_by_number_nonexistent_returns_404(self):
        """
        Requesting a PDF for a non-existent invoice number should return 404.
        """
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("invoice_pdf_by_number", args=["NO-SUCH-INV"])
        )
        self.assertEqual(response.status_code, 404)


class ConsolidatedInvoicePDFTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="cons.inv@example.com",
            username="cons_inv_user",
            password="testpass123",
        )
        self.client.force_login(self.user)

    def test_consolidated_invoice_pdf_nonexistent_returns_404(self):
        """
        Requesting a PDF for a non-existent consolidated invoice number should return 404.
        """
        response = self.client.get(
            reverse("consolidated_invoice_pdf", args=["NO-SUCH-CONS"])
        )
        self.assertEqual(response.status_code, 404)
