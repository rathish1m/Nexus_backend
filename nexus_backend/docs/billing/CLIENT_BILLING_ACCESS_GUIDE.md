# Client Additional Billing Access Guide
**Date:** October 3, 2025

## 📍 Where Customers Can Find Additional Billings

### **Main Access Point:**

**URL:** `/client/billing/` or use the route name `billing_page`

**Full URL Example:**
```
http://your-domain.com/client/billing/
```

---

## 🎯 Page Details

### **View Function:**
- **Location:** `client_app/views.py` (Line 1719)
- **Function:** `billing_page(request)`
- **Decorators:**
  - `@require_full_login` - Requires authenticated user
  - `@customer_nonstaff_required` - Only for customers (not staff)

### **Template:**
- **File:** `client_app/templates/billing_management.html`
- **Section:** "Additional Equipment Billings" (starts around line 133)

---

## 📊 What Customers See

The billing page displays:

### **Desktop View (Table Format):**
| Reference | Order | Amount | Status | Created | Actions |
|-----------|-------|---------|--------|---------|---------|
| BILL-XXX | ORD-XXX | $XX.XX | Status Badge | Date | Button |

### **Mobile View (Card Format):**
- Billing reference
- Order reference
- Amount
- Status badge
- Created date
- Action button

---

## 🎨 Status Display

### **Status Badges:**

1. **⏳ Pending Approval** (Yellow)
   - Customer hasn't approved the billing yet
   - Action: "Review" button → Links to approval page

2. **👍 Approved** (Blue)
   - Customer has approved, but not paid
   - Action: "Pay Now" button → Links to payment page

3. **✅ Paid** (Green)
   - Payment completed
   - Action: "Completed" label (no button)

4. **❌ Rejected** (Red)
   - Billing was rejected
   - Action: No action available

---

## 🔗 Action Links

### **1. Review/Approve Billing:**
```
URL: /site-survey/billing/approval/<billing_id>/
When: Status = "pending_approval"
Button: "Review" (Indigo)
```

### **2. Pay Billing:**
```
URL: /site-survey/billing/payment/<billing_id>/
When: Status = "approved"
Button: "Pay Now" (Green)
```

---

## 🔍 Query Details

### **Current Implementation:**
```python
additional_billings = (
    AdditionalBilling.objects.filter(
        survey__order__user=request.user  # Filters by logged-in customer
    )
    .select_related("survey", "survey__order", "order", "customer")
    .order_by("-created_at")  # Most recent first
)
```

### **What This Does:**
- Fetches all additional billings where the order belongs to the logged-in customer
- Optimizes database queries using `select_related()`
- Orders billings with newest first

---

## 🐛 **IMPORTANT: Template Bug Found**

### **Current Issue:**
The template uses **incorrect relationship path**:
```django
❌ {{ billing.survey_cost.site_survey.order.order_reference }}
```

### **Should Be:**
```django
✅ {{ billing.survey.order.order_reference }}
```

### **Where to Fix:**
- **File:** `client_app/templates/billing_management.html`
- **Lines:** 169, 237 (and possibly others)

### **Relationship Structure:**
```
AdditionalBilling
    ├─ survey (ForeignKey → SiteSurvey)
    │   └─ order (ForeignKey → Order)
    │       └─ order_reference
    ├─ order (ForeignKey → Order) [direct reference]
    └─ customer (ForeignKey → User)
```

---

## 🛠️ How to Fix the Template

### **Find and Replace:**

**Line 169 (Desktop Table):**
```django
<!-- BEFORE -->
<td class="px-6 py-4 text-gray-600">
  {{ billing.survey_cost.site_survey.order.order_reference }}
</td>

<!-- AFTER -->
<td class="px-6 py-4 text-gray-600">
  {{ billing.survey.order.order_reference }}
</td>
```

**Line 237 (Mobile View):**
```django
<!-- BEFORE -->
<p class="text-sm text-gray-500">{{ billing.survey_cost.site_survey.order.order_reference }}</p>

<!-- AFTER -->
<p class="text-sm text-gray-500">{{ billing.survey.order.order_reference }}</p>
```

---

## 📧 Email Notifications

Customers also receive emails with links to the billing page:

