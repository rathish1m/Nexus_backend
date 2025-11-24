# Test-Driven Development Workflow Guide

## Overview
This document outlines the TDD workflow for NEXUS Telecoms backend development.

## RED-GREEN-REFACTOR Cycle

### 1. RED Phase: Write Failing Test First

Before writing any production code, write a test that fails:

```python
# main/tests/test_models.py
import pytest
from main.models import Order

@pytest.mark.unit
def test_order_cancellation(user):
    """Test that an order can be cancelled"""
    order = Order.objects.create(
        user=user,
        subscription_plan_id=1,
        kit_id=1,
        status='pending'
    )

    # This will fail because cancel() doesn't exist yet
    result = order.cancel()

    assert result is True
    assert order.status == 'cancelled'
    assert order.cancelled_at is not None
```

Run the test to confirm it fails:
```bash
pytest main/tests/test_models.py::test_order_cancellation -v
```

### 2. GREEN Phase: Write Minimal Code to Pass

Write just enough code to make the test pass:

```python
# main/models.py
from django.db import models
from django.utils import timezone

class Order(models.Model):
    # ... existing fields ...

    def cancel(self):
        """Cancel the order"""
        self.status = 'cancelled'
        self.cancelled_at = timezone.now()
        self.save()
        return True
```

Run the test to confirm it passes:
```bash
pytest main/tests/test_models.py::test_order_cancellation -v
```

### 3. REFACTOR Phase: Improve Code Quality

Now that tests are green, refactor without changing behavior:

```python
# main/models.py
class Order(models.Model):
    # ... existing fields ...

    CANCELLABLE_STATUSES = ['pending', 'confirmed']

    def can_cancel(self):
        """Check if order can be cancelled"""
        return self.status in self.CANCELLABLE_STATUSES

    def cancel(self, reason=None):
        """
        Cancel the order if it's in a cancellable status.

        Args:
            reason: Optional cancellation reason

        Returns:
            bool: True if cancelled successfully, False otherwise

        Raises:
            ValueError: If order cannot be cancelled
        """
        if not self.can_cancel():
            raise ValueError(f"Cannot cancel order with status: {self.status}")

        self.status = 'cancelled'
        self.cancelled_at = timezone.now()
        self.cancellation_reason = reason
        self.save()

        # Notify customer
        self.send_cancellation_email()

        return True
```

Update test to cover new behavior:

```python
@pytest.mark.unit
def test_order_cancellation_with_reason(user):
    """Test that an order can be cancelled with a reason"""
    order = Order.objects.create(
        user=user,
        subscription_plan_id=1,
        kit_id=1,
        status='pending'
    )

    result = order.cancel(reason="Customer request")

    assert result is True
    assert order.status == 'cancelled'
    assert order.cancelled_at is not None
    assert order.cancellation_reason == "Customer request"

@pytest.mark.unit
def test_order_cancellation_fails_for_completed_order(user):
    """Test that completed orders cannot be cancelled"""
    order = Order.objects.create(
        user=user,
        subscription_plan_id=1,
        kit_id=1,
        status='completed'
    )

    with pytest.raises(ValueError, match="Cannot cancel order"):
        order.cancel()
```

Run all tests to ensure refactoring didn't break anything:
```bash
pytest main/tests/test_models.py -v
```

## Complete TDD Example: New Feature

### Example: Adding Payment Retry Logic

#### Step 1: Write Test First (RED)

```python
# billing_management/tests/test_services.py
import pytest
from decimal import Decimal
from billing_management.services import PaymentService
from main.models import PaymentAttempt

@pytest.mark.unit
def test_payment_retry_increments_attempt_count(user, mock_flexpay):
    """Test that payment retry increments attempt count"""
    # Arrange
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='failed',
        attempt_count=1
    )

    # Act
    result = PaymentService.retry_payment(payment.id)

    # Assert
    payment.refresh_from_db()
    assert payment.attempt_count == 2
    assert result.success is True


@pytest.mark.unit
def test_payment_retry_max_attempts_exceeded(user):
    """Test that payment retry fails after max attempts"""
    # Arrange
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='failed',
        attempt_count=3  # Max attempts
    )

    # Act & Assert
    with pytest.raises(ValueError, match="Maximum retry attempts exceeded"):
        PaymentService.retry_payment(payment.id)
```

Run test (should fail):
```bash
pytest billing_management/tests/test_services.py::test_payment_retry_increments_attempt_count -v
# FAILS: PaymentService.retry_payment() doesn't exist
```

#### Step 2: Implement Minimal Code (GREEN)

