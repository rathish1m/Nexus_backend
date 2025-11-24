"""
Test script to validate hybrid invoice context with CDF calculations.
Run with: python manage.py runscript test_hybrid_invoice_context
"""

from billing_management.views import _build_invoice_context
from main.models import CompanySettings, Invoice


def run():
    # Get latest invoice
    inv = Invoice.objects.order_by("-id").first()
    if not inv:
        print("❌ No invoice found in database")
        return

    print(f"🧾 Testing invoice: {inv.number}")

    # Build context
    cs = CompanySettings.get()

    try:
        context = _build_invoice_context(inv, cs)

        # Check hybrid flags
        print("\n✅ Hybrid Context Built Successfully!")
        print(f"  show_cdf_column: {context.get('show_cdf_column')}")
        print(f"  show_bank_details: {context.get('show_bank_details')}")
        print(f"  exchange_rate: {context.get('exchange_rate')}")

        # Check CDF calculations on items (dict-based)
        if context.get("invoice", {}).get("items"):
            item = context["invoice"]["items"][0]
            print("\n💵 First invoice item (dict):")
            print(f"  USD: {item.get('line_total', 'N/A')}")
            print(f"  CDF: {item.get('line_total_cdf', 'N/A')}")

        # Check CDF calculations on order groups (object-based)
        if context.get("order_groups"):
            og = context["order_groups"][0]
            if og.get("lines"):
                first_line = og["lines"][0]
                print("\n📦 First order group line (InvoiceLine object):")
                print(f"  Type: {type(first_line).__name__}")
                print(f"  USD: {getattr(first_line, 'line_total', 'N/A')}")
                print(
                    f"  CDF: {getattr(first_line, 'line_total_cdf', '❌ NOT CALCULATED')}"
                )

        print("\n✅ All checks passed - no TypeError!")

    except TypeError as e:
        print(f"\n❌ TypeError occurred: {e}")
        import traceback

        traceback.print_exc()
