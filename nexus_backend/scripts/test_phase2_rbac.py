#!/usr/bin/env python
"""
Phase 2 RBAC Migration Test Script
===================================

Tests the 6 commercial management views migrated in Phase 2:
1. create_subscription_plan() - admin + manager
2. edit_subscription() - admin + manager
3. get_subscription_plans() - admin + manager + sales (read-only for sales)
4. add_kit() - admin + manager
5. edit_kit() - admin + manager
6. get_kits() - admin + manager + sales + dispatcher

Expected Behavior:
- Admin users: Full access to all 6 views
- Manager users: Full access to all 6 views
- Sales users: Can VIEW plans and kits, BLOCKED from create/edit
- Dispatcher users: Can VIEW kits, BLOCKED from plans and create/edit
- Support users: BLOCKED from all Phase 2 views
- All access denials must be logged in audit logs

Usage:
    python scripts/test_phase2_rbac.py
"""

import os
import sys

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import django

django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from app_settings.views import (
    add_kit,
    create_subscription_plan,
    edit_kit,
    edit_subscription,
    get_kits,
    get_subscription_plans,
)
from main.models import UserRole

User = get_user_model()


class Phase2RBACTester:
    """Test harness for Phase 2 RBAC migration"""

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
                "/test/",
                data=data or {},
                content_type="multipart/form-data",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        else:
            request = self.factory.get("/test/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        request.user = user

        # Call view
        try:
            if "edit" in view_name or "pk" in str(view_func.__code__.co_varnames):
                # Views that take a pk parameter
                response = view_func(request, pk=1)
            else:
                response = view_func(request)

            # Check response (302 = denied, 200/400/404/500 = access granted)
            if should_pass:
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
                    self.record_test(
                        view_name,
                        user.username,
                        user.roles,
                        expected="PASS",
                        actual=f"PASS ({response.status_code})",
                        passed=True,
                    )
            else:
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
        print("\n" + "=" * 120)
        print("PHASE 2 RBAC MIGRATION TEST RESULTS")
        print("=" * 120)
        print(
            f"{'View Name':<35} {'User':<15} {'Roles':<25} {'Expected':<10} {'Actual':<15} {'Status':<10}"
        )
        print("-" * 120)

        for test in self.results["tests"]:
            status = "✓ PASS" if test["passed"] else "✗ FAIL"
            roles_str = ", ".join(test["roles"]) if test["roles"] else "none"
            print(
                f"{test['view']:<35} {test['user']:<15} {roles_str:<25} {test['expected']:<10} {test['actual']:<15} {status:<10}"
            )

        print("-" * 120)
        print(
            f"Total: {self.results['passed'] + self.results['failed']} | Passed: {self.results['passed']} | Failed: {self.results['failed']}"
        )
        print("=" * 120 + "\n")

        # Return exit code
        return 0 if self.results["failed"] == 0 else 1

    def run_all_tests(self):
        """Run all Phase 2 RBAC tests"""
        print("\n🔧 Creating test users...")

        # Create test users
        admin_user = self.create_test_user(
            "test_admin", [UserRole.ADMIN], is_staff=True
        )
        manager_user = self.create_test_user(
            "test_manager", [UserRole.MANAGER], is_staff=True
        )
        sales_user = self.create_test_user(
            "test_sales", [UserRole.SALES], is_staff=True
        )
        dispatcher_user = self.create_test_user(
            "test_dispatcher", [UserRole.DISPATCHER], is_staff=True
        )
        support_user = self.create_test_user(
            "test_support", [UserRole.SUPPORT], is_staff=True
        )

        print("✓ Test users created")
        print("\n🧪 Running Phase 2 tests...\n")

        # Test data
        plan_data = {
            "name": "Test Plan",
            "description": "Test Description",
            "data_cap_gb": "100",
            "price_usd": "50.00",
            "is_active": "true",
        }
        kit_data = {
            "name": "Test Kit",
            "model": "Starlink V2",
            "description": "Test Description",
            "price_usd": "500.00",
        }

        # Test 1: create_subscription_plan (admin + manager)
        print("Testing create_subscription_plan...")
        self.test_view(
            create_subscription_plan,
            "create_subscription_plan",
            admin_user,
            data=plan_data,
            should_pass=True,
        )
        self.test_view(
            create_subscription_plan,
            "create_subscription_plan",
            manager_user,
            data=plan_data,
            should_pass=True,
        )
        self.test_view(
            create_subscription_plan,
            "create_subscription_plan",
            sales_user,
            data=plan_data,
            should_pass=False,
        )
        self.test_view(
            create_subscription_plan,
            "create_subscription_plan",
            support_user,
            data=plan_data,
            should_pass=False,
        )

        # Test 2: edit_subscription (admin + manager)
        print("Testing edit_subscription...")
        self.test_view(
            edit_subscription,
            "edit_subscription",
            admin_user,
            data=plan_data,
            should_pass=True,
        )
        self.test_view(
            edit_subscription,
            "edit_subscription",
            manager_user,
            data=plan_data,
            should_pass=True,
        )
        self.test_view(
            edit_subscription,
            "edit_subscription",
            sales_user,
            data=plan_data,
            should_pass=False,
        )
        self.test_view(
            edit_subscription,
            "edit_subscription",
            support_user,
            data=plan_data,
            should_pass=False,
        )

        # Test 3: get_subscription_plans (admin + manager + sales)
        print("Testing get_subscription_plans...")
        self.test_view(
            get_subscription_plans,
            "get_subscription_plans",
            admin_user,
            method="GET",
            should_pass=True,
        )
        self.test_view(
            get_subscription_plans,
            "get_subscription_plans",
            manager_user,
            method="GET",
            should_pass=True,
        )
        self.test_view(
            get_subscription_plans,
            "get_subscription_plans",
            sales_user,
            method="GET",
            should_pass=True,
        )
        self.test_view(
            get_subscription_plans,
            "get_subscription_plans",
            support_user,
            method="GET",
            should_pass=False,
        )

        # Test 4: add_kit (admin + manager)
        print("Testing add_kit...")
        self.test_view(add_kit, "add_kit", admin_user, data=kit_data, should_pass=True)
        self.test_view(
            add_kit, "add_kit", manager_user, data=kit_data, should_pass=True
        )
        self.test_view(add_kit, "add_kit", sales_user, data=kit_data, should_pass=False)
        self.test_view(
            add_kit, "add_kit", support_user, data=kit_data, should_pass=False
        )

        # Test 5: edit_kit (admin + manager)
        print("Testing edit_kit...")
        self.test_view(
            edit_kit, "edit_kit", admin_user, data=kit_data, should_pass=True
        )
        self.test_view(
            edit_kit, "edit_kit", manager_user, data=kit_data, should_pass=True
        )
        self.test_view(
            edit_kit, "edit_kit", sales_user, data=kit_data, should_pass=False
        )
        self.test_view(
            edit_kit, "edit_kit", support_user, data=kit_data, should_pass=False
        )

        # Test 6: get_kits (admin + manager + sales + dispatcher)
        print("Testing get_kits...")
        self.test_view(get_kits, "get_kits", admin_user, method="GET", should_pass=True)
        self.test_view(
            get_kits, "get_kits", manager_user, method="GET", should_pass=True
        )
        self.test_view(get_kits, "get_kits", sales_user, method="GET", should_pass=True)
        self.test_view(
            get_kits, "get_kits", dispatcher_user, method="GET", should_pass=True
        )
        self.test_view(
            get_kits, "get_kits", support_user, method="GET", should_pass=False
        )

        # Print results
        return self.print_results()


def main():
    """Main entry point"""
    print("\n" + "=" * 120)
    print("NEXUS TELECOMS - Phase 2 RBAC Migration Test Suite")
    print("=" * 120)
    print("Testing commercial management views (subscription plans & Starlink kits)")
    print("Migration Date: 2025-11-06")
    print("=" * 120)

    tester = Phase2RBACTester()
    exit_code = tester.run_all_tests()

    if exit_code == 0:
        print("✅ All tests passed! Phase 2 migration successful.")
        print("\nNext Steps:")
        print("1. Review audit logs for access denials")
        print("2. Verify sales can view but not modify plans/kits")
        print("3. Proceed to Phase 3: Delete operations (admin-only)")
    else:
        print("❌ Some tests failed. Please review the results above.")
        print("\nTroubleshooting:")
        print("1. Check that all 6 views use @require_staff_role with correct roles")
        print("2. Verify user roles are correctly set in the database")
        print("3. Check that sales has read-only access (can GET but not POST)")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
