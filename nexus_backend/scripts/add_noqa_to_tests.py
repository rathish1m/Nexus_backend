#!/usr/bin/env python
"""Add ruff noqa comment to test files that need Django setup."""

import os

# Test files that need Django setup before imports
TEST_FILES = [
    "billing_management/tests/test_billing_approval.py",
    "billing_management/tests/test_billing_workflow.py",
    "site_survey/tests/test_approval_request.py",
    "site_survey/tests/test_photo_upload_feature.py",
    "site_survey/tests/test_survey_validation.py",
    "tech/tests/test_installation_logic.py",
    "tech/tests/test_new_installation_workflow.py",
    "tech/tests/test_simple_installation.py",
    "tests/e2e/test_edit_window.py",
    "tests/integration/api/test_edit_api.py",
    "tests/integration/api/test_response_structure.py",
    "tests/integration/i18n/test_complete_dashboard_translations.py",
    "tests/integration/i18n/test_dashboard_translations.py",
    "tests/integration/i18n/test_translations.py",
    "tests/integration/notifications/test_notifications.py",
]

NOQA_COMMENT = "# ruff: noqa: E402\n"


def add_noqa_to_file(filepath):
    """Add noqa comment to file if not already present."""
    if not os.path.exists(filepath):
        print(f"⊘ File not found: {filepath}")
        return False

    with open(filepath, "r") as f:
        content = f.read()

    # Check if already has the comment
    if "ruff: noqa: E402" in content:
        print(f"✓ Already has noqa: {filepath}")
        return True

    # Add comment after shebang if present, otherwise at the beginning
    lines = content.split("\n")
    if lines[0].startswith("#!"):
        # Insert after shebang and docstring
        insert_pos = 1
        # Skip docstring if present
        if len(lines) > 1 and '"""' in lines[1]:
            for i in range(2, len(lines)):
                if '"""' in lines[i]:
                    insert_pos = i + 1
                    break
        lines.insert(insert_pos, NOQA_COMMENT)
    else:
        lines.insert(0, NOQA_COMMENT)

    with open(filepath, "w") as f:
        f.write("\n".join(lines))

    print(f"✓ Added noqa to: {filepath}")
    return True


def main():
    """Add noqa comments to all test files."""
    project_root = (
        "/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend"
    )
    os.chdir(project_root)

    print("=" * 50)
    print("Adding ruff noqa comments to test files")
    print("=" * 50)
    print()

    success_count = 0
    for test_file in TEST_FILES:
        if add_noqa_to_file(test_file):
            success_count += 1

    print()
    print("=" * 50)
    print(f"✓ Successfully processed: {success_count}/{len(TEST_FILES)} files")
    print("=" * 50)


if __name__ == "__main__":
    main()
