"""
Quick test to verify the corrected tax calculation logic.
Excise applies only to subscription plans (kind='plan'), not to all items.
"""

import os
import sys

import django

# Setup Django
sys.path.insert(
    0, "/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend"
)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from decimal import Decimal

from billing_management.services.invoice_grouping import group_invoice_lines_by_order
from main.models import Invoice, InvoiceLine, Order, User

# Create test data
print("Creating test invoice...")
user = User.objects.first()
if not user:
    print("❌ No users found. Please create a user first.")
    sys.exit(1)

order = Order.objects.create(
    user=user, order_reference="TEST-TAX-001", total_price=Decimal("260.00")
)

invoice = Invoice.objects.create(
    user=user,
    number="TEST/2025/TAX",
    vat_rate_percent=Decimal("16.00"),
    excise_rate_percent=Decimal("10.00"),
)

# Add lines with different kinds
# Mini Kit: $55 (no excise)
InvoiceLine.objects.create(
    invoice=invoice,
    order=order,
    description="Mini Kit",
    kind="item",
    quantity=Decimal("1.00"),
    unit_price=Decimal("55.00"),
    line_total=Decimal("55.00"),
)

# Limited Fast (Plan): $85 (EXCISE APPLIES)
InvoiceLine.objects.create(
    invoice=invoice,
    order=order,
    description="Limited Fast - monthly",
    kind="plan",
    quantity=Decimal("1.00"),
    unit_price=Decimal("85.00"),
    line_total=Decimal("85.00"),
)

# Installation fee: $120 (no excise)
InvoiceLine.objects.create(
    invoice=invoice,
    order=order,
    description="Installation fee",
    kind="item",
    quantity=Decimal("1.00"),
    unit_price=Decimal("120.00"),
    line_total=Decimal("120.00"),
)

print("\n" + "=" * 60)
print("TEST INVOICE LINES:")
print("=" * 60)
print("Mini Kit (item):        $55.00")
print("Limited Fast (plan):    $85.00  ← Excise applies here")
print("Installation (item):   $120.00")
print("Subtotal:              $260.00")

# Calculate with our service
result = group_invoice_lines_by_order(invoice)

if result["order_groups"]:
    group = result["order_groups"][0]

    print("\n" + "=" * 60)
    print("CALCULATED TAXES:")
    print("=" * 60)
    print("Excise base (plan only): $85.00")
    print(f"Excise (10% of $85):     ${group['excise_amount']}")
    print("")
    print(
        f"VAT base: $260 + ${group['excise_amount']} = ${Decimal('260.00') + group['excise_amount']}"
    )
    print(f"VAT (16%):               ${group['vat_amount']}")
    print("")
    print(f"Total TTC:               ${group['total_ttc']}")

    print("\n" + "=" * 60)
    print("EXPECTED VALUES:")
    print("=" * 60)
    print("Excise:  $8.50  (10% of $85)")
    print("VAT:    $42.96  (16% of $268.50)")
    print("Total:  $311.46")

    print("\n" + "=" * 60)
    print("VERIFICATION:")
    print("=" * 60)

    excise_ok = group["excise_amount"] == Decimal("8.50")
    vat_ok = group["vat_amount"] == Decimal("42.96")
    total_ok = group["total_ttc"] == Decimal("311.46")

    print(f"✅ Excise correct:  {excise_ok}  (${group['excise_amount']} == $8.50)")
    print(f"✅ VAT correct:     {vat_ok}  (${group['vat_amount']} == $42.96)")
    print(f"✅ Total correct:   {total_ok}  (${group['total_ttc']} == $311.46)")

    if excise_ok and vat_ok and total_ok:
        print("\n🎉 ALL TESTS PASSED! Tax logic is correct.")
    else:
        print("\n❌ TESTS FAILED! Check the calculations.")
        sys.exit(1)
else:
    print("❌ No order groups found")
    sys.exit(1)

# Cleanup
print("\nCleaning up test data...")
invoice.delete()
order.delete()
print("✅ Done!")
