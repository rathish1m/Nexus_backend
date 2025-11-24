# Security| Priority | Document | Description | For |
|----------|----------|-------------|-----|
| ⭐⭐⭐ | [RBAC_INDEX.md](./RBAC_INDEX.md) | Master RBAC index with all documentation | Everyone |
| 🚀 | [RBAC_QUICK_START.md](./RBAC_QUICK_START.md) | 5-minute quick start guide | Developers |
| 📊 | [RBAC_FINAL_SUMMARY.md](./RBAC_FINAL_SUMMARY.md) | Executive summary and roadmap | Tech Leads |
| 📘 | [RBAC_IMPLEMENTATION_GUIDE.md](./RBAC_IMPLEMENTATION_GUIDE.md) | Step-by-step migration guide | Teams |
| 📝 | [MIGRATION_EXAMPLE_client_app.md](./MIGRATION_EXAMPLE_client_app.md) | Before/after code examples | Developers |
| 🔐 | [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) | Best practices for managing secrets | DevOps/Security |
| 🔑 | [PASSWORD_HASHING.md](./PASSWORD_HASHING.md) | Password hashing with Argon2 | DevOps/Security |
| 🔒 | [SECURITY_AUDIT_RBAC_2025-11-05.md](./SECURITY_AUDIT_RBAC_2025-11-05.md) | RBAC security audit | Security |
| 🛡️ | [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) | General security audit | Security |cumentation

This directory contains all documentation related to security, authentication, authorization, and Role-Based Access Control (RBAC).

## 📋 Start Here

**New to RBAC?** Start with [RBAC_INDEX.md](./RBAC_INDEX.md) - the master index for all RBAC documentation.

## 📚 Quick Links

| Priority | Document | Description | For |
|----------|----------|-------------|-----|
| ⭐⭐⭐ | [RBAC_INDEX.md](./RBAC_INDEX.md) | Master RBAC index with all documentation | Everyone |
| 🚀 | [RBAC_QUICK_START.md](./RBAC_QUICK_START.md) | 5-minute quick start guide | Developers |
| 📊 | [RBAC_FINAL_SUMMARY.md](./RBAC_FINAL_SUMMARY.md) | Executive summary and roadmap | Tech Leads |
| 📘 | [RBAC_IMPLEMENTATION_GUIDE.md](./RBAC_IMPLEMENTATION_GUIDE.md) | Step-by-step migration guide | Teams |
| 📝 | [MIGRATION_EXAMPLE_client_app.md](./MIGRATION_EXAMPLE_client_app.md) | Before/after code examples | Developers |
| � | [SECRETS_MANAGEMENT.md](./SECRETS_MANAGEMENT.md) | Best practices for managing secrets | DevOps/Security |
| �🔒 | [SECURITY_AUDIT_RBAC_2025-11-05.md](./SECURITY_AUDIT_RBAC_2025-11-05.md) | RBAC security audit | Security |
| 🛡️ | [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) | General security audit | Security |

## 🎯 Reading Path

### For Developers (30 min)
1. [RBAC_QUICK_START.md](./RBAC_QUICK_START.md) - 5 min
2. [MIGRATION_EXAMPLE_client_app.md](./MIGRATION_EXAMPLE_client_app.md) - 15 min
3. Start implementing with examples from the guide

### For Tech Leads (1.5 hours)
1. [RBAC_FINAL_SUMMARY.md](./RBAC_FINAL_SUMMARY.md) - 20 min
2. [RBAC_IMPLEMENTATION_GUIDE.md](./RBAC_IMPLEMENTATION_GUIDE.md) - 30 min
3. [SECURITY_AUDIT_RBAC_2025-11-05.md](./SECURITY_AUDIT_RBAC_2025-11-05.md) - 20 min

### For Security Officers (1 hour)
1. [SECURITY_AUDIT_RBAC_2025-11-05.md](./SECURITY_AUDIT_RBAC_2025-11-05.md) - 30 min
2. [SECURITY_AUDIT.md](./SECURITY_AUDIT.md) - 20 min
3. Review `user/permissions.py` source code - 10 min

## 🔑 Key Concepts

### Core Permission System

Located in `user/permissions.py`:

- **Decorators** for function-based views
- **Permission Classes** for DRF APIs
- **Helper Functions** for role checking
- **Audit Logging** for security events

### Roles

- `customer` - End users (customers)
- `admin` - Full system access
- `manager` - Backoffice management
- `tech` - Technicians
- `sales` - Sales team
- Custom roles as needed

## ✅ Quick Reference

```python
from user.permissions import require_customer_only, require_staff_role

# Customer-only view
@require_customer_only()
def customer_dashboard(request):
    pass

# Staff with specific roles
@require_staff_role(['admin', 'manager'])
def backoffice_reports(request):
    pass
```

## 📞 Need Help?

- Check [RBAC_INDEX.md](./RBAC_INDEX.md) for complete navigation
- Review inline documentation in `user/permissions.py`
- File GitHub issues tagged with `[rbac]` or `[security]`

---

**Back to**: [Documentation Index](../INDEX.md)
