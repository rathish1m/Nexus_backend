#!/bin/bash

# Test Files Reorganization Script
# Reorganizes test files from project root to appropriate directories
# Following Django best practices

set -e

PROJECT_ROOT="/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend"
cd "$PROJECT_ROOT"

echo "========================================="
echo "Test Files Reorganization Script"
echo "========================================="
echo ""
echo "Purpose: Move test files to appropriate directories"
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
move_test_file() {
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

# Create test directories
ensure_dir "site_survey/tests"
ensure_dir "tech/tests"
ensure_dir "billing_management/tests"
ensure_dir "tests/integration/i18n"
ensure_dir "tests/integration/api"
ensure_dir "tests/integration/notifications"
ensure_dir "tests/e2e"

echo ""
echo "========================================="
echo "Phase 2: Move Site Survey Tests"
echo "========================================="
echo ""

move_test_file "test_survey_form.py" "site_survey/tests"
move_test_file "test_survey_validation.py" "site_survey/tests"
move_test_file "test_survey_validation_fix.py" "site_survey/tests"
move_test_file "test_complete_survey_validation.py" "site_survey/tests"
move_test_file "test_rejection_workflow.py" "site_survey/tests"
move_test_file "test_approval_request.py" "site_survey/tests"
move_test_file "test_weather_fields_fix.py" "site_survey/tests"
move_test_file "test_validation_preselected_fix.py" "site_survey/tests"
move_test_file "test_photo_upload_feature.py" "site_survey/tests"

echo ""
echo "========================================="
echo "Phase 3: Move Installation/Tech Tests"
echo "========================================="
echo ""

move_test_file "test_installation_logic.py" "tech/tests"
move_test_file "test_new_installation_workflow.py" "tech/tests"
move_test_file "test_simple_installation.py" "tech/tests"
move_test_file "test_reassignment.py" "tech/tests"
move_test_file "test_new_required_fields.py" "tech/tests"
move_test_file "test_additional_equipment_validation.py" "tech/tests"

echo ""
echo "========================================="
echo "Phase 4: Move Billing Tests"
echo "========================================="
echo ""

move_test_file "test_billing_approval.py" "billing_management/tests"
move_test_file "test_billing_workflow.py" "billing_management/tests"

echo ""
echo "========================================="
echo "Phase 5: Move Translation Tests"
echo "========================================="
echo ""

move_test_file "test_translations.py" "tests/integration/i18n"
move_test_file "test_dashboard_translations.py" "tests/integration/i18n"
move_test_file "test_complete_dashboard_translations.py" "tests/integration/i18n"

echo ""
echo "========================================="
echo "Phase 6: Move API Tests"
echo "========================================="
echo ""

move_test_file "test_edit_api.py" "tests/integration/api"
move_test_file "test_response_structure.py" "tests/integration/api"

echo ""
echo "========================================="
echo "Phase 7: Move Notification Tests"
echo "========================================="
echo ""

move_test_file "test_notifications.py" "tests/integration/notifications"

echo ""
echo "========================================="
echo "Phase 8: Move E2E/UI Tests"
echo "========================================="
echo ""

move_test_file "test_edit_window.py" "tests/e2e"

echo ""
echo "========================================="
echo "Phase 9: Create __init__.py Files"
echo "========================================="
echo ""

# Create __init__.py in all test directories
find . -type d -name tests -exec touch {}/__init__.py \; 2>/dev/null
touch tests/integration/__init__.py 2>/dev/null
touch tests/integration/i18n/__init__.py 2>/dev/null
touch tests/integration/api/__init__.py 2>/dev/null
touch tests/integration/notifications/__init__.py 2>/dev/null
touch tests/e2e/__init__.py 2>/dev/null

echo -e "${GREEN}✓ Created __init__.py files in all test directories${NC}"

echo ""
echo "========================================="
echo "Summary"
echo "========================================="
echo ""
echo -e "${GREEN}Successfully moved:${NC} $moved_count files"
echo -e "${RED}Failed:${NC} $failed_count files"
echo ""

if [ $failed_count -eq 0 ]; then
    echo -e "${GREEN}✓ Test reorganization complete!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run tests to verify: pytest"
    echo "  2. Check coverage: pytest --cov"
    echo "  3. Update documentation if needed"
    echo "  4. Commit changes"
else
    echo -e "${RED}✗ Some files failed to move${NC}"
    echo "Please check the errors above and resolve manually."
    exit 1
fi

echo ""
echo "========================================="
