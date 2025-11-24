#!/bin/bash
#
# i18n-onboarding.sh - Internationalization Onboarding Script
#
# This script helps new developers understand and set up the i18n workflow
# for the Nexus Telecom project. It provides guided assistance for translation
# management and common i18n tasks.
#
# Usage: ./scripts/i18n-onboarding.sh
#
# Author: Nexus Telecom Development Team
# Version: 1.0.0

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo -e "${BOLD}${BLUE}🌍 Nexus Telecom - Internationalization Onboarding${RESET}"
echo -e "${BLUE}=================================================${RESET}"
echo ""

# Check current status
echo -e "${CYAN}📊 Current Translation Status:${RESET}"
"$SCRIPT_DIR/i18n-audit.sh" --quiet || true
echo ""

# Show available commands
echo -e "${CYAN}🔧 Available i18n Commands:${RESET}"
echo ""
echo -e "${GREEN}Basic Commands:${RESET}"
echo "  make i18n-audit        - View detailed translation coverage"
echo "  make i18n-extract      - Extract new translatable strings"
echo "  make i18n-compile      - Compile translation files"
echo "  make i18n-update       - Extract and compile (full update)"
echo ""
echo -e "${GREEN}Advanced Commands:${RESET}"
echo "  make i18n-audit-json   - JSON output for automation"
echo "  make i18n-check        - CI-friendly coverage check"
echo ""

# Show workflow
echo -e "${CYAN}📋 Typical i18n Workflow:${RESET}"
echo ""
echo -e "${YELLOW}1. Development Phase:${RESET}"
echo "   • Add {% trans \"Your text\" %} tags in templates"
echo "   • Use gettext() or _() functions in Python code"
echo "   • Run: make i18n-extract"
echo ""
echo -e "${YELLOW}2. Translation Phase:${RESET}"
echo "   • Edit files in locale/*/LC_MESSAGES/django.po"
echo "   • Add French translations for new msgid entries"
echo "   • Run: make i18n-compile"
echo ""
echo -e "${YELLOW}3. Quality Assurance:${RESET}"
echo "   • Run: make i18n-audit"
echo "   • Ensure coverage meets requirements (≥80%)"
echo "   • Test in both languages"
echo ""

# Show file structure
echo -e "${CYAN}📁 Project Structure:${RESET}"
echo ""
echo "nexus_backend/"
echo "├── locale/"
echo "│   ├── en/LC_MESSAGES/"
echo "│   │   ├── django.po     # English translations"
echo "│   │   └── django.mo     # Compiled English"
echo "│   └── fr/LC_MESSAGES/"
echo "│       ├── django.po     # French translations"
echo "│       └── django.mo     # Compiled French"
echo "├── scripts/"
echo "│   ├── i18n-audit.sh     # Translation audit tool"
echo "│   └── i18n-onboarding.sh # This onboarding script"
echo "└── Makefile              # Contains i18n-* targets"
echo ""

# Quick tips
echo -e "${CYAN}💡 Quick Tips:${RESET}"
echo ""
echo -e "${GREEN}Template Tags:${RESET}"
echo "  {% load i18n %}                    # At top of templates"
echo "  {% trans \"Simple text\" %}         # For simple strings"
echo "  {% blocktrans %}...{% endblocktrans %} # For complex content"
echo ""
echo -e "${GREEN}Python Code:${RESET}"
echo "  from django.utils.translation import gettext as _"
echo "  message = _(\"Your translatable text\")"
echo ""
echo -e "${GREEN}JavaScript:${RESET}"
echo "  // Use Django's i18n framework or template interpolation"
echo "  alert(\"{{ 'Your text'|escapejs }}\");"
echo ""

# Interactive menu
echo -e "${CYAN}🎯 What would you like to do?${RESET}"
echo ""
echo "1) View current translation status"
echo "2) Extract new translatable strings"
echo "3) Compile translation files"
echo "4) Full i18n update (extract + compile)"
echo "5) Open French translation file for editing"
echo "6) Run quality check"
echo "7) View this help again"
echo "8) Exit"
echo ""

read -p "Choose an option (1-8): " choice

case $choice in
    1)
        echo ""
        echo -e "${BLUE}Running translation audit...${RESET}"
        "$SCRIPT_DIR/i18n-audit.sh"
        ;;
    2)
        echo ""
        echo -e "${BLUE}Extracting translatable strings...${RESET}"
        cd "$PROJECT_ROOT"
        make i18n-extract
        ;;
    3)
        echo ""
        echo -e "${BLUE}Compiling translation files...${RESET}"
        cd "$PROJECT_ROOT"
        make i18n-compile
        ;;
    4)
        echo ""
        echo -e "${BLUE}Running full i18n update...${RESET}"
        cd "$PROJECT_ROOT"
        make i18n-update
        ;;
    5)
        echo ""
        echo -e "${BLUE}Opening French translation file...${RESET}"
        french_po="$PROJECT_ROOT/locale/fr/LC_MESSAGES/django.po"
        if [[ -f "$french_po" ]]; then
            if command -v code >/dev/null 2>&1; then
                code "$french_po"
                echo "Opened in VS Code"
            elif command -v nano >/dev/null 2>&1; then
                nano "$french_po"
            elif command -v vim >/dev/null 2>&1; then
                vim "$french_po"
            else
                echo "Please open: $french_po"
            fi
        else
            echo -e "${RED}French translation file not found: $french_po${RESET}"
        fi
        ;;
    6)
        echo ""
        echo -e "${BLUE}Running quality check...${RESET}"
        cd "$PROJECT_ROOT"
        make i18n-check
        ;;
    7)
        exec "$0"
        ;;
    8)
        echo ""
        echo -e "${GREEN}Happy translating! 🌍${RESET}"
        exit 0
        ;;
    *)
        echo ""
        echo -e "${RED}Invalid option. Please choose 1-8.${RESET}"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}✅ Task completed!${RESET}"
echo ""
echo -e "${CYAN}💡 Pro tip:${RESET} You can run this onboarding script anytime with:"
echo "   ./scripts/i18n-onboarding.sh"
echo ""
echo -e "${CYAN}📚 For more information:${RESET}"
echo "   • Django i18n docs: https://docs.djangoproject.com/en/stable/topics/i18n/"
echo "   • Project Makefile: make help"
echo ""
