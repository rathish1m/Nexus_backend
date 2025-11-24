#!/bin/bash
# Quick Manual Test Script for Invoice Logo Fix
# Usage: ./scripts/test_invoice_logo.sh

echo "🧪 Invoice Logo Fix - Manual Testing Guide"
echo "=========================================="
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}1. Run Unit Tests${NC}"
echo "   python manage.py test billing_management.tests.test_invoice_logo_simple -v 2"
echo ""

echo -e "${YELLOW}2. Start Development Server${NC}"
echo "   python manage.py runserver"
echo ""

echo -e "${YELLOW}3. Test URLs to Visit:${NC}"
echo "   • Regular Invoice PDF:"
echo "     http://localhost:8000/en/billing/invoice/2025-IND-000001/pdf/"
echo ""
echo "   • Consolidated Invoice PDF (if applicable):"
echo "     http://localhost:8000/en/billing/consolidated-invoice/{number}/pdf/"
echo ""

echo -e "${YELLOW}4. Visual Checks:${NC}"
echo "   ✓ Logo appears in top-left corner"
echo "   ✓ Logo is properly sized (40px height)"
echo "   ✓ Logo displays even if CompanySettings.logo is empty"
echo "   ✓ No broken image icons"
echo "   ✓ Logo path resolves correctly for WeasyPrint"
echo ""

echo -e "${GREEN}✅ Expected Result:${NC}"
echo "   Logo should always be visible at /static/images/logo/logo.png"
echo "   (or custom logo if CompanySettings.logo is set)"
echo ""

echo -e "${YELLOW}5. Check Static File Exists:${NC}"
ls -lh static/images/logo/logo.png 2>/dev/null || echo "   ⚠️  Logo file not found!"
echo ""

echo "📖 Full Documentation: docs/billing/INVOICE_LOGO_FIX_TDD.md"
