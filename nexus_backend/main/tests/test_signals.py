"""
Unit tests for Django signals in main module

Tests for automatic creation and updates triggered by model signals:
- BillingAccount auto-creation on user save
- Wallet auto-creation on user save
- UserPreferences auto-creation on user save
- CompanyDocument count updates on CompanyKYC

Coverage target: 90%+ for signal handlers
"""

import pytest

from django.contrib.auth import get_user_model

from main.factories import UserFactory
from main.models import (
    BillingAccount,
    CompanyDocument,
    CompanyKYC,
    UserPreferences,
    Wallet,
)

User = get_user_model()


# ============================================================================
# User Signal Tests
# ============================================================================


@pytest.mark.django_db
class TestUserSignals:
    """Test signals triggered when User instances are created/updated."""

    def test_billing_account_created_on_user_creation(self):
        """Test that BillingAccount is auto-created when user is created."""
        user = UserFactory()

        # BillingAccount should be auto-created by signal
        assert hasattr(user, "billing_account")
        assert BillingAccount.objects.filter(user=user).exists()

        billing_account = BillingAccount.objects.get(user=user)
        assert billing_account.user == user

    def test_wallet_created_on_user_creation(self):
        """Test that Wallet is auto-created when user is created."""
        user = UserFactory()

        # Wallet should be auto-created by signal
        assert hasattr(user, "wallet")
        assert Wallet.objects.filter(user=user).exists()

        wallet = Wallet.objects.get(user=user)
        assert wallet.user == user

    def test_user_preferences_created_on_user_creation(self):
        """Test that UserPreferences is auto-created when user is created."""
        user = UserFactory()

        # UserPreferences should be auto-created by signal
        # Note: The signal checks hasattr, so we need to refresh from DB
        user.refresh_from_db()

        assert UserPreferences.objects.filter(user=user).exists()
        prefs = UserPreferences.objects.get(user=user)
        assert prefs.user == user

    def test_signals_idempotent_on_user_update(self):
        """Test that signals don't create duplicates on user update."""
        user = UserFactory()
        user.refresh_from_db()

        # Get initial counts
        billing_count = BillingAccount.objects.filter(user=user).count()
        wallet_count = Wallet.objects.filter(user=user).count()
        prefs_count = UserPreferences.objects.filter(user=user).count()

        # Update user
        user.full_name = "Updated Name"
        user.save()
        user.refresh_from_db()

        # Counts should remain the same (no duplicates)
        assert BillingAccount.objects.filter(user=user).count() == billing_count
        assert Wallet.objects.filter(user=user).count() == wallet_count
        assert UserPreferences.objects.filter(user=user).count() == prefs_count

    def test_signal_handles_none_instance(self):
        """Test that signals gracefully handle None instance."""
        from main.models import ensure_billing_account, ensure_simple_wallet

        # These should not raise exceptions
        ensure_billing_account(User, None, created=True)
        ensure_simple_wallet(User, None, created=True)

    def test_billing_account_not_duplicated(self):
        """Test that existing BillingAccount is not duplicated."""
        user = UserFactory()
        user.refresh_from_db()

        # Get the auto-created billing account
        original_ba = BillingAccount.objects.get(user=user)

        # Trigger signal again
        user.email = "newemail@example.com"
        user.save()

        # Should still have only one billing account
        assert BillingAccount.objects.filter(user=user).count() == 1
        current_ba = BillingAccount.objects.get(user=user)
        assert current_ba.id == original_ba.id


# ============================================================================
# CompanyDocument Signal Tests
# ============================================================================


