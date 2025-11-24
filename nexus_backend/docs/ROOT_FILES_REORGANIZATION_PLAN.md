# Root Files Reorganization Plan

## Current Situation

**Problem:** 15 Python/shell scripts cluttering project root
**Impact:** Poor project organization, violates Django best practices
**Solution:** Move files to appropriate directories based on their purpose

---

## Files to Reorganize

### Category 1: Documentation Scripts (5 files)
**Destination:** `scripts/docs/`

1. ✅ `check_docs_structure.py` - Validates documentation structure
2. ✅ `check_filename_i18n.py` - Checks i18n compliance of filenames
3. ✅ `check_i18n_compliance.py` - Validates i18n compliance
4. ✅ `browse_docs.sh` - Documentation browser

### Category 2: Development/Debug Scripts (3 files)
**Destination:** `scripts/dev/`

1. ✅ `analyze_rejection_workflow.py` - Analyzes site survey workflow
2. ✅ `demo_new_installation_logic.py` - Demo script for installation
3. ✅ `verify_photo_upload.py` - Photo upload verification

### Category 3: Data Management Scripts (5 files)
**Destination:** `scripts/data/`

1. ✅ `check_inventory.py` - Inventory verification
2. ✅ `check_signal_duplicates.py` - Signal duplicate detection
3. ✅ `clean_duplicates.py` - Cleanup duplicates
4. ✅ `create_extra_charge_test_data.py` - Test data creation
5. ✅ `create_test_installation.py` - Test installation creation

### Category 4: Migration/Fix Scripts (2 files)
**Destination:** `scripts/fixes/`

1. ✅ `fix_billing_customers.py` - Billing customer fixes
2. ✅ `verify_billing_creation.py` - Billing verification

### Category 5: Keep at Root (Essential Files)
**No changes needed:**

- ✅ `manage.py` - Django management command (MUST stay at root)
- ✅ `conftest.py` - Pytest configuration (MUST stay at root)
- ✅ `README.md` - Project documentation (standard location)
- ✅ `requirements.txt` - Dependencies (standard location)
- ✅ `requirements-dev.txt` - Dev dependencies (standard location)
- ✅ `runtime.txt` - Runtime specification (deployment)
- ✅ `pytest.ini` - Pytest configuration (standard location)
- ✅ `Makefile` - Build automation (standard location)
- ✅ `Dockerfile` - Docker configuration (standard location)
- ✅ `docker-compose*.yml` - Docker compose files (standard location)

---

## Proposed Structure

```
nexus_backend/
├── scripts/
│   ├── docs/              ← Documentation validation scripts
│   │   ├── __init__.py
│   │   ├── check_docs_structure.py
│   │   ├── check_filename_i18n.py
│   │   ├── check_i18n_compliance.py
│   │   └── browse_docs.sh
│   │
│   ├── dev/               ← Development/debugging scripts
│   │   ├── __init__.py
│   │   ├── analyze_rejection_workflow.py
│   │   ├── demo_new_installation_logic.py
│   │   └── verify_photo_upload.py
│   │
│   ├── data/              ← Data management scripts
│   │   ├── __init__.py
│   │   ├── check_inventory.py
│   │   ├── check_signal_duplicates.py
│   │   ├── clean_duplicates.py
│   │   ├── create_extra_charge_test_data.py
│   │   └── create_test_installation.py
│   │
│   └── fixes/             ← Migration/fix scripts
│       ├── __init__.py
│       ├── fix_billing_customers.py
│       └── verify_billing_creation.py
│
├── manage.py              ← KEEP (Django CLI)
├── conftest.py            ← KEEP (pytest root config)
├── pytest.ini             ← KEEP (pytest settings)
├── README.md              ← KEEP (project docs)
├── requirements.txt       ← KEEP (dependencies)
├── requirements-dev.txt   ← KEEP (dev dependencies)
├── runtime.txt            ← KEEP (runtime version)
├── Makefile               ← KEEP (build commands)
└── Dockerfile             ← KEEP (container config)
```

---

## Migration Steps

### Phase 1: Create Directory Structure
```bash
mkdir -p scripts/docs
mkdir -p scripts/dev
mkdir -p scripts/data
mkdir -p scripts/fixes
```

