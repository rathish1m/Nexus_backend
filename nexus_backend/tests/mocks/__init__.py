"""
External Service Mocks
======================

This module provides mock implementations for external services used in tests.

Available Mocks:
---------------
- FlexPayMock: Mock FlexPay payment gateway API
- TwilioMock: Mock Twilio SMS/OTP service
- AWSMock: Mock AWS S3/Spaces storage service
- EmailMock: Mock email sending service

Usage:
-----
import pytest
from tests.mocks import FlexPayMock

@pytest.fixture
def mock_flexpay(monkeypatch):
    mock = FlexPayMock()
    monkeypatch.setattr('path.to.flexpay.client', mock)
    return mock

def test_payment(mock_flexpay):
    # Test code here
    assert mock_flexpay.payment_initiated
"""
