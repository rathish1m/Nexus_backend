# RBAC Analysis - `app_settings` Application

**Date**: November 6, 2025
**Analyzed File**: `app_settings/views.py`
**Analyst**: GitHub Copilot
**Branch**: `fix/user_access_management_by_role`
**Language**: English (Source of Truth - All translations derive from this)

> **⚠️ IMPORTANT**: This document is written in English as the **single source of truth** for all translations. All French, Spanish, or other language versions must be translated from this English original to maintain consistency and accuracy across the internationalization system.

---

## 📊 Overview

### File Statistics

| Metric | Value |
|--------|-------|
| **Total lines** | 4,118 lines |
| **Total functions** | 80 functions |
| **Views protected by `@user_passes_test`** | 70 views |
| **Views using RBAC** | ❌ **0 views** |

---

## ⚠️ Issues Identified

### 🔴 **Critical Issue #1: Obsolete Authorization System**

**All views** use the obsolete pattern:

```python
@login_required(login_url="login_page")
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def my_view(request):
    pass
```

#### **Weaknesses of this approach:**

1. **No granular role control**
   - Only checks `is_staff=True`
   - Any staff member (admin, sales, support, finance) has the same access
   - No separation of duties

2. **Violation of principle of least privilege**
   - A sales agent can modify financial settings
   - A technician can manage subscription plans
   - A support agent can delete critical data

3. **Security risks**
   - Easy privilege escalation
   - No audit trail by role
   - No detailed logs by user type

---

## 📋 Views Inventory (Sample)

### Extra Charges Management (4 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 42 | `get_extra_charges()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'finance'])` |
| 96 | `create_extra_charge()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 214 | `edit_extra_charge()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 337 | `delete_extra_charge()` | `is_staff` | `@require_staff_role(['admin'])` |

### Subscription Plans Management (8 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 424 | `create_subscription_plan()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 545 | `get_subscription_plans()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales'])` |
| 598 | `get_subscription()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales'])` |
| 634 | `edit_subscription()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 676 | `toggle_plan_status()` | `is_staff` | `@require_staff_role(['admin'])` |
| 702 | `delete_plan()` | `is_staff` | `@require_staff_role(['admin'])` |

### Starlink Kits Management (6 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 751 | `get_kits()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales', 'dispatcher'])` |
| 776 | `add_kit()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 849 | `get_kit()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales'])` |
| 876 | `delete_kit()` | `is_staff` | `@require_staff_role(['admin'])` |
| 892 | `edit_kit()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |

### Tax Management (3 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 936 | `taxes_add()` | `is_staff` | `@require_staff_role(['admin', 'finance'])` |
| 963 | `taxes_list()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |
| 1131 | `taxes_detail()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |

### Payment Methods Management (3 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 984 | `payments_method_add()` | `is_staff` | `@require_staff_role(['admin', 'finance'])` |
| 1012 | `payments_method_list()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |
| 1219 | `payments_method_detail()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |

### Regions Management (2 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 1034 | `region_add()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 1107 | `region_list()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'dispatcher'])` |

### Installation Fees Management (4 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 1297 | `installation_fee_add()` | `is_staff` | `@require_staff_role(['admin', 'finance'])` |
| 1355 | `installation_fee_choices()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'sales'])` |
| 1384 | `installation_fee_list()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |
| 1404 | `installation_fee_detail()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |

### Site Survey Checklist Management (4 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 2305 | `get_site_survey_checklist()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'dispatcher'])` |
| 2359 | `create_checklist_item()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 2457 | `update_checklist_item()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 2563 | `delete_checklist_item()` | `is_staff` | `@require_staff_role(['admin'])` |

### Additional Billing Management (4 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 2867 | `additional_billings_management()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |
| 2876 | `get_additional_billings()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'manager'])` |
| 2979 | `generate_survey_billing()` | `is_staff` | `@require_staff_role(['admin', 'finance', 'dispatcher'])` |
| 3064 | `update_billing_status()` | `is_staff` | `@require_staff_role(['admin', 'finance'])` |

