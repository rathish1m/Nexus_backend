import json
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from main.factories import (
    UserFactory,
    InstallationActivityFactory,
    OrderFactory,
    PersonalKYCFactory,
    CompanyKYCFactory,
)
from main.models import (
    CompanyDocument,
    CompanyKYC,
    PersonalKYC,
    UserPreferences,
    AccountEntry,
)


User = get_user_model()


class DeleteKYCFilesTests(TestCase):
    def setUp(self):
        self.client = Client()
        # Non-staff customer user to satisfy customer_nonstaff_required
        self.user = User.objects.create_user(
            email="customer.docs@example.com",
            username="customer_docs",
            password="testpass123",
            full_name="Customer Docs",
            is_staff=False,
        )
        self.user.roles = ["customer"]
        self.user.save()
        self.client.force_login(self.user)

    def test_delete_company_document_success_and_missing(self):
        company_kyc = CompanyKYC.objects.create(user=self.user, company_name="Test Co")
        # Create a dummy document file in memory
        doc_file = ContentFile(b"test", name="doc.pdf")
        doc = CompanyDocument.objects.create(
            company_kyc=company_kyc,
            document_type="other",
            document=doc_file,
            document_name="Test Document",
        )

        url = reverse("delete_company_document")
        # Successful deletion
        resp = self.client.post(
            url,
            data=json.dumps({"doc_id": doc.id}),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertTrue(payload.get("success"))
        self.assertFalse(
            CompanyDocument.objects.filter(id=doc.id).exists(),
            "CompanyDocument should be deleted",
        )

        # Missing doc_id
        resp_missing = self.client.post(
            url,
            data=json.dumps({}),
            content_type="application/json",
        )
        self.assertEqual(resp_missing.status_code, 200)
        payload_missing = resp_missing.json()
        self.assertFalse(payload_missing.get("success"))
        self.assertIn("ID du document manquant", payload_missing["message"])

    def test_delete_personal_document_and_visa(self):
        personal = PersonalKYC.objects.create(user=self.user)
        doc_file = ContentFile(b"test-doc", name="id.pdf")
        visa_file = ContentFile(b"test-visa", name="visa.pdf")
        personal.document_file = doc_file
        personal.visa_last_page = visa_file
        personal.save()

        # Delete personal document
        url_doc = reverse("delete_personal_document")
        resp_doc = self.client.post(url_doc)
        self.assertEqual(resp_doc.status_code, 200)
        payload_doc = resp_doc.json()
        self.assertTrue(payload_doc.get("success"))

        personal.refresh_from_db()
        # File field should now be empty
        self.assertFalse(bool(personal.document_file))

        # Delete personal visa last page
        url_visa = reverse("delete_personal_visa")
        resp_visa = self.client.post(url_visa)
        self.assertEqual(resp_visa.status_code, 200)
        payload_visa = resp_visa.json()
        self.assertTrue(payload_visa.get("success"))

        personal.refresh_from_db()
        self.assertFalse(bool(personal.visa_last_page))


class GetKYCStatusTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_get_kyc_status_not_submitted(self):
        url = reverse("get_kyc_status")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["kyc_status"], "Not submitted")
        self.assertEqual(data["kyc_data"], {})

    def test_get_kyc_status_personal_rejected_includes_kyc_data(self):
        personal = PersonalKYC.objects.create(
            user=self.user,
            full_name="John Doe",
            nationality="French",
            id_document_type="passport",
            document_number="DOC123",
            status=PersonalKYC.Status.REJECTED,
            rejection_reason="document_expired",
            remarks="Expired document",
        )
        # Attach a visa file so has_visa_file becomes True
        personal.visa_last_page = ContentFile(b"visa", name="visa.pdf")
        personal.save()

        url = reverse("get_kyc_status")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["kyc_status"], "rejected")
        self.assertEqual(
            data["kyc_rejection_reason"], personal.get_rejection_reason_display()
        )
        kyc_data = data["kyc_data"]
        self.assertEqual(kyc_data["full_name"], "John Doe")
        self.assertTrue(kyc_data["has_visa_file"])

    def test_get_kyc_status_company_rejected_includes_company_fields(self):
        company = CompanyKYC.objects.create(
            user=self.user,
            company_name="ACME Corp",
            address="Somewhere",
            rccm="RCCM123",
            nif="NIF123",
            id_nat="IDNAT123",
            status=CompanyKYC.Status.REJECTED,
            rejection_reason="invalid_document",
            remarks="Invalid docs",
        )

        url = reverse("get_kyc_status")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["kyc_status"], "rejected")
        kyc_data = data["kyc_data"]
        self.assertEqual(kyc_data["company_name"], "ACME Corp")
        self.assertEqual(kyc_data["rccm_number"], "RCCM123")


class DashboardViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_dashboard_redirects_to_landing_when_kyc_not_submitted(self):
        url = reverse("dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("landing_page"))

    def test_dashboard_allows_access_when_kyc_approved_and_sets_has_billing(self):
        PersonalKYC.objects.create(
            user=self.user,
            status=PersonalKYC.Status.APPROVED,
        )
        url = reverse("dashboard")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertEqual(ctx["kyc_status"], "approved")
        # has_billing is True even without orders when KYC is approved
        self.assertTrue(ctx["has_billing"])
        self.assertFalse(ctx["has_orders"])
        self.assertFalse(ctx["has_subscriptions"])
        self.assertFalse(ctx["has_payments"])


class SubmitPersonalKYCTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def _base_payload(self):
        return {
            "full_name": "Jane Customer",
            "date_of_birth": "1990-01-01",
            "nationality": "Congolese",
            "id_document_type": "passport",
            "id_number": "DOC999",
            "id_issue_date": "2010-01-01",
            "id_expiry_date": "2030-01-01",
            "address": "123 Test Street",
        }

    def test_submit_personal_kyc_missing_full_name_returns_422(self):
        url = reverse("submit_personal_kyc")
        payload = self._base_payload()
        payload["full_name"] = ""
        payload["file"] = SimpleUploadedFile(
            "id.pdf", b"dummy-id", content_type="application/pdf"
        )
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data.get("field"), "full_name")

    def test_submit_personal_kyc_happy_path_creates_kyc(self):
        url = reverse("submit_personal_kyc")
        payload = self._base_payload()
        payload["file"] = SimpleUploadedFile(
            "id.pdf", b"dummy-id", content_type="application/pdf"
        )
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))
        kyc = PersonalKYC.objects.get(user=self.user)
        self.assertEqual(kyc.full_name, "Jane Customer")
        self.assertEqual(kyc.document_number, "DOC999")

    def test_submit_personal_kyc_duplicate_document_number_returns_409(self):
        # Existing KYC with same document_number for another user
        other_user = UserFactory()
        PersonalKYC.objects.create(
            user=other_user,
            document_number="DUPDOC",
        )
        url = reverse("submit_personal_kyc")
        payload = self._base_payload()
        payload["id_number"] = "DUPDOC"
        payload["file"] = SimpleUploadedFile(
            "id.pdf", b"dummy-id", content_type="application/pdf"
        )
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertEqual(data.get("field"), "id_number")


class BillingViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_billing_page_renders_for_customer(self):
        # Even without KYC, the billing landing page should render for a logged-in customer
        url = reverse("billing_page")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        # Basic KYC-related key should be present
        self.assertIn("kyc_status", ctx)


class BillingHistoryViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_billing_history_empty_for_new_user(self):
        url = reverse("billing_history")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertTrue(data.get("success"))

        summary = data.get("summary", {})
        # New customer, no orders or payments yet -> all zeroed summary fields
        self.assertEqual(summary.get("unpaid_total_usd"), 0.0)
        self.assertEqual(summary.get("current_balance_usd"), 0.0)
        self.assertEqual(summary.get("account_credit_usd"), 0.0)
        self.assertEqual(summary.get("wallet_balance_usd"), 0.0)
        self.assertEqual(summary.get("paid_this_month_usd"), 0.0)
        # History should be an empty list with a single empty page
        history = data.get("history", [])
        self.assertEqual(history, [])
        self.assertEqual(data.get("page"), 1)
        self.assertEqual(data.get("total_pages"), 1)


class SettingsViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_settings_creates_prefs_and_populates_profile_and_panels(self):
        # No prefs yet; view should create them
        url = reverse("settings")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context

        # UserPreferences should now exist
        self.assertTrue(UserPreferences.objects.filter(user=self.user).exists())

        profile = ctx["profile"]
        self.assertEqual(profile["email"], self.user.email.lower())
        self.assertEqual(profile["phone"], self.user.phone or "")

        # KYC panel keys present (status may be "not_submitted")
        self.assertIn("kyc_status", ctx)
        self.assertIn("billing", ctx)
        # Optional subscription preview key present
        self.assertIn("active_subscription", ctx)


class ThinPageViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_orders_page_renders(self):
        resp = self.client.get(reverse("orders_page"))
        self.assertEqual(resp.status_code, 200)

    def test_billing_approval_details_renders(self):
        resp = self.client.get(reverse("billing_approval_details", args=[123]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.context.get("billing_id"), 123)

    def test_support_page_renders(self):
        resp = self.client.get(reverse("support_page"))
        self.assertEqual(resp.status_code, 200)


class FeedbackViewTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def test_feedback_view_get_without_existing_feedback(self):
        order = OrderFactory(user=self.user)
        job = InstallationActivityFactory(order=order)

        url = reverse("client_feedback_detail", args=[job.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        ctx = resp.context
        self.assertEqual(ctx["installation"].pk, job.pk)
        self.assertIsNone(ctx["feedback_obj"])
        self.assertIsNone(ctx["feedback"])
        self.assertTrue(ctx["can_edit"])
        self.assertEqual(list(ctx["rating_options"]), list(range(1, 6)))

    def test_feedback_view_post_creates_feedback_and_redirects(self):
        order = OrderFactory(user=self.user)
        job = InstallationActivityFactory(order=order)

        url = reverse("client_feedback_detail", args=[job.pk])
        resp = self.client.post(
            url,
            {
                "rating": "5",
                "comment": "Great installation!",
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, url)
        # Feedback should now exist for this installation
        job.refresh_from_db()
        self.assertIsNotNone(getattr(job, "feedback", None))
        self.assertEqual(job.feedback.rating, 5)
        self.assertEqual(job.feedback.customer, self.user)


class SubmitBusinessKYCTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(self.user)

    def _base_payload(self):
        return {
            "representative_name": "Rep Name",
            "company_name": "ACME Corp",
            "address": "Biz Street",
            "established_date": "2020-01-01",
            "business_sector": "trade",
            "legal_status": "sarl",
            "rccm_number": "RCCM123",
            "nif": "NIF123",
            "id_nat": "IDNAT123",
        }

    def test_submit_business_kyc_missing_representative_name_returns_422(self):
        url = reverse("submit_business_kyc")
        payload = self._base_payload()
        payload["representative_name"] = ""
        payload["representative_file"] = SimpleUploadedFile(
            "id.pdf", b"rep-id", content_type="application/pdf"
        )
        payload["company_document_files"] = [
            SimpleUploadedFile(
                "doc.pdf", b"company-doc", content_type="application/pdf"
            )
        ]
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, 422)
        data = resp.json()
        self.assertEqual(data.get("field"), "representative_name")

    def test_submit_business_kyc_happy_path_creates_kyc_and_documents(self):
        url = reverse("submit_business_kyc")
        payload = self._base_payload()
        payload["representative_file"] = SimpleUploadedFile(
            "id.pdf", b"rep-id", content_type="application/pdf"
        )
        files = {
            "company_document_files": [
                SimpleUploadedFile(
                    "rccm_doc.pdf", b"company-doc-1", content_type="application/pdf"
                ),
                SimpleUploadedFile(
                    "nif_doc.pdf", b"company-doc-2", content_type="application/pdf"
                ),
            ]
        }
        resp = self.client.post(url, data=payload | files)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data.get("success"))

        kyc = CompanyKYC.objects.get(user=self.user)
        self.assertEqual(kyc.company_name, "ACME Corp")
        self.assertEqual(kyc.rccm, "RCCM123")
        # Two CompanyDocument records should be created
        self.assertEqual(kyc.documents.count(), 2)

    def test_submit_business_kyc_duplicate_rccm_returns_409(self):
        other_user = UserFactory()
        CompanyKYC.objects.create(
            user=other_user,
            company_name="Other Co",
            rccm="DUPRCCM",
        )
        url = reverse("submit_business_kyc")
        payload = self._base_payload()
        payload["rccm_number"] = "DUPRCCM"
        payload["representative_file"] = SimpleUploadedFile(
            "id.pdf", b"rep-id", content_type="application/pdf"
        )
        payload["company_document_files"] = [
            SimpleUploadedFile(
                "doc.pdf", b"company-doc", content_type="application/pdf"
            )
        ]
        resp = self.client.post(url, data=payload)
        self.assertEqual(resp.status_code, 409)
        data = resp.json()
        self.assertEqual(data.get("field"), "rccm_number")


class ClientHelpersTests(TestCase):
    def test_get_user_kyc_prefers_company_then_personal_and_not_submitted(self):
        # User with no KYC
        user_no_kyc = UserFactory()
        from client_app.client_helpers import _get_user_kyc

        kyc, status, reason, details = _get_user_kyc(user_no_kyc)
        self.assertIsNone(kyc)
        self.assertEqual(status, "not_submitted")
        self.assertIsNone(reason)
        self.assertIsNone(details)

        # Personal KYC only
        user_personal = UserFactory()
        pkyc = PersonalKYCFactory(user=user_personal)
        pkyc.status = PersonalKYC.Status.REJECTED
        pkyc.rejection_reason = "document_expired"
        pkyc.remarks = "Expired ID"
        pkyc.save()

        kyc_p, status_p, reason_p, details_p = _get_user_kyc(user_personal)
        self.assertEqual(kyc_p, user_personal.personnal_kyc)
        self.assertEqual(status_p, PersonalKYC.Status.REJECTED)
        self.assertEqual(reason_p, "document_expired")
        self.assertEqual(details_p, "Expired ID")

        # Company KYC present: should be preferred over personal
        user_company = UserFactory()
        PersonalKYCFactory(user=user_company)
        ckyc = CompanyKYCFactory(user=user_company)
        ckyc.status = CompanyKYC.Status.APPROVED
        ckyc.rejection_reason = None
        ckyc.remarks = ""
        ckyc.save()

        kyc_c, status_c, reason_c, details_c = _get_user_kyc(user_company)
        self.assertEqual(kyc_c, user_company.company_kyc)
        self.assertEqual(status_c, CompanyKYC.Status.APPROVED)
        self.assertIsNone(reason_c)
        self.assertEqual(details_c, "")

    def test_get_billing_overview_returns_balances_and_last_entries(self):
        user = UserFactory()
        from client_app.client_helpers import (
            _get_billing_overview,
            get_or_create_account,
        )

        acct = get_or_create_account(user)

        # Seed a couple of entries
        AccountEntry.objects.create(
            account=acct,
            entry_type="invoice",
            amount_usd=Decimal("100.00"),
            description="Initial invoice",
        )
        AccountEntry.objects.create(
            account=acct,
            entry_type="payment",
            amount_usd=Decimal("-50.00"),
            description="Payment",
        )

        overview = _get_billing_overview(user)
        # With invoice 100 and payment -50, net balance is 50 (due), no credit
        self.assertEqual(overview["balance_usd"], "50.00")
        self.assertEqual(overview["due_usd"], "50.00")
        self.assertEqual(overview["credit_usd"], "0.00")
        self.assertEqual(len(overview["last_entries"]), 2)
