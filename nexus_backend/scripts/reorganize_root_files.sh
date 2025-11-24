#!/bin/bash

# Root Files Reorganization Script
# Moves utility scripts from project root to organized subdirectories
# Following Django best practices

set -e

PROJECT_ROOT="/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend"
cd "$PROJECT_ROOT"

echo "========================================="
echo "Root Files Reorganization Script"
echo "========================================="
echo ""
echo "Purpose: Organize utility scripts into categorized directories"
echo "Date: $(date)"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

moved_count=0
failed_count=0

# Function to move file
move_script() {
    local file="$1"
    local target_dir="$2"

    if [ ! -f "$file" ]; then
        echo -e "${YELLOW}  ⊘ File not found: $file${NC}"
        return
    fi

    echo -n "  Moving $(basename "$file") → $target_dir/... "

    if mv "$file" "$target_dir/" 2>/dev/null; then
        echo -e "${GREEN}✓${NC}"
        ((moved_count++))
    else
        echo -e "${RED}✗ FAILED${NC}"
        ((failed_count++))
    fi
}

# Function to create directory if it doesn't exist
ensure_dir() {
    local dir="$1"
    if [ ! -d "$dir" ]; then
        echo -e "${BLUE}Creating directory: $dir${NC}"
        mkdir -p "$dir"
    fi
}

echo "========================================="
echo "Phase 1: Create Directory Structure"
echo "========================================="
echo ""

# Create script directories
ensure_dir "scripts/docs"
ensure_dir "scripts/dev"
ensure_dir "scripts/data"
ensure_dir "scripts/fixes"

echo ""
echo "========================================="
echo "Phase 2: Move Documentation Scripts"
echo "========================================="
echo ""

move_script "check_docs_structure.py" "scripts/docs"
move_script "check_filename_i18n.py" "scripts/docs"
move_script "check_i18n_compliance.py" "scripts/docs"
move_script "browse_docs.sh" "scripts/docs"

echo ""
echo "========================================="
echo "Phase 3: Move Development Scripts"
echo "========================================="
echo ""

move_script "analyze_rejection_workflow.py" "scripts/dev"
move_script "demo_new_installation_logic.py" "scripts/dev"
move_script "verify_photo_upload.py" "scripts/dev"

echo ""
echo "========================================="
echo "Phase 4: Move Data Management Scripts"
echo "========================================="
echo ""

move_script "check_inventory.py" "scripts/data"
move_script "check_signal_duplicates.py" "scripts/data"
move_script "clean_duplicates.py" "scripts/data"
move_script "create_extra_charge_test_data.py" "scripts/data"
move_script "create_test_installation.py" "scripts/data"

echo ""
echo "========================================="
echo "Phase 5: Move Fix/Migration Scripts"
echo "========================================="
echo ""

move_script "fix_billing_customers.py" "scripts/fixes"
move_script "verify_billing_creation.py" "scripts/fixes"

echo ""
echo "========================================="
echo "Phase 6: Create __init__.py Files"
echo "========================================="
echo ""

# Create __init__.py in all script directories
touch scripts/docs/__init__.py 2>/dev/null
touch scripts/dev/__init__.py 2>/dev/null
touch scripts/data/__init__.py 2>/dev/null
touch scripts/fixes/__init__.py 2>/dev/null

echo -e "${GREEN}✓ Created __init__.py files in all script directories${NC}"

echo ""
echo "========================================="
echo "Phase 7: Verification"
echo "========================================="
echo ""

# Count remaining scripts at root (excluding essential files)
remaining=$(find . -maxdepth 1 -type f \( -name "*.py" -o -name "*.sh" \) ! -name "manage.py" ! -name "conftest.py" | wc -l)

echo "Essential files at root (should remain):"
echo "  - manage.py"
echo "  - conftest.py"
echo "  - pytest.ini"
echo "  - README.md"
echo "  - requirements*.txt"
echo "  - runtime.txt"
echo "  - Makefile"
echo "  - Dockerfile"
echo ""
echo "Utility scripts remaining at root: $remaining"
if [ "$remaining" -eq 0 ]; then
    echo -e "${GREEN}✓ All utility scripts successfully moved!${NC}"
else
    echo -e "${YELLOW}⚠ Some scripts remain at root (may be intentional)${NC}"
fi

echo ""
echo "========================================="
echo "Summary"
echo "========================================="
echo ""
echo -e "${GREEN}Successfully moved:${NC} $moved_count files"
echo -e "${RED}Failed:${NC} $failed_count files"
echo ""

if [ $failed_count -eq 0 ]; then
    echo -e "${GREEN}✓ Root files reorganization complete!${NC}"
    echo ""
    echo "New structure:"
    echo "  scripts/docs/    - Documentation validation scripts (4)"
    echo "  scripts/dev/     - Development/debugging scripts (3)"
    echo "  scripts/data/    - Data management scripts (5)"
    echo "  scripts/fixes/   - Migration/fix scripts (2)"
    echo ""
    echo "Next steps:"
    echo "  1. Update Makefile references"
    echo "  2. Test script execution"
    echo "  3. Update documentation"
    echo "  4. Commit changes"
else
    echo -e "${RED}✗ Some files failed to move${NC}"
    echo "Please check the errors above and resolve manually."
    exit 1
fi

echo ""
echo "========================================="
