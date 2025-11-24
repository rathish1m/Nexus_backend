#!/usr/bin/env python
"""
Phase 3 RBAC Migration Test Script
===================================

Tests the 11 delete/toggle views migrated in Phase 3 (all admin-only):
1. delete_plan() - admin only
2. toggle_plan_status() - admin only
3. delete_kit() - admin only
4. delete_starlink_kit() - admin only
5. delete_subscription_plan() - admin only
6. toggle_subscription_plan_status() - admin only
7. delete_extra_charge() - admin only
8. delete_checklist_item() - admin only
9. coupon_delete() - admin only
10. coupon_toggle() - admin only
11. promotion_delete() - admin only
12. promotion_toggle() - admin only

Expected Behavior:
- Admin users: Full access to all delete/toggle operations
- Manager users: BLOCKED from all delete/toggle operations
- Sales users: BLOCKED from all delete/toggle operations
- All other roles: BLOCKED from all delete/toggle operations
- All access denials must be logged in audit logs

Rationale:
- Delete operations are irreversible and require highest privilege
- Toggle operations change critical state (active/inactive)
- Prevents accidental data loss from non-admin users
- Implements least privilege principle for destructive operations

Usage:
    python scripts/test_phase3_rbac.py
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
    coupon_delete,
    coupon_toggle,
    delete_checklist_item,
    delete_extra_charge,
    delete_kit,
    delete_plan,
    delete_starlink_kit,
    delete_subscription_plan,
    promotion_delete,
    promotion_toggle,
    toggle_plan_status,
    toggle_subscription_plan_status,
)
from main.models import UserRole

User = get_user_model()


class Phase3RBACTester:
    """Test harness for Phase 3 RBAC migration (admin-only delete/toggle operations)"""

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
        self,
        view_func,
        view_name,
        user,
        method="POST",
        data=None,
        should_pass=True,
        pk=1,
        coupon_id=None,
        promotion_id=None,
    ):
        """Test a single view with a specific user"""
        # Create request
        if method == "POST":
            request = self.factory.post(
                "/test/",
                data=data or {},
                content_type="application/json",
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        else:
            request = self.factory.get("/test/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")

        request.user = user

        # Call view
        try:
            # Determine which parameter to use
            if coupon_id is not None:
                response = view_func(request, coupon_id=coupon_id)
            elif promotion_id is not None:
                response = view_func(request, promotion_id=promotion_id)
            else:
                response = view_func(request, pk=pk)

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
        print(
            "PHASE 3 RBAC MIGRATION TEST RESULTS (ADMIN-ONLY DELETE/TOGGLE OPERATIONS)"
        )
        print("=" * 120)
        print(
            f"{'View Name':<40} {'User':<15} {'Roles':<20} {'Expected':<10} {'Actual':<15} {'Status':<10}"
        )
        print("-" * 120)

        for test in self.results["tests"]:
            status = "✓ PASS" if test["passed"] else "✗ FAIL"
            roles_str = ", ".join(test["roles"]) if test["roles"] else "none"
            print(
                f"{test['view']:<40} {test['user']:<15} {roles_str:<20} {test['expected']:<10} {test['actual']:<15} {status:<10}"
            )

        print("-" * 120)
        print(
            f"Total: {self.results['passed'] + self.results['failed']} | Passed: {self.results['passed']} | Failed: {self.results['failed']}"
        )
        print("=" * 120 + "\n")

        # Return exit code
        return 0 if self.results["failed"] == 0 else 1

    def run_all_tests(self):
        """Run all Phase 3 RBAC tests"""
        print("\n🔧 Creating test users...")

        # Create test users
        admin_user = self.create_test_user(
            "test_admin_phase3", [UserRole.ADMIN], is_staff=True
        )
        manager_user = self.create_test_user(
            "test_manager_phase3", [UserRole.MANAGER], is_staff=True
        )
        sales_user = self.create_test_user(
            "test_sales_phase3", [UserRole.SALES], is_staff=True
        )
        support_user = self.create_test_user(
            "test_support_phase3", [UserRole.SUPPORT], is_staff=True
        )

        print("✓ Test users created")
        print("\n🧪 Running Phase 3 tests (admin-only delete/toggle operations)...\n")

        # Test data
        test_data = '{"plan_id": 1}'

        # Test 1: delete_plan (admin only)
        print("Testing delete_plan (admin-only)...")
        self.test_view(delete_plan, "delete_plan", admin_user, should_pass=True)
        self.test_view(delete_plan, "delete_plan", manager_user, should_pass=False)
        self.test_view(delete_plan, "delete_plan", sales_user, should_pass=False)
        self.test_view(delete_plan, "delete_plan", support_user, should_pass=False)

        # Test 2: toggle_plan_status (admin only)
        print("Testing toggle_plan_status (admin-only)...")
        self.test_view(
            toggle_plan_status, "toggle_plan_status", admin_user, should_pass=True
        )
        self.test_view(
            toggle_plan_status, "toggle_plan_status", manager_user, should_pass=False
        )
        self.test_view(
            toggle_plan_status, "toggle_plan_status", sales_user, should_pass=False
        )
        self.test_view(
            toggle_plan_status, "toggle_plan_status", support_user, should_pass=False
        )

        # Test 3: delete_kit (admin only)
        print("Testing delete_kit (admin-only)...")
        self.test_view(delete_kit, "delete_kit", admin_user, should_pass=True)
        self.test_view(delete_kit, "delete_kit", manager_user, should_pass=False)
        self.test_view(delete_kit, "delete_kit", sales_user, should_pass=False)
        self.test_view(delete_kit, "delete_kit", support_user, should_pass=False)

        # Test 4: delete_starlink_kit (admin only)
        print("Testing delete_starlink_kit (admin-only)...")
        self.test_view(
            delete_starlink_kit, "delete_starlink_kit", admin_user, should_pass=True
        )
        self.test_view(
            delete_starlink_kit, "delete_starlink_kit", manager_user, should_pass=False
        )
        self.test_view(
            delete_starlink_kit, "delete_starlink_kit", sales_user, should_pass=False
        )
        self.test_view(
            delete_starlink_kit, "delete_starlink_kit", support_user, should_pass=False
        )

        # Test 5: delete_subscription_plan (admin only)
        print("Testing delete_subscription_plan (admin-only)...")
        self.test_view(
            delete_subscription_plan,
            "delete_subscription_plan",
            admin_user,
            should_pass=True,
        )
        self.test_view(
            delete_subscription_plan,
            "delete_subscription_plan",
            manager_user,
            should_pass=False,
        )
        self.test_view(
            delete_subscription_plan,
            "delete_subscription_plan",
            sales_user,
            should_pass=False,
        )
        self.test_view(
            delete_subscription_plan,
            "delete_subscription_plan",
            support_user,
            should_pass=False,
        )

        # Test 6: toggle_subscription_plan_status (admin only)
        print("Testing toggle_subscription_plan_status (admin-only)...")
        self.test_view(
            toggle_subscription_plan_status,
            "toggle_subscription_plan_status",
            admin_user,
            should_pass=True,
        )
        self.test_view(
            toggle_subscription_plan_status,
            "toggle_subscription_plan_status",
            manager_user,
            should_pass=False,
        )
        self.test_view(
            toggle_subscription_plan_status,
            "toggle_subscription_plan_status",
            sales_user,
            should_pass=False,
        )
        self.test_view(
            toggle_subscription_plan_status,
            "toggle_subscription_plan_status",
            support_user,
            should_pass=False,
        )

        # Test 7: delete_extra_charge (admin only)
        print("Testing delete_extra_charge (admin-only)...")
        self.test_view(
            delete_extra_charge, "delete_extra_charge", admin_user, should_pass=True
        )
        self.test_view(
            delete_extra_charge, "delete_extra_charge", manager_user, should_pass=False
        )
        self.test_view(
            delete_extra_charge, "delete_extra_charge", sales_user, should_pass=False
        )
        self.test_view(
            delete_extra_charge, "delete_extra_charge", support_user, should_pass=False
        )

        # Test 8: delete_checklist_item (admin only)
        print("Testing delete_checklist_item (admin-only)...")
        self.test_view(
            delete_checklist_item,
            "delete_checklist_item",
            admin_user,
            should_pass=True,
        )
        self.test_view(
            delete_checklist_item,
            "delete_checklist_item",
            manager_user,
            should_pass=False,
        )
        self.test_view(
            delete_checklist_item,
            "delete_checklist_item",
            sales_user,
            should_pass=False,
        )
        self.test_view(
            delete_checklist_item,
            "delete_checklist_item",
            support_user,
            should_pass=False,
        )

        # Test 9: coupon_delete (admin only)
        print("Testing coupon_delete (admin-only)...")
        self.test_view(
            coupon_delete,
            "coupon_delete",
            admin_user,
            should_pass=True,
            coupon_id=1,
        )
        self.test_view(
            coupon_delete,
            "coupon_delete",
            manager_user,
            should_pass=False,
            coupon_id=1,
        )
        self.test_view(
            coupon_delete,
            "coupon_delete",
            sales_user,
            should_pass=False,
            coupon_id=1,
        )
        self.test_view(
            coupon_delete,
            "coupon_delete",
            support_user,
            should_pass=False,
            coupon_id=1,
        )

        # Test 10: coupon_toggle (admin only)
        print("Testing coupon_toggle (admin-only)...")
        self.test_view(
            coupon_toggle,
            "coupon_toggle",
            admin_user,
            should_pass=True,
            coupon_id=1,
        )
        self.test_view(
            coupon_toggle,
            "coupon_toggle",
            manager_user,
            should_pass=False,
            coupon_id=1,
        )
        self.test_view(
            coupon_toggle,
            "coupon_toggle",
            sales_user,
            should_pass=False,
            coupon_id=1,
        )
        self.test_view(
            coupon_toggle,
            "coupon_toggle",
            support_user,
            should_pass=False,
            coupon_id=1,
        )

        # Test 11: promotion_delete (admin only)
        print("Testing promotion_delete (admin-only)...")
        self.test_view(
            promotion_delete,
            "promotion_delete",
            admin_user,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_delete,
            "promotion_delete",
            manager_user,
            should_pass=False,
            promotion_id=1,
        )
        self.test_view(
            promotion_delete,
            "promotion_delete",
            sales_user,
            should_pass=False,
            promotion_id=1,
        )
        self.test_view(
            promotion_delete,
            "promotion_delete",
            support_user,
            should_pass=False,
            promotion_id=1,
        )

        # Test 12: promotion_toggle (admin only)
        print("Testing promotion_toggle (admin-only)...")
        self.test_view(
            promotion_toggle,
            "promotion_toggle",
            admin_user,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_toggle,
            "promotion_toggle",
            manager_user,
            should_pass=False,
            promotion_id=1,
        )
        self.test_view(
            promotion_toggle,
            "promotion_toggle",
            sales_user,
            should_pass=False,
            promotion_id=1,
        )
        self.test_view(
            promotion_toggle,
            "promotion_toggle",
            support_user,
            should_pass=False,
            promotion_id=1,
        )

        # Print results
        return self.print_results()


def main():
    """Main entry point"""
    print("\n" + "=" * 120)
    print("NEXUS TELECOMS - Phase 3 RBAC Migration Test Suite")
    print("=" * 120)
    print("Testing admin-only delete/toggle operations (12 views)")
    print("Migration Date: 2025-11-06")
    print("=" * 120)

    tester = Phase3RBACTester()
    exit_code = tester.run_all_tests()

    if exit_code == 0:
        print("✅ All tests passed! Phase 3 migration successful.")
        print("\nKey Security Improvements:")
        print("- All delete operations now require admin privilege")
        print("- All toggle operations (status changes) require admin privilege")
        print("- Managers and other staff BLOCKED from irreversible operations")
        print("- Prevents accidental data loss and unauthorized state changes")
        print("\nNext Steps:")
        print("1. Review audit logs for access denials")
        print("2. Communicate admin-only delete policy to managers")
        print("3. Proceed to Phase 4: Coupons & Promotions (create/list views)")
    else:
        print("❌ Some tests failed. Please review the results above.")
        print("\nTroubleshooting:")
        print("1. Check that all 12 views use @require_staff_role(['admin'])")
        print("2. Verify user roles are correctly set in the database")
        print("3. Check that managers/sales/support are properly blocked")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
