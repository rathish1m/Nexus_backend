from main.phonenumber import format_phone_number


def test_format_phone_number_strips_spaces_and_hyphens():
    assert format_phone_number(" 0 81-234-5678 ") == "+243812345678"


def test_format_phone_number_handles_leading_zero():
    assert format_phone_number("0812345678") == "+243812345678"


def test_format_phone_number_handles_00243_prefix():
    assert format_phone_number("00243812345678") == "+243812345678"


def test_format_phone_number_handles_plus_243_prefix():
    assert format_phone_number("+243812345678") == "+243812345678"


def test_format_phone_number_handles_243_prefix():
    assert format_phone_number("243812345678") == "+243812345678"
