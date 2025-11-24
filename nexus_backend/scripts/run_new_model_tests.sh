#!/bin/bash
# Quick test script to run only the new model tests

echo "🧪 Running new model tests..."
echo "=============================="
echo ""

echo "1️⃣  Testing Order.cancel() methods (3 tests)..."
pytest main/tests/test_models.py::TestOrder::test_order_cancel_method_without_inventory -v
pytest main/tests/test_models.py::TestOrder::test_order_cancel_method_with_inventory -v
pytest main/tests/test_models.py::TestOrder::test_order_cancel_method_idempotent -v

echo ""
echo "2️⃣  Testing OTPVerification model (6 tests)..."
pytest main/tests/test_models.py::TestOTPModel -v

echo ""
echo "3️⃣  Testing User role methods (5 tests)..."
pytest main/tests/test_models.py::TestUserAdditionalMethods -v

echo ""
echo "4️⃣  Testing CompanyKYC status methods (3 tests)..."
pytest main/tests/test_models.py::TestCompanyKYCStatus -v

echo ""
echo "=============================="
echo "✅ All new tests completed!"
