"""
Analyze the generated hybrid invoice PDF content.
Run with: python manage.py runscript analyze_pdf_content
"""

import os

import PyPDF2


def run():
    pdf_path = "/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend/tmp/test_invoice_2025-IND-000003.pdf"

    if not os.path.exists(pdf_path):
        print(f"❌ PDF not found: {pdf_path}")
        return

    print(f"📄 Analyzing: {pdf_path}\n")

    with open(pdf_path, "rb") as file:
        pdf_reader = PyPDF2.PdfReader(file)

        print(f"📊 Total pages: {len(pdf_reader.pages)}")
        print(f"📝 Title: {pdf_reader.metadata.get('/Title', 'N/A')}")
        print(f"🗓️  Created: {pdf_reader.metadata.get('/CreationDate', 'N/A')}\n")

        # Extract text from first page
        first_page = pdf_reader.pages[0]
        text = first_page.extract_text()

        print("=" * 80)
        print("EXTRACTED TEXT CONTENT:")
        print("=" * 80)
        print(text)
        print("=" * 80)

        # Check for hybrid features
        print("\n✅ HYBRID FEATURES VALIDATION:")

        checks = {
            "CDF column": "CDF" in text or "FC" in text,
            "Exchange rate": "2300" in text or "2,300" in text,
            "No emojis (Order text)": "Order" in text and "📦" not in text,
            "No emojis (Subtotal text)": "Subtotal" in text and "💵" not in text,
            "Professional formatting": "USD" in text,
            "Bank details section": "Bank" in text or "Payment Information" in text,
        }

        for feature, found in checks.items():
            status = "✅" if found else "❌"
            print(f"  {status} {feature}")

        # Check for specific amounts
        print("\n💰 AMOUNT VALIDATION:")
        if "230000" in text.replace(",", "").replace(" ", ""):
            print("  ✅ CDF amount found: 230,000 CDF (= $100 × 2300)")
        else:
            print("  ⚠️  CDF amount 230,000 not clearly visible")
