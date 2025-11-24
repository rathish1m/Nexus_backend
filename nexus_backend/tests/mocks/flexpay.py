"""
FlexPay Payment Gateway Mock
============================

Mock implementation of the FlexPay API for testing payment workflows.

Usage:
-----
@pytest.fixture
def mock_flexpay(responses):
    '''Mock all FlexPay API endpoints'''
    mock = FlexPayMock()
    mock.register_responses(responses)
    return mock
"""

import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, Optional


class FlexPayMock:
    """Mock FlexPay payment gateway for testing"""

    def __init__(self):
        self.payments = {}
        self.payment_counter = 1000
        self.api_url = "https://api.flexpay.test"

    def register_responses(self, responses_mock):
        """Register all FlexPay API mock responses"""

        def _as_callback(func):
            """Wrap a JSON-producing method into a responses callback."""

            def _callback(request):
                payload = func(request) or {}
                return (
                    200,
                    {"Content-Type": "application/json"},
                    json.dumps(payload, default=str),
                )

            return _callback

        # Payment initiation endpoint (used by example integration tests)
        responses_mock.add_callback(
            responses_mock.POST,
            f"{self.api_url}/v1/payments/initiate",
            callback=_as_callback(self._payment_initiation_callback),
        )

    def _payment_initiation_callback(self, request) -> Dict[str, Any]:
        """Simulate payment initiation"""
        data = json.loads(request.body)

        payment_id = f"FP-{self.payment_counter}"
        self.payment_counter += 1

        self.payments[payment_id] = {
            "id": payment_id,
            "amount": Decimal(str(data.get("amount", 0))),
            "currency": data.get("currency", "USD"),
            "customer_id": data.get("customer_id"),
            "order_id": data.get("order_id"),
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }

        return {
            "success": True,
            "payment_id": payment_id,
            "status": "pending",
            "redirect_url": f"{self.api_url}/checkout/{payment_id}",
            "expires_at": (datetime.now() + timedelta(minutes=15)).isoformat(),
        }

    def _payment_status_callback(self, request) -> Dict[str, Any]:
        """Check payment status"""
        payment_id = request.params.get("payment_id")

        if payment_id not in self.payments:
            return {
                "success": False,
                "error": "Payment not found",
                "error_code": "PAYMENT_NOT_FOUND",
            }

        payment = self.payments[payment_id]
        return {
            "success": True,
            "payment_id": payment_id,
            "status": payment["status"],
            "amount": float(payment["amount"]),
            "currency": payment["currency"],
            "updated_at": payment["updated_at"],
        }

    def _payment_confirmation_callback(self, request) -> Dict[str, Any]:
        """Confirm payment"""
        data = json.loads(request.body)
        payment_id = data.get("payment_id")

        if payment_id not in self.payments:
            return {"success": False, "error": "Payment not found"}

        self.payments[payment_id]["status"] = "completed"
        self.payments[payment_id]["updated_at"] = datetime.now().isoformat()
        self.payments[payment_id]["transaction_id"] = f"TXN-{payment_id}"

        return {
            "success": True,
            "payment_id": payment_id,
            "status": "completed",
            "transaction_id": f"TXN-{payment_id}",
            "confirmed_at": datetime.now().isoformat(),
        }

    def _refund_callback(self, request) -> Dict[str, Any]:
        """Process refund"""
        data = json.loads(request.body)
        payment_id = data.get("payment_id")

        if payment_id not in self.payments:
            return {"success": False, "error": "Payment not found"}

        payment = self.payments[payment_id]

        if payment["status"] != "completed":
            return {"success": False, "error": "Cannot refund non-completed payment"}

        refund_id = f"RFD-{payment_id}"
        payment["status"] = "refunded"
        payment["refund_id"] = refund_id
        payment["refunded_at"] = datetime.now().isoformat()

        return {
            "success": True,
            "refund_id": refund_id,
            "payment_id": payment_id,
            "status": "refunded",
            "amount": float(payment["amount"]),
            "refunded_at": datetime.now().isoformat(),
        }

    def simulate_payment_success(self, payment_id: str):
        """Manually set payment to successful status"""
        if payment_id in self.payments:
            self.payments[payment_id]["status"] = "completed"
            self.payments[payment_id]["updated_at"] = datetime.now().isoformat()

    def simulate_payment_failure(
        self, payment_id: str, reason: str = "insufficient_funds"
    ):
        """Manually set payment to failed status"""
        if payment_id in self.payments:
            self.payments[payment_id]["status"] = "failed"
            self.payments[payment_id]["failure_reason"] = reason
            self.payments[payment_id]["updated_at"] = datetime.now().isoformat()

    def get_payment(self, payment_id: str) -> Optional[Dict[str, Any]]:
        """Get payment details"""
        return self.payments.get(payment_id)

    def reset(self):
        """Reset all mock data"""
        self.payments = {}
        self.payment_counter = 1000
