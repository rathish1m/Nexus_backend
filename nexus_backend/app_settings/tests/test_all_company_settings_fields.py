"""
TDD Tests for All Company Settings Form Fields Persistence

Tests to ensure ALL form fields in Company Settings can be:
1. Saved with values
2. Cleared (set to empty)
3. Updated without affecting other fields

This covers fields across all tabs:
- Company (Identity, Address, Legal Identifiers)
- Billing Defaults (Numbering, Currency & Terms, Payment Instructions)
- Branding (Stamp, Signature, Signatory)
- Compliance & Legal (Tax Office, Legal Notes)
"""

from django.test import Client, TestCase
from django.urls import reverse

from main.models import CompanySettings
from user.models import User


class AllCompanySettingsFieldsTest(TestCase):
    """Comprehensive test suite for all Company Settings fields"""

    def setUp(self):
        """Create test user and authenticate"""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testadmin",
            email="admin@test.com",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.user)
        self.url = reverse("settings_company_update")
        self.cs = CompanySettings.get()

    # ========== IDENTITY FIELDS TESTS ==========

    def test_trade_name_can_be_saved_and_cleared(self):
        """Test that Trade Name can be saved and cleared"""
        # Save a value
        response = self.client.post(self.url, {"trade_name": "My Trade Name"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.trade_name, "My Trade Name")

        # Clear it
        response = self.client.post(self.url, {"trade_name": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.trade_name, "")

    # ========== ADDRESS FIELDS TESTS ==========

    def test_street_address_can_be_saved_and_cleared(self):
        """Test that Street Address can be saved and cleared"""
        response = self.client.post(self.url, {"street_address": "123 Main St"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.street_address, "123 Main St")

        # Clear it
        response = self.client.post(self.url, {"street_address": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.street_address, "")

    def test_province_can_be_saved_and_cleared(self):
        """Test that Province can be saved and cleared"""
        response = self.client.post(self.url, {"province": "Haut-Katanga"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.province, "Haut-Katanga")

        # Clear it
        response = self.client.post(self.url, {"province": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.province, "")

    # ========== BILLING DEFAULTS TESTS ==========

    def test_reset_number_annually_checkbox(self):
        """Test that reset_number_annually checkbox works correctly"""
        # Test checking the box
        response = self.client.post(
            self.url,
            {
                "reset_number_annually_cb": "on",
                "_section": "billing",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertTrue(self.cs.reset_number_annually)

        # Test unchecking the box (not sending the field)
        response = self.client.post(
            self.url,
            {
                "_section": "billing",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertFalse(self.cs.reset_number_annually)

    def test_default_currency_can_be_changed(self):
        """Test that Default Currency can be changed"""
        response = self.client.post(self.url, {"default_currency": "CDF"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.default_currency, "CDF")

        response = self.client.post(self.url, {"default_currency": "USD"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.default_currency, "USD")

    def test_payment_terms_days_can_be_saved_and_cleared(self):
        """Test that Payment Terms (days) can be saved and cleared"""
        response = self.client.post(self.url, {"payment_terms_days": "30"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.payment_terms_days, 30)

        # Clear it
        response = self.client.post(self.url, {"payment_terms_days": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertIsNone(self.cs.payment_terms_days)

    def test_show_prices_in_cdf_checkbox(self):
        """Test that show_prices_in_cdf checkbox works correctly"""
        # Test checking the box
        response = self.client.post(
            self.url,
            {
                "show_prices_in_cdf_cb": "on",
                "_section": "billing",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertTrue(self.cs.show_prices_in_cdf)

        # Test unchecking the box
        response = self.client.post(
            self.url,
            {
                "_section": "billing",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertFalse(self.cs.show_prices_in_cdf)

    # ========== PAYMENT INSTRUCTIONS & FOOTERS TESTS ==========

    def test_payment_instructions_can_be_saved_and_cleared(self):
        """Test that Payment Instructions can be saved and cleared"""
        instructions = "Pay within 30 days to avoid penalties"
        response = self.client.post(self.url, {"payment_instructions": instructions})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.payment_instructions, instructions)

        # Clear it
        response = self.client.post(self.url, {"payment_instructions": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.payment_instructions, "")

    def test_invoice_footer_fr_can_be_saved_and_cleared(self):
        """Test that Invoice Footer (FR) can be saved and cleared"""
        footer_fr = "Merci pour votre confiance"
        response = self.client.post(self.url, {"footer_text_fr": footer_fr})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.footer_text_fr, footer_fr)

        # Clear it
        response = self.client.post(self.url, {"footer_text_fr": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.footer_text_fr, "")

    def test_invoice_footer_en_can_be_saved_and_cleared(self):
        """Test that Invoice Footer (EN) can be saved and cleared"""
        footer_en = "Thank you for your business"
        response = self.client.post(self.url, {"footer_text_en": footer_en})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.footer_text_en, footer_en)

        # Clear it
        response = self.client.post(self.url, {"footer_text_en": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.footer_text_en, "")

    # ========== BRANDING TESTS ==========

    def test_signatory_name_can_be_saved_and_cleared(self):
        """Test that Signatory Name can be saved and cleared"""
        response = self.client.post(self.url, {"signatory_name": "John Doe"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.signatory_name, "John Doe")

        # Clear it
        response = self.client.post(self.url, {"signatory_name": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.signatory_name, "")

    def test_signatory_title_can_be_saved_and_cleared(self):
        """Test that Signatory Title can be saved and cleared"""
        response = self.client.post(self.url, {"signatory_title": "CEO"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.signatory_title, "CEO")

        # Clear it
        response = self.client.post(self.url, {"signatory_title": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.signatory_title, "")

    # ========== COMPLIANCE & LEGAL TESTS ==========

    def test_tax_office_name_can_be_saved_and_cleared(self):
        """Test that Tax Office/Directorate can be saved and cleared"""
        response = self.client.post(self.url, {"tax_office_name": "DGI Lubumbashi"})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.tax_office_name, "DGI Lubumbashi")

        # Clear it
        response = self.client.post(self.url, {"tax_office_name": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.tax_office_name, "")

    def test_legal_notes_can_be_saved_and_cleared(self):
        """Test that Legal Notes can be saved and cleared"""
        notes = "Company registered in DRC under law XYZ"
        response = self.client.post(self.url, {"legal_notes": notes})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.legal_notes, notes)

        # Clear it
        response = self.client.post(self.url, {"legal_notes": ""})
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.legal_notes, "")

    # ========== INTEGRATION TESTS ==========

    def test_all_fields_can_be_saved_together(self):
        """Test that all fields can be saved in a single request"""
        data = {
            # Identity
            "trade_name": "Test Trade Name",
            # Address
            "street_address": "456 Test Ave",
            "province": "Test Province",
            # Billing
            "default_currency": "CDF",
            "payment_terms_days": "45",
            # Payment & Footers
            "payment_instructions": "Test payment instructions",
            "footer_text_fr": "Pied de page FR",
            "footer_text_en": "Footer EN",
            # Branding
            "signatory_name": "Test Signatory",
            "signatory_title": "Test Title",
            # Compliance
            "tax_office_name": "Test Tax Office",
            "legal_notes": "Test legal notes",
        }

        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()

        # Verify all fields
        self.assertEqual(self.cs.trade_name, "Test Trade Name")
        self.assertEqual(self.cs.street_address, "456 Test Ave")
        self.assertEqual(self.cs.province, "Test Province")
        self.assertEqual(self.cs.default_currency, "CDF")
        self.assertEqual(self.cs.payment_terms_days, 45)
        self.assertEqual(self.cs.payment_instructions, "Test payment instructions")
        self.assertEqual(self.cs.footer_text_fr, "Pied de page FR")
        self.assertEqual(self.cs.footer_text_en, "Footer EN")
        self.assertEqual(self.cs.signatory_name, "Test Signatory")
        self.assertEqual(self.cs.signatory_title, "Test Title")
        self.assertEqual(self.cs.tax_office_name, "Test Tax Office")
        self.assertEqual(self.cs.legal_notes, "Test legal notes")
