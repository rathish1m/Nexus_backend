# Create your tests here.

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from main.models import AccountEntry

User = get_user_model()


class CustomerActionsTestCase(TestCase):
    def setUp(self):
        # Create admin user
        self.admin = User.objects.create_user(
            username="admin",
            email="admin@test.com",
            full_name="Admin User",
            password="password",
            roles=["admin"],
            is_staff=True,
        )
        # Create support user
        self.support = User.objects.create_user(
            username="support",
            email="support@test.com",
            full_name="Support User",
            password="password",
            roles=["support"],
            is_staff=True,
        )
        # Create customer
        self.customer = User.objects.create_user(
            username="customer",
            email="customer@test.com",
            full_name="Customer User",
            password="password",
            roles=["customer"],
            is_staff=False,
        )

    def test_edit_customer_success(self):
        """Test editing a customer successfully."""
        self.client.login(username="admin@test.com", password="password")
        url = reverse("edit_customer")
        data = {
            "customer_id": self.customer.id_user,
            "full_name": "Updated Name",
            "email": "updated@test.com",
            "phone": "+1234567890",
        }
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.full_name, "Updated Name")
        self.assertEqual(self.customer.email, "updated@test.com")

    def test_edit_customer_unauthorized(self):
        """Test that non-admin/support cannot edit."""
        # Create non-staff user
        User.objects.create_user(
            username="nonstaff",
            email="nonstaff@test.com",
            full_name="Non Staff",
            password="password",
            roles=["customer"],
            is_staff=False,
        )
        self.client.login(username="nonstaff@test.com", password="password")
        url = reverse("edit_customer")
        data = {"customer_id": self.customer.id_user, "full_name": "Hacked"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_toggle_customer_status_activate(self):
        """Test activating an inactive customer."""
        self.customer.is_active = False
        self.customer.save()
        self.client.login(username="admin@test.com", password="password")
        url = reverse("toggle_customer_status")
        data = {"customer_id": self.customer.id_user, "action": "activate"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)

    def test_toggle_customer_status_deactivate(self):
        """Test deactivating an active customer."""
        self.client.login(username="admin@test.com", password="password")
        url = reverse("toggle_customer_status")
        data = {"customer_id": self.customer.id_user, "action": "deactivate"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_reset_customer_password(self):
        """Test resetting customer password and email sending."""
        self.client.login(username="admin@test.com", password="password")
        url = reverse("reset_customer_password")
        data = {"customer_id": self.customer.id_user}

        # Mock email sending to avoid actual emails in tests
        with patch("customers.views.send_mail") as mock_send_mail:
            response = self.client.post(url, data, content_type="application/json")
            self.assertEqual(response.status_code, 200)

            # Check response structure
            data = response.json()
            self.assertTrue(data["success"])
            self.assertIn("message", data)
            self.assertNotIn("new_password", data)  # Password should not be returned

            # Verify email was attempted to be sent
            mock_send_mail.assert_called_once()
            call_args = mock_send_mail.call_args
            self.assertEqual(call_args[0][2], [self.customer.email])  # Recipient email

    def test_delete_customer_success(self):
        """Test soft deleting a customer with no unpaid invoices."""
        self.client.login(username="admin@test.com", password="password")
        url = reverse("delete_customer")
        data = {"customer_id": self.customer.id_user}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.customer.refresh_from_db()
        self.assertFalse(self.customer.is_active)

    def test_delete_customer_with_unpaid_invoices(self):
        """Test cannot delete customer with unpaid invoices."""
        # Create unpaid invoice entry
        AccountEntry.objects.create(
            account=self.customer.billing_account,
            entry_type="invoice",
            amount_usd=100.00,
            description="Test invoice",
        )
        self.client.login(username="admin@test.com", password="password")
        url = reverse("delete_customer")
        data = {"customer_id": self.customer.id_user}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.customer.refresh_from_db()
        self.assertTrue(self.customer.is_active)  # Still active

    def test_purge_customer_data_success(self):
        """Test hard deleting a customer with admin password."""
        self.client.login(username="admin@test.com", password="password")
        url = reverse("purge_customer_data")
        data = {"customer_id": self.customer.id_user, "admin_password": "password"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        # Check customer is deleted
        with self.assertRaises(User.DoesNotExist):
            User.objects.get(id_user=self.customer.id_user)

    def test_purge_customer_data_wrong_password(self):
        """Test purge fails with wrong password."""
        self.client.login(username="admin@test.com", password="password")
        url = reverse("purge_customer_data")
        data = {"customer_id": self.customer.id_user, "admin_password": "wrong"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
        # Customer still exists
        self.customer.refresh_from_db()

    def test_purge_customer_data_non_admin(self):
        """Test only admin can purge."""
        self.client.login(username="support@test.com", password="password")
        url = reverse("purge_customer_data")
        data = {"customer_id": self.customer.id_user, "admin_password": "password"}
        response = self.client.post(url, data, content_type="application/json")
        self.assertEqual(response.status_code, 403)