```python
# billing_management/services.py
from decimal import Decimal
from typing import Dict, Any
from main.models import PaymentAttempt

class PaymentService:
    MAX_RETRY_ATTEMPTS = 3

    @staticmethod
    def retry_payment(payment_id: int) -> Dict[str, Any]:
        """
        Retry a failed payment.

        Args:
            payment_id: ID of the payment to retry

        Returns:
            Dict with success status and payment info

        Raises:
            ValueError: If max retry attempts exceeded
        """
        payment = PaymentAttempt.objects.get(id=payment_id)

        if payment.attempt_count >= PaymentService.MAX_RETRY_ATTEMPTS:
            raise ValueError("Maximum retry attempts exceeded")

        payment.attempt_count += 1
        payment.save()

        return {"success": True, "payment_id": payment.id}
```

Run test (should pass):
```bash
pytest billing_management/tests/test_services.py::test_payment_retry_increments_attempt_count -v
# PASSES
```

#### Step 3: Refactor and Add More Tests

```python
# billing_management/services.py
from decimal import Decimal
from typing import Dict, Any, Optional
from django.utils import timezone
from main.models import PaymentAttempt
from .flexpay_client import FlexPayClient

class PaymentService:
    MAX_RETRY_ATTEMPTS = 3
    RETRY_DELAY_MINUTES = 15

    @staticmethod
    def retry_payment(payment_id: int, user_initiated: bool = False) -> Dict[str, Any]:
        """
        Retry a failed payment.

        Args:
            payment_id: ID of the payment to retry
            user_initiated: Whether retry was initiated by user (allows override)

        Returns:
            Dict with success status, payment info, and next retry time

        Raises:
            ValueError: If max retry attempts exceeded or payment not retryable
        """
        payment = PaymentAttempt.objects.select_for_update().get(id=payment_id)

        # Validate payment is retryable
        if payment.status not in ['failed', 'pending']:
            raise ValueError(f"Cannot retry payment with status: {payment.status}")

        # Check retry attempts (allow override for user-initiated)
        if not user_initiated and payment.attempt_count >= PaymentService.MAX_RETRY_ATTEMPTS:
            raise ValueError("Maximum retry attempts exceeded")

        # Increment attempt count
        payment.attempt_count += 1
        payment.last_retry_at = timezone.now()
        payment.save()

        # Process payment with FlexPay
        flexpay_client = FlexPayClient()
        try:
            result = flexpay_client.process_payment(
                amount=payment.amount,
                customer_id=payment.user.id,
                order_id=payment.order_id
            )

            payment.status = 'completed' if result['success'] else 'failed'
            payment.external_transaction_id = result.get('transaction_id')
            payment.failure_reason = result.get('error')
            payment.save()

            return {
                "success": result['success'],
                "payment_id": payment.id,
                "transaction_id": result.get('transaction_id'),
                "next_retry": PaymentService._calculate_next_retry(payment)
            }

        except Exception as e:
            payment.status = 'failed'
            payment.failure_reason = str(e)
            payment.save()

            return {
                "success": False,
                "payment_id": payment.id,
                "error": str(e),
                "next_retry": PaymentService._calculate_next_retry(payment)
            }

    @staticmethod
    def _calculate_next_retry(payment: PaymentAttempt) -> Optional[str]:
        """Calculate next retry timestamp"""
        if payment.attempt_count >= PaymentService.MAX_RETRY_ATTEMPTS:
            return None

        next_retry = timezone.now() + timezone.timedelta(
            minutes=PaymentService.RETRY_DELAY_MINUTES * payment.attempt_count
        )
        return next_retry.isoformat()
```

Add comprehensive tests:

