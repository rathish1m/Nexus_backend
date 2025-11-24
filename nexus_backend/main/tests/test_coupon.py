"""
Tests for main.utilities.coupon module.

Coverage target: 80%+ for coupon.py
Tests: ~24 covering validation, discounts, edge cases, error handling
"""

import json
from decimal import Decimal

import pytest

from django.test import RequestFactory
from django.utils import timezone

from main.models import Coupon
from main.utilities.coupon import validate_coupon

pytestmark = pytest.mark.django_db


class TestCouponValidation:
    """Tests for coupon validation logic."""

    def setup_method(self):
        """Setup common test fixtures."""
        self.factory = RequestFactory()
        self.now = timezone.now()

    def _make_request(self, payload):
        """Helper to create a POST request with CSRF bypass."""
        request = self.factory.post(
            "/validate-coupon/",
            data=json.dumps(payload),
            content_type="application/json",
        )
        # Bypass CSRF check for unit tests
        request._dont_enforce_csrf_checks = True
        return request

    def test_validate_coupon_missing_code(self):
        """Test validation with missing coupon code."""
        payload = {"cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "code" in data["message"].lower()

    def test_validate_coupon_missing_cart(self):
        """Test validation with missing cart data."""
        payload = {"code": "SUMMER20"}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "cart" in data["message"].lower()

    def test_validate_coupon_empty_cart(self):
        """Test validation with empty cart."""
        payload = {"code": "SUMMER20", "cart": []}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "empty" in data["message"].lower()

    def test_validate_coupon_invalid_json(self):
        """Test validation with invalid JSON."""
        request = self.factory.post(
            "/validate-coupon/",
            data="invalid json",
            content_type="application/json",
        )
        request._dont_enforce_csrf_checks = True

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "json" in data["message"].lower() or "invalid" in data["message"].lower()

    def test_validate_coupon_not_found(self):
        """Test validation with non-existent coupon code."""
        payload = {"code": "NONEXISTENT", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 404
        assert data["success"] is False
        assert "not found" in data["message"].lower()

    def test_validate_coupon_inactive(self):
        """Test validation with inactive coupon."""
        Coupon.objects.create(
            code="INACTIVE",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=False,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "INACTIVE", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "not active" in data["message"].lower()

    def test_validate_coupon_expired(self):
        """Test validation with expired coupon."""
        Coupon.objects.create(
            code="EXPIRED",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now - timezone.timedelta(days=14),
            valid_to=self.now - timezone.timedelta(days=7),
        )

        payload = {"code": "EXPIRED", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "expired" in data["message"].lower()

    def test_validate_coupon_not_yet_valid(self):
        """Test validation with coupon not yet valid."""
        Coupon.objects.create(
            code="FUTURE",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now + timezone.timedelta(days=7),
            valid_to=self.now + timezone.timedelta(days=14),
        )

        payload = {"code": "FUTURE", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "not yet valid" in data["message"].lower()

    def test_validate_coupon_usage_exceeded(self):
        """Test validation with usage limit exceeded."""
        from main.factories import UserFactory
        from main.models import CouponRedemption, DiscountType

        coupon = Coupon.objects.create(
            code="LIMITED",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
            max_redemptions=10,
        )

        # Simulate prior redemptions hitting the limit
        user = UserFactory()
        for _ in range(10):
            CouponRedemption.objects.create(
                coupon=coupon,
                user=user,
                discount_type=DiscountType.PERCENT,
                value=Decimal("10.00"),
                discounted_amount=Decimal("1.00"),
            )

        payload = {"code": "LIMITED", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "usage limit" in data["message"].lower()

    def test_validate_coupon_below_minimum_total(self):
        """Test validation with cart total below minimum."""
        Coupon.objects.create(
            code="BIGSPENDER",
            discount_type="percent",
            percent_off=Decimal("15.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
            min_cart_total=Decimal("500.00"),
        )

        payload = {"code": "BIGSPENDER", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "minimum cart total" in data["message"].lower()
        assert "500.00" in data["message"]

    def test_validate_coupon_meets_minimum_total(self):
        """Test validation with cart total meeting minimum."""
        Coupon.objects.create(
            code="BIGSPENDER2",
            discount_type="percent",
            percent_off=Decimal("15.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
            min_cart_total=Decimal("500.00"),
        )

        payload = {"code": "BIGSPENDER2", "cart": [{"grand_total": "600.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(90.00)  # 15% of 600
        assert data["new_total"] == pytest.approx(510.00)

    def test_validate_coupon_percent_discount(self):
        """Test successful percent discount validation."""
        Coupon.objects.create(
            code="SUMMER20",
            discount_type="percent",
            percent_off=Decimal("20.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "SUMMER20", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(20.00)  # 20% of 100
        assert data["new_total"] == pytest.approx(80.00)
        assert "20" in data["message"]

    def test_validate_coupon_amount_discount(self):
        """Test successful fixed amount discount validation."""
        Coupon.objects.create(
            code="SAVE50",
            discount_type="amount",
            amount_off=Decimal("50.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "SAVE50", "cart": [{"grand_total": "200.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(50.00)
        assert data["new_total"] == pytest.approx(150.00)
        assert "50.00" in data["message"]

    def test_validate_coupon_discount_exceeds_total(self):
        """Test discount clamped to cart total."""
        Coupon.objects.create(
            code="MEGA100",
            discount_type="amount",
            amount_off=Decimal("100.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "MEGA100", "cart": [{"grand_total": "50.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(50.00)  # Clamped to cart total
        assert data["new_total"] == pytest.approx(0.00)

    def test_validate_coupon_multiple_cart_items(self):
        """Test discount with multiple cart items."""
        Coupon.objects.create(
            code="MULTI10",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {
            "code": "MULTI10",
            "cart": [
                {"grand_total": "100.00"},
                {"grand_total": "150.00"},
                {"grand_total": "50.00"},
            ],
        }
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(30.00)  # 10% of 300
        assert data["new_total"] == pytest.approx(270.00)

    def test_validate_coupon_invalid_percent_value_zero(self):
        """Test validation with zero percent discount."""
        Coupon.objects.create(
            code="ZERO",
            discount_type="percent",
            percent_off=Decimal("0.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "ZERO", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "invalid percent" in data["message"].lower()

    def test_validate_coupon_invalid_percent_value_over_100(self):
        """Test validation with percent discount over 100%."""
        Coupon.objects.create(
            code="OVER100",
            discount_type="percent",
            percent_off=Decimal("150.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "OVER100", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "invalid percent" in data["message"].lower()

    def test_validate_coupon_invalid_amount_value(self):
        """Test validation with negative amount discount."""
        Coupon.objects.create(
            code="NEGATIVE",
            discount_type="amount",
            amount_off=Decimal("-10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "NEGATIVE", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "invalid discount amount" in data["message"].lower()

    def test_validate_coupon_negative_line_total(self):
        """Test validation with negative line total in cart."""
        Coupon.objects.create(
            code="VALID",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "VALID", "cart": [{"grand_total": "-50.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "negative" in data["message"].lower()

    def test_validate_coupon_invalid_line_total(self):
        """Test validation with invalid line total format."""
        Coupon.objects.create(
            code="VALID2",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "VALID2", "cart": [{"grand_total": "invalid"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 400
        assert data["success"] is False
        assert "invalid line total" in data["message"].lower()

    def test_validate_coupon_case_insensitive_code(self):
        """Test coupon code is case-insensitive."""
        Coupon.objects.create(
            code="CASEMATCH",
            discount_type="percent",
            percent_off=Decimal("20.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "casematch", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(20.00)

    def test_validate_coupon_decimal_precision(self):
        """Test discount calculation maintains decimal precision."""
        Coupon.objects.create(
            code="PRECISE",
            discount_type="percent",
            percent_off=Decimal("33.33"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
        )

        payload = {"code": "PRECISE", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        # 33.33% of 100 = 33.33
        assert data["discount_amount"] == pytest.approx(33.33)
        assert data["new_total"] == pytest.approx(66.67)

    def test_validate_coupon_unlimited_usage(self):
        """Test coupon with no usage limit."""
        Coupon.objects.create(
            code="UNLIMITED",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
            max_redemptions=None,  # No limit
        )

        payload = {"code": "UNLIMITED", "cart": [{"grand_total": "100.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True

    def test_validate_coupon_no_minimum_total(self):
        """Test coupon with no minimum cart total requirement."""
        Coupon.objects.create(
            code="NOMINI",
            discount_type="percent",
            percent_off=Decimal("10.00"),
            is_active=True,
            valid_from=self.now,
            valid_to=self.now + timezone.timedelta(days=7),
            min_cart_total=None,  # No minimum
        )

        payload = {"code": "NOMINI", "cart": [{"grand_total": "5.00"}]}
        request = self._make_request(payload)

        response = validate_coupon(request)
        data = json.loads(response.content)

        assert response.status_code == 200
        assert data["success"] is True
        assert data["discount_amount"] == pytest.approx(0.50)
        assert data["new_total"] == pytest.approx(4.50)
