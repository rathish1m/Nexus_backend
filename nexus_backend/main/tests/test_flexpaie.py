"""
Tests for FlexPay payment integration.

This module tests the FlexPay payment processing functions including:
- check_flexpay_transactions: Polling FlexPay API for payment status
- probe_payment_status: Browser-triggered payment status checks
- mobile_probe: Mobile money payment verification
- cancel_order_now: Order cancellation

All tests use mocks to avoid real API calls.
"""

import json
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock, patch

import pytest

from django.contrib.auth import get_user_model
from django.test import RequestFactory
from django.utils import timezone

from main.factories import OrderFactory, UserFactory
from main.flexpaie import (
    _parse_flexpay_datetime,
    cancel_order_now,
    check_flexpay_transactions,
    mobile_probe,
    probe_payment_status,
)
from main.models import PaymentAttempt

User = get_user_model()


class TestParseFlexpayDatetime:
    """Tests for FlexPay datetime parsing utility."""

    def test_parse_valid_iso_format(self):
        """Test parsing valid ISO datetime string."""
        result = _parse_flexpay_datetime("2024-10-20T13:45:22Z")
        assert isinstance(result, datetime)
        assert result.year == 2024
        assert result.month == 10
        assert result.day == 20

    def test_parse_invalid_datetime_returns_now(self):
        """Test that invalid datetime returns current time."""
        result = _parse_flexpay_datetime("invalid-date")
        assert isinstance(result, datetime)
        # Should be close to now (within 1 second)
        assert abs((timezone.now() - result).total_seconds()) < 1

    def test_parse_none_returns_now(self):
        """Test that None returns current time."""
        result = _parse_flexpay_datetime(None)
        assert isinstance(result, datetime)


