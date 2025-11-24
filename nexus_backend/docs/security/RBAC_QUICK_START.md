# RBAC Permission System - Quick Start Guide

> **Role-Based Access Control for NEXUS TELECOMS Backend**
> Secure your Django application with granular, role-based permissions

---

## 🚀 Quick Start (5 minutes)

### For Customer-Only Views

```python
from django.contrib.auth.decorators import login_required
from user.permissions import require_customer_only

@login_required(login_url="login_page")
@require_customer_only()
def my_customer_view(request):
    """Only non-staff customers can access this view"""
    return render(request, "my_template.html")
```

### For Staff-Only Views with Role Control

```python
from user.permissions import require_staff_role

@require_staff_role(['admin', 'manager'])
def my_admin_view(request):
    """Only admin and manager roles can access"""
    return render(request, "admin_template.html")
```

### For Django REST Framework APIs

```python
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from user.permissions import IsCustomerOnly, IsStaffWithRole

class CustomerOrderViewSet(viewsets.ModelViewSet):
    """Customer API - customers only"""
    permission_classes = [IsAuthenticated, IsCustomerOnly]

class StaffRevenueViewSet(viewsets.ModelViewSet):
    """Staff API - finance/admin only"""
    permission_classes = [IsAuthenticated, IsStaffWithRole]
    required_staff_roles = ['finance', 'admin']
```

---

## 📚 Available Decorators

### Function-Based Views

| Decorator | Description | Use Case |
|-----------|-------------|----------|
| `@require_customer_only()` | Non-staff customers only | Client-facing views |
| `@require_staff_role([roles])` | Staff with specific roles | Backoffice views |
| `@require_role('role')` | Specific role (any user) | Special features |
| `@require_any_role([roles])` | At least one role | Flexible access |
| `@require_all_roles([roles])` | All roles required | High security |

### DRF Permission Classes

| Class | Description | Use Case |
|-------|-------------|----------|
| `IsCustomerOnly` | Customers only (not staff) | Customer APIs |
| `IsStaffWithRole` | Staff with specific roles | Admin APIs |
| `HasRole` | Single role check | Specific endpoints |
| `HasAnyRole` | Multiple role options | Flexible APIs |

---

## 🔧 Common Patterns

### Pattern 1: Customer Dashboard

```python
@login_required(login_url="login_page")
@require_customer_only()
def dashboard(request):
    user = request.user
    # user.is_staff is guaranteed to be False
    # user has 'customer' role
    return render(request, "dashboard.html", {
        "user": user,
        "orders": Order.objects.filter(user=user)
    })
```

### Pattern 2: Admin Panel with Multiple Roles

```python
@require_staff_role(['admin', 'manager'])
def admin_panel(request):
    # Only admin or manager can access
    stats = get_system_stats()
    return render(request, "admin_panel.html", {"stats": stats})
```

### Pattern 3: Financial Data (Restricted)

```python
@require_staff_role(['finance', 'admin'])
def revenue_dashboard(request):
    # Only finance and admin roles
    revenue = calculate_revenue()
    return render(request, "revenue.html", {"revenue": revenue})
```

### Pattern 4: API with Owner Check

```python
from user.permissions import IsCustomerOnly

class SubscriptionViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsCustomerOnly]

    def get_queryset(self):
        # Customers see only their own subscriptions
        return Subscription.objects.filter(user=self.request.user)
```

### Pattern 5: API with Staff Override

```python
from rest_framework.permissions import BasePermission
from user.permissions import user_has_any_role

class IsOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        # Owner can access
        if obj.user == request.user:
            return True
        # Admin/support staff can access
        return user_has_any_role(request.user, ['admin', 'support'])

class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerOrStaff]
```

---

## ⚠️ Migration from Old System

### Replace customer_nonstaff_required

```python
# ❌ OLD WAY
from user.auth import customer_nonstaff_required

@require_full_login
@customer_nonstaff_required
def my_view(request):
    pass

# ✅ NEW WAY
from user.permissions import require_customer_only

@login_required(login_url="login_page")
@require_customer_only()
def my_view(request):
    pass
```

### Replace is_staff Check

```python
# ❌ OLD WAY
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def backoffice_view(request):
    pass

# ✅ NEW WAY
from user.permissions import require_staff_role

@require_staff_role(['admin', 'manager', 'dispatcher'])
def backoffice_view(request):
    pass
```

