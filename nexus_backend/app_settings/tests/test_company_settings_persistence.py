"""
TDD Tests for Company Settings Persistence Bug Fix

ISSUE: The company_settings_update view had buggy logic that prevented
empty values from being saved. Pattern like:
    tax_id = g("tax_id")
    if tax_id:
        cs.nif = tax_id
This meant if a user tried to clear the NIF field, it wouldn't be saved.

SOLUTION: Check if field exists in POST data using:
    if "nif" in request.POST:
        cs.nif = g("nif")
This allows empty values to be saved, enabling users to clear fields.
"""

from django.test import Client, TestCase
from django.urls import reverse

from main.models import CompanySettings
from user.models import User


class CompanySettingsPersistenceTest(TestCase):
    """Test that Company Settings can be cleared and persisted correctly"""

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

        # Get or create company settings
        self.cs = CompanySettings.get()

    def test_nif_can_be_saved(self):
        """Test that NIF (tax_id) can be saved via POST"""
        response = self.client.post(
            self.url,
            {
                "nif": "A1234567890B",
            },
        )

        self.assertEqual(response.status_code, 200)

        # Reload from database
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.nif, "A1234567890B")

    def test_nif_can_be_cleared(self):
        """Test that NIF can be emptied/cleared"""
        # First, set a value
        self.cs.nif = "A1234567890B"
        self.cs.save()

        # Now clear it
        response = self.client.post(
            self.url,
            {
                "nif": "",  # Empty string
            },
        )

        self.assertEqual(response.status_code, 200)

        # Reload and verify it's empty
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.nif, "")

    def test_rccm_can_be_cleared(self):
        """Test that RCCM can be emptied"""
        self.cs.rccm = "CD/LSHI/RCCM/19-A-00050"
        self.cs.save()

        response = self.client.post(
            self.url,
            {
                "rccm": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.rccm, "")

    def test_id_nat_can_be_cleared(self):
        """Test that Id.Nat can be emptied"""
        self.cs.id_nat = "0009000"
        self.cs.save()

        response = self.client.post(
            self.url,
            {
                "id_nat": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.id_nat, "")

    def test_arptc_license_can_be_cleared(self):
        """Test that ARPTC license can be emptied"""
        self.cs.arptc_license = "ARPTC-12345"
        self.cs.save()

        response = self.client.post(
            self.url,
            {
                "arptc_license": "",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.arptc_license, "")

    def test_multiple_fields_save_correctly(self):
        """Test that multiple fields can be updated in one request"""
        response = self.client.post(
            self.url,
            {
                "nif": "A1111111111B",
                "rccm": "CD/KIN/RCCM/20-B-12345",
                "id_nat": "0012345",
                "arptc_license": "ARPTC-67890",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.nif, "A1111111111B")
        self.assertEqual(self.cs.rccm, "CD/KIN/RCCM/20-B-12345")
        self.assertEqual(self.cs.id_nat, "0012345")
        self.assertEqual(self.cs.arptc_license, "ARPTC-67890")

    def test_partial_update_does_not_clear_other_fields(self):
        """Test that updating only NIF doesn't clear RCCM or Id.Nat"""
        # Set initial values
        self.cs.nif = "OLD_NIF"
        self.cs.rccm = "OLD_RCCM"
        self.cs.id_nat = "OLD_ID_NAT"
        self.cs.save()

        # Update only NIF
        response = self.client.post(
            self.url,
            {
                "nif": "NEW_NIF",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()

        # NIF should be updated
        self.assertEqual(self.cs.nif, "NEW_NIF")

        # Other fields should remain unchanged
        self.assertEqual(self.cs.rccm, "OLD_RCCM")
        self.assertEqual(self.cs.id_nat, "OLD_ID_NAT")

    def test_nif_with_special_characters(self):
        """Test that NIF with special characters is saved correctly"""
        nif_with_special = "A-1234/567.890:B"
        response = self.client.post(
            self.url,
            {
                "nif": nif_with_special,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.cs.refresh_from_db()
        self.assertEqual(self.cs.nif, nif_with_special)