@pytest.mark.django_db
class TestCheckFlexpayTransactions:
    """Tests for check_flexpay_transactions function."""

    def test_no_pending_attempts_returns_empty_result(self):
        """Test that no pending attempts returns empty result."""
        result = check_flexpay_transactions()

        assert result["checked"] == 0
        assert result["attempts_updated"] == 0
        assert result["orders_updated"] == 0
        assert result["attempts"] == []

    @patch("main.flexpaie.requests.get")
    def test_successful_payment_updates_order_and_attempt(self, mock_get):
        """Test successful payment updates both order and payment attempt."""
        # Create order and payment attempt
        user = UserFactory()
        order = OrderFactory(user=user, payment_status="pending", status="pending")

        attempt = PaymentAttempt.objects.create(
            order=order,
            order_number="TEST123",
            reference=order.order_reference,  # Match order reference
            amount=Decimal("100.00"),
            currency="USD",
            status="pending",
        )

        # Mock successful FlexPay response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "0",
            "transaction": {
                "status": "0",
                "reference": order.order_reference,  # Use order reference
                "amount": "100.00",
                "amountCustomer": "105.00",
                "currency": "USD",
                "createdAt": "2024-10-20T13:45:22Z",
            },
        }
        mock_get.return_value = mock_response

        # Execute
        result = check_flexpay_transactions(order_number="TEST123")

        # Verify results
        assert result["checked"] == 1
        assert result["attempts_updated"] == 1
        assert result["orders_updated"] == 1

        # Verify attempt updated
        attempt.refresh_from_db()
        assert attempt.status == "paid"
        assert attempt.code == "0"
        assert attempt.reference == order.order_reference
        assert attempt.amount == Decimal("100.00")
        assert attempt.amount_customer == Decimal("105.00")

        # Verify order updated
        order.refresh_from_db()
        assert order.payment_status == "paid"
        assert order.status == "fulfilled"

    @patch("main.flexpaie.requests.get")
    def test_failed_payment_updates_attempt_only(self, mock_get):
        """Test failed payment updates attempt but not order."""
        user = UserFactory()
        order = OrderFactory(user=user, payment_status="pending")

        attempt = PaymentAttempt.objects.create(
            order=order,
            order_number="TEST456",
            reference=order.order_reference,  # Match order reference
            amount=Decimal("50.00"),
            status="pending",
        )

        # Mock failed FlexPay response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "0",
            "transaction": {
                "status": "1",  # Failed status
                "reference": order.order_reference,  # Use order reference
            },
        }
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(order_number="TEST456")

        assert result["attempts_updated"] == 1
        assert result["orders_updated"] == 0

        attempt.refresh_from_db()
        assert attempt.status == "failed"

        order.refresh_from_db()
        assert order.payment_status == "pending"

    @patch("main.flexpaie.requests.get")
    def test_pending_payment_status(self, mock_get):
        """Test pending payment status (status=2)."""
        user = UserFactory()
        order = OrderFactory(user=user)

        attempt = PaymentAttempt.objects.create(
            order=order,
            order_number="TEST789",
            amount=Decimal("75.00"),
            status="pending",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "0",
            "transaction": {
                "status": "2",  # Pending status
                "reference": "FP999",
            },
        }
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(order_number="TEST789")

        attempt.refresh_from_db()
        assert attempt.status == "pending"
        assert result["orders_updated"] == 0

    @patch("main.flexpaie.requests.get")
    def test_http_error_response(self, mock_get):
        """Test handling of HTTP error responses."""
        user = UserFactory()
        order = OrderFactory(user=user)

        PaymentAttempt.objects.create(
            order=order,
            order_number="TEST404",
            amount=Decimal("25.00"),
            status="pending",
        )

        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(order_number="TEST404")

        assert result["checked"] == 1
        assert result["attempts_updated"] == 0
        assert len(result["attempts"]) == 1
        assert result["attempts"][0]["success"] is False
        assert "http_404" in result["attempts"][0]["reason"]

    @patch("main.flexpaie.requests.get")
    def test_timeout_handling(self, mock_get):
        """Test handling of request timeouts."""
        import requests

        user = UserFactory()
        order = OrderFactory(user=user)

        PaymentAttempt.objects.create(
            order=order,
            order_number="TESTTIMEOUT",
            amount=Decimal("30.00"),
            status="pending",
        )

        mock_get.side_effect = requests.Timeout("Connection timeout")

        result = check_flexpay_transactions(order_number="TESTTIMEOUT")

        assert result["checked"] == 0
        assert len(result["attempts"]) == 1
        assert result["attempts"][0]["reason"] == "timeout"

    @patch("main.flexpaie.requests.get")
    def test_no_transaction_yet(self, mock_get):
        """Test response when no transaction exists yet (code=1)."""
        user = UserFactory()
        order = OrderFactory(user=user)

        attempt = PaymentAttempt.objects.create(
            order=order,
            order_number="TESTNONE",
            amount=Decimal("40.00"),
            status="pending",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"code": "1"}
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(order_number="TESTNONE")

        assert result["attempts_updated"] == 0
        assert result["orders_updated"] == 0

        attempt.refresh_from_db()
        assert attempt.status == "pending"

    @patch("main.flexpaie.requests.get")
    def test_invalid_amount_handling(self, mock_get):
        """Test handling of invalid amounts in response."""
        user = UserFactory()
        order = OrderFactory(user=user)

        attempt = PaymentAttempt.objects.create(
            order=order,
            order_number="TESTINVALID",
            amount=Decimal("50.00"),
            status="pending",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "0",
            "transaction": {
                "status": "0",
                "amount": "invalid_amount",
                "amountCustomer": None,
            },
        }
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(order_number="TESTINVALID")

        # Should still update attempt despite invalid amounts
        assert result["attempts_updated"] == 1

        attempt.refresh_from_db()
        # Amount should remain unchanged when invalid
        assert attempt.amount == Decimal("50.00")

    @patch("main.flexpaie.requests.get")
    def test_filter_by_trans_id(self, mock_get):
        """Test filtering by transaction ID."""
        user = UserFactory()
        order = OrderFactory(user=user)

        PaymentAttempt.objects.create(
            order=order,
            order_number="TESTREF",
            reference="FP12345",
            amount=Decimal("60.00"),
            status="pending",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "0",
            "transaction": {"status": "0"},
        }
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(trans_id="FP12345")

        assert result["checked"] == 1

    @patch("main.flexpaie.requests.get")
    def test_filter_by_order_reference(self, mock_get):
        """Test filtering by order reference."""
        user = UserFactory()
        order = OrderFactory(user=user)

        PaymentAttempt.objects.create(
            order=order,
            order_number="TESTORDERREF",
            amount=Decimal("70.00"),
            status="pending",
        )

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "code": "0",
            "transaction": {"status": "0"},
        }
        mock_get.return_value = mock_response

        result = check_flexpay_transactions(order_reference=order.order_reference)

        assert result["checked"] == 1

    def test_skip_attempt_without_order_number(self):
        """Test that attempts without order_number are skipped."""
        user = UserFactory()
        order = OrderFactory(user=user)

        PaymentAttempt.objects.create(
            order=order,
            order_number=None,  # No order number
            amount=Decimal("80.00"),
            status="pending",
        )

        result = check_flexpay_transactions()

        assert result["checked"] == 0


