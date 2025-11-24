"""
Simple TDD Tests for Invoice Logo Resolution

This test suite follows Test-Driven Development (TDD) methodology:

1. RED Phase: Write tests that fail because the feature doesn't exist yet
2. GREEN Phase: Implement minimal code to make tests pass
3. REFACTOR Phase: Improve code quality while keeping tests green

Problem Solved:
- Invoice PDFs were generated without a logo when CompanySettings.logo was empty
- This resulted in invoices lacking proper branding

Solution:
- Modified invoice templates to always display a logo
- Uses static fallback logo (static/images/logo/logo.png) when no custom logo is uploaded
- Ensures consistent branding across all invoices

Tests verify:
- Static logo file exists in the project
- resolve_uri() correctly converts static URLs to absolute paths for WeasyPrint/xhtml2pdf
- Invoice template always references a logo (either custom or static fallback)
"""

import os

from django.conf import settings
from django.test import SimpleTestCase

from billing_management.views import resolve_uri


class LogoResolveURITests(SimpleTestCase):
    """
    Simple tests that don't require database access.
    These verify the logo resolution mechanism works correctly.
    """

    def test_static_logo_file_exists(self):
        """
        RED TEST: Verify that the static logo file exists.
        This is a prerequisite for displaying logos in PDFs.
        """
        logo_path = os.path.join(
            settings.BASE_DIR, "static", "images", "logo", "logo.png"
        )

        self.assertTrue(
            os.path.exists(logo_path), f"Logo file must exist at {logo_path}"
        )

    def test_resolve_uri_converts_static_url_to_absolute_path(self):
        """
        RED TEST: Verify resolve_uri converts static URLs to absolute paths.
        WeasyPrint/xhtml2pdf requires absolute file paths for images.
        """
        # Test with the logo URL
        logo_url = "/static/images/logo/logo.png"

        # Resolve the URI
        resolved_path = resolve_uri(logo_url)

        # Assertions
        self.assertIsNotNone(
            resolved_path, "resolve_uri should return a path for static URLs"
        )

        self.assertNotEqual(
            resolved_path, logo_url, "Resolved path should be different from the URL"
        )

        # The resolved path should be an absolute file path
        self.assertTrue(
            os.path.isabs(resolved_path) or os.path.exists(resolved_path),
            f"Resolved path should be absolute or exist: {resolved_path}",
        )

    def test_resolve_uri_returns_existing_file_for_logo(self):
        """
        RED TEST: Verify that the resolved logo path actually exists.
        This ensures WeasyPrint can find and embed the logo.
        """
        logo_url = "/static/images/logo/logo.png"
        resolved_path = resolve_uri(logo_url)

        self.assertTrue(
            os.path.exists(resolved_path),
            f"Resolved logo file must exist at {resolved_path}",
        )


class LogoTemplateTests(SimpleTestCase):
    """
    Tests for the invoice template logo rendering logic.
    """

    def test_template_file_exists(self):
        """
        Verify the invoice template file exists.
        """
        template_path = os.path.join(
            settings.BASE_DIR,
            "billing_management",
            "templates",
            "invoices",
            "inv_templates.html",
        )

        self.assertTrue(
            os.path.exists(template_path),
            f"Invoice template must exist at {template_path}",
        )

    def test_template_contains_logo_section(self):
        """
        RED TEST: Verify template has a logo section.
        Currently it only shows logo if company.logo exists.
        We need it to always show a logo (using static fallback).
        """
        template_path = os.path.join(
            settings.BASE_DIR,
            "billing_management",
            "templates",
            "invoices",
            "inv_templates.html",
        )

        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Template should have a logo div
        self.assertIn('<div class="logo">', content)

        # RED TEST: This will initially fail because the template
        # only shows logo conditionally via {% if company.logo %}
        # We need to ensure static logo is ALWAYS present
        # Check for Django static tag with logo path
        self.assertTrue(
            "{% static 'images/logo/logo.png' %}" in content
            or "static/images/logo/logo.png" in content,
            "Template should reference static logo file (this test should fail initially)",
        )

    def test_logo_css_has_explicit_height(self):
        """
        Test that the logo CSS sets height to 40px with width auto.

        This maintains the original proportions while ensuring WeasyPrint
        properly renders the logo. Height is fixed at 40px, width adjusts
        automatically to maintain the logo's natural aspect ratio.
        """
        template_path = os.path.join(
            settings.BASE_DIR,
            "billing_management",
            "templates",
            "invoices",
            "inv_templates.html",
        )

        with open(template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for explicit height of 40px with !important
        self.assertTrue(
            "height: 40px !important" in content or "height:40px!important" in content,
            "Logo img should have 'height: 40px !important' for consistent height",
        )

        # Check for width: auto with !important (maintains aspect ratio)
        self.assertTrue(
            "width: auto !important" in content or "width:auto!important" in content,
            "Logo img should have 'width: auto !important' to maintain aspect ratio",
        )

        # Check for display: block to prevent inline issues
        self.assertTrue(
            (
                "display: block !important" in content
                or "display:block!important" in content
            ),
            "Logo img should have 'display: block !important' for proper rendering",
        )

        # Check for object-fit: contain
        self.assertTrue(
            "object-fit: contain" in content or "object-fit:contain" in content,
            "Logo should have 'object-fit: contain' to fit within dimensions without distortion",
        )
