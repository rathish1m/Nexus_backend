# Internationalization & Translation Documentation

This directory contains all documentation related to internationalization (i18n), translation management, and multi-language support.

## 📋 Master Guide

**Start here**: [INTERNATIONALIZATION_GUIDELINES.md](./INTERNATIONALIZATION_GUIDELINES.md)

## 📚 Documentation Index

### Core Guides

| Document | Description | Language |
|----------|-------------|----------|
| [INTERNATIONALIZATION_GUIDELINES.md](./INTERNATIONALIZATION_GUIDELINES.md) | Master i18n guidelines | English |
| [TRANSLATION_BEST_PRACTICES.md](./TRANSLATION_BEST_PRACTICES.md) | Translation best practices | English |
| [DATABASE_TRANSLATION_MANAGEMENT.md](./DATABASE_TRANSLATION_MANAGEMENT.md) | Database translation management | English |
| [I18N_FINALIZATION.md](./I18N_FINALIZATION.md) | i18n finalization status | English |
| [DOCUMENTATION_TRANSLATION_COMPLETE.md](./DOCUMENTATION_TRANSLATION_COMPLETE.md) | Translation completion report | English |

### Component Translations

| Document | Area | Description |
|----------|------|-------------|
| [PLAN_NAMES_TRANSLATION_GUIDE.md](./PLAN_NAMES_TRANSLATION_GUIDE.md) | Subscriptions | Plan name translations |
| [LOGIN_TRANSLATION_FIXES.md](./LOGIN_TRANSLATION_FIXES.md) | Authentication | Login page fixes |
| [CLIENT_AREA_TRANSLATION_FIXES.md](./CLIENT_AREA_TRANSLATION_FIXES.md) | Client Area | Client interface fixes |
| [SUBSCRIPTION_TEXT_CORRECTIONS.md](./SUBSCRIPTION_TEXT_CORRECTIONS.md) | Subscriptions | Subscription text corrections |
| [LANGUAGE_SELECTOR_FIXES.md](./LANGUAGE_SELECTOR_FIXES.md) | UI | Language selector fixes |
| [SUPPORT_LANGUAGE_SELECTOR_FIX.md](./SUPPORT_LANGUAGE_SELECTOR_FIX.md) | Support | Support language selector |
| [KYC_JS_TRANSLATION_ERROR.md](./KYC_JS_TRANSLATION_ERROR.md) | KYC | JavaScript translation fixes |

### Optimizations

| Document | Description |
|----------|-------------|
| [TRANSLATION_OPTIMIZATIONS.md](./TRANSLATION_OPTIMIZATIONS.md) | Translation performance optimizations |

## 🌍 Supported Languages

- **English (en)** - Source language ⭐
- **French (fr)** - Complete translation
- **Others** - Extensible

## 🛠️ Translation Workflow

### 1. Mark Strings for Translation

```python
from django.utils.translation import gettext_lazy as _

# In views or models
message = _("Welcome to NEXUS TELECOMS")
```

### 2. Generate Translation Files

```bash
python manage.py makemessages -l fr
```

### 3. Translate

Edit `locale/fr/LC_MESSAGES/django.po`:

```po
msgid "Welcome to NEXUS TELECOMS"
msgstr "Bienvenue chez NEXUS TELECOMS"
```

### 4. Compile Translations

```bash
python manage.py compilemessages
```

### 5. Validate

Run i18n compliance checker:

```bash
python check_i18n_compliance.py
```

## 🎯 Quick Reference

### For Developers

```python
# Template translation
{% load i18n %}
{% trans "Text to translate" %}

# Pluralization
{% blocktrans count counter=items|length %}
    {{ counter }} item
{% plural %}
    {{ counter }} items
{% endblocktrans %}

# Python code translation
from django.utils.translation import gettext_lazy as _
message = _("Error message")
```

### For Translators

1. Check [GUIDE_BONNES_PRATIQUES_TRADUCTION.md](./GUIDE_BONNES_PRATIQUES_TRADUCTION.md)
2. Use translation tools (Poedit, etc.)
3. Maintain consistency across translations
4. Test in context before committing

## ✅ Best Practices

1. **English as Source** - All strings start in English
2. **Use `gettext_lazy`** - For strings in models/settings
3. **Context Matters** - Add context with `pgettext`
4. **No Hardcoded Text** - All user-facing text must be translatable
5. **Database Content** - Store in English, translate on display

## 📊 Translation Coverage

Check current coverage:

```bash
python manage.py makemessages -l fr --dry-run
```

## 🔗 Related Documentation

- **Features**: [../features/](../features/) - UI component fixes
- **Guides**: [../guides/](../guides/) - Frontend integration

---

**Back to**: [Documentation Index](../INDEX.md)
