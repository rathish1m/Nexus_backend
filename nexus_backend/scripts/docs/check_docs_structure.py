#!/usr/bin/env python3
"""
Documentation Structure Validator

This script validates the documentation structure and generates a report.
It checks for:
- Missing README files in subdirectories
- Broken links between documentation files
- Orphaned documentation files
- Documentation statistics

Usage:
    python check_docs_structure.py
"""

import re
from pathlib import Path
from typing import Dict, List

# ANSI color codes
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"


class DocsValidator:
    def __init__(self, docs_root: Path):
        self.docs_root = docs_root
        self.issues: List[str] = []
        self.warnings: List[str] = []
        self.stats: Dict[str, int] = {}

    def validate(self) -> bool:
        """Run all validation checks."""
        print(f"{BOLD}📚 NEXUS TELECOMS - Documentation Structure Validator{RESET}\n")
        print(f"Checking documentation in: {BLUE}{self.docs_root}{RESET}\n")

        all_ok = True

        # Check if docs directory exists
        if not self.docs_root.exists():
            print(f"{RED}✗ Documentation directory not found: {self.docs_root}{RESET}")
            return False

        # Run checks
        all_ok &= self.check_index_exists()
        all_ok &= self.check_subdirectory_readmes()
        all_ok &= self.check_file_organization()
        all_ok &= self.collect_statistics()
        all_ok &= self.check_broken_links()

        # Print report
        self.print_report()

        return all_ok

    def check_index_exists(self) -> bool:
        """Check if INDEX.md exists at docs root."""
        print(f"{BOLD}Checking for INDEX.md...{RESET}")
        index_path = self.docs_root / "INDEX.md"

        if index_path.exists():
            print(f"{GREEN}✓ INDEX.md found{RESET}")
            return True
        else:
            self.issues.append("Missing INDEX.md at docs root")
            print(f"{RED}✗ INDEX.md not found{RESET}")
            return False

    def check_subdirectory_readmes(self) -> bool:
        """Check if all subdirectories have README.md files."""
        print(f"\n{BOLD}Checking subdirectory README files...{RESET}")

        subdirs = [
            d
            for d in self.docs_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        missing_readmes = []

        for subdir in subdirs:
            readme_path = subdir / "README.md"
            if not readme_path.exists():
                missing_readmes.append(subdir.name)
                print(f"{RED}✗ Missing README.md in {subdir.name}/{RESET}")
            else:
                print(f"{GREEN}✓ README.md found in {subdir.name}/{RESET}")

        if missing_readmes:
            self.issues.append(f"Missing README.md in: {', '.join(missing_readmes)}")
            return False

        return True

    def check_file_organization(self) -> bool:
        """Check for .md files that should be in subdirectories."""
        print(f"\n{BOLD}Checking file organization...{RESET}")

        # Expected files at root
        allowed_root_files = {
            "INDEX.md",
            "PROJECT_FINAL_SUMMARY.md",
            "FINAL_SUMMARY.md",
            "BACKEND_IMPLEMENTATION_SUMMARY.md",
            "audit_codex_report.md",
            "DOCUMENTATION_REORGANIZATION.md",
        }

        root_md_files = [f for f in self.docs_root.glob("*.md")]
        misplaced_files = []

        for file_path in root_md_files:
            if file_path.name not in allowed_root_files:
                misplaced_files.append(file_path.name)
                print(
                    f"{YELLOW}⚠ Potentially misplaced file at root: {file_path.name}{RESET}"
                )

        if misplaced_files:
            self.warnings.append(
                f"Files at root that might belong in subdirectories: {', '.join(misplaced_files)}"
            )
        else:
            print(f"{GREEN}✓ All files properly organized{RESET}")

        return True

    def collect_statistics(self) -> bool:
        """Collect statistics about documentation."""
        print(f"\n{BOLD}Collecting statistics...{RESET}")

        # Count files by category
        subdirs = [
            d
            for d in self.docs_root.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]

        total_files = 0
        for subdir in subdirs:
            md_files = list(subdir.glob("*.md"))
            count = len(md_files)
            self.stats[subdir.name] = count
            total_files += count
            print(f"{BLUE}  {subdir.name}: {count} files{RESET}")

        # Count root files
        root_files = len(list(self.docs_root.glob("*.md")))
        self.stats["_root"] = root_files
        total_files += root_files

        self.stats["_total"] = total_files
        print(f"{GREEN}✓ Total documentation files: {total_files}{RESET}")

        return True

    def check_broken_links(self) -> bool:
        """Check for broken internal links (basic check)."""
        print(f"\n{BOLD}Checking for potential broken links...{RESET}")

        # This is a simplified check
        # A full check would parse markdown and validate all links

        all_md_files = list(self.docs_root.rglob("*.md"))
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

        broken_links = []

        for md_file in all_md_files:
            try:
                content = md_file.read_text(encoding="utf-8")
                matches = link_pattern.findall(content)

                for link_text, link_url in matches:
                    # Only check relative markdown links
                    if link_url.endswith(".md") and not link_url.startswith("http"):
                        # Resolve relative path
                        target_path = (md_file.parent / link_url).resolve()

                        if not target_path.exists():
                            broken_links.append(
                                f"{md_file.relative_to(self.docs_root)} → {link_url}"
                            )
            except Exception as e:
                self.warnings.append(f"Could not check links in {md_file.name}: {e}")

        if broken_links:
            print(
                f"{YELLOW}⚠ Found {len(broken_links)} potentially broken links{RESET}"
            )
            for link in broken_links[:5]:  # Show first 5
                print(f"{YELLOW}  - {link}{RESET}")
            if len(broken_links) > 5:
                print(f"{YELLOW}  ... and {len(broken_links) - 5} more{RESET}")
            self.warnings.append(f"Found {len(broken_links)} potentially broken links")
        else:
            print(f"{GREEN}✓ No broken links detected{RESET}")

        return True

    def print_report(self):
        """Print validation report."""
        print(f"\n{BOLD}{'='*60}{RESET}")
        print(f"{BOLD}📊 VALIDATION REPORT{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")

        # Statistics
        print(f"{BOLD}📈 Documentation Statistics:{RESET}")
        for category, count in sorted(self.stats.items()):
            if category.startswith("_"):
                continue
            print(f"  {category}: {count} files")
        print(
            f"\n  {BOLD}Total: {self.stats.get('_total', 0)} documentation files{RESET}\n"
        )

        # Issues
        if self.issues:
            print(f"{RED}{BOLD}❌ Issues Found ({len(self.issues)}):{RESET}")
            for issue in self.issues:
                print(f"{RED}  • {issue}{RESET}")
            print()
        else:
            print(f"{GREEN}{BOLD}✅ No critical issues found{RESET}\n")

        # Warnings
        if self.warnings:
            print(f"{YELLOW}{BOLD}⚠️  Warnings ({len(self.warnings)}):{RESET}")
            for warning in self.warnings:
                print(f"{YELLOW}  • {warning}{RESET}")
            print()
        else:
            print(f"{GREEN}{BOLD}✅ No warnings{RESET}\n")

        # Summary
        print(f"{BOLD}{'='*60}{RESET}")
        if not self.issues and not self.warnings:
            print(f"{GREEN}{BOLD}🎉 Documentation structure is perfect!{RESET}")
        elif not self.issues:
            print(
                f"{YELLOW}{BOLD}⚠️  Documentation structure is good with minor warnings{RESET}"
            )
        else:
            print(f"{RED}{BOLD}❌ Documentation structure needs attention{RESET}")
        print(f"{BOLD}{'='*60}{RESET}\n")


def main():
    """Main entry point."""
    # Determine docs root - go up to project root then to docs
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent  # scripts/docs/ -> scripts/ -> project root
    docs_root = project_root / "docs"

    # Run validation
    validator = DocsValidator(docs_root)
    success = validator.validate()

    # Exit with appropriate code
    exit(0 if success and not validator.issues else 1)


if __name__ == "__main__":
    main()
