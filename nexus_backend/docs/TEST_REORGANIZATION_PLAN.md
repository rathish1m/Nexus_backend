# Test Files Reorganization Plan

**Date**: November 5, 2025
**Purpose**: Reorganize test files following Django best practices
**Current Issue**: 24 test files scattered at project root

---

## 📋 Current Situation

### Test Files at Root (24 files)
```
test_additional_equipment_validation.py
test_approval_request.py
test_billing_approval.py
test_billing_workflow.py
test_complete_dashboard_translations.py
test_complete_survey_validation.py
test_dashboard_translations.py
test_edit_api.py
test_edit_window.py
test_installation_logic.py
test_new_installation_workflow.py
test_new_required_fields.py
test_notifications.py
test_photo_upload_feature.py
test_reassignment.py
test_rejection_workflow.py
test_response_structure.py
test_simple_installation.py
test_survey_form.py
test_survey_validation_fix.py
test_survey_validation.py
test_translations.py
test_validation_preselected_fix.py
test_weather_fields_fix.py
```

---

## 🎯 Django Best Practices

### Recommended Structure

```
project_root/
├── app_name/
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── test_models.py
│   │   ├── test_views.py
│   │   ├── test_forms.py
│   │   ├── test_api.py
│   │   └── test_services.py
│   └── ...
└── tests/                      # Integration/E2E tests
    ├── __init__.py
    ├── integration/
    │   ├── __init__.py
    │   └── test_*.py
    └── e2e/
        ├── __init__.py
        └── test_*.py
```

### Principles

1. **Unit tests** → Within each app's `tests/` directory
2. **Integration tests** → Root `tests/integration/`
3. **E2E tests** → Root `tests/e2e/`
4. **Test organization** → Mirror app structure

---

## 📂 Proposed Reorganization

### Category 1: Site Survey Tests
**Target**: `site_survey/tests/`

- `test_survey_form.py`
- `test_survey_validation.py`
- `test_survey_validation_fix.py`
- `test_complete_survey_validation.py`
- `test_rejection_workflow.py`
- `test_approval_request.py`
- `test_weather_fields_fix.py`
- `test_validation_preselected_fix.py`
- `test_photo_upload_feature.py`

### Category 2: Installation Tests
**Target**: `tech/tests/` or new `installations/tests/`

- `test_installation_logic.py`
- `test_new_installation_workflow.py`
- `test_simple_installation.py`
- `test_reassignment.py`
- `test_new_required_fields.py`
- `test_additional_equipment_validation.py`

### Category 3: Billing Tests
**Target**: `billing_management/tests/`

- `test_billing_approval.py`
- `test_billing_workflow.py`

### Category 4: Translation/i18n Tests
**Target**: `tests/integration/i18n/`

- `test_translations.py`
- `test_dashboard_translations.py`
- `test_complete_dashboard_translations.py`

### Category 5: API Tests
**Target**: `api/tests/` or `tests/integration/api/`

- `test_edit_api.py`
- `test_response_structure.py`

### Category 6: Notification Tests
**Target**: `tests/integration/notifications/`

- `test_notifications.py`

### Category 7: UI/Window Tests
**Target**: `tests/e2e/` or specific app

- `test_edit_window.py`

---

## 🚀 Migration Strategy

### Phase 1: Create Directory Structure
```bash
# Site survey tests
mkdir -p site_survey/tests

# Tech/Installation tests (if doesn't exist)
mkdir -p tech/tests

# Integration tests
mkdir -p tests/integration/{i18n,api,notifications}

# E2E tests
mkdir -p tests/e2e
```

### Phase 2: Move Files

```bash
# Site Survey
mv test_survey_*.py site_survey/tests/
mv test_*_validation*.py site_survey/tests/
mv test_rejection_workflow.py site_survey/tests/
mv test_approval_request.py site_survey/tests/
mv test_weather_fields_fix.py site_survey/tests/
mv test_photo_upload_feature.py site_survey/tests/

# Installations
mv test_installation_*.py tech/tests/
mv test_*_installation_*.py tech/tests/
mv test_reassignment.py tech/tests/
mv test_new_required_fields.py tech/tests/
mv test_additional_equipment_validation.py tech/tests/

# Billing
mv test_billing_*.py billing_management/tests/

# Translations
mv test_*translations*.py tests/integration/i18n/

# API
mv test_edit_api.py api/tests/
mv test_response_structure.py api/tests/

# Notifications
mv test_notifications.py tests/integration/notifications/

# UI/E2E
mv test_edit_window.py tests/e2e/
```

### Phase 3: Create __init__.py Files

```bash
# Ensure all test directories have __init__.py
find . -type d -name tests -exec touch {}/__init__.py \;
touch tests/integration/__init__.py
touch tests/integration/i18n/__init__.py
touch tests/integration/api/__init__.py
touch tests/integration/notifications/__init__.py
touch tests/e2e/__init__.py
```

### Phase 4: Update pytest Configuration

Update `pytest.ini`:
```ini
[pytest]
DJANGO_SETTINGS_MODULE = nexus_backend.settings
python_files = tests.py test_*.py *_tests.py
python_classes = Test*
python_functions = test_*
testpaths =
    .
    tests
    */tests

# Add markers for different test types
markers =
    unit: Unit tests
    integration: Integration tests
    e2e: End-to-end tests
    slow: Tests that take a long time
```

---

## ✅ Benefits

### Before
- ❌ 24 test files at root
- ❌ Hard to find tests for specific feature
- ❌ No clear organization
- ❌ Difficult to run tests by category

### After
- ✅ Tests organized by app/feature
- ✅ Clear separation: unit/integration/e2e
- ✅ Easy to find and run tests
- ✅ Follows Django conventions
- ✅ Scalable structure

---

## 🧪 Running Tests After Reorganization

```bash
# All tests
pytest

# Unit tests only (app-specific)
pytest site_survey/tests/
pytest tech/tests/
pytest billing_management/tests/

# Integration tests
pytest tests/integration/

# E2E tests
pytest tests/e2e/

# Specific test file
pytest site_survey/tests/test_survey_validation.py

# By marker
pytest -m unit
pytest -m integration
pytest -m e2e
```

---

## 📝 Checklist

- [ ] Create directory structure
- [ ] Move survey tests to `site_survey/tests/`
- [ ] Move installation tests to `tech/tests/`
- [ ] Move billing tests to `billing_management/tests/`
- [ ] Move translation tests to `tests/integration/i18n/`
- [ ] Move API tests to `tests/integration/api/`
- [ ] Move notification tests to `tests/integration/notifications/`
- [ ] Move UI tests to `tests/e2e/`
- [ ] Create all `__init__.py` files
- [ ] Update `pytest.ini` configuration
- [ ] Update CI/CD configuration (if any)
- [ ] Run all tests to verify
- [ ] Update documentation
- [ ] Commit changes

---

## 🔗 Related Files

- `pytest.ini` - Test configuration
- `conftest.py` - Shared fixtures
- `.coveragerc` - Coverage configuration
- `.github/workflows/` - CI/CD (if applicable)

---

**Status**: Ready to execute
**Estimated Time**: ~30 minutes
**Risk**: Low (non-breaking change)
