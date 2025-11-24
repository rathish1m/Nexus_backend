#!/bin/bash

# Script to rename French documentation filenames to English
# Following i18n best practices: English as source of truth
# Date: November 5, 2025

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DOCS_DIR="$PROJECT_ROOT/docs"

echo "========================================="
echo "Documentation Filename Cleanup Script"
echo "========================================="
echo ""
echo "Purpose: Rename French filenames to English (i18n compliance)"
echo "Project: NEXUS TELECOMS Backend"
echo "Date: $(date)"
echo ""

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Counter
renamed_count=0
failed_count=0

# Function to rename a file
rename_file() {
    local old_path="$1"
    local new_path="$2"

    if [ -f "$old_path" ]; then
        echo -n "  Renaming: $(basename "$old_path") → $(basename "$new_path")... "

        # Try git mv first (preserves history)
        if git mv "$old_path" "$new_path" 2>/dev/null; then
            echo -e "${GREEN}✓ (git mv)${NC}"
            ((renamed_count++))
        # Fall back to regular mv
        elif mv "$old_path" "$new_path" 2>/dev/null; then
            echo -e "${GREEN}✓ (mv)${NC}"
            ((renamed_count++))
        else
            echo -e "${RED}✗ FAILED${NC}"
            ((failed_count++))
        fi
    else
        echo -e "  ${YELLOW}⊘ File not found: $(basename "$old_path")${NC}"
    fi
}

# Change to project root
cd "$PROJECT_ROOT"

echo "========================================="
echo "Phase 1: Translation Documentation"
echo "========================================="
echo ""

cd "$DOCS_DIR/translations"

rename_file "GUIDE_BONNES_PRATIQUES_TRADUCTION.md" "TRANSLATION_BEST_PRACTICES.md"
rename_file "GESTION_DONNEES_BDD_TRADUCTION.md" "DATABASE_TRANSLATION_MANAGEMENT.md"
rename_file "OPTIMISATION_TRADUCTIONS.md" "TRANSLATION_OPTIMIZATIONS.md"
rename_file "FINALISATION_INTERNATIONALISATION.md" "I18N_FINALIZATION.md"
rename_file "CORRECTION_TRADUCTIONS_LOGIN_FINAL.md" "LOGIN_TRANSLATION_FIXES.md"
rename_file "CORRECTION_TRADUCTIONS_CLIENT_FINAL.md" "CLIENT_AREA_TRANSLATION_FIXES.md"
rename_file "CORRECTION_TEXTES_ABONNEMENTS.md" "SUBSCRIPTION_TEXT_CORRECTIONS.md"
rename_file "CORRECTION_SELECTEUR_LANGUE.md" "LANGUAGE_SELECTOR_FIXES.md"

echo ""
echo "========================================="
echo "Phase 2: Feature Documentation"
echo "========================================="
echo ""

cd "$DOCS_DIR/features"

rename_file "CORRECTION_DASHBOARD_FINAL.md" "DASHBOARD_CORRECTIONS.md"
rename_file "CORRECTION_FINALE_COLONNES_TABLEAU.md" "TABLE_COLUMN_FIXES.md"
rename_file "CORRECTION_COMPLEMENT_ABONNEMENTS.md" "SUBSCRIPTION_ENHANCEMENTS.md"
rename_file "OPTIMISATION_RESULTATS.md" "RESULTS_OPTIMIZATION.md"

echo ""
echo "========================================="
echo "Summary"
echo "========================================="
echo ""
echo -e "${GREEN}Successfully renamed:${NC} $renamed_count files"
echo -e "${RED}Failed:${NC} $failed_count files"
echo ""

if [ $failed_count -eq 0 ]; then
    echo -e "${GREEN}✓ All files renamed successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Update INDEX.md with new filenames"
    echo "  2. Update README.md files in each directory"
    echo "  3. Search for broken links: grep -r 'GUIDE_BONNES_PRATIQUES' docs/"
    echo "  4. Run validation: python scripts/validate_docs_structure.py"
    echo "  5. Commit changes: git commit -m 'docs: rename French filenames to English'"
else
    echo -e "${RED}✗ Some files failed to rename${NC}"
    echo "Please check the errors above and resolve manually."
    exit 1
fi

echo ""
echo "========================================="
