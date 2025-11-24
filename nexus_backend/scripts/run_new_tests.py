#!/usr/bin/env python
"""
Quick test runner for new model tests.
Runs tests and shows results without using pytest directly.
"""

import os
import sys

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.conf import settings
from django.test.utils import get_runner

if __name__ == "__main__":
    TestRunner = get_runner(settings)
    test_runner = TestRunner(verbosity=2, interactive=False, keepdb=True)

    # Run specific test classes
    test_labels = [
        "main.tests.test_models.TestOTPModel",
        "main.tests.test_models.TestUserAdditionalMethods",
        "main.tests.test_models.TestCompanyKYCStatus",
    ]

    print("=" * 70)
    print("Running new model tests...")
    print("=" * 70)

    failures = test_runner.run_tests(test_labels)

    if failures:
        print(f"\n❌ {failures} test(s) failed")
        sys.exit(1)
    else:
        print("\n✅ All new tests passed!")
        sys.exit(0)
