from decimal import Decimal

import pytest

from api.api_helpers import (
    _d,
    _get_req_data,
    _order_gross_amount,
    _is_success,
    _is_failure,
)
from main.factories import OrderFactory
from main.models import OrderLine, OrderTax


def test_d_helper_handles_various_inputs():
    assert _d(Decimal("10.50")) == Decimal("10.50")
    assert _d(10) == Decimal("10")
    assert _d("20.25") == Decimal("20.25")
    # Invalid input falls back to 0.00
    assert _d(object()) == Decimal("0.00")


def test_get_req_data_prefers_drf_data_over_body():
    class DRFRequest:
        def __init__(self):
            self.data = {"key": "value"}
            self.body = b'{"ignored": true}'

    req = DRFRequest()
    assert _get_req_data(req) == {"key": "value"}


def test_get_req_data_falls_back_to_json_body():
    class HttpRequestLike:
        def __init__(self, body):
            self.body = body

    req = HttpRequestLike(b'{"a": 1, "b": "two"}')
    assert _get_req_data(req) == {"a": 1, "b": "two"}

    # Invalid JSON returns empty dict
    bad = HttpRequestLike(b"{not-json")
    assert _get_req_data(bad) == {}


@pytest.mark.django_db
def test_order_gross_amount_prefers_order_total_price():
    order = OrderFactory(total_price=Decimal("123.45"))
    gross = _order_gross_amount(order)
    assert isinstance(gross, Decimal)
    assert gross == Decimal("123.45")


@pytest.mark.django_db
def test_order_gross_amount_falls_back_to_lines_and_taxes():
    order = OrderFactory(total_price=None)
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.KIT,
        description="Kit",
        quantity=1,
        unit_price=Decimal("100.00"),
    )
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.EXTRA,
        description="Extra",
        quantity=1,
        unit_price=Decimal("50.00"),
    )
    OrderTax.objects.create(
        order=order,
        kind=OrderTax.Kind.VAT,
        rate=Decimal("16.00"),
        amount=Decimal("16.00"),
    )

    gross = _order_gross_amount(order)
    assert isinstance(gross, Decimal)
    assert gross == Decimal("166.00")


def test_is_success_and_is_failure_decodes_codes_and_strings():
    # Numeric codes
    assert _is_success(0) is True
    assert _is_success("0") is True
    assert _is_failure(1) is True
    assert _is_failure("1") is True

    # String status values
    for val in ["success", "succeeded", "completed", "paid"]:
        assert _is_success(val) is True
    for val in ["failed", "failure", "error", "cancelled"]:
        assert _is_failure(val) is True

    # Non-matching values
    assert _is_success("other") is False
    assert _is_failure("other") is False
