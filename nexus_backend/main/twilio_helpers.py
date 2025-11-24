from os import environ
from typing import Optional, Tuple

from twilio.rest import Client


def send_otp_sms(
    full_name: str,
    cleaned_phone: str,
    otp_code: str,
    *,
    alpha_sender: str = "NEXUS",
    sid: Optional[str] = None,
    token: Optional[str] = None,
    fallback_number: Optional[str] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Send an OTP via Twilio SMS.

    Args:
        full_name: Recipient's name (used in the SMS body).
        cleaned_phone: Phone number WITHOUT the leading '+' (e.g., '2438XXXXXXX').
        otp_code: The 6-digit OTP string to send.
        alpha_sender: Alphanumeric sender ID to use first (if supported by destination).
        sid: Optional override for TWILIO_ACCOUNT_SID (defaults to env).
        token: Optional override for TWILIO_AUTH_TOKEN (defaults to env).
        fallback_number: Optional override for TWILIO_PHONE_NUMBER (defaults to env).

    Returns:
        (success, info)
          - success: True if the message was queued by Twilio.
          - info: Twilio Message SID on success; error string on failure.

    Notes:
        - Alphanumeric sender IDs are not supported in all countries/operators.
          This function tries `alpha_sender` first, then falls back to your
          numeric Twilio number if provided.
    """
    sid = sid or environ.get("TWILIO_ACCOUNT_SID")
    token = token or environ.get("TWILIO_AUTH_TOKEN")
    fallback_number = fallback_number or environ.get("TWILIO_PHONE_NUMBER")

    if not sid or not token:
        return False, "Missing Twilio credentials (SID/TOKEN)."

    client = Client(sid, token)
    to_number = cleaned_phone if cleaned_phone.startswith("+") else f"+{cleaned_phone}"
    body = f"Hi {full_name}, your OTP code is: {otp_code}"

    # Try alphanumeric sender first (if provided)
    try:
        from_id = alpha_sender or fallback_number
        message = client.messages.create(body=body, from_=from_id, to=to_number)
        if getattr(message, "sid", None):
            print(f"[Twilio] SMS sent (SID: {message.sid}, Status: {message.status})")
            return True, message.sid
        print("[Twilio] SMS sending failed: No SID returned")
        return False, "No SID returned by Twilio."
    except Exception as e_first:
        print(f"[Twilio] First attempt failed (from='{alpha_sender}') → {e_first}")

        # Fallback to numeric number if available and different from alpha
        if fallback_number and alpha_sender and fallback_number != alpha_sender:
            try:
                message = client.messages.create(
                    body=body, from_=fallback_number, to=to_number
                )
                if getattr(message, "sid", None):
                    print(
                        f"[Twilio] Fallback SMS sent (SID: {message.sid}, Status: {message.status})"
                    )
                    return True, message.sid
                print("[Twilio] Fallback send failed: No SID returned")
                return False, "Fallback send returned no SID."
            except Exception as e_second:
                print(f"[Twilio] Fallback attempt failed → {e_second}")
                return False, str(e_second)

        # No fallback possible
        return False, str(e_first)