@pytest.mark.django_db
class TestProbePaymentStatus:
    """Tests for probe_payment_status view."""

    def setup_method(self):
        """Set up test request factory and user."""
        self.factory = RequestFactory()
        self.user = UserFactory()

    @patch("main.flexpaie.check_flexpay_transactions")
    def test_successful_probe_with_order_number(self, mock_check):
        """Test successful payment probe with order number."""
        mock_check.return_value = {
            "checked": 1,
            "attempts_updated": 1,
            "orders_updated": 1,
            "attempts": [],
        }

        request = self.factory.post(
            "/probe/",
            data=json.dumps({"order_number": "TEST123"}),
            content_type="application/json",
        )
        request.user = self.user

        response = probe_payment_status(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["checked"] == 1

    @patch("main.flexpaie.check_flexpay_transactions")
    def test_probe_with_trans_id(self, mock_check):
        """Test probe with transaction ID."""
        mock_check.return_value = {
            "checked": 1,
            "attempts_updated": 0,
            "orders_updated": 0,
            "attempts": [],
        }

        request = self.factory.post(
            "/probe/",
            data=json.dumps({"trans_id": "FP123"}),
            content_type="application/json",
        )
        request.user = self.user

        response = probe_payment_status(request)

        assert response.status_code == 200
        mock_check.assert_called_once_with(
            order_number=None, trans_id="FP123", order_reference=None
        )

    def test_probe_handles_exceptions(self):
        """Test that probe handles exceptions gracefully."""
        request = self.factory.post(
            "/probe/",
            data="invalid json",
            content_type="application/json",
        )
        request.user = self.user

        response = probe_payment_status(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert data["success"] is False
        assert "message" in data


@pytest.mark.django_db
class TestMobileProbe:
    """Tests for mobile_probe view."""

    def setup_method(self):
        """Set up test request factory and user."""
        self.factory = RequestFactory()
        self.user = UserFactory()

    @patch("main.flexpaie.cancel_expired_orders.delay")
    @patch("main.flexpaie.check_flexpay_transactions")
    def test_successful_payment_probe(self, mock_check, mock_cancel):
        """Test successful mobile payment probe."""
        mock_check.return_value = {
            "orders_updated": 1,
            "attempts": [{"success": True, "final_status": "paid"}],
        }

        request = self.factory.post(
            "/mobile-probe/",
            data=json.dumps({"order_number": "MOB123"}),
            content_type="application/json",
        )
        request.user = self.user

        response = mobile_probe(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True
        assert data["status"] == "paid"
        assert data["orders_updated"] == 1

    @patch("main.flexpaie.cancel_expired_orders.delay")
    @patch("main.flexpaie.check_flexpay_transactions")
    def test_failed_payment_triggers_cancellation(self, mock_check, mock_cancel):
        """Test that failed payment triggers order cancellation."""
        mock_check.return_value = {
            "orders_updated": 0,
            "attempts": [{"success": False, "final_status": "failed"}],
        }

        request = self.factory.post(
            "/mobile-probe/",
            data=json.dumps({"order_number": "MOB456"}),
            content_type="application/json",
        )
        request.user = self.user

        response = mobile_probe(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is False
        assert data["status"] == "failed"

        # Should trigger cancellation
        mock_cancel.assert_called_once()

    @patch("main.flexpaie.check_flexpay_transactions")
    def test_pending_payment_status(self, mock_check):
        """Test pending payment status."""
        mock_check.return_value = {
            "orders_updated": 0,
            "attempts": [{"success": True, "final_status": "pending"}],
        }

        request = self.factory.post(
            "/mobile-probe/",
            data=json.dumps({"order_number": "MOB789"}),
            content_type="application/json",
        )
        request.user = self.user

        response = mobile_probe(request)

        data = json.loads(response.content)
        assert data["status"] == "pending"
        assert data["success"] is False

    def test_exception_handling_returns_pending(self):
        """Test that exceptions return pending status."""
        request = self.factory.post(
            "/mobile-probe/",
            data="invalid json",
            content_type="application/json",
        )
        request.user = self.user

        response = mobile_probe(request)

        assert response.status_code == 200  # Still 200 on error
        data = json.loads(response.content)
        assert data["success"] is False
        assert data["status"] == "pending"


@pytest.mark.django_db
class TestCancelOrderNow:
    """Tests for cancel_order_now view."""

    def setup_method(self):
        """Set up test request factory and user."""
        self.factory = RequestFactory()
        self.user = UserFactory()

    def test_cancel_by_order_reference(self):
        """Test canceling order by order reference."""
        order = OrderFactory(user=self.user, status="pending")

        request = self.factory.post(
            "/cancel/",
            data=json.dumps({"order_reference": order.order_reference}),
            content_type="application/json",
        )
        request.user = self.user

        response = cancel_order_now(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True

    def test_cancel_by_order_number(self):
        """Test canceling order by order number via payment attempt."""
        order = OrderFactory(user=self.user, status="pending")

        PaymentAttempt.objects.create(
            order=order,
            order_number="CANCEL123",
            amount=Decimal("100.00"),
        )

        request = self.factory.post(
            "/cancel/",
            data=json.dumps({"order_number": "CANCEL123"}),
            content_type="application/json",
        )
        request.user = self.user

        response = cancel_order_now(request)

        assert response.status_code == 200
        data = json.loads(response.content)
        assert data["success"] is True

    def test_cancel_nonexistent_order(self):
        """Test canceling non-existent order returns 404."""
        request = self.factory.post(
            "/cancel/",
            data=json.dumps({"order_reference": "NONEXISTENT"}),
            content_type="application/json",
        )
        request.user = self.user

        response = cancel_order_now(request)

        assert response.status_code == 404
        data = json.loads(response.content)
        assert data["success"] is False
        assert "not found" in data["message"].lower()

    def test_cancel_handles_exceptions(self):
        """Test that cancel handles exceptions gracefully."""
        request = self.factory.post(
            "/cancel/",
            data="invalid json",
            content_type="application/json",
        )
        request.user = self.user

        response = cancel_order_now(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert data["success"] is False
