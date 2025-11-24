import json

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.files.base import ContentFile
from django.test import Client, TestCase
from django.urls import reverse
from django.shortcuts import resolve_url

from main.factories import UserFactory, PersonalKYCFactory
from main.models import (
    CompanyKYC,
    CompanyDocument,
    PersonalKYC,
    UserPreferences,
    Wallet,
)
from user.auth import role_redirect, normalized_roles
from user.erase_account_data import (
    _safe_delete_field_file,
    _anonymized_email,
    erase_user_personal_data,
)


User = get_user_model()


class RequireFullLoginTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_unauthenticated_request_redirects_and_stashes_next(self):
        path = reverse("dashboard") + "?foo=bar"
        resp = self.client.get(path)
        # Redirect to login_page
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(resp.url.endswith(reverse("login_page")))
        # post_login_next stored in session
        self.assertEqual(self.client.session.get("post_login_next"), path)

    def test_authenticated_request_passes_through(self):
        user = UserFactory(is_staff=False, roles=["customer"])
        self.client.force_login(user)
        resp = self.client.get(reverse("dashboard"))
        # For authenticated customers without approved KYC, dashboard redirects to landing_page,
        # which demonstrates that require_full_login lets them through (no redirect to login_page).
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("landing_page"))


class NormalizedRolesTests(TestCase):
    def test_normalized_roles_handles_list_and_string_and_json(self):
        user = UserFactory()
        user.roles = ["Admin", " sales ", "CUSTOMER"]
        roles = normalized_roles(user)
        self.assertEqual(sorted(roles), ["admin", "customer", "sales"])

        # Comma-separated string
        user.roles = "admin, sales , customer"
        roles_str = normalized_roles(user)
        self.assertEqual(sorted(roles_str), ["admin", "customer", "sales"])

        # JSON string
        user.roles = json.dumps(["Admin", "support"])
        roles_json = normalized_roles(user)
        self.assertEqual(sorted(roles_json), ["admin", "support"])


class RoleRedirectTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_anonymous_user_redirects_to_default(self):
        anon = AnonymousUser()
        resp = role_redirect(anon, default_urlname="login_page")
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, resolve_url("login_page"))

    def test_customer_only_with_approved_kyc_goes_to_dashboard(self):
        user = UserFactory(is_staff=False, roles=["customer"])
        PersonalKYCFactory(user=user, status=PersonalKYC.Status.APPROVED)
        resp = role_redirect(user)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, resolve_url("dashboard"))

    def test_customer_only_without_approved_kyc_goes_to_landing(self):
        user = UserFactory(is_staff=False, roles=["customer"])
        # No KYC or non-approved KYC -> landing_page
        resp = role_redirect(user)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, resolve_url("landing_page"))

    def test_multi_role_prefers_priority_non_customer_role(self):
        user = UserFactory(is_staff=True)
        user.roles = ["customer", "sales"]
        user.save()
        resp = role_redirect(user)
        self.assertEqual(resp.status_code, 302)
        # sales role should route to sales_dashboard
        self.assertEqual(resp.url, resolve_url("sales_dashboard"))

    def test_unknown_role_falls_back_to_default_dashboard(self):
        user = UserFactory()
        user.roles = ["unknown_role"]
        user.save()
        resp = role_redirect(user)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, resolve_url("dashboard"))


class EraseAccountDataTests(TestCase):
    def test_safe_delete_field_file_handles_delete_and_errors(self):
        class DummyField:
            def __init__(self):
                self.deleted = False

            def delete(self, save=False):
                self.deleted = True

        f = DummyField()
        _safe_delete_field_file(f)
        self.assertTrue(f.deleted)

        class ErrorField:
            def delete(self, save=False):
                raise ValueError("boom")

        # Should not raise
        _safe_delete_field_file(ErrorField())

    def test_anonymized_email_contains_user_id_and_is_unique(self):
        email1 = _anonymized_email(42)
        email2 = _anonymized_email(42)
        self.assertIn("u42-", email1)
        self.assertIn("@example.invalid", email1)
        self.assertNotEqual(email1, email2)

    def test_erase_user_personal_data_scrubs_pii_and_related_records(self):
        user = UserFactory()

        # Preferences with avatar (UserPreferences is auto-created via signals)
        prefs = UserPreferences.objects.get(user=user)
        prefs.avatar = ContentFile(b"avatar", name="avatar.png")
        prefs.save()

        # Personal KYC
        pkyc = PersonalKYCFactory(user=user)
        pkyc.document_file = ContentFile(b"doc", name="id.pdf")
        pkyc.save()

        # Company KYC with docs
        ckyc = CompanyKYC.objects.create(
            user=user, company_name="Test Co", rccm="RCCM123"
        )
        ckyc.representative_id_file = ContentFile(b"rep", name="rep.pdf")
        ckyc.company_documents = ContentFile(b"legacy", name="legacy.pdf")
        ckyc.save()
        CompanyDocument.objects.create(
            company_kyc=ckyc,
            document=ContentFile(b"doc", name="comp1.pdf"),
            document_name="Comp Doc 1",
        )

        # Wallet (auto-created via signals)
        wallet = Wallet.objects.get(user=user)
        wallet.balance = "10.00"
        wallet.is_active = True
        wallet.save(update_fields=["balance", "is_active"])

        # Run erasure
        erase_user_personal_data(user.id)

        user.refresh_from_db()
        self.assertEqual(user.full_name, "Deleted Account")
        self.assertEqual(user.first_name, "")
        self.assertEqual(user.last_name, "")
        self.assertIsNone(user.phone)
        self.assertFalse(user.is_verified)
        self.assertEqual(user.roles, [])
        self.assertTrue(user.email.endswith("@example.invalid"))
        self.assertTrue(user.email.startswith(f"deleted+u{user.id}-"))
        self.assertEqual(user.username, f"deleted_{user.id}")

        # KYC rows deleted
        self.assertFalse(PersonalKYC.objects.filter(user=user).exists())
        self.assertFalse(CompanyKYC.objects.filter(user=user).exists())
        self.assertFalse(
            CompanyDocument.objects.filter(company_kyc__user=user).exists()
        )

        # Wallet disabled but preserved
        wallet.refresh_from_db()
        self.assertFalse(wallet.is_active)
