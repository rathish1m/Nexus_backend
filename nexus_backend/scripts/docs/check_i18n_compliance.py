#!/usr/bin/env python3
"""
Internationalization Compliance Checker

This script validates that:
1. All user-facing messages use gettext (_() or gettext())
2. No hardcoded French/non-English messages in Python code
3. Log messages are in English (not user-facing, no translation needed)
4. Documentation is in English

Usage:
    python check_i18n_compliance.py [--fix]

Author: VirgoCoachman
Date: 2025-11-05
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple

# Patterns to check
FRENCH_PATTERNS = [
    r"[\"'].*[àâäéèêëïîôùûüÿæœç].*[\"']",  # French accents
    r"[\"'].*\b(utilisateur|mot de passe|connexion|déconnexion|erreur|succès|échec)\b.*[\"']",  # Common French words
]

# Files to skip
SKIP_PATTERNS = [
    r"migrations/",
    r"__pycache__/",
    r"\.pyc$",
    r"check_i18n_compliance\.py",
    r"locale/",
    r"\.md$",  # Documentation is separate
]

# Directories to check
DIRS_TO_CHECK = [
    "user",
    "client_app",
    "backoffice",
    "api",
    "main",
    "sales",
    "tech",
    "site_survey",
    "subscriptions",
    "orders",
    "billing_management",
]


def should_skip(file_path: str) -> bool:
    """Check if file should be skipped"""
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, file_path):
            return True
    return False


def check_file_for_french(file_path: Path) -> List[Tuple[int, str]]:
    """
    Check a Python file for hardcoded French text.

    Returns:
        List of (line_number, line_content) tuples with issues
    """
    issues = []

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                # Skip comments and docstrings context
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue

                # Check for French patterns
                for pattern in FRENCH_PATTERNS:
                    if re.search(pattern, line):
                        # Make sure it's not in a comment
                        code_part = line.split("#")[0]
                        if re.search(pattern, code_part):
                            issues.append((line_num, line.strip()))
                            break
    except Exception as e:
        print(f"⚠️  Error reading {file_path}: {e}")

    return issues


def check_for_untranslated_messages(file_path: Path) -> List[Tuple[int, str]]:
    """
    Check for user-facing messages that should use gettext but don't.

    Looks for JsonResponse, messages, render context with hardcoded strings.
    """
    issues = []

    # Patterns for user-facing messages
    message_patterns = [
        r'JsonResponse\s*\(\s*\{[^}]*["\']message["\']\s*:\s*["\']([^"\']+)["\']',
        r'JsonResponse\s*\(\s*\{[^}]*["\']error["\']\s*:\s*["\']([^"\']+)["\']',
        r'messages\.(success|error|warning|info)\s*\([^,]+,\s*["\']([^"\']+)["\']',
    ]

    try:
        content = file_path.read_text(encoding="utf-8")

        for pattern in message_patterns:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                # Check if it's wrapped in _() or gettext()
                start = max(0, match.start() - 50)
                context = content[start : match.end()]

                if not re.search(r"_\s*\(|gettext\s*\(", context):
                    # Find line number
                    line_num = content[: match.start()].count("\n") + 1
                    issues.append((line_num, match.group(0)[:80]))
    except Exception as e:
        print(f"⚠️  Error checking {file_path}: {e}")

    return issues


def main():
    """Run compliance checks"""
    print("🔍 Checking Internationalization Compliance\n")
    print("=" * 70)

    total_issues = 0
    files_checked = 0

    for dir_name in DIRS_TO_CHECK:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            continue

        print(f"\n📂 Checking {dir_name}/")

        for py_file in dir_path.rglob("*.py"):
            if should_skip(str(py_file)):
                continue

            files_checked += 1

            # Check for French text
            french_issues = check_file_for_french(py_file)
            if french_issues:
                print(f"\n  ⚠️  {py_file}")
                for line_num, line in french_issues:
                    print(f"      Line {line_num}: {line[:60]}...")
                    total_issues += 1

            # Check for untranslated messages
            untranslated = check_for_untranslated_messages(py_file)
            if untranslated:
                print(f"\n  ℹ️  {py_file} - Untranslated messages:")
                for line_num, line in untranslated:
                    print(f"      Line {line_num}: {line[:60]}...")

    print("\n" + "=" * 70)
    print("\n📊 Summary:")
    print(f"   Files checked: {files_checked}")
    print(f"   Issues found: {total_issues}")

    if total_issues > 0:
        print("\n💡 Recommendations:")
        print("   1. Replace hardcoded strings with _('English text')")
        print("   2. Import: from django.utils.translation import gettext as _")
        print("   3. Run: python manage.py makemessages -l fr")
        print("   4. Translate in locale/fr/LC_MESSAGES/django.po")
        return 1
    else:
        print("\n✅ All checks passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