### Phase 2: Move Documentation Scripts
```bash
mv check_docs_structure.py scripts/docs/
mv check_filename_i18n.py scripts/docs/
mv check_i18n_compliance.py scripts/docs/
mv browse_docs.sh scripts/docs/
```

### Phase 3: Move Development Scripts
```bash
mv analyze_rejection_workflow.py scripts/dev/
mv demo_new_installation_logic.py scripts/dev/
mv verify_photo_upload.py scripts/dev/
```

### Phase 4: Move Data Management Scripts
```bash
mv check_inventory.py scripts/data/
mv check_signal_duplicates.py scripts/data/
mv clean_duplicates.py scripts/data/
mv create_extra_charge_test_data.py scripts/data/
mv create_test_installation.py scripts/data/
```

### Phase 5: Move Fix Scripts
```bash
mv fix_billing_customers.py scripts/fixes/
mv verify_billing_creation.py scripts/fixes/
```

### Phase 6: Create __init__.py Files
```bash
touch scripts/docs/__init__.py
touch scripts/dev/__init__.py
touch scripts/data/__init__.py
touch scripts/fixes/__init__.py
```

### Phase 7: Update Makefile
Update any references to moved scripts in Makefile

---

## Makefile Updates Needed

### Current Issues to Check:
1. Any commands referencing moved scripts
2. Path updates needed for script execution
3. Add new helper commands for organized scripts

### Proposed Makefile Additions:
```makefile
# Documentation validation
.PHONY: check-docs
check-docs:
	python scripts/docs/check_docs_structure.py
	python scripts/docs/check_i18n_compliance.py
	python scripts/docs/check_filename_i18n.py

# Browse documentation
.PHONY: browse-docs
browse-docs:
	bash scripts/docs/browse_docs.sh

# Data management
.PHONY: check-inventory
check-inventory:
	python scripts/data/check_inventory.py

.PHONY: clean-duplicates
clean-duplicates:
	python scripts/data/clean_duplicates.py

# Development helpers
.PHONY: demo-installation
demo-installation:
	python scripts/dev/demo_new_installation_logic.py
```

---

## Benefits

### Organization
- ✅ Scripts categorized by purpose
- ✅ Clear separation of concerns
- ✅ Follows Django/Python best practices
- ✅ Professional project structure

### Maintainability
- ✅ Easy to find scripts by category
- ✅ Reduced root directory clutter (15 files → 0)
- ✅ Clear script ownership
- ✅ Better code navigation

### Developer Experience
- ✅ Intuitive script discovery
- ✅ Makefile commands for common tasks
- ✅ Clear categorization
- ✅ Professional appearance

---

## Validation

### Before
```bash
$ ls -1 *.py *.sh | grep -v manage.py | grep -v conftest.py | wc -l
15
```

### After
```bash
$ ls -1 *.py *.sh | grep -v manage.py | grep -v conftest.py
# (empty - all scripts moved)
```

---

## Files That MUST Stay at Root

Django and Python standards dictate these files stay at root:

1. **`manage.py`** - Django's command-line utility
2. **`conftest.py`** - Pytest's root configuration
3. **`pytest.ini`** - Pytest settings
4. **`README.md`** - Project documentation
5. **`requirements.txt`** - Python dependencies
6. **`requirements-dev.txt`** - Development dependencies
7. **`runtime.txt`** - Python runtime version (for deployment)
8. **`Makefile`** - Build automation
9. **`Dockerfile`** - Container configuration
10. **`docker-compose*.yml`** - Container orchestration
11. **`.gitignore`** - Git configuration
12. **`.pre-commit-config.yaml`** - Pre-commit hooks
13. **`setup.py` / `pyproject.toml`** - Package configuration (if present)

---

## Next Steps

1. ✅ Create directory structure
2. ✅ Move files to appropriate directories
3. ✅ Create __init__.py files
4. ✅ Update Makefile references
5. ✅ Test script execution from new locations
6. ✅ Update documentation
7. ✅ Commit changes

---

## Related Documentation

- **Test Reorganization:** `docs/TEST_REORGANIZATION_SUCCESS.md`
- **Documentation Organization:** `docs/INDEX.md`
- **Script Locations:** `scripts/README.md` (to be created)

---

**Total Files to Move:** 15
**Estimated Time:** 15-20 minutes
**Risk Level:** Low (scripts only, no code changes)