### Billing Configuration (2 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 3124 | `billing_config_get()` | `is_staff` | `@require_staff_role(['admin', 'finance'])` |
| 3146 | `billing_config_save()` | `is_staff` | `@require_staff_role(['admin'])` |

### Coupons Management (5 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 3244 | `coupon_list()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales'])` |
| 3352 | `coupon_create()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 3502 | `coupon_bulk_create()` | `is_staff` | `@require_staff_role(['admin'])` |
| 3687 | `coupon_toggle()` | `is_staff` | `@require_staff_role(['admin'])` |
| 3704 | `coupon_delete()` | `is_staff` | `@require_staff_role(['admin'])` |

### Promotions Management (6 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 3844 | `promotion_list()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales'])` |
| 3853 | `promotion_detail()` | `is_staff` | `@require_staff_role(['admin', 'manager', 'sales'])` |
| 3867 | `promotion_create()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 3886 | `promotion_update()` | `is_staff` | `@require_staff_role(['admin', 'manager'])` |
| 3911 | `promotion_toggle()` | `is_staff` | `@require_staff_role(['admin'])` |
| 3928 | `promotion_delete()` | `is_staff` | `@require_staff_role(['admin'])` |

### Company Settings (2 views)

| Ligne | Fonction | Autorisation Actuelle | Autorisation Recommandée |
|-------|----------|----------------------|-------------------------|
| 3949 | `company_settings_view()` | `is_staff` | `@require_staff_role(['admin'])` |
| 3966 | `company_settings_update()` | `is_staff` | `@require_staff_role(['admin'])` |

---

## 🎯 Recommendations by Priority

### 🔴 **CRITICAL Priority** (Financial Security)

**Finance-related views** - Secure immediately:

1. **Billing configuration** → Only `admin`
   - `billing_config_save()` (line 3146)
   - `company_settings_update()` (line 3966)

2. **Tax management** → `admin` + `finance`
   - `taxes_add()` (line 936)
   - `taxes_detail()` (line 1131)

3. **Payment methods** → `admin` + `finance`
   - `payments_method_add()` (line 984)
   - `payments_method_detail()` (line 1219)

4. **Installation fees** → `admin` + `finance`
   - `installation_fee_add()` (line 1297)
   - `installation_fee_detail()` (line 1404)

### 🟠 **HIGH Priority** (Data Integrity)

**Delete operations** - Reserve for `admin` only:

- `delete_plan()` (line 702)
- `delete_kit()` (line 876)
- `delete_extra_charge()` (line 337, 2796)
- `delete_checklist_item()` (line 2563)
- `coupon_delete()` (line 3704)
- `promotion_delete()` (line 3928)
- `delete_starlink_kit()` (line 2253)
- `delete_subscription_plan()` (line 2207)

### 🟡 **MEDIUM Priority** (Separation of Duties)

**Read-only views** - Allow multiple roles:

- Sales agents can view plans/kits
- Finance can view taxes and fees
- Dispatchers can view regions and checklists

### 🟢 **LOW Priority** (Optimization)

**Create/edit views** - Limit by domain:

- Managers can create plans and kits
- Finance can create taxes and fees
- Sales can create coupons (with admin approval for activation)

---

## 🛠️ Migration Plan

### **Step 1: Import RBAC system**

Add at the top of `app_settings/views.py`:

```python
# Replace
from django.contrib.auth.decorators import login_required, user_passes_test

# With
from django.contrib.auth.decorators import login_required
from user.permissions import require_staff_role
```

### **Step 2: Migration by functional blocks**

#### **Block 1: System Configuration (CRITICAL)**

```python
# ❌ AVANT
@login_required(login_url="login_page")
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def company_settings_update(request):
    pass

# ✅ APRÈS
@require_staff_role(['admin'])
def company_settings_update(request):
    pass
```

#### **Block 2: Financial Management**

```python
# Taxes
@require_staff_role(['admin', 'finance'])
def taxes_add(request):
    pass

@require_staff_role(['admin', 'finance', 'manager'])
def taxes_list(request):
    pass

# Méthodes de paiement
@require_staff_role(['admin', 'finance'])
def payments_method_add(request):
    pass
