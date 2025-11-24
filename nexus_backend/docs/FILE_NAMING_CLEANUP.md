# Documentation File Naming Cleanup

**Date**: November 5, 2025
**Purpose**: Ensure all documentation follows English naming convention (source of truth)
**Status**: Action Required

---

## 📋 Current Issue

Several documentation files still use **French names**, violating the i18n principle:
- **Source Language**: English (en-US)
- **Translation**: Content can be in French, but filenames and structure must be English

---

## 🔄 Files Requiring Renaming

### Translation Documentation (`docs/translations/`)

| Current French Name | → | Proposed English Name |
|---------------------|---|----------------------|
| `GUIDE_BONNES_PRATIQUES_TRADUCTION.md` | → | `TRANSLATION_BEST_PRACTICES.md` |
| `GESTION_DONNEES_BDD_TRADUCTION.md` | → | `DATABASE_TRANSLATION_MANAGEMENT.md` |
| `OPTIMISATION_TRADUCTIONS.md` | → | `TRANSLATION_OPTIMIZATIONS.md` |
| `FINALISATION_INTERNATIONALISATION.md` | → | `I18N_FINALIZATION.md` |
| `CORRECTION_TRADUCTIONS_LOGIN_FINAL.md` | → | `LOGIN_TRANSLATION_FIXES.md` |
| `CORRECTION_TRADUCTIONS_CLIENT_FINAL.md` | → | `CLIENT_AREA_TRANSLATION_FIXES.md` |
| `CORRECTION_TEXTES_ABONNEMENTS.md` | → | `SUBSCRIPTION_TEXT_CORRECTIONS.md` |
| `CORRECTION_SELECTEUR_LANGUE.md` | → | `LANGUAGE_SELECTOR_FIXES.md` |

### Features Documentation (`docs/features/`)

| Current French Name | → | Proposed English Name |
|---------------------|---|----------------------|
| `CORRECTION_DASHBOARD_FINAL.md` | → | `DASHBOARD_CORRECTIONS.md` |
| `CORRECTION_FINALE_COLONNES_TABLEAU.md` | → | `TABLE_COLUMN_FIXES.md` |
| `CORRECTION_COMPLEMENT_ABONNEMENTS.md` | → | `SUBSCRIPTION_ENHANCEMENTS.md` |
| `OPTIMISATION_RESULTATS.md` | → | `RESULTS_OPTIMIZATION.md` |

---

## 🎯 Renaming Strategy

### Option 1: Immediate Rename (Recommended)

```bash
# Translation files
cd docs/translations/
mv GUIDE_BONNES_PRATIQUES_TRADUCTION.md TRANSLATION_BEST_PRACTICES.md
mv GESTION_DONNEES_BDD_TRADUCTION.md DATABASE_TRANSLATION_MANAGEMENT.md
mv OPTIMISATION_TRADUCTIONS.md TRANSLATION_OPTIMIZATIONS.md
mv FINALISATION_INTERNATIONALISATION.md I18N_FINALIZATION.md
mv CORRECTION_TRADUCTIONS_LOGIN_FINAL.md LOGIN_TRANSLATION_FIXES.md
mv CORRECTION_TRADUCTIONS_CLIENT_FINAL.md CLIENT_AREA_TRANSLATION_FIXES.md
mv CORRECTION_TEXTES_ABONNEMENTS.md SUBSCRIPTION_TEXT_CORRECTIONS.md
mv CORRECTION_SELECTEUR_LANGUE.md LANGUAGE_SELECTOR_FIXES.md

# Feature files
cd ../features/
mv CORRECTION_DASHBOARD_FINAL.md DASHBOARD_CORRECTIONS.md
mv CORRECTION_FINALE_COLONNES_TABLEAU.md TABLE_COLUMN_FIXES.md
mv CORRECTION_COMPLEMENT_ABONNEMENTS.md SUBSCRIPTION_ENHANCEMENTS.md
mv OPTIMISATION_RESULTATS.md RESULTS_OPTIMIZATION.md
```

### Option 2: Git-Aware Rename (Preserves History)

