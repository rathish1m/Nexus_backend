"""
Twilio SMS/OTP Service Mock
===========================

Mock implementation of Twilio API for testing SMS and OTP workflows.

Usage:
-----
@pytest.fixture
def mock_twilio(monkeypatch):
    mock = TwilioMock()
    monkeypatch.setattr('twilio.rest.Client', lambda *args, **kwargs: mock)
    return mock
"""

import random
import string
from datetime import datetime
from typing import Dict, List, Optional


class TwilioMock:
    """Mock Twilio client for testing SMS/OTP"""

    def __init__(self, account_sid: str = "test_sid", auth_token: str = "test_token"):
        self.account_sid = account_sid
        self.auth_token = auth_token
        self.sent_messages: List[Dict] = []
        self.message_counter = 1000

        # Create messages property to match Twilio API
        self.messages = self._MessagesProxy(self)

    class _MessagesProxy:
        """Proxy for messages.create() to match Twilio API"""

        def __init__(self, parent):
            self.parent = parent

        def create(
            self, to: str, from_: str = None, body: str = None
        ) -> "TwilioMock._Message":
            return self.parent.send_sms(to, body, from_)

    class _Message:
        """Mock Twilio message object"""

        def __init__(
            self, sid: str, to: str, from_: str, body: str, status: str = "sent"
        ):
            self.sid = sid
            self.to = to
            self.from_ = from_
            self.body = body
            self.status = status
            self.date_created = datetime.now()
            self.date_sent = datetime.now()
            self.error_code = None
            self.error_message = None

    def send_sms(self, to: str, body: str, from_: str = "+1234567890") -> _Message:
        """Send SMS message (mocked)"""
        message_sid = f"SM{self.message_counter:032x}"
        self.message_counter += 1

        message = self._Message(
            sid=message_sid, to=to, from_=from_, body=body, status="sent"
        )

        self.sent_messages.append(
            {
                "sid": message_sid,
                "to": to,
                "from": from_,
                "body": body,
                "status": "sent",
                "created_at": datetime.now().isoformat(),
            }
        )

        return message

    def generate_otp(self, length: int = 6) -> str:
        """Generate random OTP code"""
        return "".join(random.choices(string.digits, k=length))

    def send_otp(
        self, to: str, otp: Optional[str] = None, from_: str = "+1234567890"
    ) -> Dict:
        """Send OTP via SMS"""
        if otp is None:
            otp = self.generate_otp()

        body = f"Your NEXUS Telecoms verification code is: {otp}. Valid for 10 minutes."
        message = self.send_sms(to, body, from_)

        return {"sid": message.sid, "to": to, "otp": otp, "status": "sent"}

    def verify_otp(self, phone: str, otp: str) -> bool:
        """Verify OTP code (always returns True in mock for testing)"""
        # In real implementation, this would check against stored OTPs
        # For testing, we accept any 6-digit code
        return len(otp) == 6 and otp.isdigit()

    def get_sent_messages(self, to: Optional[str] = None) -> List[Dict]:
        """Get all sent messages, optionally filtered by recipient"""
        if to:
            return [msg for msg in self.sent_messages if msg["to"] == to]
        return self.sent_messages

    def get_last_message(self, to: Optional[str] = None) -> Optional[Dict]:
        """Get last sent message"""
        messages = self.get_sent_messages(to)
        return messages[-1] if messages else None

    def extract_otp_from_message(self, message: Dict) -> Optional[str]:
        """Extract OTP code from message body"""
        body = message.get("body", "")
        # Simple extraction: find 6-digit number
        import re

        match = re.search(r"\b(\d{6})\b", body)
        return match.group(1) if match else None

    def reset(self):
        """Reset all mock data"""
        self.sent_messages = []
        self.message_counter = 1000

    def simulate_delivery_failure(self, message_sid: str, error_code: str = "30001"):
        """Simulate message delivery failure"""
        for msg in self.sent_messages:
            if msg["sid"] == message_sid:
                msg["status"] = "failed"
                msg["error_code"] = error_code
                msg["error_message"] = "Queue overflow"
                break