```

#### **Block 3: Commercial Management**

```python
# Plans d'abonnement
@require_staff_role(['admin', 'manager'])
def create_subscription_plan(request):
    pass

@require_staff_role(['admin', 'manager', 'sales'])
def get_subscription_plans(request):
    pass

# Coupons et promotions
@require_staff_role(['admin', 'manager'])
def coupon_create(request):
    pass

@require_staff_role(['admin'])
def coupon_delete(request):
    pass
```

#### **Block 4: Delete Operations**

```python
# All deletions reserved for admins only
@require_staff_role(['admin'])
def delete_plan(request, pk):
    pass

@require_staff_role(['admin'])
def delete_kit(request, pk):
    pass

@require_staff_role(['admin'])
def delete_extra_charge(request):
    pass
```

### **Step 3: Regression Testing**

After each migrated block:

1. **Test with admin account** → Must work
2. **Test with sales account** → Appropriate restricted access
3. **Test with support account** → Must be blocked
4. **Check logs** → Access denials logged

---

## 📊 Migration Impact

### **Before (Current State)**

```
┌─────────────────────────────────────┐
│   ALL STAFF (is_staff=True)         │
│                                     │
│  ✓ Admin                            │
│  ✓ Manager                          │
│  ✓ Sales                            │
│  ✓ Support                          │
│  ✓ Finance                          │
│  ✓ Technician (if is_staff)         │
│  ✓ Dispatcher                       │
│                                     │
│  FULL access to app_settings        │
└─────────────────────────────────────┘
```

### **After (With RBAC)**

```
┌────────────────────┬────────────────────┬────────────────────┐
│   ADMIN            │   FINANCE          │   MANAGER/SALES    │
│                    │                    │                    │
│  ✓ Everything      │  ✓ Taxes           │  ✓ Plans           │
│  ✓ Delete          │  ✓ Payments        │  ✓ Kits            │
│  ✓ Configure       │  ✓ Install fees    │  ✓ Coupons (read)  │
│                    │  ✓ Billing         │  ✓ Promotions      │
│                    │  ✗ Delete          │  ✗ Delete          │
│                    │  ✗ Sys config      │  ✗ Finances        │
└────────────────────┴────────────────────┴────────────────────┘