```bash
# Translation files
cd docs/translations/
git mv GUIDE_BONNES_PRATIQUES_TRADUCTION.md TRANSLATION_BEST_PRACTICES.md
git mv GESTION_DONNEES_BDD_TRADUCTION.md DATABASE_TRANSLATION_MANAGEMENT.md
git mv OPTIMISATION_TRADUCTIONS.md TRANSLATION_OPTIMIZATIONS.md
git mv FINALISATION_INTERNATIONALISATION.md I18N_FINALIZATION.md
git mv CORRECTION_TRADUCTIONS_LOGIN_FINAL.md LOGIN_TRANSLATION_FIXES.md
git mv CORRECTION_TRADUCTIONS_CLIENT_FINAL.md CLIENT_AREA_TRANSLATION_FIXES.md
git mv CORRECTION_TEXTES_ABONNEMENTS.md SUBSCRIPTION_TEXT_CORRECTIONS.md
git mv CORRECTION_SELECTEUR_LANGUE.md LANGUAGE_SELECTOR_FIXES.md

# Feature files
cd ../features/
git mv CORRECTION_DASHBOARD_FINAL.md DASHBOARD_CORRECTIONS.md
git mv CORRECTION_FINALE_COLONNES_TABLEAU.md TABLE_COLUMN_FIXES.md
git mv CORRECTION_COMPLEMENT_ABONNEMENTS.md SUBSCRIPTION_ENHANCEMENTS.md
git mv OPTIMISATION_RESULTATS.md RESULTS_OPTIMIZATION.md
```

---

## 📝 Post-Rename Actions

### 1. Update INDEX.md References

```bash
# Update docs/INDEX.md with new filenames
# Update docs/translations/README.md with new filenames
# Update docs/features/README.md with new filenames
```

### 2. Update Internal Links

Search for references to old filenames in all .md files:

```bash
cd /home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend
grep -r "GUIDE_BONNES_PRATIQUES_TRADUCTION" docs/
grep -r "GESTION_DONNEES_BDD_TRADUCTION" docs/
grep -r "OPTIMISATION_TRADUCTIONS" docs/
grep -r "CORRECTION_DASHBOARD_FINAL" docs/
# ... etc for all renamed files
```

### 3. Validate Links

```bash
python scripts/validate_docs_structure.py
```

---

## ✅ Validation Checklist

After renaming:

- [ ] All filenames use English naming convention
- [ ] No French words in filenames (except proper nouns)
- [ ] INDEX.md updated with new paths
- [ ] README files updated in each directory
- [ ] Internal links updated (no broken links)
- [ ] Git history preserved (if using git mv)
- [ ] Validation script passes

---

## 🌍 i18n Naming Principles

### ✅ Correct Approach

```
✅ Filename: TRANSLATION_BEST_PRACTICES.md
✅ Content: Can be in French, English, or multilingual
✅ Headers: English preferred for consistency
✅ Code examples: English variable/function names
```

### ❌ Incorrect Approach

```
❌ Filename: GUIDE_BONNES_PRATIQUES_TRADUCTION.md
❌ Reason: French filename violates source-of-truth principle
```

### Rationale

1. **Source of Truth**: English filenames ensure consistency across teams
2. **Tooling Compatibility**: English filenames work better with CI/CD
3. **International Teams**: Non-French speakers can navigate structure
4. **Git Clarity**: Diffs and logs are clearer with English filenames
5. **URL Friendliness**: English paths work better in web contexts

---

## 📊 Impact Analysis

| Category | Files Affected | Estimated Time |
|----------|----------------|----------------|
| Translation docs | 8 files | 15 minutes |
| Feature docs | 4 files | 10 minutes |
| INDEX updates | 3 files | 10 minutes |
| Link validation | All docs | 15 minutes |
| **TOTAL** | **15 files** | **~50 minutes** |

---

## 🚀 Execution Plan

### Phase 1: Rename Files (10 min)

```bash
./scripts/rename_french_docs.sh  # Create this script
```

### Phase 2: Update References (20 min)

```bash
./scripts/update_doc_links.sh
```

### Phase 3: Validate (10 min)

```bash
python scripts/validate_docs_structure.py
python check_i18n_compliance.py
```

### Phase 4: Commit (5 min)

```bash
git add docs/
git commit -m "docs: rename French filenames to English (i18n compliance)"
```

---

## 🔗 Related Documentation

- [INTERNATIONALIZATION_GUIDELINES.md](./translations/INTERNATIONALIZATION_GUIDELINES.md)
- [docs/INDEX.md](./INDEX.md)
- [RBAC_INDEX.md](./security/RBAC_INDEX.md)

---

## 📝 Notes

- **Backward Compatibility**: Old French filenames will break if external links exist
- **Documentation Search**: Update any external documentation referencing old names
- **Team Notification**: Inform team of filename changes to update bookmarks

---

**Action Required**: Execute rename script to align with i18n best practices.

**Priority**: Medium (structural cleanup, not blocking functionality)

**Owner**: Development Team
