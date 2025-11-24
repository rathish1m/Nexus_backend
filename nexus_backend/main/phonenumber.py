def format_phone_number(phone):
    phone = phone.strip().replace(" ", "").replace("-", "")

    # Normalize common DR Congo prefixes in a consistent order:
    # - Strip full international prefixes first (00243, +243)
    # - Then bare country code 243
    # - Finally a single leading 0 used for local format
    if phone.startswith("00243"):
        phone = phone[5:]
    elif phone.startswith("+243"):
        phone = phone[4:]
    elif phone.startswith("243"):
        phone = phone[3:]
    elif phone.startswith("0"):
        phone = phone[1:]

    return f"+243{phone}"