### **1. Billing Notification Email**
- **Sent When:** Backoffice approves survey with additional costs
- **Template:** `site_survey/templates/site_survey/emails/billing_notification.html`
- **Link:** Direct link to approval page

### **2. Payment Confirmation Email**
- **Sent When:** Customer pays the billing
- **Template:** `site_survey/templates/site_survey/emails/payment_confirmation.html`
- **Content:** Receipt and next steps

---

## 🔐 Access Control

### **Who Can Access:**
- ✅ Authenticated customers only
- ✅ Non-staff users only (regular customers)
- ❌ Staff users redirected
- ❌ Anonymous users redirected to login

### **Security:**
- Users can only see their own billings (filtered by `request.user`)
- Direct URL access is protected by authentication decorators

---

## 🎯 Customer Workflow

### **Complete Flow:**

```
1. Site Survey Conducted
   ↓
2. Backoffice Approves Survey
   ↓
3. Additional Billing Created Automatically
   ↓
4. 📧 Customer Receives Email Notification
   ↓
5. 👤 Customer Visits: /client/billing/
   ↓
6. Customer Sees Billing with "Review" Button
   ↓
7. Customer Clicks "Review" → /site-survey/billing/approval/{id}/
   ↓
8. Customer Reviews Details & Approves
   ↓
9. Status Changes to "Approved"
   ↓
10. Customer Sees "Pay Now" Button on /client/billing/
   ↓
11. Customer Clicks "Pay Now" → /site-survey/billing/payment/{id}/
   ↓
12. Customer Makes Payment
   ↓
13. 📧 Customer Receives Payment Confirmation
   ↓
14. Status Changes to "Paid"
   ↓
15. Installation Scheduled
```

---

## 📱 Navigation Menu Access

### **Where in the Client App:**
The billing page should be accessible from the main navigation menu. Check:

1. **Dashboard Sidebar/Menu**
   - Look for "Billing" or "Billing Management" link
   - Should link to `{% url 'billing_page' %}`

2. **If Not Present, Add to Navigation:**
   ```django
   <a href="{% url 'billing_page' %}" class="nav-link">
     <i class="fas fa-file-invoice-dollar"></i>
     {% trans "Billing" %}
   </a>
   ```

---

## 🧪 Testing the Page

### **Test as Customer:**

1. **Login as customer:**
   ```
   http://your-domain.com/login/
   ```

2. **Navigate to billing:**
   ```
   http://your-domain.com/client/billing/
   ```

3. **Check for:**
   - ✅ Page loads without errors
   - ✅ Additional billings are displayed
   - ✅ Status badges show correctly
   - ✅ Action buttons appear based on status
   - ✅ Order references display correctly (after fixing template)

---

## 📝 Related URLs

### **Client App URLs:**
- Dashboard: `/client/` or `/`
- Billing: `/client/billing/`
- Orders: `/client/orders/`
- Settings: `/client/settings/`

### **Site Survey Billing URLs:**
- Approval: `/site-survey/billing/approval/<billing_id>/`
- Payment: `/site-survey/billing/payment/<billing_id>/`

### **Backoffice URLs:**
- Billings List: `/backoffice/site-survey/additional-billings/`
- Survey Approval: `/backoffice/site-survey/<survey_id>/approval/`

---

## 🚀 Quick Summary

### **For Customers:**
👉 **Go to:** `/client/billing/`

### **What They'll See:**
- All their additional equipment billings
- Current status of each billing
- Action buttons to review/approve/pay
- Order references and amounts
- Created dates

### **What They Can Do:**
1. **Review pending billings**
2. **Approve billings**
3. **Make payments**
4. **Track billing history**

---

## ⚠️ Action Required

### **Fix the Template Bug:**
The template currently uses an incorrect relationship path that will cause errors:
- **File:** `client_app/templates/billing_management.html`
- **Fix:** Replace `billing.survey_cost.site_survey.order.order_reference` with `billing.survey.order.order_reference`
- **Lines:** 169, 237 (search for all occurrences)

After fixing, customers will be able to see their order references correctly!

---

**Last Updated:** October 3, 2025
**Status:** ⚠️ Template fix needed
