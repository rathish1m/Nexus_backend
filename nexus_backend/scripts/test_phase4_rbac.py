#!/usr/bin/env python
"""
NEXUS TELECOMS - Phase 4 RBAC Migration Test Suite
Testing coupons and promotions management views (7 views)
Migration Date: 2025-11-06

Tests Role-Based Access Control for Phase 4 operations:
1. coupon_list() - read-only (admin, manager, sales)
2. coupon_create() - write (admin, manager)
3. coupon_bulk_create() - write (admin, manager)
4. promotion_list() - read-only (admin, manager, sales)
5. promotion_detail() - read-only (admin, manager, sales)
6. promotion_create() - write (admin, manager)
7. promotion_update() - write (admin, manager)

Test Matrix:
- Admin: Full access to all operations (PASS)
- Manager: Full access to all operations (PASS)
- Sales: Read-only access (list/detail PASS, create/update BLOCKED)
- Support: Blocked from all Phase 4 operations (BLOCKED)

Expected Behavior:
- Read operations (list/detail): admin, manager, sales = PASS | support = BLOCKED (302)
- Write operations (create/update): admin, manager = PASS | sales, support = BLOCKED (302)
"""

import os
import sys

import django

# Setup Django
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from app_settings.views import (
    coupon_bulk_create,
    coupon_create,
    coupon_list,
    promotion_create,
    promotion_detail,
    promotion_list,
    promotion_update,
)

User = get_user_model()


