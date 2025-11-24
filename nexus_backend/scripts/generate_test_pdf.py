"""
Generate a test PDF invoice to validate hybrid template rendering.
Run with: python manage.py runscript generate_test_pdf
"""

import os

from xhtml2pdf import pisa

from django.template.loader import render_to_string

from billing_management.views import _build_invoice_context
from main.models import CompanySettings, Invoice


def run():
    # Get latest invoice
    inv = Invoice.objects.order_by("-id").first()
    if not inv:
        print("❌ No invoice found in database")
        return

    print(f"🧾 Generating PDF for invoice: {inv.number}")

    # Build context
    cs = CompanySettings.get()
    context = _build_invoice_context(inv, cs)

    # Check hybrid features
    print(f"  ✅ show_cdf_column: {context.get('show_cdf_column')}")
    print(f"  ✅ exchange_rate: {context.get('exchange_rate')}")
    print(f"  ✅ show_bank_details: {context.get('show_bank_details')}")

    # Render template
    html = render_to_string("invoices/inv_templates.html", context)

    # Generate PDF
    output_dir = (
        "/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend/tmp"
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(
        output_dir, f"test_invoice_{inv.number.replace('/', '-')}.pdf"
    )

    with open(output_path, "wb") as pdf_file:
        pisa_status = pisa.CreatePDF(html, dest=pdf_file)

    if pisa_status.err:
        print("❌ PDF generation failed with errors")
        return

    print("\n✅ PDF generated successfully!")
    print(f"📄 Location: {output_path}")
    print(f"\nTo view: xdg-open {output_path}")
