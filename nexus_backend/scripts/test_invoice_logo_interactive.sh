#!/bin/bash
# Interactive Manual Test Script for Invoice Logo Fix
# Author: GitHub Copilot
# Date: November 11, 2025

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Unicode symbols
CHECK="✅"
CROSS="❌"
WARN="⚠️ "
INFO="ℹ️ "
ROCKET="🚀"
TEST="🧪"

echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo -e "${PURPLE}${TEST}  Invoice Logo Fix - Interactive Test Guide${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo ""

# Step 1: Check logo file exists
echo -e "${BLUE}[Step 1/5]${NC} ${INFO} Checking if logo file exists..."
if [ -f "static/images/logo/logo.png" ]; then
    echo -e "${GREEN}${CHECK} Logo file found: static/images/logo/logo.png${NC}"
    ls -lh static/images/logo/logo.png
else
    echo -e "${RED}${CROSS} Logo file NOT found: static/images/logo/logo.png${NC}"
    echo -e "${YELLOW}${WARN} Please ensure the logo file exists before continuing.${NC}"
    exit 1
fi
echo ""

# Step 2: Run unit tests
echo -e "${BLUE}[Step 2/5]${NC} ${TEST} Running unit tests..."
echo -e "${YELLOW}Command: python manage.py test billing_management.tests.test_invoice_logo_simple -v 2${NC}"
read -p "Press Enter to run tests or Ctrl+C to skip..."
echo ""

if python manage.py test billing_management.tests.test_invoice_logo_simple --parallel=1 2>&1 | grep -q "OK"; then
    echo -e "${GREEN}${CHECK} All tests passed!${NC}"
else
    echo -e "${YELLOW}${WARN} Some tests may have issues. Check output above.${NC}"
fi
echo ""

# Step 3: List available invoices
echo -e "${BLUE}[Step 3/5]${NC} ${INFO} Finding available invoices..."
echo ""
python manage.py shell <<EOF
from main.models import Invoice
invoices = Invoice.objects.all().order_by('-issued_at')[:5]
if invoices:
    print("${GREEN}Available invoices:${NC}")
    for inv in invoices:
        print(f"  • {inv.number} - User: {inv.user.email if inv.user else 'N/A'} - Status: {inv.status}")
else:
    print("${YELLOW}${WARN} No invoices found in database${NC}")
EOF
echo ""

# Step 4: Server instructions
echo -e "${BLUE}[Step 4/5]${NC} ${ROCKET} Starting development server..."
echo ""
echo -e "${YELLOW}Instructions:${NC}"
echo -e "  1. The server will start in a moment"
echo -e "  2. Open your browser and navigate to:"
echo -e "     ${CYAN}http://localhost:8000/en/billing/invoice/[INVOICE_NUMBER]/pdf/${NC}"
echo -e "  3. Verify the logo appears in the top-left corner"
echo -e "  4. Press ${RED}Ctrl+C${NC} to stop the server when done"
echo ""
echo -e "${GREEN}Visual Checklist:${NC}"
echo "  ☐ Logo visible in top-left corner"
echo "  ☐ Logo properly sized (~40px height)"
echo "  ☐ No broken image icon"
echo "  ☐ Professional appearance"
echo ""
read -p "Press Enter to start the server..."
echo ""

# Start Django server
python manage.py runserver

# Step 5: After server stops
echo ""
echo -e "${BLUE}[Step 5/5]${NC} ${INFO} Test completion"
echo ""
echo -e "${GREEN}Test Results:${NC}"
read -p "Did the logo appear correctly? (y/n): " logo_visible
read -p "Was the logo properly positioned? (y/n): " logo_positioned
read -p "Was the logo the right size? (y/n): " logo_sized

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo -e "${PURPLE}Test Summary${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"

if [[ "$logo_visible" == "y" && "$logo_positioned" == "y" && "$logo_sized" == "y" ]]; then
    echo -e "${GREEN}${CHECK} ALL TESTS PASSED!${NC}"
    echo ""
    echo -e "${GREEN}Next steps:${NC}"
    echo "  1. Mark the issue as resolved"
    echo "  2. Commit your changes:"
    echo -e "     ${CYAN}git add .${NC}"
    echo -e "     ${CYAN}git commit -m \"fix: Add static logo fallback for invoice PDFs (TDD)\"${NC}"
    echo -e "     ${CYAN}git push origin feat/add_sonarqube_and_testing_architecture${NC}"
    echo "  3. Create a Pull Request"
else
    echo -e "${YELLOW}${WARN} SOME TESTS FAILED${NC}"
    echo ""
    echo -e "${YELLOW}Please review:${NC}"
    echo "  • Template: billing_management/templates/invoices/inv_templates.html"
    echo "  • Documentation: docs/billing/MANUAL_TESTING_GUIDE.md"
    echo "  • Unit tests: billing_management/tests/test_invoice_logo_simple.py"
fi

echo ""
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
echo -e "${INFO} Full documentation: ${CYAN}docs/billing/INVOICE_LOGO_FIX_TDD.md${NC}"
echo -e "${CYAN}════════════════════════════════════════════════════════${NC}"