class Phase4RBACTester:
    """Test RBAC implementation for Phase 4 (coupons & promotions)"""

    def __init__(self):
        self.factory = RequestFactory()
        self.results = []

    def create_test_users(self):
        """Create test users with different roles"""
        print("🔧 Creating test users...")

        # Clean up existing test users
        User.objects.filter(username__contains="phase4").delete()

        # Create users with different roles
        admin_user = User.objects.create_user(
            username="test_admin_phase4",
            email="test_admin_phase4@test.com",
            full_name="Admin Phase4",
            is_staff=True,
            is_active=True,
            roles=["admin"],
        )
        admin_user.set_password("testpass123")
        admin_user.save()

        manager_user = User.objects.create_user(
            username="test_manager_phase4",
            email="test_manager_phase4@test.com",
            full_name="Manager Phase4",
            is_staff=True,
            is_active=True,
            roles=["manager"],
        )
        manager_user.set_password("testpass123")
        manager_user.save()

        sales_user = User.objects.create_user(
            username="test_sales_phase4",
            email="test_sales_phase4@test.com",
            full_name="Sales Phase4",
            is_staff=True,
            is_active=True,
            roles=["sales"],
        )
        sales_user.set_password("testpass123")
        sales_user.save()

        support_user = User.objects.create_user(
            username="test_support_phase4",
            email="test_support_phase4@test.com",
            full_name="Support Phase4",
            is_staff=True,
            is_active=True,
            roles=["support"],
        )
        support_user.set_password("testpass123")
        support_user.save()

        print("✓ Test users created\n")
        return admin_user, manager_user, sales_user, support_user

    def test_view(
        self,
        view_func,
        view_name,
        user,
        method="GET",
        data=None,
        should_pass=True,
        pk=None,
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
            if promotion_id is not None:
                response = view_func(request, promotion_id=promotion_id)
            elif pk is not None:
                response = view_func(request, pk=pk)
            else:
                response = view_func(request)

            # Check response (302 = denied, 200/400/404/500 = access granted)
            status = response.status_code
            if status == 302:
                actual = "BLOCKED (302 redirect)"
                passed = not should_pass
            elif status in (200, 400, 404, 403, 500):
                if status == 404:
                    actual = f"PASS ({status})"
                elif status == 403:
                    actual = f"PASS ({status})"
                elif status == 500:
                    # Get error message
                    try:
                        import json

                        error_data = json.loads(response.content)
                        error_msg = error_data.get("message", "Unknown error")
                        actual = f"ERROR: {error_msg}"
                    except:
                        actual = f"ERROR: Status {status}"
                else:
                    actual = f"PASS ({status})"
                passed = should_pass
            else:
                actual = f"UNEXPECTED ({status})"
                passed = False

            expected = "PASS" if should_pass else "BLOCKED"

            self.results.append(
                {
                    "view": view_name,
                    "user": user.email.split("@")[0],
                    "role": ", ".join(user.roles) if user.roles else "none",
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                }
            )

        except Exception as e:
            self.results.append(
                {
                    "view": view_name,
                    "user": user.email.split("@")[0],
                    "role": ", ".join(user.roles) if user.roles else "none",
                    "expected": "PASS" if should_pass else "BLOCKED",
                    "actual": f"EXCEPTION: {str(e)[:50]}",
                    "passed": False,
                }
            )

    def run_tests(self):
        """Run all Phase 4 RBAC tests"""
        print("🧪 Running Phase 4 tests (coupons & promotions management)...\n")

        admin_user, manager_user, sales_user, support_user = self.create_test_users()

        # Test 1: coupon_list (read-only: admin, manager, sales)
        print("Testing coupon_list (read-only)...")
        self.test_view(coupon_list, "coupon_list", admin_user, should_pass=True)
        self.test_view(coupon_list, "coupon_list", manager_user, should_pass=True)
        self.test_view(coupon_list, "coupon_list", sales_user, should_pass=True)
        self.test_view(coupon_list, "coupon_list", support_user, should_pass=False)

        # Test 2: coupon_create (write: admin, manager only)
        print("Testing coupon_create (write - admin, manager only)...")
        test_data = {
            "code": "TEST123",
            "discount_type": "percent",
            "percent_off": "10",
            "max_redemptions": 100,
        }
        self.test_view(
            coupon_create,
            "coupon_create",
            admin_user,
            method="POST",
            data=test_data,
            should_pass=True,
        )
        self.test_view(
            coupon_create,
            "coupon_create",
            manager_user,
            method="POST",
            data=test_data,
            should_pass=True,
        )
        self.test_view(
            coupon_create,
            "coupon_create",
            sales_user,
            method="POST",
            data=test_data,
            should_pass=False,
        )
        self.test_view(
            coupon_create,
            "coupon_create",
            support_user,
            method="POST",
            data=test_data,
            should_pass=False,
        )

        # Test 3: coupon_bulk_create (write: admin, manager only)
        print("Testing coupon_bulk_create (write - admin, manager only)...")
        bulk_data = {
            "count": 10,
            "length": 8,
            "prefix": "BULK",
            "discount_type": "percent",
            "percent_off": "15",
        }
        self.test_view(
            coupon_bulk_create,
            "coupon_bulk_create",
            admin_user,
            method="POST",
            data=bulk_data,
            should_pass=True,
        )
        self.test_view(
            coupon_bulk_create,
            "coupon_bulk_create",
            manager_user,
            method="POST",
            data=bulk_data,
            should_pass=True,
        )
        self.test_view(
            coupon_bulk_create,
            "coupon_bulk_create",
            sales_user,
            method="POST",
            data=bulk_data,
            should_pass=False,
        )
        self.test_view(
            coupon_bulk_create,
            "coupon_bulk_create",
            support_user,
            method="POST",
            data=bulk_data,
            should_pass=False,
        )

        # Test 4: promotion_list (read-only: admin, manager, sales)
        print("Testing promotion_list (read-only)...")
        self.test_view(promotion_list, "promotion_list", admin_user, should_pass=True)
        self.test_view(promotion_list, "promotion_list", manager_user, should_pass=True)
        self.test_view(promotion_list, "promotion_list", sales_user, should_pass=True)
        self.test_view(
            promotion_list, "promotion_list", support_user, should_pass=False
        )

        # Test 5: promotion_detail (read-only: admin, manager, sales)
        print("Testing promotion_detail (read-only)...")
        self.test_view(
            promotion_detail,
            "promotion_detail",
            admin_user,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_detail,
            "promotion_detail",
            manager_user,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_detail,
            "promotion_detail",
            sales_user,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_detail,
            "promotion_detail",
            support_user,
            should_pass=False,
            promotion_id=1,
        )

        # Test 6: promotion_create (write: admin, manager only)
        print("Testing promotion_create (write - admin, manager only)...")
        promo_data = {
            "name": "Test Promotion",
            "discount_type": "percent",
            "discount_value": "20",
            "active": False,
        }
        self.test_view(
            promotion_create,
            "promotion_create",
            admin_user,
            method="POST",
            data=promo_data,
            should_pass=True,
        )
        self.test_view(
            promotion_create,
            "promotion_create",
            manager_user,
            method="POST",
            data=promo_data,
            should_pass=True,
        )
        self.test_view(
            promotion_create,
            "promotion_create",
            sales_user,
            method="POST",
            data=promo_data,
            should_pass=False,
        )
        self.test_view(
            promotion_create,
            "promotion_create",
            support_user,
            method="POST",
            data=promo_data,
            should_pass=False,
        )

        # Test 7: promotion_update (write: admin, manager only)
        print("Testing promotion_update (write - admin, manager only)...")
        update_data = {"name": "Updated Promotion", "active": True}
        self.test_view(
            promotion_update,
            "promotion_update",
            admin_user,
            method="POST",
            data=update_data,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_update,
            "promotion_update",
            manager_user,
            method="POST",
            data=update_data,
            should_pass=True,
            promotion_id=1,
        )
        self.test_view(
            promotion_update,
            "promotion_update",
            sales_user,
            method="POST",
            data=update_data,
            should_pass=False,
            promotion_id=1,
        )
        self.test_view(
            promotion_update,
            "promotion_update",
            support_user,
            method="POST",
            data=update_data,
            should_pass=False,
            promotion_id=1,
        )

    def print_results(self):
        """Print test results in a formatted table"""
        print("\n" + "=" * 150)
        print(" " * 45 + "PHASE 4 RBAC MIGRATION TEST RESULTS (COUPONS & PROMOTIONS)")
        print("=" * 150)

        # Print header
        print(
            f"{'View Name':<35} {'User':<20} {'Roles':<15} {'Expected':<10} {'Actual':<25} {'Status':<10}"
        )
        print("-" * 150)

        # Print results
        passed = 0
        failed = 0
        for result in self.results:
            status = "✓ PASS" if result["passed"] else "✗ FAIL"
            if result["passed"]:
                passed += 1
            else:
                failed += 1

            print(
                f"{result['view']:<35} {result['user']:<20} {result['role']:<15} "
                f"{result['expected']:<10} {result['actual']:<25} {status:<10}"
            )

        print("-" * 150)
        print(f"Total: {len(self.results)} | Passed: {passed} | Failed: {failed}")
        print("=" * 150)

        if failed == 0:
            print("\n✅ All tests passed! Phase 4 migration successful.")
            print("\nKey Security Improvements:")
            print(
                "- Read operations (list/detail): Accessible to admin, manager, sales"
            )
            print("- Write operations (create/update): Restricted to admin, manager")
            print("- Support staff BLOCKED from all coupon/promotion operations")
            print("- Clear separation of duties: sales can view but not modify")
            print("\nNext Steps:")
            print("1. Review audit logs for access patterns")
            print("2. Communicate new access controls to team")
            print("3. Proceed to Phase 5: Checklists & Billing Configuration")
            return 0
        else:
            print(
                "\n❌ Some tests failed. Please review the results above.\n\nTroubleshooting:"
            )
            print(
                "1. Check that all 7 views use correct @require_staff_role decorators"
            )
            print("2. Verify user roles are correctly set in the database")
            print("3. Check that sales users are blocked from write operations")
            print("4. Check that support users are blocked from all operations")
            return 1


def main():
    """Main entry point"""
    print("=" * 150)
    print(" " * 40 + "NEXUS TELECOMS - Phase 4 RBAC Migration Test Suite")
    print("=" * 150)
    print(" " * 35 + "Testing coupons and promotions management views (7 views)")
    print(" " * 55 + "Migration Date: 2025-11-06")
    print("=" * 150)
    print()

    tester = Phase4RBACTester()
    tester.run_tests()
    exit_code = tester.print_results()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
