#!/usr/bin/env python
"""
Phase 1 RBAC Migration Test Script
===================================

Tests the 5 critical views migrated in Phase 1:
1. company_settings_update() - admin only
2. billing_config_save() - admin only
3. taxes_add() - admin + finance
4. payments_method_add() - admin + finance
5. installation_fee_add() - admin + finance

Expected Behavior:
- Admin users: Full access to all 5 views
- Finance users: Access to financial views (taxes, payments, fees), BLOCKED from system config
- Sales/Support users: BLOCKED from all Phase 1 views
- All access denials must be logged in audit logs

Usage:
    python scripts/test_phase1_rbac.py
"""

import json
import os
import sys

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from app_settings.views import (
    billing_config_save,
    company_settings_update,
    installation_fee_add,
    payments_method_add,
    taxes_add,
)
from main.models import UserRole

User = get_user_model()


class Phase1RBACTester:
    """Test harness for Phase 1 RBAC migration"""

    def __init__(self):
        self.factory = RequestFactory()
        self.results = {"passed": 0, "failed": 0, "tests": []}

    def create_test_user(self, username, roles, is_staff=True, is_superuser=False):
        """Create or get a test user with specified roles"""
        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": f"{username}@test.com",
                "is_staff": is_staff,
                "is_superuser": is_superuser,
                "roles": roles if isinstance(roles, list) else [roles],
            },
        )
        if not created:
            user.roles = roles if isinstance(roles, list) else [roles]
            user.is_staff = is_staff
            user.is_superuser = is_superuser
            user.save()
        return user

    def test_view(
        self, view_func, view_name, user, method="POST", data=None, should_pass=True
    ):
        """Test a single view with a specific user"""
        # Create request
        if method == "POST":
            request = self.factory.post(
                "/test/", data=json.dumps(data or {}), content_type="application/json"
            )
        else:
            request = self.factory.get("/test/")

        request.user = user

        # Call view
        try:
            response = view_func(request)

            # Check response
            # user_passes_test returns 302 redirect for denied access (not 403)
            # Successful responses are usually 200 or might be validation errors (400)
            if should_pass:
                # For successful access, we expect NOT a redirect (302)
                if response.status_code == 302:
                    self.record_test(
                        view_name,
                        user.username,
                        user.roles,
                        expected="PASS",
                        actual="BLOCKED (302 redirect)",
                        passed=False,
                    )
                else:
                    # Could be 200 (success) or 400 (validation error) - both are "access granted"
                    self.record_test(
                        view_name,
                        user.username,
                        user.roles,
                        expected="PASS",
                        actual=f"PASS ({response.status_code})",
                        passed=True,
                    )
            else:
                # For denied access, we expect a redirect (302) to login page
                if response.status_code == 302:
                    self.record_test(
                        view_name,
                        user.username,
                        user.roles,
                        expected="BLOCKED",
                        actual="BLOCKED (302 redirect)",
                        passed=True,
                    )
                else:
                    # If no redirect, access was granted when it shouldn't be
                    self.record_test(
                        view_name,
                        user.username,
                        user.roles,
                        expected="BLOCKED",
                        actual=f"PASS ({response.status_code})",
                        passed=False,
                    )
        except Exception as e:
            self.record_test(
                view_name,
                user.username,
                user.roles,
                expected="PASS" if should_pass else "BLOCKED",
                actual=f"ERROR: {str(e)}",
                passed=False,
            )

    def record_test(self, view_name, username, roles, expected, actual, passed):
        """Record a test result"""
        self.results["tests"].append(
            {
                "view": view_name,
                "user": username,
                "roles": roles,
                "expected": expected,
                "actual": actual,
                "passed": passed,
            }
        )
        if passed:
            self.results["passed"] += 1
        else:
            self.results["failed"] += 1

    def print_results(self):
        """Print test results in a formatted table"""
        print("\n" + "=" * 100)
        print("PHASE 1 RBAC MIGRATION TEST RESULTS")
        print("=" * 100)
        print(
            f"{'View Name':<30} {'User':<15} {'Roles':<20} {'Expected':<10} {'Actual':<10} {'Status':<10}"
        )
        print("-" * 100)

        for test in self.results["tests"]:
            status = "✓ PASS" if test["passed"] else "✗ FAIL"
            roles_str = ", ".join(test["roles"]) if test["roles"] else "none"
            print(
                f"{test['view']:<30} {test['user']:<15} {roles_str:<20} {test['expected']:<10} {test['actual']:<10} {status:<10}"
            )

        print("-" * 100)
        print(
            f"Total: {self.results['passed'] + self.results['failed']} | Passed: {self.results['passed']} | Failed: {self.results['failed']}"
        )
        print("=" * 100 + "\n")

        # Return exit code
        return 0 if self.results["failed"] == 0 else 1

    def run_all_tests(self):
        """Run all Phase 1 RBAC tests"""
        print("\n🔧 Creating test users...")

        # Create test users
        admin_user = self.create_test_user(
            "test_admin", [UserRole.ADMIN], is_staff=True
        )
        finance_user = self.create_test_user(
            "test_finance", [UserRole.FINANCE], is_staff=True
        )
        sales_user = self.create_test_user(
            "test_sales", [UserRole.SALES], is_staff=True
        )
        support_user = self.create_test_user(
            "test_support", [UserRole.SUPPORT], is_staff=True
        )

        print("✓ Test users created")
        print("\n🧪 Running Phase 1 tests...\n")

        # Test data for different views
        tax_data = {"description": "Test Tax", "percentage": 10}
        payment_data = {"name": "Test Payment", "description": "Test Description"}
        fee_data = {"region": "Test Region", "amount_usd": 100}
        billing_data = {"billing_day": 1, "grace_days": 7, "send_reminders": True}

        # Test 1: company_settings_update (admin only)
        print("Testing company_settings_update...")
        self.test_view(
            company_settings_update,
            "company_settings_update",
            admin_user,
            should_pass=True,
        )
        self.test_view(
            company_settings_update,
            "company_settings_update",
            finance_user,
            should_pass=False,
        )
        self.test_view(
            company_settings_update,
            "company_settings_update",
            sales_user,
            should_pass=False,
        )
        self.test_view(
            company_settings_update,
            "company_settings_update",
            support_user,
            should_pass=False,
        )

        # Test 2: billing_config_save (admin only)
        print("Testing billing_config_save...")
        self.test_view(
            billing_config_save,
            "billing_config_save",
            admin_user,
            data=billing_data,
            should_pass=True,
        )
        self.test_view(
            billing_config_save,
            "billing_config_save",
            finance_user,
            data=billing_data,
            should_pass=False,
        )
        self.test_view(
            billing_config_save,
            "billing_config_save",
            sales_user,
            data=billing_data,
            should_pass=False,
        )
        self.test_view(
            billing_config_save,
            "billing_config_save",
            support_user,
            data=billing_data,
            should_pass=False,
        )

        # Test 3: taxes_add (admin + finance)
        print("Testing taxes_add...")
        self.test_view(
            taxes_add, "taxes_add", admin_user, data=tax_data, should_pass=True
        )
        self.test_view(
            taxes_add, "taxes_add", finance_user, data=tax_data, should_pass=True
        )
        self.test_view(
            taxes_add, "taxes_add", sales_user, data=tax_data, should_pass=False
        )
        self.test_view(
            taxes_add, "taxes_add", support_user, data=tax_data, should_pass=False
        )

        # Test 4: payments_method_add (admin + finance)
        print("Testing payments_method_add...")
        self.test_view(
            payments_method_add,
            "payments_method_add",
            admin_user,
            data=payment_data,
            should_pass=True,
        )
        self.test_view(
            payments_method_add,
            "payments_method_add",
            finance_user,
            data=payment_data,
            should_pass=True,
        )
        self.test_view(
            payments_method_add,
            "payments_method_add",
            sales_user,
            data=payment_data,
            should_pass=False,
        )
        self.test_view(
            payments_method_add,
            "payments_method_add",
            support_user,
            data=payment_data,
            should_pass=False,
        )

        # Test 5: installation_fee_add (admin + finance)
        print("Testing installation_fee_add...")
        self.test_view(
            installation_fee_add,
            "installation_fee_add",
            admin_user,
            data=fee_data,
            should_pass=True,
        )
        self.test_view(
            installation_fee_add,
            "installation_fee_add",
            finance_user,
            data=fee_data,
            should_pass=True,
        )
        self.test_view(
            installation_fee_add,
            "installation_fee_add",
            sales_user,
            data=fee_data,
            should_pass=False,
        )
        self.test_view(
            installation_fee_add,
            "installation_fee_add",
            support_user,
            data=fee_data,
            should_pass=False,
        )

        # Print results
        return self.print_results()


def main():
    """Main entry point"""
    print("\n" + "=" * 100)
    print("NEXUS TELECOMS - Phase 1 RBAC Migration Test Suite")
    print("=" * 100)
    print("Testing critical financial and system configuration views")
    print("Migration Date: 2025-11-06")
    print("=" * 100)

    tester = Phase1RBACTester()
    exit_code = tester.run_all_tests()

    if exit_code == 0:
        print("✅ All tests passed! Phase 1 migration successful.")
        print("\nNext Steps:")
        print("1. Review audit logs for access denials")
        print("2. Test in staging environment with real user accounts")
        print("3. Proceed to Phase 2: Plans & Kits migration")
    else:
        print("❌ Some tests failed. Please review the results above.")
        print("\nTroubleshooting:")
        print("1. Check that user.permissions.require_staff_role is properly imported")
        print("2. Verify user roles are correctly set in the database")
        print("3. Check decorator syntax in app_settings/views.py")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
