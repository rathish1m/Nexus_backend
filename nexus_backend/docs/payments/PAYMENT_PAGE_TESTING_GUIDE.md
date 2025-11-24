# Payment Page Testing Guide

## Quick Start Testing

### Prerequisites
1. Ensure you have at least one PaymentMethod with `enabled=True` in the database
2. Have an AdditionalBilling with status='approved'
3. Be logged in as the customer who owns the billing

### Test Payment Method Setup

Run in Django shell or create via admin:

```python
from main.models import PaymentMethod

# Create sample payment methods
PaymentMethod.objects.get_or_create(
    name='MOBILE_MONEY',
    defaults={
        'description': 'Pay using mobile money (MTN, Orange, etc.)',
        'enabled': True
    }
)

PaymentMethod.objects.get_or_create(
    name='CREDIT_CARD',
    defaults={
        'description': 'Pay with Visa, Mastercard, or American Express',
        'enabled': True
    }
)

PaymentMethod.objects.get_or_create(
    name='BANK_TRANSFER',
    defaults={
        'description': 'Direct bank transfer to our account',
        'enabled': True
    }
)

PaymentMethod.objects.get_or_create(
    name='CASH',
    defaults={
        'description': 'Pay in cash at our office',
        'enabled': False  # Disabled by default
    }
)

PaymentMethod.objects.get_or_create(
    name='PAYPAL',
    defaults={
        'description': 'Pay securely with PayPal',
        'enabled': True
    }
)
```

### Test URL Access

1. **From Billing Management Page**:
   - Navigate to `/en/billing/` or `/fr/billing/`
   - Find an approved billing
   - Click "Pay Now" button
   - Should redirect to payment page

2. **Direct URL Access**:
   - Navigate to `/en/site-survey/billing/payment/<billing_id>/`
   - Should display payment page if:
     - You are the customer who owns the billing
     - Billing status is 'approved'

### Expected Behavior

#### Page Load
✅ Green gradient header displays
✅ Total amount shows prominently
✅ Billing reference and order reference display
✅ Payment summary shows subtotal, tax, and total
✅ Security notice appears
✅ Only enabled payment methods show
✅ Payment reference input field is present
✅ "Confirm Payment" button is active

#### Payment Method Selection
✅ Click on a payment method to select it
✅ Selected method shows blue border and check icon
✅ Only one method can be selected at a time
✅ First method is selected by default

#### Payment Submission
✅ Enter payment reference (e.g., "TXN123456")
✅ Click "Confirm Payment"
✅ Confirmation dialog appears
✅ After confirmation, payment processes
✅ Success message displays
✅ Redirects to billing page
✅ Billing status changes to "paid"

#### Validation Tests
❌ Submit without payment reference → Error: "Please enter a payment reference"
❌ Try to access another customer's billing → 403 Forbidden
❌ Try to pay a non-approved billing → 400 Bad Request
❌ Submit with disabled payment method → 400 Invalid payment method

### Browser Console Tests

Open browser console and check:

```javascript
// Test language prefix detection
console.log(window.location.pathname.split('/')[1]);
// Should output: 'en' or 'fr'

// Test CSRF token retrieval
console.log(getCookie('csrftoken'));
// Should output a valid token string
```

### Database Verification

After successful payment, check in Django shell:

```python
from site_survey.models import AdditionalBilling

billing = AdditionalBilling.objects.get(id=YOUR_BILLING_ID)
print(f"Status: {billing.status}")  # Should be 'paid'
print(f"Payment Method: {billing.payment_method}")  # E.g., 'MOBILE_MONEY'
print(f"Payment Reference: {billing.payment_reference}")  # E.g., 'TXN123456'
print(f"Paid At: {billing.paid_at}")  # Should have timestamp
```

### Mobile Testing

Test on different screen sizes:

1. **Desktop** (>= 1024px):
   - Full width layout
   - Side-by-side elements

2. **Tablet** (768px - 1023px):
   - Responsive layout
   - Adjusted spacing

3. **Mobile** (< 768px):
   - Stacked layout
   - Touch-friendly buttons
   - Full-width cards

### Language Testing

1. **English (/en/)**:
   - All labels in English
   - API calls use /en/ prefix
   - Redirects preserve language

2. **French (/fr/)**:
   - All labels in French
   - API calls use /fr/ prefix
   - Redirects preserve language

### Error Scenarios to Test

1. **No Payment Methods Available**:
   ```python
   # Disable all payment methods
   PaymentMethod.objects.all().update(enabled=False)
   ```
   - Should show warning message
   - Submit button should be disabled

2. **Unauthorized Access**:
   - Log in as different user
   - Try to access billing payment page
   - Should return 403 error

3. **Wrong Billing Status**:
   - Try to access payment page for pending/rejected/paid billing
   - Should return 400 error

### Performance Checks

- [ ] Page loads in < 2 seconds
- [ ] Payment method selection is instant
- [ ] Form validation is immediate
- [ ] Payment submission completes in < 5 seconds
- [ ] Redirect happens smoothly

### Accessibility Testing

- [ ] All buttons are keyboard accessible (Tab navigation)
- [ ] Radio buttons can be selected with Enter/Space
- [ ] Form can be submitted with Enter key
- [ ] Color contrast meets WCAG standards
- [ ] Screen reader compatible

### Admin Panel Verification

1. Navigate to Django admin
2. Go to main → Payment Methods
3. Verify you can:
   - Add new payment methods
   - Enable/disable existing methods
   - Edit descriptions
   - See changes reflected immediately on payment page

---

## Quick Test Script

Copy and paste in browser console after page loads:

```javascript
// Test 1: Check payment methods loaded
console.log('Payment methods:', document.querySelectorAll('.payment-method-input').length);

// Test 2: Test selection
document.querySelectorAll('.payment-method-input')[0]?.click();
console.log('Selected method:', document.querySelector('.payment-method-input:checked')?.value);

// Test 3: Fill payment reference
document.getElementById('payment_reference').value = 'TEST123456';
console.log('Reference set:', document.getElementById('payment_reference').value);

// Test 4: Check form is ready
console.log('Form ready:', !!document.querySelector('.payment-method-input:checked') &&
            document.getElementById('payment_reference').value.length > 0);
```

---

## Common Issues and Solutions

### Issue: Payment methods not showing
**Solution**: Check that at least one PaymentMethod has `enabled=True`

### Issue: 403 Forbidden error
**Solution**: Ensure you're logged in as the billing customer

### Issue: 400 Bad Request
**Solution**: Verify billing status is 'approved'

### Issue: Payment not processing
**Solution**: Check browser console for JavaScript errors

### Issue: Page style looks wrong
**Solution**: Clear browser cache and reload

---

## Success Criteria

✅ Payment page loads without errors
✅ Styling matches billing approval page
✅ Only enabled payment methods display
✅ Payment submission works correctly
✅ Billing status updates to "paid"
✅ Payment details are saved
✅ Redirects back to billing page
✅ Works in both English and French
✅ Works on mobile and desktop
✅ All validations work correctly

---

**Happy Testing! 🎉**
