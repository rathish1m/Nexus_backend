#!/usr/bin/env python
"""
Script to convert inv_templates.html to hybrid mode (TDD approach)
- Remove emojis
- Add conditional CDF column
- Add conditional bank details section
- Simplify colors (blue → gray)
"""

from pathlib import Path

# Emoji replacements (professional text instead)
EMOJI_REPLACEMENTS = {
    "📦 Order": "Order",
    "💵 Subtotal": "Subtotal",
    "📊 Excise": "Excise",
    "🏛️ VAT": "VAT",
    "✅ Total TTC": "Total TTC",
    "💰 Total Due": "Total Due",
    "🇨🇩 Equivalent": "Equivalent",
    "✍️ Authorized by": "Authorized by",
    "✅ Received by": "Received by",
    "📄 Page": "Page",
    "📡 ARPTC": "ARPTC",
    "🌐 ": "",
    "✉️ ": "",
    "☎️ ": "",
    "⚖️ ": "",
}

# Color simplification (blue → gray for hybrid mode)
COLOR_REPLACEMENTS = {
    "#2563eb": "#4b5563",  # Primary blue → gray-600
    "#1e40af": "#374151",  # Dark blue → gray-700
    "#1e3a8a": "#1f2937",  # Darker blue → gray-800
}


def main():
    template_path = (
        Path(__file__).parent.parent
        / "billing_management/templates/invoices/inv_templates.html"
    )

    print(f"📝 Reading template: {template_path}")
    content = template_path.read_text(encoding="utf-8")

    # Step 1: Remove emojis
    print("🔄 Step 1: Removing emojis...")
    for emoji, replacement in EMOJI_REPLACEMENTS.items():
        count = content.count(emoji)
        if count > 0:
            content = content.replace(emoji, replacement)
            print(f"   ✅ Replaced '{emoji}' → '{replacement}' ({count} occurrences)")

    # Step 2: Add CDF column header (conditional)
    print("\n🔄 Step 2: Adding conditional CDF column...")

    # Find the items table header and add CDF column
    old_header = """              <thead>
                <tr>
                  <th class="col-desc">Description</th>
                  <th class="col-qty">Qty</th>
                  <th class="col-up">Unit Price ({{ invoice.currency }})</th>
                  <th class="col-tot ta-r">Line Total ({{ invoice.currency }})</th>
                </tr>
              </thead>"""

    new_header = """              <thead>
                <tr>
                  <th class="col-desc">Description</th>
                  <th class="col-qty">Qty</th>
                  <th class="col-up">Unit Price ({{ invoice.currency }})</th>
                  <th class="col-tot ta-r">Line Total ({{ invoice.currency }})</th>
                  {% if show_cdf_column %}
                  <th class="col-cdf ta-r">Total (CDF)</th>
                  {% endif %}
                </tr>
              </thead>"""

    if old_header in content:
        content = content.replace(old_header, new_header)
        print("   ✅ Added CDF column header")

    # Step 3: Add CDF column data cells
    print("\n🔄 Step 3: Adding CDF data cells...")

    # For order grouping items
    old_item_row = """                <tr>
                  <td class="col-desc"><div class="desc"><strong>{{ line.description }}</strong></div></td>
                  <td class="col-qty">{{ line.quantity }}</td>
                  <td class="col-up">{{ line.unit_price|floatformat:2 }}</td>
                  <td class="col-tot ta-r">{{ line.line_total|floatformat:2 }}</td>
                </tr>"""

    new_item_row = """                <tr>
                  <td class="col-desc"><div class="desc"><strong>{{ line.description }}</strong></div></td>
                  <td class="col-qty">{{ line.quantity }}</td>
                  <td class="col-up">{{ line.unit_price|floatformat:2 }}</td>
                  <td class="col-tot ta-r">{{ line.line_total|floatformat:2 }}</td>
                  {% if show_cdf_column %}
                  <td class="col-cdf ta-r">{{ line.line_total|floatformat:2|multiply:exchange_rate|floatformat:0|intcomma }}</td>
                  {% endif %}
                </tr>"""

    content = content.replace(old_item_row, new_item_row)
    print("   ✅ Added CDF data cells")

    # Step 4: Simplify colors (optional - commented for now to keep branding)
    # print("\n🔄 Step 4: Simplifying colors (blue → gray)...")
    # for old_color, new_color in COLOR_REPLACEMENTS.items():
    #     content = content.replace(old_color, new_color)

    # Step 5: Add bank details section before totals
    print("\n🔄 Step 5: Adding bank details section...")

    bank_details_section = """
    {% if show_bank_details %}
    <!-- BANK DETAILS SECTION -->
    <div style="margin-top: 8pt; margin-bottom: 6pt; padding: 6pt; border: 1px solid #e2e8f0; border-radius: 3pt; background: #f8fafc;">
      <h3 style="margin: 0 0 4pt 0; font-size: 9.5px; font-weight: 700; color: #374151; text-transform: uppercase; letter-spacing: 0.05em;">
        Payment Information / Informations de Paiement
      </h3>
      <table style="width: 100%; border-spacing: 0; font-size: 9px;">
        <tr>
          <td style="width: 50%; padding: 2pt 4pt; vertical-align: top;">
            {% if company.bank_name %}
            <div style="margin-bottom: 3pt;">
              <strong>Bank:</strong> {{ company.bank_name }}
              {% if company.bank_account_name %}<br><strong>Account Name:</strong> {{ company.bank_account_name }}{% endif %}
              {% if company.bank_account_number_usd %}<br><strong>Account Number (USD):</strong> {{ company.bank_account_number_usd }}{% endif %}
              {% if company.bank_account_number_cdf %}<br><strong>Account Number (CDF):</strong> {{ company.bank_account_number_cdf }}{% endif %}
              {% if company.bank_swift %}<br><strong>SWIFT/BIC:</strong> {{ company.bank_swift }}{% endif %}
            </div>
            {% endif %}
          </td>
          <td style="width: 50%; padding: 2pt 4pt; vertical-align: top;">
            {% if company.mm_provider %}
            <div style="margin-bottom: 3pt;">
              <strong>Mobile Money:</strong> {{ company.mm_provider }}
              {% if company.mm_number %}<br><strong>Number:</strong> {{ company.mm_number }}{% endif %}
            </div>
            {% endif %}
            {% if company.payment_instructions %}
            <div style="font-size: 8.5px; color: #64748b; font-style: italic;">
              {{ company.payment_instructions }}
            </div>
            {% endif %}
          </td>
        </tr>
      </table>
    </div>
    {% endif %}

    <!-- NOTES + TOTALS -->"""

    # Insert before "<!-- NOTES + TOTALS -->"
    content = content.replace("    <!-- NOTES + TOTALS -->", bank_details_section)
    print("   ✅ Added bank details section")

    # Step 6: Add CSS for CDF column
    print("\n🔄 Step 6: Adding CSS for CDF column...")

    css_addition = """    .col-cdf  { width: 75pt; text-align: right; font-weight: 600; color: #64748b; }
"""

    # Insert after col-tot definition
    old_css = """    .col-tot  { width: 65pt; text-align: right; font-weight: 600; }"""
    new_css = """    .col-tot  { width: 65pt; text-align: right; font-weight: 600; }
    .col-cdf  { width: 75pt; text-align: right; font-weight: 600; color: #64748b; }"""

    content = content.replace(old_css, new_css)
    print("   ✅ Added CDF column CSS")

    # Save modified template
    print("\n💾 Saving modified template...")
    template_path.write_text(content, encoding="utf-8")
    print("✅ Template updated successfully!")
    print("\n📊 Summary:")
    print(f"   - Emojis removed: {len(EMOJI_REPLACEMENTS)}")
    print("   - CDF column added (conditional)")
    print("   - Bank details section added (conditional)")
    print("   - Professional styling maintained")


if __name__ == "__main__":
    main()