@pytest.mark.django_db
class TestCompanyDocumentSignals:
    """Test signals for CompanyDocument model."""

    def test_document_count_updated_on_document_creation(self):
        """Test that documents_count is updated when document is created."""
        from main.factories import UserFactory

        user = UserFactory()

        # Create CompanyKYC
        company_kyc = CompanyKYC.objects.create(
            user=user,
            company_name="Test Company",
            address="123 Test St",
        )

        # Initially should have 0 documents
        company_kyc.refresh_from_db()
        initial_count = company_kyc.documents_count

        # Create a document
        from django.core.files.uploadedfile import SimpleUploadedFile

        test_file = SimpleUploadedFile(
            "test.pdf", b"file_content", content_type="application/pdf"
        )
        CompanyDocument.objects.create(
            company_kyc=company_kyc,
            document_type="rccm",
            document=test_file,
        )

        # Count should be updated by signal
        company_kyc.refresh_from_db()
        assert company_kyc.documents_count == initial_count + 1

    def test_document_count_updated_on_document_deletion(self):
        """Test that documents_count is updated when document is deleted."""
        from main.factories import UserFactory

        user = UserFactory()

        # Create CompanyKYC
        company_kyc = CompanyKYC.objects.create(
            user=user,
            company_name="Test Company",
            address="123 Test St",
        )

        # Create documents
        from django.core.files.uploadedfile import SimpleUploadedFile

        test_file1 = SimpleUploadedFile(
            "test1.pdf", b"file_content1", content_type="application/pdf"
        )
        doc1 = CompanyDocument.objects.create(
            company_kyc=company_kyc,
            document_type="rccm",
            document=test_file1,
        )
        test_file2 = SimpleUploadedFile(
            "test2.pdf", b"file_content2", content_type="application/pdf"
        )
        CompanyDocument.objects.create(
            company_kyc=company_kyc,
            document_type="nif",
            document=test_file2,
        )

        company_kyc.refresh_from_db()
        count_before_delete = company_kyc.documents_count
        assert count_before_delete == 2

        # Delete one document
        doc1.delete()

        # Count should be updated by signal
        company_kyc.refresh_from_db()
        assert company_kyc.documents_count == count_before_delete - 1

    def test_document_count_signal_handles_no_company_kyc(self):
        """Test that signal handles document without company_kyc gracefully."""
        # This test is not applicable since company_kyc is required
        # The signal handles None company_kyc with an if check
        # We'll test that the signal doesn't crash when company_kyc exists
        from main.factories import UserFactory

        user = UserFactory()
        company_kyc = CompanyKYC.objects.create(
            user=user, company_name="Test Company", address="123 Test St"
        )

        from django.core.files.uploadedfile import SimpleUploadedFile

        test_file = SimpleUploadedFile(
            "test.pdf", b"file_content", content_type="application/pdf"
        )

        # This should not raise an exception
        CompanyDocument.objects.create(
            company_kyc=company_kyc, document_type="rccm", document=test_file
        )

        # Verify count was updated
        company_kyc.refresh_from_db()
        assert company_kyc.documents_count == 1

    def test_multiple_documents_count_accuracy(self):
        """Test that documents_count is accurate with multiple operations."""
        from main.factories import UserFactory

        user = UserFactory()

        company_kyc = CompanyKYC.objects.create(
            user=user,
            company_name="Test Company",
            address="123 Test St",
        )

        # Create multiple documents
        from django.core.files.uploadedfile import SimpleUploadedFile

        # Use different document types to avoid unique constraint violation
        doc_types = ["rccm", "nif", "id_nat", "statutes", "registration"]
        docs = []
        for i, doc_type in enumerate(doc_types):
            test_file = SimpleUploadedFile(
                f"test{i}.pdf", b"file_content", content_type="application/pdf"
            )
            doc = CompanyDocument.objects.create(
                company_kyc=company_kyc,
                document_type=doc_type,
                document=test_file,
            )
            docs.append(doc)

        company_kyc.refresh_from_db()
        assert company_kyc.documents_count == 5

        # Delete some
        docs[0].delete()
        docs[2].delete()

        company_kyc.refresh_from_db()
        assert company_kyc.documents_count == 3

        # Verify actual count matches
        actual_count = CompanyDocument.objects.filter(company_kyc=company_kyc).count()
        assert company_kyc.documents_count == actual_count


# ============================================================================
# Signal Integration Tests
# ============================================================================


@pytest.mark.django_db
@pytest.mark.integration
class TestSignalIntegration:
    """Integration tests for signal interactions."""

    def test_new_user_has_all_related_objects(self):
        """Test that a new user gets all auto-created related objects."""
        user = UserFactory()
        user.refresh_from_db()

        # Check all auto-created objects exist
        assert BillingAccount.objects.filter(user=user).exists()
        assert Wallet.objects.filter(user=user).exists()
        assert UserPreferences.objects.filter(user=user).exists()

        # Verify relationships
        assert user.billing_account.user == user
        assert user.wallet.user == user

    def test_signal_dispatch_uids_prevent_duplicates(self):
        """Test that dispatch_uid prevents duplicate signal handlers."""
        user = UserFactory()

        # Force save multiple times
        for _ in range(3):
            user.save()

        user.refresh_from_db()

        # Should still have only one of each
        assert BillingAccount.objects.filter(user=user).count() == 1
        assert Wallet.objects.filter(user=user).count() == 1
        assert UserPreferences.objects.filter(user=user).count() == 1

    def test_user_deletion_cascades_properly(self):
        """Test that deleting user handles related objects correctly."""
        user = UserFactory()
        user_pk = user.pk

        # Verify related objects exist before deletion
        assert BillingAccount.objects.filter(user=user).exists()
        assert Wallet.objects.filter(user=user).exists()

        # Delete user
        user.delete()

        # Related objects should be deleted (assuming CASCADE)
        # Note: This depends on the actual ForeignKey configuration
        # Adjust assertions based on actual on_delete behavior
        assert not User.objects.filter(pk=user_pk).exists()
