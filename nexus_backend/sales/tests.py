import json

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from main.factories import (
    OrderFactory,
    SubscriptionFactory,
    SubscriptionPlanFactory,
    UserFactory,
    StarlinkKitFactory,
    StarlinkKitInventoryFactory,
    PersonalKYCFactory,
    CompanyKYCFactory,
)
from main.models import (
    CompanyDocument,
    PaymentAttempt,
    StarlinkKitMovement,
    Subscription,
    TaxRate,
)
from django.core.files.uploadedfile import SimpleUploadedFile


User = get_user_model()


class SalesDashboardTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Staff user with sales role
        self.user = User.objects.create_user(
            email="sales.dashboard@example.com",
            username="sales_dashboard_user",
            password="testpass123",
            full_name="Sales Dashboard User",
            is_staff=True,
        )
        self.user.roles = ["sales"]
        self.user.save()
        self.client.force_login(self.user)

        # Seed customers and orders
        self.customer1 = User.objects.create_user(
            email="customer1@example.com",
            username="customer1",
            password="testpass123",
            full_name="Customer One",
            is_staff=False,
        )
        self.customer2 = User.objects.create_user(
            email="customer2@example.com",
            username="customer2",
            password="testpass123",
            full_name="Customer Two",
            is_staff=False,
        )

        OrderFactory(user=self.customer1, payment_status="unpaid")
        OrderFactory(
            user=self.customer2, payment_status="paid", total_price=Decimal("150.00")
        )

    def test_sales_dashboard_context_counts(self):
        response = self.client.get(reverse("sales_dashboard"))
        self.assertEqual(response.status_code, 200)
        ctx = response.context
        # Only non-staff users counted
        self.assertEqual(ctx["user_count"], 2)
        # One pending (unpaid) and one completed (paid) order
        self.assertEqual(ctx["pending_order"], 1)
        self.assertEqual(ctx["completed_order"], 1)
        # amount_paid aggregates total_price of paid orders
        self.assertEqual(float(ctx["amount_paid"]), 150.0)


class UserSubscriptionsListTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            email="sales.subs@example.com",
            username="sales_subs_user",
            password="testpass123",
            full_name="Sales Subs User",
            is_staff=True,
        )
        self.staff.roles = ["sales"]
        self.staff.save()
        self.client.force_login(self.staff)

        self.customer = User.objects.create_user(
            email="subs.customer@example.com",
            username="subs_customer",
            password="testpass123",
            full_name="Subs Customer",
            is_staff=False,
        )

    def test_user_subscriptions_list_rejects_non_xhr(self):
        url = reverse("user_subscriptions_list", args=[self.customer.id_user])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content.decode())
        self.assertFalse(data.get("success"))

    def test_user_subscriptions_list_returns_subscriptions_and_orders(self):
        # Seed one subscription and one order for the customer
        sub = SubscriptionFactory(user=self.customer, status="active")
        order = OrderFactory(
            user=self.customer, status="fulfilled", payment_status="paid"
        )

        url = reverse("user_subscriptions_list", args=[self.customer.id_user])
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("success"))

        subs = data.get("subscriptions") or []
        orders = data.get("orders") or []

        self.assertTrue(any(s["subscription_id"] == sub.id for s in subs))
        self.assertTrue(any(o["order_id"] == order.id for o in orders))


class CustomerListTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            email="sales.customerlist@example.com",
            username="sales_customerlist",
            password="testpass123",
            full_name="Sales CustomerList User",
            is_staff=True,
        )
        self.staff.roles = ["sales"]
        self.staff.save()
        self.client.force_login(self.staff)

        # Create a few non-staff customers
        self.c1 = User.objects.create_user(
            email="cust1@example.com",
            username="cust1",
            password="testpass123",
            full_name="Alpha Customer",
            is_staff=False,
        )
        self.c2 = User.objects.create_user(
            email="cust2@example.com",
            username="cust2",
            password="testpass123",
            full_name="Bravo Customer",
            is_staff=False,
        )
        self.c3 = User.objects.create_user(
            email="cust3@example.com",
            username="cust3",
            password="testpass123",
            full_name="Charlie Customer",
            is_staff=False,
            is_active=False,
        )

    def test_customer_list_page_mode_with_pagination_and_filters(self):
        url = reverse("customer_list")
        resp = self.client.get(url, {"page": 1, "per_page": 2, "q": "Customer"})
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode())
        self.assertTrue(payload["success"])
        self.assertEqual(payload["mode"], "page")
        # There are 3 customers matching "Customer"
        self.assertEqual(payload["total_count"], 3)
        self.assertEqual(len(payload["customers"]), 2)
        self.assertTrue(payload["has_next"])

        # Filter by status=Active should exclude inactive customer
        resp2 = self.client.get(url, {"page": 1, "per_page": 10, "status": "Active"})
        self.assertEqual(resp2.status_code, 200)
        data2 = json.loads(resp2.content.decode())
        self.assertEqual(data2["total_count"], 2)
        self.assertTrue(all(c["is_active"] for c in data2["customers"]))

    def test_customer_list_cursor_mode_basic(self):
        # Use `after` larger than any id_user to simulate first cursor page
        max_id = max(self.c1.id_user, self.c2.id_user, self.c3.id_user)
        url = reverse("customer_list")
        resp = self.client.get(url, {"after": max_id + 1, "limit": 2})
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["mode"], "cursor")
        self.assertEqual(len(data["customers"]), 2)
        self.assertTrue(data["has_more"])
        self.assertIsNotNone(data["next_after"])


class GetKitsDropdownTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = UserFactory(is_staff=True, roles=["sales"])
        self.client.force_login(self.staff)

    def test_get_kits_dropdown_rejects_non_xhr(self):
        url = reverse("get_kits_dropdown")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("error"), "Invalid request")

    def test_get_kits_dropdown_returns_grouped_kits_with_quantity(self):
        kit = StarlinkKitFactory(model="STD", base_price_usd=Decimal("100.00"))
        inv = StarlinkKitInventoryFactory(kit=kit)
        # One received movement => quantity = 1
        StarlinkKitMovement.objects.create(
            inventory_item=inv,
            movement_type="received",
        )

        url = reverse("get_kits_dropdown")
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        kits_by_model = data.get("kits") or {}
        self.assertIn("std", kits_by_model)
        kit_entries = kits_by_model["std"]
        self.assertEqual(len(kit_entries), 1)
        entry = kit_entries[0]
        self.assertEqual(entry["id"], kit.id)
        self.assertEqual(entry["quantity"], 1)
        self.assertFalse(entry["out_of_stock"])
        # Price should be derived from base_price_usd
        self.assertEqual(entry["price_usd"], float(Decimal("100.00")))


class SubscriptionBillingTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Customer user (login_required only, no staff role)
        self.user = UserFactory(is_tax_exempt=True)
        self.client.force_login(self.user)

        self.plan = SubscriptionPlanFactory(monthly_price_usd=Decimal("50.00"))
        self.order = OrderFactory(user=self.user, plan=self.plan, payment_status="paid")
        self.subscription = Subscription.objects.create(
            user=self.user,
            plan=self.plan,
            order=self.order,
            status="active",
        )

        # Minimal tax rates so percentages are defined (but user is tax-exempt)
        TaxRate.objects.create(description="VAT", percentage=Decimal("16.0"))
        TaxRate.objects.create(description="EXCISE", percentage=Decimal("10.0"))

    def test_get_subscription_billing_fallback_uses_payment_attempts(self):
        # No AccountEntry rows -> fallback to PaymentAttempt on subscription.order
        PaymentAttempt.objects.create(
            order=self.order,
            amount=Decimal("50.00"),
            currency="USD",
            status="success",
            payment_type="cash",
            payment_for="subscription",
        )

        url = reverse("get_subscription_billing", args=[self.subscription.id])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode())
        self.assertTrue(payload["success"])

        payments = payload.get("payments") or []
        self.assertEqual(len(payments), 1)
        row = payments[0]
        # Status should reflect exact order.payment_status (lowercased)
        self.assertEqual(row["status"], "paid")
        self.assertEqual(row["payment_status"], "paid")
        self.assertEqual(row["order_id"], self.order.id)

        # Summary amounts come from plan price; tax amounts are zero because user is tax-exempt
        self.assertEqual(payload["subscription_plan_price"], "50.00")
        self.assertEqual(payload["vat_amount"], "0.00")
        self.assertEqual(payload["excise_amount"], "0.00")
        self.assertEqual(payload["total_with_tax"], "50.00")
        self.assertTrue(payload["tax_exempt"])


class RegisterCustomerTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            email="sales.register@example.com",
            username="sales_register",
            password="testpass123",
            full_name="Sales Register User",
            is_staff=True,
        )
        self.staff.roles = ["sales"]
        self.staff.save()
        self.client.force_login(self.staff)

    def test_register_customer_invalid_kyc_type_returns_400(self):
        url = reverse("register_customer")
        resp = self.client.post(url, {"kyc_type": "unknown"})
        self.assertEqual(resp.status_code, 400)
        data = json.loads(resp.content.decode())
        self.assertFalse(data.get("success"))

    def test_register_customer_personal_happy_path(self):
        url = reverse("register_customer")
        email = "new.customer@example.com"
        payload = {
            "kyc_type": "personal",
            "first_name": "New",
            "last_name": "Customer",
            "full_name": "New Customer",
            "email": email,
            "username": "new_customer",
            "phone": "+243812345678",
            "password": "testpass123",
            "password_confirm": "testpass123",
            "document_number": "DOC123456",
            "nationality": "Congolese",
            "date_of_birth": "1990-01-01",
            "id_document_type": "passport",
            "id_issue_date": "2010-01-01",
            "id_expiry_date": "2030-01-01",
            "address_personal": "123 Test Street",
        }
        document_file = SimpleUploadedFile(
            "id.pdf", b"dummy-id-content", content_type="application/pdf"
        )
        resp = self.client.post(
            url,
            data={**payload, "document_file": document_file},
        )
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("success"))
        self.assertTrue(User.objects.filter(email=email).exists())
        user = User.objects.get(email=email)
        # Personal KYC should have been created and linked
        self.assertTrue(hasattr(user, "personnal_kyc"))

    def test_register_customer_invalid_phone_returns_422(self):
        url = reverse("register_customer")
        resp = self.client.post(
            url,
            {
                "kyc_type": "personal",
                "first_name": "Bad",
                "last_name": "Phone",
                "full_name": "Bad Phone",
                "email": "bad.phone@example.com",
                "username": "bad_phone",
                "phone": "not-a-phone",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("field"), "phone")

    def test_register_customer_duplicate_email_returns_409(self):
        # Existing user with same email
        existing = User.objects.create_user(
            email="dup@example.com",
            username="dup_user",
            password="testpass123",
            full_name="Existing User",
        )
        url = reverse("register_customer")
        resp = self.client.post(
            url,
            {
                "kyc_type": "personal",
                "first_name": "New",
                "last_name": "User",
                "full_name": "New User",
                "email": existing.email,
                "username": "new_user_dup_email",
                "phone": "+243812345679",
                "password": "testpass123",
                "password_confirm": "testpass123",
            },
        )
        self.assertEqual(resp.status_code, 409)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("field"), "email")

    def test_register_customer_non_congolese_requires_visa_file(self):
        url = reverse("register_customer")
        resp = self.client.post(
            url,
            {
                "kyc_type": "personal",
                "first_name": "Visa",
                "last_name": "Required",
                "full_name": "Visa Required",
                "email": "visa.required@example.com",
                "username": "visa_required",
                "phone": "+243812345680",
                "password": "testpass123",
                "password_confirm": "testpass123",
                "nationality": "French",  # triggers needs_visa
            },
        )
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("field"), "visa_last_page")


class CustomerDetailsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.viewer = UserFactory()
        self.client.force_login(self.viewer)

    def test_customer_details_requires_ajax_get(self):
        customer = UserFactory()
        url = reverse("sales_customer_details", args=[customer.id_user])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    def test_customer_details_personal_kyc_payload(self):
        kyc = PersonalKYCFactory()
        customer = kyc.user
        url = reverse("sales_customer_details", args=[customer.id_user])
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode())
        self.assertTrue(payload["success"])
        self.assertEqual(payload["customer"]["kyc_type"], "personal")

    def test_customer_details_company_kyc_with_documents(self):
        company_kyc = CompanyKYCFactory()
        customer = company_kyc.user
        # Attach one document so multiple_documents path is populated
        doc_file = SimpleUploadedFile(
            "rccm.pdf", b"dummy-doc", content_type="application/pdf"
        )
        CompanyDocument.objects.create(
            company_kyc=company_kyc,
            document_type="rccm",
            document=doc_file,
            document_name="RCCM Document",
        )
        url = reverse("sales_customer_details", args=[customer.id_user])
        resp = self.client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data["success"])
        self.assertEqual(data["customer"]["kyc_type"], "company")
        kyc_payload = data["customer"]["kyc"]
        self.assertGreaterEqual(kyc_payload.get("documents_count", 0), 1)


class ResubmitPersonalKYCTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff = User.objects.create_user(
            email="sales.kyc@example.com",
            username="sales_kyc",
            password="testpass123",
            full_name="Sales KYC User",
            is_staff=True,
        )
        self.staff.roles = ["sales"]
        self.staff.save()
        self.client.force_login(self.staff)

    def test_resubmit_personal_kyc_missing_full_name_returns_422(self):
        customer = UserFactory()
        url = reverse("sales_resubmit_personal_kyc", args=[customer.id_user])
        resp = self.client.post(
            url,
            {
                # full_name missing
                "date_of_birth": "1990-01-01",
                "nationality": "Congolese",
                "id_document_type": "passport",
                "document_number": "DOC0001",
                "id_issue_date": "2010-01-01",
                "id_expiry_date": "2030-01-01",
                "address": "Some address",
            },
        )
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("field"), "full_name")

    def test_resubmit_personal_kyc_future_dob_returns_422(self):
        customer = UserFactory()
        tomorrow = timezone.localdate() + timezone.timedelta(days=1)
        url = reverse("sales_resubmit_personal_kyc", args=[customer.id_user])
        document_file = SimpleUploadedFile(
            "id.pdf", b"dummy-id-content", content_type="application/pdf"
        )
        resp = self.client.post(
            url,
            {
                "full_name": "Future DOB",
                "date_of_birth": tomorrow.strftime("%Y-%m-%d"),
                "nationality": "Congolese",
                "id_document_type": "passport",
                "document_number": "DOC0002",
                "id_issue_date": "2010-01-01",
                "id_expiry_date": "2030-01-01",
                "address": "Some address",
                "document_file": document_file,
            },
        )
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("field"), "date_of_birth")

    def test_resubmit_personal_kyc_needs_visa_without_file_returns_422(self):
        customer = UserFactory()
        url = reverse("sales_resubmit_personal_kyc", args=[customer.id_user])
        document_file = SimpleUploadedFile(
            "id.pdf", b"dummy-id-content", content_type="application/pdf"
        )
        resp = self.client.post(
            url,
            {
                "full_name": "Needs Visa",
                "date_of_birth": "1990-01-01",
                "nationality": "French",  # triggers needs_visa
                "id_document_type": "passport",
                "document_number": "DOC0003",
                "id_issue_date": "2010-01-01",
                "id_expiry_date": "2030-01-01",
                "address": "Some address",
                "document_file": document_file,
            },
        )
        self.assertEqual(resp.status_code, 422)
        data = json.loads(resp.content.decode())
        self.assertEqual(data.get("field"), "visa_file")
