# Payment Methods - Admin Setup Guide

## Quick Setup Instructions

### Step 1: Access Django Admin
1. Navigate to your Django admin panel: `https://yourdomain.com/admin/`
2. Log in with superuser credentials

### Step 2: Navigate to Payment Methods
1. Look for **Main** section in the admin
2. Click on **Payment Methods**

### Step 3: Create Payment Methods

#### Option A: Manual Creation (via Admin Panel)

Click **Add Payment Method** and fill in:

**Example 1: Mobile Money**
- **Name**: Select "Mobile Money" from dropdown
- **Description**: "Pay using mobile money services like MTN Mobile Money, Orange Money, or Moov Money. Available 24/7."
- **Enabled**: ✅ Checked

**Example 2: Credit Card**
- **Name**: Select "Credit Card" from dropdown
- **Description**: "Pay securely with Visa, Mastercard, or American Express. All major credit cards accepted."
- **Enabled**: ✅ Checked

**Example 3: Bank Transfer**
- **Name**: Select "Bank Transfer" from dropdown
- **Description**: "Direct bank transfer to our company account. Transfer may take 1-3 business days to process."
- **Enabled**: ✅ Checked

**Example 4: Cash**
- **Name**: Select "Cash" from dropdown
- **Description**: "Pay in cash at our office during business hours (9 AM - 5 PM, Monday to Friday)."
- **Enabled**: ❌ Unchecked (if you don't accept cash)

**Example 5: PayPal**
- **Name**: Select "PayPal" from dropdown
- **Description**: "Pay securely using your PayPal account. International payments accepted."
- **Enabled**: ✅ Checked

Click **Save** for each method.

---

#### Option B: Programmatic Creation (Django Shell)

Run in Django shell (`python manage.py shell`):

```python
from main.models import PaymentMethod

# Create all payment methods at once
payment_methods = [
    {
        'name': 'MOBILE_MONEY',
        'description': 'Pay using mobile money services like MTN Mobile Money, Orange Money, or Moov Money. Available 24/7.',
        'enabled': True
    },
    {
        'name': 'CREDIT_CARD',
        'description': 'Pay securely with Visa, Mastercard, or American Express. All major credit cards accepted.',
        'enabled': True
    },
    {
        'name': 'BANK_TRANSFER',
        'description': 'Direct bank transfer to our company account. Transfer may take 1-3 business days to process.',
        'enabled': True
    },
    {
        'name': 'CASH',
        'description': 'Pay in cash at our office during business hours (9 AM - 5 PM, Monday to Friday).',
        'enabled': False  # Disabled by default
    },
    {
        'name': 'PAYPAL',
        'description': 'Pay securely using your PayPal account. International payments accepted.',
        'enabled': True
    },
]

for method_data in payment_methods:
    PaymentMethod.objects.get_or_create(
        name=method_data['name'],
        defaults={
            'description': method_data['description'],
            'enabled': method_data['enabled']
        }
    )

print("✅ Payment methods created successfully!")

# Verify
print(f"\nEnabled payment methods: {PaymentMethod.objects.filter(enabled=True).count()}")
print(f"Total payment methods: {PaymentMethod.objects.count()}")
```

---

### Step 4: Verify Setup

#### Check in Admin Panel
1. Navigate to **Main → Payment Methods**
2. You should see all 5 payment methods listed
3. Verify the **Enabled** column shows checkmarks for active methods

#### Check on Payment Page
1. Log in as a customer
2. Navigate to a billing with status "approved"
3. Click "Pay Now"
4. Verify only enabled payment methods appear
5. Verify descriptions show correctly

---

## Managing Payment Methods

### Enable a Payment Method
1. Go to **Main → Payment Methods**
2. Click on the payment method (e.g., "Cash")
3. Check the **Enabled** checkbox
4. Click **Save**
5. ✅ Immediately available on payment page

### Disable a Payment Method
1. Go to **Main → Payment Methods**
2. Click on the payment method
3. Uncheck the **Enabled** checkbox
4. Click **Save**
5. ✅ Immediately hidden from payment page

### Update Description
1. Go to **Main → Payment Methods**
2. Click on the payment method
3. Edit the **Description** field
4. Click **Save**
5. ✅ Updated description shows immediately

---

## Payment Method Details

### Available Payment Methods

| Name | Internal Code | Icon | Default Status |
|------|---------------|------|----------------|
| Cash | `CASH` | 💰 fa-money-bill-wave | Disabled |
| Mobile Money | `MOBILE_MONEY` | 📱 fa-mobile-alt | Enabled |
| Credit Card | `CREDIT_CARD` | 💳 fa-credit-card | Enabled |
| Bank Transfer | `BANK_TRANSFER` | 🏦 fa-university | Enabled |
| PayPal | `PAYPAL` | 💙 fab fa-paypal | Enabled |

### Payment Method Icons

Icons are automatically assigned based on the payment method name:

- **MOBILE_MONEY** → `<i class="fas fa-mobile-alt text-green-500"></i>`
- **CREDIT_CARD** → `<i class="fas fa-credit-card text-blue-500"></i>`
- **BANK_TRANSFER** → `<i class="fas fa-university text-indigo-500"></i>`
- **CASH** → `<i class="fas fa-money-bill-wave text-emerald-500"></i>`
- **PAYPAL** → `<i class="fab fa-paypal text-blue-600"></i>`

---

## Best Practices

### Description Guidelines

**Good Descriptions** ✅
- "Pay using MTN Mobile Money, Orange Money, or Moov Money. Instant confirmation."
- "Secure credit card payment. We accept Visa, Mastercard, and American Express."
- "Bank transfer to our account. Please include your billing reference."

**Poor Descriptions** ❌
- "Pay here" (not informative)
- Empty description (customers don't know what to expect)
- Too long (3+ paragraphs)

### Enable/Disable Strategy

**When to Enable**:
- ✅ Payment processor is integrated and tested
- ✅ You have capacity to process this payment type
- ✅ You can verify payments within reasonable time

**When to Disable**:
- ❌ Payment processor maintenance
- ❌ Temporary service outage
- ❌ Regional restrictions
- ❌ Testing new payment gateway (enable after testing)

---

## Common Scenarios

### Scenario 1: Temporarily Disable Credit Cards
**Reason**: Payment gateway maintenance

**Steps**:
1. Go to **Main → Payment Methods**
2. Click **Credit Card**
3. Uncheck **Enabled**
4. Update **Description**: "Credit card payments temporarily unavailable due to maintenance. Please use mobile money or bank transfer."
5. Click **Save**

**Result**: Customers see other payment options, with helpful message about credit cards.

---

### Scenario 2: Add Cash Payments for Office Visits
**Reason**: Opening new physical office

**Steps**:
1. Go to **Main → Payment Methods**
2. Click **Cash**
3. Check **Enabled**
4. Update **Description**: "Pay in cash at our new office: 123 Main Street, Yaoundé. Open Mon-Fri 9AM-5PM."
5. Click **Save**

**Result**: Cash option appears immediately for customers.

---

### Scenario 3: Regional Payment Method
**Reason**: Operating in multiple countries

**Option A**: Use description to clarify
```
Description: "Mobile Money - Available in Cameroon (MTN, Orange),
              Nigeria (MTN), and Senegal (Orange Money)"
```

**Option B**: Create separate payment methods (requires code changes)
```python
# This would require extending the PAYMENT_METHOD_CHOICES
PAYMENT_METHOD_CHOICES = [
    ...
    ('MOBILE_MONEY_CM', 'Mobile Money (Cameroon)'),
    ('MOBILE_MONEY_NG', 'Mobile Money (Nigeria)'),
]
```

---

## Monitoring & Analytics

### Check Payment Method Usage

Run in Django shell:

```python
from site_survey.models import AdditionalBilling

# Count payments by method
from django.db.models import Count

payment_stats = AdditionalBilling.objects.filter(
    status='paid'
).values('payment_method').annotate(
    count=Count('id')
).order_by('-count')

for stat in payment_stats:
    print(f"{stat['payment_method']}: {stat['count']} payments")
```

Example output:
```
MOBILE_MONEY: 245 payments
BANK_TRANSFER: 123 payments
CREDIT_CARD: 89 payments
PAYPAL: 34 payments
CASH: 12 payments
```

### Popular Payment Methods

```python
from site_survey.models import AdditionalBilling

# Get most popular payment method
most_popular = AdditionalBilling.objects.filter(
    status='paid'
).values('payment_method').annotate(
    count=Count('id')
).order_by('-count').first()

print(f"Most popular: {most_popular['payment_method']} ({most_popular['count']} uses)")
```

---

## Troubleshooting

### Issue: No Payment Methods Showing
**Problem**: All payment methods are disabled

**Solution**:
```python
from main.models import PaymentMethod

# Check status
print(PaymentMethod.objects.filter(enabled=True).count())
# If 0, enable at least one:

method = PaymentMethod.objects.get(name='MOBILE_MONEY')
method.enabled = True
method.save()
```

---

### Issue: Wrong Icon Displaying
**Problem**: Icon doesn't match payment method

**Solution**: Icons are based on the `name` field, not description. Ensure the name is correctly set to one of:
- `CASH`
- `MOBILE_MONEY`
- `CREDIT_CARD`
- `BANK_TRANSFER`
- `PAYPAL`

---

### Issue: Description Not Showing
**Problem**: Description field is empty

**Solution**:
1. Edit the payment method in admin
2. Add a description
3. Save
4. Refresh payment page

---

## Migration Script

If you're upgrading from the old hardcoded system, run this migration:

```python
from main.models import PaymentMethod
from site_survey.models import AdditionalBilling

# Create standard payment methods
PaymentMethod.objects.get_or_create(name='MOBILE_MONEY', defaults={'enabled': True})
PaymentMethod.objects.get_or_create(name='CREDIT_CARD', defaults={'enabled': True})
PaymentMethod.objects.get_or_create(name='BANK_TRANSFER', defaults={'enabled': True})

# Map old payment_method values to new names
old_to_new_mapping = {
    'mobile_money': 'MOBILE_MONEY',
    'credit_card': 'CREDIT_CARD',
    'bank_transfer': 'BANK_TRANSFER',
    'cash': 'CASH',
    'paypal': 'PAYPAL',
}

# Update existing billings
for billing in AdditionalBilling.objects.filter(status='paid'):
    old_method = billing.payment_method
    if old_method in old_to_new_mapping:
        billing.payment_method = old_to_new_mapping[old_method]
        billing.save()
        print(f"Updated billing {billing.id}: {old_method} → {billing.payment_method}")
```

---

## Security Considerations

### Payment Method Validation
The system automatically validates:
- ✅ Payment method must exist in database
- ✅ Payment method must be enabled
- ✅ Payment reference is required
- ✅ Only authorized customer can pay their billing

### Admin Access Control
- Only superusers should manage payment methods
- Use Django's permission system to restrict access
- Enable Django admin login logging

---

## API Integration (Future)

### Payment Gateway Integration
When integrating with payment gateways:

```python
# Example: Stripe integration
class PaymentMethod(models.Model):
    # ... existing fields ...
    gateway_provider = models.CharField(max_length=50, blank=True)
    # e.g., 'stripe', 'paypal', 'flutterwave'

    gateway_config = models.JSONField(blank=True, null=True)
    # Store API keys, merchant IDs, etc.
```

This structure allows:
- Multiple payment gateways
- Gateway-specific configuration
- Easy switching between providers

---

## Summary Checklist

### Initial Setup
- [ ] Create all 5 payment methods in admin
- [ ] Add helpful descriptions
- [ ] Enable appropriate methods for your business
- [ ] Test payment page displays correctly
- [ ] Verify customer can select and pay

### Regular Maintenance
- [ ] Monitor payment method usage
- [ ] Update descriptions as needed
- [ ] Disable methods during maintenance
- [ ] Re-enable after testing
- [ ] Keep payment references organized

### Best Practices
- [ ] Always have at least 2 payment methods enabled
- [ ] Write clear, concise descriptions
- [ ] Include processing time in descriptions
- [ ] Disable before removing support
- [ ] Test after any changes

---

**You're all set! 🎉**

Payment methods are now fully configured and ready to accept customer payments.