---

## 🧪 Testing Your Permissions

### Manual Testing

```bash
# 1. Create test users
python manage.py shell

from main.models import User

# Customer user
customer = User.objects.create_user(
    email='customer@test.com',
    password='test123',
    username='customer@test.com',
    roles=['customer'],
    is_staff=False
)

# Admin user
admin = User.objects.create_user(
    email='admin@test.com',
    password='test123',
    username='admin@test.com',
    roles=['admin'],
    is_staff=True
)

# 2. Test access
# Login as customer → try /backoffice/ → should be blocked
# Login as admin → try /client/dashboard/ → should be blocked
```

### Automated Testing

```python
import pytest
from django.test import Client
from django.urls import reverse

@pytest.mark.django_db
def test_customer_blocked_from_backoffice(customer_user):
    client = Client()
    client.force_login(customer_user)
    response = client.get(reverse('backoffice_main'))
    assert response.status_code in [302, 403]

@pytest.mark.django_db
def test_staff_blocked_from_customer_dashboard(admin_user):
    client = Client()
    client.force_login(admin_user)
    response = client.get(reverse('dashboard'))
    assert response.status_code in [302, 403]
```

---

## 🔍 Debugging

### Check User Roles

```python
from user.permissions import normalize_roles, user_has_role

# In shell or view
user = request.user
print(f"Roles: {normalize_roles(user)}")
print(f"Has admin role: {user_has_role(user, 'admin')}")
```

### View Audit Logs

```bash
# Check logs for access denials
tail -f logs/django.log | grep "Access denied"

# Or in Django admin
# Check User model → roles field
```

### Common Issues

**Issue**: Staff user can access customer views

```python
# Check: Is is_staff = True?
# customer_only views block ALL staff users
# If staff needs customer access, use separate customer account
```

**Issue**: User has role but still blocked

```python
# Check role spelling and case
# Roles are case-insensitive but must match
user.roles = ['Admin']  # ✅ Works with user_has_role(user, 'admin')
user.roles = ['admn']   # ❌ Typo, won't match
```

---

## 📖 Complete Documentation

For detailed information, see:

1. **[RBAC_FINAL_SUMMARY.md](./RBAC_FINAL_SUMMARY.md)** - Complete overview
2. **[RBAC_IMPLEMENTATION_GUIDE.md](./RBAC_IMPLEMENTATION_GUIDE.md)** - Step-by-step migration
3. **[SECURITY_AUDIT_RBAC_2025-11-05.md](./SECURITY_AUDIT_RBAC_2025-11-05.md)** - Security analysis
4. **[MIGRATION_EXAMPLE_client_app.md](./MIGRATION_EXAMPLE_client_app.md)** - Practical examples

---

## 🆘 Need Help?

1. **Check inline docs**: `user/permissions.py` has detailed docstrings
2. **Review tests**: `user/tests/test_permissions.py` has examples
3. **Search examples**: `MIGRATION_EXAMPLE_client_app.md`
4. **Create issue**: GitHub issue with `[rbac]` tag

---

## 🎯 Role Reference

### Available Roles (from main.models.UserRole)

- `customer` - Regular customers
- `admin` - System administrators
- `manager` - Managers
- `dispatcher` - Dispatch coordinators
- `technician` - Field technicians
- `leadtechnician` - Lead technicians
- `installer` - Installers
- `sales` - Sales agents
- `support` - Support staff
- `compliance` - Compliance officers
- `finance` - Finance staff

### Role Hierarchy (Recommended)

```
Superuser (bypasses all checks)
  ↓
Admin (access to most admin functions)
  ↓
Manager (business oversight)
  ↓
Finance (financial data)
  ↓
Dispatcher (operations coordination)
  ↓
Sales / Support / Compliance (departmental)
  ↓
Technician / Installer (field operations)
  ↓
Customer (client-facing features only)
```

---

## ✅ Quick Validation

After implementing permissions, verify:

- [ ] Customer users **cannot** access `/backoffice/*`
- [ ] Staff users **cannot** access `/client/*` endpoints
- [ ] Finance views only accessible to finance/admin/manager
- [ ] Technical views only accessible to appropriate technical roles
- [ ] All access denials appear in logs
- [ ] Tests pass: `pytest user/tests/test_permissions.py`

---

**Version**: 1.0
**Last Updated**: 2025-11-05
**Maintained By**: VirgoCoachman