```python
# billing_management/tests/test_services.py
import pytest
from decimal import Decimal
from freezegun import freeze_time
from billing_management.services import PaymentService
from main.models import PaymentAttempt

@pytest.mark.unit
def test_payment_retry_increments_attempt_count(user, mock_flexpay):
    """Test that payment retry increments attempt count"""
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='failed',
        attempt_count=1
    )

    mock_flexpay.simulate_payment_success(payment.id)
    result = PaymentService.retry_payment(payment.id)

    payment.refresh_from_db()
    assert payment.attempt_count == 2
    assert result['success'] is True


@pytest.mark.unit
def test_payment_retry_max_attempts_exceeded(user):
    """Test that payment retry fails after max attempts"""
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='failed',
        attempt_count=3
    )

    with pytest.raises(ValueError, match="Maximum retry attempts exceeded"):
        PaymentService.retry_payment(payment.id)


@pytest.mark.unit
def test_payment_retry_user_initiated_allows_override(user, mock_flexpay):
    """Test that user-initiated retry allows max attempts override"""
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='failed',
        attempt_count=5  # Above max
    )

    mock_flexpay.simulate_payment_success(payment.id)
    result = PaymentService.retry_payment(payment.id, user_initiated=True)

    assert result['success'] is True
    payment.refresh_from_db()
    assert payment.attempt_count == 6


@pytest.mark.unit
def test_payment_retry_calculates_next_retry_time(user, mock_flexpay):
    """Test that next retry time is calculated correctly"""
    with freeze_time('2024-01-01 12:00:00'):
        payment = PaymentAttempt.objects.create(
            user=user,
            amount=Decimal('100.00'),
            status='failed',
            attempt_count=1
        )

        result = PaymentService.retry_payment(payment.id)

        # Next retry should be in 15 * 2 = 30 minutes
        assert result['next_retry'] == '2024-01-01T12:30:00'


@pytest.mark.unit
def test_payment_retry_invalid_status(user):
    """Test that retry fails for non-retryable status"""
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='completed',
        attempt_count=1
    )

    with pytest.raises(ValueError, match="Cannot retry payment with status"):
        PaymentService.retry_payment(payment.id)


@pytest.mark.integration
def test_payment_retry_integration(user, mock_flexpay, authenticated_client):
    """Test payment retry end-to-end"""
    # Create failed payment
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=Decimal('100.00'),
        status='failed',
        attempt_count=1
    )

    # Retry via API
    response = authenticated_client.post(f'/api/payments/{payment.id}/retry/')

    assert response.status_code == 200
    assert response.json()['success'] is True

    payment.refresh_from_db()
    assert payment.attempt_count == 2
```

Run all tests:
```bash
pytest billing_management/tests/test_services.py -v
```

## TDD Workflow Checklist

For every new feature or bug fix:

- [ ] Write failing test first (RED)
- [ ] Run test to confirm it fails
- [ ] Write minimal code to pass test (GREEN)
- [ ] Run test to confirm it passes
- [ ] Refactor code for quality (REFACTOR)
- [ ] Run all tests to ensure nothing broke
- [ ] Add edge case tests
- [ ] Run coverage check (aim for 90%+)
- [ ] Commit with descriptive message
- [ ] Push and verify CI passes

## TDD Best Practices

### 1. Test Naming Convention
```python
# Good
def test_order_cancellation_sends_email_to_customer():
    pass

# Bad
def test_cancel():
    pass
```

### 2. One Assertion Per Test (when possible)
```python
# Good
def test_order_status_changes_to_cancelled():
    order.cancel()
    assert order.status == 'cancelled'

def test_order_sets_cancelled_timestamp():
    order.cancel()
    assert order.cancelled_at is not None

# Less ideal (but acceptable for related assertions)
def test_order_cancellation():
    order.cancel()
    assert order.status == 'cancelled'
    assert order.cancelled_at is not None
```

### 3. Arrange-Act-Assert (AAA) Pattern
```python
def test_payment_creation():
    # Arrange
    user = UserFactory()
    amount = Decimal('100.00')

    # Act
    payment = PaymentAttempt.objects.create(
        user=user,
        amount=amount
    )

    # Assert
    assert payment.amount == amount
    assert payment.user == user
```

### 4. Test Fixtures Over Setup/Teardown
```python
# Good (pytest fixtures)
@pytest.fixture
def sample_order(user):
    return Order.objects.create(user=user, status='pending')

def test_order_cancellation(sample_order):
    sample_order.cancel()
    assert sample_order.status == 'cancelled'

# Less ideal (setUp/tearDown)
class TestOrder(TestCase):
    def setUp(self):
        self.order = Order.objects.create(...)

    def test_cancellation(self):
        self.order.cancel()
```

### 5. Mock External Dependencies
```python
def test_payment_with_flexpay(mock_flexpay):
    """Always mock external services"""
    payment_id = PaymentService.create_payment(amount=100)

    assert mock_flexpay.payments[payment_id]['amount'] == 100
    assert len(mock_flexpay.payments) == 1
```

## Coverage Requirements

- **New code**: 90%+ coverage mandatory
- **Modified code**: Maintain or improve existing coverage
- **Critical modules**: 85%+ coverage
- **Overall project**: 80%+ coverage

Check coverage before committing:
```bash
pytest --cov=. --cov-report=term-missing
coverage report --fail-under=80
```

## Resources

- [Test-Driven Development by Example (Kent Beck)](https://www.amazon.com/Test-Driven-Development-Kent-Beck/dp/0321146530)
- [pytest documentation](https://docs.pytest.org/)
- [Django testing best practices](https://docs.djangoproject.com/en/stable/topics/testing/overview/)
- [NEXUS Testing README](../tests/README.md)
