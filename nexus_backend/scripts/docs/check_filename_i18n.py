#!/usr/bin/env python3
"""
i18n Filename Compliance Checker

Validates that all documentation filenames follow English naming convention.
This is part of the i18n best practice: English as source of truth.

Usage:
    python check_filename_i18n.py
"""

import re
from pathlib import Path
from typing import List, Tuple

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

# French words that should not appear in filenames
FRENCH_WORDS = [
    "CORRECTION",
    "TRADUCTION",
    "TRADUCTIONS",
    "OPTIMISATION",
    "FINALISATION",
    "GESTION",
    "DONNEES",
    "BDD",
    "BONNES",
    "PRATIQUES",
    "GUIDE",
    "COMPLEMENT",
    "SELECTEUR",
    "LANGUE",
    "TEXTES",
    "COLONNES",
    "TABLEAU",
    "RESULTATS",
    "ABONNEMENTS",
]

# Patterns for French naming
FRENCH_PATTERNS = [
    r"^CORRECTION_",  # CORRECTION_*
    r"_TRADUCTION",  # *_TRADUCTION*
    r"^OPTIMISATION_",  # OPTIMISATION_*
    r"^FINALISATION_",  # FINALISATION_*
    r"^GESTION_",  # GESTION_*
    r"^GUIDE_",  # GUIDE_* (unless it's GUIDE in English context)
]


def check_filename(filepath: Path) -> Tuple[bool, str]:
    """
    Check if a filename follows English naming convention.

    Returns:
        (is_valid, reason)
    """
    filename = filepath.name

    # Skip README and INDEX files
    if filename in ["README.md", "INDEX.md"]:
        return True, "Standard file"

    # Skip meta-documentation about reorganization
    if "REORGANIZATION" in filename or "REORGANISATION" in filename:
        return True, "Meta-documentation"

    # Check for French patterns
    for pattern in FRENCH_PATTERNS:
        if re.search(pattern, filename, re.IGNORECASE):
            return False, f"French pattern detected: {pattern}"

    # Check for French words (but allow CORRECTIONS which is English)
    words_in_filename = re.findall(r"[A-Z]+", filename)
    for word in words_in_filename:
        if word in FRENCH_WORDS and word not in ["CORRECTIONS", "GUIDE"]:
            return False, f"French word detected: {word}"

    return True, "Valid"


def main():
    """Main entry point."""
    print(f"{BOLD}🌍 i18n Filename Compliance Checker{RESET}\n")
    print("Checking: Documentation filenames for English-only naming\n")
    print(f"{BOLD}{'='*60}{RESET}\n")

    # Find project root - go up to project root then to docs
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent  # scripts/docs/ -> scripts/ -> project root
    docs_dir = project_root / "docs"

    if not docs_dir.exists():
        print(f"{RED}✗ docs/ directory not found at {docs_dir}{RESET}")
        return 1

    # Collect all markdown files
    all_md_files = list(docs_dir.rglob("*.md"))

    valid_files: List[Path] = []
    invalid_files: List[Tuple[Path, str]] = []

    # Check each file
    for md_file in all_md_files:
        is_valid, reason = check_filename(md_file)

        if is_valid:
            valid_files.append(md_file)
        else:
            invalid_files.append((md_file, reason))

    # Print results
    print(f"{BOLD}📊 Results:{RESET}\n")

    # Valid files
    print(f"{GREEN}✓ Valid filenames: {len(valid_files)}{RESET}")
    if len(valid_files) <= 10:
        for f in valid_files:
            print(f"{GREEN}  ✓ {f.relative_to(docs_dir)}{RESET}")
    else:
        print(f"{BLUE}  (Showing first 5 of {len(valid_files)}){RESET}")
        for f in valid_files[:5]:
            print(f"{GREEN}  ✓ {f.relative_to(docs_dir)}{RESET}")

    print()

    # Invalid files
    if invalid_files:
        print(f"{RED}✗ Invalid filenames: {len(invalid_files)}{RESET}\n")
        for f, reason in invalid_files:
            print(f"{RED}  ✗ {f.relative_to(docs_dir)}{RESET}")
            print(f"{YELLOW}    Reason: {reason}{RESET}")
        print()
    else:
        print(f"{GREEN}✓ No invalid filenames found{RESET}\n")

    # Summary
    print(f"{BOLD}{'='*60}{RESET}")
    total = len(all_md_files)
    valid = len(valid_files)
    invalid = len(invalid_files)

    print(f"{BOLD}Summary:{RESET}")
    print(f"  Total files: {total}")
    print(f"  Valid: {GREEN}{valid}{RESET} ({100*valid//total if total else 0}%)")
    print(f"  Invalid: {RED}{invalid}{RESET} ({100*invalid//total if total else 0}%)")
    print()

    if invalid_files:
        print(f"{RED}{BOLD}❌ i18n filename compliance check FAILED{RESET}")
        print(f"\n{YELLOW}Suggestion:{RESET} Run scripts/rename_french_docs.sh to fix")
        return 1
    else:
        print(f"{GREEN}{BOLD}✅ i18n filename compliance check PASSED{RESET}")
        print(f"\n{GREEN}All filenames follow English naming convention!{RESET}")
        return 0


if __name__ == "__main__":
    exit(main())
