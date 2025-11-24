from decimal import Decimal

from client_app.client_helpers import ZERO, _qmoney, order_amount_components


def _money_str(val: Decimal | None) -> str:
    return str(_qmoney(val or ZERO))


def serialize_order(order):
    components = order_amount_components(order)
    return {
        "id": order.order_reference,
        "kit": _money_str(components["kit"]),
        "plan": _money_str(components["plan"]),
        "install_fee_usd": _money_str(components["install"]),
        "total_price": _money_str(order.total_price or ZERO),
        "vat": _money_str(components["vat"]),
        "exc": _money_str(components["exc"]),
        "expires_at": order.expires_at.isoformat() if order.expires_at else None,
    }