┌────────────────────┬────────────────────┬────────────────────┐
│   DISPATCHER       │   SUPPORT          │   TECHNICIAN       │
│                    │                    │                    │
│  ✓ Regions         │  ✗ Access denied   │  ✗ Access denied   │
│  ✓ Checklists      │                    │                    │
│  ✓ Billing         │                    │                    │
│     (generation)   │                    │                    │
│  ✗ Modify config   │                    │                    │
│  ✗ Delete          │                    │                    │
└────────────────────┴────────────────────┴────────────────────┘
```

---

## ✅ Migration Checklist

### Phase 1: Configuration & Finance (Week 1)

- [ ] Migrate `company_settings_update()` → `['admin']`
- [ ] Migrate `billing_config_save()` → `['admin']`
- [ ] Migrate `taxes_add()` → `['admin', 'finance']`
- [ ] Migrate `taxes_detail()` → `['admin', 'finance', 'manager']`
- [ ] Migrate `payments_method_add()` → `['admin', 'finance']`
- [ ] Migrate `installation_fee_add()` → `['admin', 'finance']`
- [ ] Test with admin, finance, sales profiles
- [ ] Verify audit logs

### Phase 2: Plans & Kits (Week 2)

- [ ] Migrate `create_subscription_plan()` → `['admin', 'manager']`
- [ ] Migrate `edit_subscription_plan()` → `['admin', 'manager']`
- [ ] Migrate `get_subscription_plans()` → `['admin', 'manager', 'sales']`
- [ ] Migrate `add_starlink_kit()` → `['admin', 'manager']`
- [ ] Migrate `edit_starlink_kit()` → `['admin', 'manager']`
- [ ] Migrate `get_starlink_kits()` → `['admin', 'manager', 'sales', 'dispatcher']`
- [ ] Test complete commercial workflow
- [ ] Verify sales can view data but cannot modify

### Phase 3: Deletions (Week 3)

- [ ] Migrate all `delete_*()` functions → `['admin']`
- [ ] Migrate `toggle_*()` → `['admin']`
- [ ] Test that manager CANNOT delete
- [ ] Test that admin CAN delete
- [ ] Verify appropriate error messages

### Phase 4: Coupons & Promotions (Week 4)

- [ ] Migrate `coupon_create()` → `['admin', 'manager']`
- [ ] Migrate `coupon_list()` → `['admin', 'manager', 'sales']`
- [ ] Migrate `promotion_create()` → `['admin', 'manager']`
- [ ] Migrate `promotion_list()` → `['admin', 'manager', 'sales']`
- [ ] Test promotional workflow
- [ ] Verify sales can view but not create

### Phase 5: Checklists & Billing (Week 5)

- [ ] Migrate `get_site_survey_checklist()` → `['admin', 'manager', 'dispatcher']`
- [ ] Migrate `create_checklist_item()` → `['admin', 'manager']`
- [ ] Migrate `generate_survey_billing()` → `['admin', 'finance', 'dispatcher']`
- [ ] Migrate `update_billing_status()` → `['admin', 'finance']`
- [ ] Test dispatcher workflow
- [ ] Verify finance/operations separation

### Phase 6: Tests & Documentation (Week 6)

- [ ] Complete regression tests
- [ ] Tests with all user profiles
- [ ] Document permissions per view
- [ ] Train teams on new access controls
- [ ] Update user documentation

---

## 🔒 Final Security Matrix

| Feature | Admin | Finance | Manager | Sales | Dispatcher | Support | Tech |
|---------|-------|---------|---------|-------|------------|---------|------|
| **Company config** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Billing config** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| **Taxes CRUD** | ✅ | ✅ | 👁️ | ❌ | ❌ | ❌ | ❌ |
| **Payments CRUD** | ✅ | ✅ | 👁️ | ❌ | ❌ | ❌ | ❌ |
| **Plans CRUD** | ✅ | ❌ | ✅ | 👁️ | ❌ | ❌ | ❌ |
| **Kits CRUD** | ✅ | ❌ | ✅ | 👁️ | 👁️ | ❌ | ❌ |
| **Coupons CRUD** | ✅ | ❌ | ✅ | 👁️ | ❌ | ❌ | ❌ |
| **Promotions CRUD** | ✅ | ❌ | ✅ | 👁️ | ❌ | ❌ | ❌ |
| **Regions** | ✅ | ❌ | ✅ | ❌ | 👁️ | ❌ | ❌ |
| **Checklists** | ✅ | ❌ | ✅ | ❌ | 👁️ | ❌ | ❌ |
| **Additional billing** | ✅ | ✅ | 👁️ | ❌ | 🔧 | ❌ | ❌ |
| **Deletions** | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |

**Legend:**
- ✅ = Full access (CRUD)
- 🔧 = Partial access (e.g., generate billing)
- 👁️ = Read-only
- ❌ = No access

---

## 📈 Expected Benefits

### **Security**
- ✅ Elimination of unauthorized access
- ✅ Separation of duties
- ✅ Principle of least privilege enforced
- ✅ Audit trail by role

### **Compliance**
- ✅ GDPR: Data access limited by role
- ✅ SOX: Finance/operations separation
- ✅ ISO 27001: Role-based access control

### **Operational**
- ✅ Fewer human errors
- ✅ Simpler training (each sees only relevant data)
- ✅ Faster onboarding
- ✅ Reduced support tickets

---

## 🎓 Conclusion

The `app_settings` application requires **complete migration to RBAC system**. With **70 views protected only by `is_staff`**, there is currently **no granular access control**.

### Immediate Actions

1. **Week 1**: Secure critical financial views
2. **Week 2-3**: Migrate commercial management views
3. **Week 4-5**: Finalize all remaining views
4. **Week 6**: Complete testing and training

### Resources

- **RBAC Documentation**: `docs/security/RBAC_QUICK_START.md`
- **Examples**: `docs/security/MIGRATION_EXAMPLE_client_app.md`
- **Tests**: `user/tests/test_permissions.py`

---

**Recommended next step**: Start migration with critical financial views (Phase 1).
