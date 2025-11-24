#!/usr/bin/env python3
"""
Script to extract and restore French translations from git history
while avoiding duplicate message issues.
"""

import subprocess
import sys
from pathlib import Path


def run_command(cmd, capture_output=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=capture_output, text=True, check=True
        )
        return result.stdout if capture_output else None
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed: {cmd}")
        print(f"Error: {e.stderr}")
        return None


def extract_translations_from_backup():
    """Extract translations from git history."""
    print("🔄 Extracting translations from git history...")

    # Get the old file content
    old_content = run_command("git show feecd15:locale/fr/LC_MESSAGES/django.po")
    if not old_content:
        print("❌ Failed to get old translations from git")
        return None

    # Parse msgid/msgstr pairs, handling duplicates by keeping first occurrence
    translations = {}
    current_msgid = None
    current_msgstr = None
    in_msgid = False
    in_msgstr = False

    for line in old_content.split("\n"):
        line = line.strip()

        # Skip comments and empty lines
        if line.startswith("#") or not line:
            continue

        # Start of msgid
        if line.startswith("msgid "):
            if current_msgid and current_msgstr and current_msgid not in translations:
                # Store previous translation if it was complete and unique
                if current_msgstr and current_msgstr != '""':
                    translations[current_msgid] = current_msgstr

            current_msgid = line[6:].strip()  # Remove 'msgid '
            current_msgstr = None
            in_msgid = True
            in_msgstr = False

        # Start of msgstr
        elif line.startswith("msgstr "):
            current_msgstr = line[7:].strip()  # Remove 'msgstr '
            in_msgid = False
            in_msgstr = True

        # Continuation lines
        elif line.startswith('"') and line.endswith('"'):
            if in_msgid and current_msgid:
                current_msgid += line
            elif in_msgstr and current_msgstr is not None:
                current_msgstr += line

    # Don't forget the last translation
    if current_msgid and current_msgstr and current_msgid not in translations:
        if current_msgstr and current_msgstr != '""':
            translations[current_msgid] = current_msgstr

    # Filter out empty translations
    valid_translations = {
        k: v
        for k, v in translations.items()
        if v and v != '""' and len(v.strip('"')) > 0
    }

    print(f"📊 Extracted {len(valid_translations)} unique translations")
    return valid_translations


def update_current_po_file(translations):
    """Update the current .po file with extracted translations."""
    po_file = Path("locale/fr/LC_MESSAGES/django.po")

    if not po_file.exists():
        print("❌ Current French .po file not found")
        return False

    print("🔧 Updating current .po file with restored translations...")

    # Read current file
    with open(po_file, "r", encoding="utf-8") as f:
        content = f.read()

    updated_count = 0
    lines = content.split("\n")
    result_lines = []
    i = 0

    while i < len(lines):
        line = lines[i]

        # Look for msgid lines
        if line.strip().startswith("msgid "):
            # Reconstruct the complete msgid (handling multiline)
            msgid_lines = [line]
            i += 1

            # Collect continuation lines for msgid
            while i < len(lines) and lines[i].strip().startswith('"'):
                msgid_lines.append(lines[i])
                i += 1

            # Reconstruct the msgid
            msgid = msgid_lines[0][msgid_lines[0].find("msgid ") + 6 :].strip()
            for msgid_line in msgid_lines[1:]:
                msgid += msgid_line.strip()

            # Add the msgid lines to result
            result_lines.extend(msgid_lines)

            # Look for corresponding msgstr
            if i < len(lines) and lines[i].strip().startswith("msgstr "):
                msgstr_line = lines[i]
                msgstr_lines = [msgstr_line]
                i += 1

                # Collect continuation lines for msgstr
                while i < len(lines) and lines[i].strip().startswith('"'):
                    msgstr_lines.append(lines[i])
                    i += 1

                # Check if we have a translation for this msgid
                if msgid in translations:
                    # Replace with our translation
                    result_lines.append(f"msgstr {translations[msgid]}")
                    updated_count += 1
                else:
                    # Keep original msgstr lines
                    result_lines.extend(msgstr_lines)

        else:
            result_lines.append(line)
            i += 1

    # Write back the updated content
    with open(po_file, "w", encoding="utf-8") as f:
        f.write("\n".join(result_lines))

    print(f"✅ Updated {updated_count} translations in the .po file")
    return True


def main():
    """Main function."""
    print("🚀 Starting French translation restoration...")

    # Change to project directory
    project_root = Path(__file__).parent.parent
    import os

    os.chdir(project_root)

    # Extract translations from backup
    translations = extract_translations_from_backup()
    if not translations:
        print("❌ Failed to extract translations")
        sys.exit(1)

    # Update current file
    if update_current_po_file(translations):
        print("🎉 Translation restoration completed successfully!")
        print("💡 Run 'make i18n-audit' to verify the results")
        print("🔧 Run 'make i18n-compile' to compile the translations")
    else:
        print("❌ Failed to update .po file")
        sys.exit(1)


if __name__ == "__main__":
    main()
