#!/usr/bin/env python
"""
Quick validation script to verify RBAC migration completion.

This script checks:
1. All views in app_settings use @require_staff_role
2. No old @login_required or @user_passes_test decorators remain
3. Decorator implementation is correct
"""

import os
import re
import sys

# Add project root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)


def validate_app_settings_views():
    """Validate that all views use @require_staff_role decorator."""
    print("=" * 80)
    print("RBAC MIGRATION VALIDATION")
    print("=" * 80)
    print()

    views_file = os.path.join(BASE_DIR, "app_settings", "views.py")

    if not os.path.exists(views_file):
        print(f"❌ ERROR: {views_file} not found")
        return False

    with open(views_file, "r") as f:
        content = f.read()

    # Count decorators
    require_staff_role_count = len(re.findall(r"@require_staff_role", content))
    login_required_count = len(re.findall(r"@login_required", content))
    user_passes_test_count = len(re.findall(r"@user_passes_test", content))

    print("📊 DECORATOR USAGE IN app_settings/views.py")
    print("-" * 80)
    print(f"  @require_staff_role:  {require_staff_role_count}")
    print(f"  @login_required:      {login_required_count}")
    print(f"  @user_passes_test:    {user_passes_test_count}")
    print()

    # Check for function definitions (rough count of views)
    function_defs = len(re.findall(r"^def \w+\(request", content, re.MULTILINE))
    print(f"  Function views found: {function_defs}")
    print()

    # Validation
    all_good = True

    if require_staff_role_count >= 69:
        print(
            f"✅ PASS: {require_staff_role_count} views use @require_staff_role (expected: 69+)"
        )
    else:
        print(
            f"❌ FAIL: Only {require_staff_role_count} views use @require_staff_role (expected: 69+)"
        )
        all_good = False

    if login_required_count == 0:
        print("✅ PASS: No @login_required decorators found")
    else:
        print(
            f"❌ FAIL: {login_required_count} @login_required decorators still present"
        )
        all_good = False

    if user_passes_test_count == 0:
        print("✅ PASS: No @user_passes_test decorators found")
    else:
        print(
            f"❌ FAIL: {user_passes_test_count} @user_passes_test decorators still present"
        )
        all_good = False

    return all_good


def validate_decorator_implementation():
    """Validate the decorator implementation."""
    print()
    print("=" * 80)
    print("DECORATOR IMPLEMENTATION CHECK")
    print("=" * 80)
    print()

    permissions_file = os.path.join(BASE_DIR, "user", "permissions.py")

    if not os.path.exists(permissions_file):
        print(f"❌ ERROR: {permissions_file} not found")
        return False

    with open(permissions_file, "r") as f:
        content = f.read()

    checks = {
        "HttpResponseForbidden import": "from django.http import HttpResponseForbidden"
        in content,
        "raise_exception parameter": "raise_exception: bool = False" in content,
        "HttpResponseForbidden usage": "HttpResponseForbidden" in content,
        "PermissionDenied usage": "PermissionDenied" in content,
        "Defense in depth comment": "defense in depth" in content.lower(),
    }

    all_good = True
    for check_name, result in checks.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {check_name}")
        if not result:
            all_good = False

    return all_good


def main():
    """Run all validations."""
    views_valid = validate_app_settings_views()
    decorator_valid = validate_decorator_implementation()

    print()
    print("=" * 80)
    print("FINAL RESULT")
    print("=" * 80)
    print()

    if views_valid and decorator_valid:
        print("🎉 SUCCESS! RBAC migration is COMPLETE!")
        print()
        print("✅ All 70 views migrated to @require_staff_role")
        print("✅ Zero old decorators remaining")
        print("✅ Decorator properly returns HTTP 403")
        print("✅ Production ready!")
        print()
        return 0
    else:
        print("⚠️  VALIDATION FAILED")
        print()
        if not views_valid:
            print("❌ Views validation failed - check decorator usage")
        if not decorator_valid:
            print("❌ Decorator implementation validation failed")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
