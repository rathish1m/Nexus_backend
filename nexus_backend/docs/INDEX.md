# NEXUS TELECOMS - Documentation Index

**Project**: NEXUS TELECOMS Backend
**Version**: 2.0
**Last Updated**: November 5, 2025
**Language**: English (en-US) - Source of Truth

---

## 📚 Table of Contents

1. [Project Overview](#project-overview)
2. [Security & RBAC](#security--rbac)
3. [Billing System](#billing-system)
4. [Internationalization & Translations](#internationalization--translations)
5. [Installation Management](#installation-management)
6. [Survey System](#survey-system)
7. [Payment System](#payment-system)
8. [Features & Fixes](#features--fixes)
9. [Integration Guides](#integration-guides)
10. [Project Summaries](#project-summaries)

---

## 📖 Project Overview

NEXUS TELECOMS is a Django-based backend system for managing telecommunications services, including:
- Customer management and KYC
- Installation workflow (site surveys, equipment assignment)
- Subscription billing and payment processing
- Multi-role access control (customers, technicians, sales, backoffice)
- Multi-language support (English, French, etc.)

### Quick Links

- **Main README**: [../README.md](../README.md)
- **Project Summary**: [PROJECT_FINAL_SUMMARY.md](./PROJECT_FINAL_SUMMARY.md)
- **Backend Implementation**: [BACKEND_IMPLEMENTATION_SUMMARY.md](./BACKEND_IMPLEMENTATION_SUMMARY.md)

---

## 🔒 Security & RBAC

**Location**: [`docs/security/`](./security/)

Role-Based Access Control (RBAC) system ensuring users access only authorized resources.

### Documentation

| Document | Description | Audience |
|----------|-------------|----------|
| **[RBAC_INDEX.md](./security/RBAC_INDEX.md)** ⭐ | Master index for all RBAC documentation | All |
| **[RBAC_QUICK_START.md](./security/RBAC_QUICK_START.md)** 🚀 | 5-minute quick start guide | Developers |
| **[RBAC_FINAL_SUMMARY.md](./security/RBAC_FINAL_SUMMARY.md)** | Executive summary and roadmap | Tech Leads |
| **[RBAC_IMPLEMENTATION_GUIDE.md](./security/RBAC_IMPLEMENTATION_GUIDE.md)** | Step-by-step migration guide | Developers |
| **[MIGRATION_EXAMPLE_client_app.md](./security/MIGRATION_EXAMPLE_client_app.md)** | Before/after code examples | Developers |
| **[SECURITY_AUDIT_RBAC_2025-11-05.md](./security/SECURITY_AUDIT_RBAC_2025-11-05.md)** | Security audit and compliance | Security Officers |
| **[SECURITY_AUDIT.md](./security/SECURITY_AUDIT.md)** | General security audit | Security Officers |

### Key Features

- ✅ Centralized permission system (`user/permissions.py`)
- ✅ Decorators for function-based views
- ✅ DRF permission classes for APIs
- ✅ 35+ comprehensive unit tests
- ✅ Full i18n support with `gettext_lazy`
- ✅ Audit logging for access denials

### Quick Start

```python
from user.permissions import require_customer_only, require_staff_role

@require_customer_only()
def customer_dashboard(request):
    # Only accessible by customers (not staff)
    pass

@require_staff_role(['admin', 'manager'])
def backoffice_reports(request):
    # Only accessible by admins and managers
    pass
```

**Start Here**: [security/RBAC_INDEX.md](./security/RBAC_INDEX.md)

---

## 💰 Billing System

**Location**: [`docs/billing/`](./billing/)

Comprehensive billing and invoicing system for subscriptions and extra charges.

### Documentation

| Document | Description |
|----------|-------------|
| **[CLIENT_BILLING_ACCESS_GUIDE.md](./billing/CLIENT_BILLING_ACCESS_GUIDE.md)** | Client-side billing access guide |
| **[BILLING_WORKFLOW_VERIFICATION.md](./billing/BILLING_WORKFLOW_VERIFICATION.md)** | Billing workflow validation |
| **[BILLING_MODAL_IMPLEMENTATION.md](./billing/BILLING_MODAL_IMPLEMENTATION.md)** | Billing modal UI implementation |
| **[BILLING_API_PARAMETER_FIX.md](./billing/BILLING_API_PARAMETER_FIX.md)** | API parameter fixes |
| **[BILLING_REVIEW_FIX.md](./billing/BILLING_REVIEW_FIX.md)** | Billing review fixes |
| **[BILLING_TRANSLATION_FIX.md](./billing/BILLING_TRANSLATION_FIX.md)** | Translation fixes for billing |
| **[ADDITIONAL_BILLING_SYSTEM.md](./billing/ADDITIONAL_BILLING_SYSTEM.md)** | Additional billing features |

### Key Features

- Monthly subscription billing
- Extra charges (installation fees, equipment)
- Invoice generation and tracking
- Payment status management
- Customer billing history

---

## 🌍 Internationalization & Translations

**Location**: [`docs/translations/`](./translations/)

Multi-language support with English as the source of truth.

### Documentation

| Document | Description |
|----------|-------------|
| **[INTERNATIONALIZATION_GUIDELINES.md](./translations/INTERNATIONALIZATION_GUIDELINES.md)** ⭐ | Master i18n guidelines |
| **[TRANSLATION_BEST_PRACTICES.md](./translations/TRANSLATION_BEST_PRACTICES.md)** | Translation best practices |
| **[DATABASE_TRANSLATION_MANAGEMENT.md](./translations/DATABASE_TRANSLATION_MANAGEMENT.md)** | Database translation management |
| **[PLAN_NAMES_TRANSLATION_GUIDE.md](./translations/PLAN_NAMES_TRANSLATION_GUIDE.md)** | Subscription plan name translations |
| **[TRANSLATION_OPTIMIZATIONS.md](./translations/TRANSLATION_OPTIMIZATIONS.md)** | Translation optimizations |
| **[I18N_FINALIZATION.md](./translations/I18N_FINALIZATION.md)** | i18n finalization |
| **[DOCUMENTATION_TRANSLATION_COMPLETE.md](./translations/DOCUMENTATION_TRANSLATION_COMPLETE.md)** | Translation completion status |
| **[LOGIN_TRANSLATION_FIXES.md](./translations/LOGIN_TRANSLATION_FIXES.md)** | Login page translation fixes |
| **[CLIENT_AREA_TRANSLATION_FIXES.md](./translations/CLIENT_AREA_TRANSLATION_FIXES.md)** | Client area translation fixes |
| **[SUBSCRIPTION_TEXT_CORRECTIONS.md](./translations/SUBSCRIPTION_TEXT_CORRECTIONS.md)** | Subscription text corrections |
| **[LANGUAGE_SELECTOR_FIXES.md](./translations/LANGUAGE_SELECTOR_FIXES.md)** | Language selector fixes |
| **[SUPPORT_LANGUAGE_SELECTOR_FIX.md](./translations/SUPPORT_LANGUAGE_SELECTOR_FIX.md)** | Support language selector |
| **[KYC_JS_TRANSLATION_ERROR.md](./translations/KYC_JS_TRANSLATION_ERROR.md)** | KYC JavaScript translation fixes |

### Key Principles

- **Source Language**: English (en-US)
- **Translation Method**: Django's `gettext_lazy`
- **Supported Languages**: French (fr), extendable
- **Database Content**: Stored in English, translated on display

### Workflow

```bash
# Generate translation files
python manage.py makemessages -l fr

# Edit translations
# Edit locale/fr/LC_MESSAGES/django.po

# Compile translations
python manage.py compilemessages
```

---

## 🏗️ Installation Management

**Location**: [`docs/installations/`](./installations/)

Complete installation workflow from site survey to equipment installation.

### Documentation

| Document | Description |
|----------|-------------|
| **[NEW_INSTALLATION_LOGIC.md](./installations/NEW_INSTALLATION_LOGIC.md)** | New installation workflow logic |
| **[TECHNICAL_SUMMARY_INSTALLATION.md](./installations/TECHNICAL_SUMMARY_INSTALLATION.md)** | Technical implementation summary |
| **[SUMMARY_INSTALLATION_ACTIVITY.md](./installations/SUMMARY_INSTALLATION_ACTIVITY.md)** | Installation activity tracking |
| **[INSTALLATION_ACTIVITY_EVOLUTION.md](./installations/INSTALLATION_ACTIVITY_EVOLUTION.md)** | Activity evolution and metrics |
| **[COMPLETED_INSTALLATIONS_FEATURE.md](./installations/COMPLETED_INSTALLATIONS_FEATURE.md)** | Completed installations feature |
| **[COMPLETED_INSTALLATIONS_FILTERS.md](./installations/COMPLETED_INSTALLATIONS_FILTERS.md)** | Filtering and search |
| **[REASSIGNMENT_IMPLEMENTATION.md](./installations/REASSIGNMENT_IMPLEMENTATION.md)** | Technician reassignment |

### Key Features

- Site survey scheduling and approval
- Equipment (Starlink kits) assignment
- Technician assignment and reassignment
- Installation status tracking
- Completion workflow

---

## 📋 Survey System

**Location**: [`docs/surveys/`](./surveys/)

Site survey workflow for pre-installation assessment.

### Documentation

| Document | Description |
|----------|-------------|
| **[SURVEY_VALIDATION_SUMMARY.md](./surveys/SURVEY_VALIDATION_SUMMARY.md)** | Survey validation logic |
| **[SURVEY_REJECTION_WORKFLOW_SPECS.md](./surveys/SURVEY_REJECTION_WORKFLOW_SPECS.md)** | Rejection workflow specifications |
| **[SURVEY_APPROVAL_FIX.md](./surveys/SURVEY_APPROVAL_FIX.md)** | Approval process fixes |
| **[SITE_SURVEY_IMPROVEMENTS.md](./surveys/SITE_SURVEY_IMPROVEMENTS.md)** | Survey improvements |
| **[CONDUCT_SURVEY_IMPLEMENTATION.md](./surveys/CONDUCT_SURVEY_IMPLEMENTATION.md)** | Survey conduct implementation |

### Key Features

- Survey request submission
- Technician survey assignment
- Survey conduct (photos, coordinates, notes)
- Approval/rejection workflow
- Resubmission process

---

## 💳 Payment System

**Location**: [`docs/payments/`](./payments/)

Payment processing and payment methods management.

### Documentation

| Document | Description |
|----------|-------------|
| **[PAYMENT_PAGE_REDESIGN_SUMMARY.md](./payments/PAYMENT_PAGE_REDESIGN_SUMMARY.md)** | Payment page redesign |
| **[PAYMENT_PAGE_BEFORE_AFTER.md](./payments/PAYMENT_PAGE_BEFORE_AFTER.md)** | Before/after comparison |
| **[PAYMENT_PAGE_TESTING_GUIDE.md](./payments/PAYMENT_PAGE_TESTING_GUIDE.md)** | Testing guide |
| **[PAYMENT_METHODS_ADMIN_SETUP.md](./payments/PAYMENT_METHODS_ADMIN_SETUP.md)** | Admin setup guide |

### Key Features

- Multiple payment methods (Mobile Money, Bank Transfer)
- Payment proof upload
- Payment verification by backoffice
- Payment history tracking

---

## ✨ Features & Fixes

**Location**: [`docs/features/`](./features/)

Individual feature implementations and bug fixes.

### Documentation

| Document | Description |
|----------|-------------|
| **[ADD_ITEM_BUTTON_FIX.md](./features/ADD_ITEM_BUTTON_FIX.md)** | Add item button fixes |
| **[FIELD_MAPPING_FIX.md](./features/FIELD_MAPPING_FIX.md)** | Field mapping corrections |
| **[DASHBOARD_CORRECTIONS.md](./features/DASHBOARD_CORRECTIONS.md)** | Dashboard corrections |
| **[TABLE_COLUMN_FIXES.md](./features/TABLE_COLUMN_FIXES.md)** | Table column fixes |
| **[SUBSCRIPTION_ENHANCEMENTS.md](./features/SUBSCRIPTION_ENHANCEMENTS.md)** | Subscription enhancements |
| **[RESULTS_OPTIMIZATION.md](./features/RESULTS_OPTIMIZATION.md)** | Results optimization |

---

## 📘 Integration Guides

**Location**: [`docs/guides/`](./guides/)

Step-by-step integration and testing guides.

### Documentation

| Document | Description |
|----------|-------------|
| **[FRONTEND_INTEGRATION_GUIDE.md](./guides/FRONTEND_INTEGRATION_GUIDE.md)** | Frontend integration |
| **[FRONTEND_INTEGRATION_COMPLETE.md](./guides/FRONTEND_INTEGRATION_COMPLETE.md)** | Integration completion |
| **[FINAL_IMPLEMENTATION_GUIDE.md](./guides/FINAL_IMPLEMENTATION_GUIDE.md)** | Final implementation |
| **[KYC_RESUBMISSION_TEST_GUIDE.md](./guides/KYC_RESUBMISSION_TEST_GUIDE.md)** | KYC testing guide |

---

## 📊 Project Summaries

**Location**: [`docs/`](.)

High-level project summaries and audit reports.

### Documentation

| Document | Description |
|----------|-------------|
| **[PROJECT_FINAL_SUMMARY.md](./PROJECT_FINAL_SUMMARY.md)** | Complete project summary |
| **[FINAL_SUMMARY.md](./FINAL_SUMMARY.md)** | Final implementation summary |
| **[BACKEND_IMPLEMENTATION_SUMMARY.md](./BACKEND_IMPLEMENTATION_SUMMARY.md)** | Backend implementation details |
| **[audit_codex_report.md](./audit_codex_report.md)** | Code audit report |

---

## 🗂️ Directory Structure

```
nexus_backend/
├── docs/                           # 📁 All documentation
│   ├── INDEX.md                    # 👈 You are here
│   ├── security/                   # 🔒 RBAC & security
│   ├── billing/                    # 💰 Billing system
│   ├── translations/               # 🌍 i18n & translations
│   ├── installations/              # 🏗️ Installation workflow
│   ├── surveys/                    # 📋 Survey system
│   ├── payments/                   # 💳 Payment processing
│   ├── features/                   # ✨ Features & fixes
│   └── guides/                     # 📘 Integration guides
├── user/                           # User management app
│   ├── permissions.py              # 🔑 RBAC system
│   └── tests/test_permissions.py   # 🧪 Permission tests
├── client_app/                     # Customer-facing app
├── backoffice/                     # Staff management app
├── tech/                           # Technician app
├── sales/                          # Sales team app
├── api/                            # REST API
└── README.md                       # Main project README
```

---

## 🎯 Quick Navigation by Role

### For Developers

1. **Getting Started**: [../README.md](../README.md)
2. **RBAC Quick Start**: [security/RBAC_QUICK_START.md](./security/RBAC_QUICK_START.md)
3. **Frontend Integration**: [guides/FRONTEND_INTEGRATION_GUIDE.md](./guides/FRONTEND_INTEGRATION_GUIDE.md)

### For Tech Leads

1. **Project Summary**: [PROJECT_FINAL_SUMMARY.md](./PROJECT_FINAL_SUMMARY.md)
2. **RBAC Summary**: [security/RBAC_FINAL_SUMMARY.md](./security/RBAC_FINAL_SUMMARY.md)
3. **Implementation Guide**: [security/RBAC_IMPLEMENTATION_GUIDE.md](./security/RBAC_IMPLEMENTATION_GUIDE.md)

### For Security Officers

1. **RBAC Security Audit**: [security/SECURITY_AUDIT_RBAC_2025-11-05.md](./security/SECURITY_AUDIT_RBAC_2025-11-05.md)
2. **General Security Audit**: [security/SECURITY_AUDIT.md](./security/SECURITY_AUDIT.md)
3. **Permission System**: [security/RBAC_IMPLEMENTATION_GUIDE.md](./security/RBAC_IMPLEMENTATION_GUIDE.md)

### For QA Engineers

1. **Payment Testing**: [payments/PAYMENT_PAGE_TESTING_GUIDE.md](./payments/PAYMENT_PAGE_TESTING_GUIDE.md)
2. **KYC Testing**: [guides/KYC_RESUBMISSION_TEST_GUIDE.md](./guides/KYC_RESUBMISSION_TEST_GUIDE.md)
3. **RBAC Testing**: Run `pytest user/tests/test_permissions.py`

---

## 📞 Support & Contribution

### Filing Issues

- Tag security issues with `[security]`
- Tag RBAC issues with `[rbac]`
- Tag i18n issues with `[i18n]`

### Code Review

All changes require:
- Unit tests with >80% coverage
- Security review for permission changes
- i18n compliance check

### Resources

- **Django Docs**: https://docs.djangoproject.com/
- **DRF Docs**: https://www.django-rest-framework.org/
- **OWASP**: https://owasp.org/

---

## 📈 Documentation Metrics

- **Total Documents**: 60+
- **Security Docs**: 7
- **Billing Docs**: 7
- **Translation Docs**: 13
- **Installation Docs**: 7
- **Survey Docs**: 5
- **Payment Docs**: 4
- **Feature Docs**: 6
- **Guide Docs**: 4

---

**Maintained By**: VirgoCoachman
**Last Updated**: November 5, 2025
**Next Review**: December 5, 2025 (monthly)
