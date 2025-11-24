# 🛠️ Utility Scripts

This directory contains organized utility scripts for the Nexus Telecom project, categorized by purpose following Django best practices.

## 📂 Directory Structure

```
scripts/
├── docs/              # Documentation validation scripts
├── dev/               # Development and debugging scripts
├── data/              # Data management scripts
├── fixes/             # Migration and fix scripts
├── i18n-audit.sh      # Translation coverage audit
├── i18n-onboarding.sh # i18n onboarding guide
└── README.md          # This file
```

---

## 📚 Documentation Scripts (`docs/`)

Scripts for validating documentation structure and i18n compliance.

### Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `check_docs_structure.py` | Validates documentation organization | `python scripts/docs/check_docs_structure.py` |
| `check_filename_i18n.py` | Checks i18n compliance of filenames | `python scripts/docs/check_filename_i18n.py` |
| `check_i18n_compliance.py` | Validates complete i18n compliance | `python scripts/docs/check_i18n_compliance.py` |
| `browse_docs.sh` | Interactive documentation browser | `bash scripts/docs/browse_docs.sh` |

### Makefile Commands
```bash
make check-docs    # Run all documentation validation scripts
make browse-docs   # Open documentation browser
```

---

## 🔧 Development Scripts (`dev/`)

Scripts for development, debugging, and analysis.

### Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `analyze_rejection_workflow.py` | Analyze site survey rejection workflow | `python scripts/dev/analyze_rejection_workflow.py` |
| `demo_new_installation_logic.py` | Demo new installation workflow | `python scripts/dev/demo_new_installation_logic.py` |
| `verify_photo_upload.py` | Verify photo upload functionality | `python scripts/dev/verify_photo_upload.py` |

### Makefile Commands
```bash
make demo-installation   # Run installation demo
make verify-photos       # Verify photo uploads
make analyze-workflow    # Analyze rejection workflow
```

---

## 📦 Data Management Scripts (`data/`)

Scripts for managing data, inventory, and test data creation.

### Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `check_inventory.py` | Check Starlink kit inventory | `python scripts/data/check_inventory.py` |
| `check_signal_duplicates.py` | Detect duplicate signals | `python scripts/data/check_signal_duplicates.py` |
| `clean_duplicates.py` | Clean duplicate records | `python scripts/data/clean_duplicates.py` |
| `create_extra_charge_test_data.py` | Create extra charge test data | `python scripts/data/create_extra_charge_test_data.py` |
| `create_test_installation.py` | Create test installation data | `python scripts/data/create_test_installation.py` |

### Makefile Commands
```bash
make check-inventory     # Check inventory status
make check-duplicates    # Check for duplicates
make clean-duplicates    # Clean duplicates
make create-test-data    # Create test data
```

---

## 🔧 Fix & Migration Scripts (`fixes/`)

Scripts for fixing data issues and performing migrations.

### Available Scripts

| Script | Purpose | Usage |
|--------|---------|-------|
| `fix_billing_customers.py` | Fix billing customer data | `python scripts/fixes/fix_billing_customers.py` |
| `verify_billing_creation.py` | Verify billing record creation | `python scripts/fixes/verify_billing_creation.py` |

### Makefile Commands
```bash
make fix-billing       # Fix billing customers
make verify-billing    # Verify billing creation
```

---

## 🌍 Internationalization (i18n) Tools

### 1. Translation Coverage Audit (`i18n-audit.sh`)

Script sophistiqué d'analyse de la couverture des traductions avec sortie triée par langue.

#### Caractéristiques :
- ✅ Analyse automatique de tous les fichiers `.po`
- ✅ Calcul de la couverture de traduction par langue
- ✅ Sortie bilingue (FR/EN) avec détection automatique
- ✅ Format JSON pour l'automatisation CI/CD
- ✅ Codes de sortie pour l'intégration dans les pipelines
- ✅ Seuils de couverture configurables
- ✅ Sortie colorée et formatée

#### Usage :
```bash
# Audit basique avec auto-détection de langue
./scripts/i18n-audit.sh

# Sortie JSON pour CI/CD
./scripts/i18n-audit.sh --json

# Audit silencieux avec seuil personnalisé
./scripts/i18n-audit.sh --quiet --min-coverage 90

# Forcer la langue française
./scripts/i18n-audit.sh --french

# Aide complète
./scripts/i18n-audit.sh --help
```

#### Codes de sortie :
- `0` : Toutes les traductions respectent le seuil
- `1` : Certaines traductions sous le seuil
- `2` : Aucun fichier de traduction trouvé
- `3` : Arguments invalides

### 2. Script d'onboarding (`i18n-onboarding.sh`)

Guide interactif pour les nouveaux développeurs sur le workflow i18n.

#### Usage :
```bash
./scripts/i18n-onboarding.sh
```

Le script propose un menu interactif pour :
- Visualiser le statut actuel des traductions
- Extraire de nouvelles chaînes traduisibles
- Compiler les fichiers de traduction
- Ouvrir les fichiers de traduction pour édition
- Lancer des vérifications qualité

## 🎯 Intégration Makefile

Les outils sont intégrés dans le Makefile principal pour une utilisation simplifiée :

```bash
# Audit des traductions
make i18n-audit

# Audit avec sortie JSON
make i18n-audit-json

# Extraction des chaînes traduisibles
make i18n-extract

# Compilation des traductions
make i18n-compile

# Mise à jour complète (extract + compile)
make i18n-update

# Vérification pour CI (silencieux)
make i18n-check
```

## 📊 Exemple de sortie

### Format tableau (défaut) :
```
🌍 Audit des Traductions Multilingues
Analyse du répertoire: /path/to/locale
2 fichiers .po trouvés

Langue        Lignes totales Entrées msgid    Traduites     Couverture
──────────────────────────────────────────────────────────────────────
en                       591          184          183         99%
fr                       857          269          268         99%

📊 Résumé
──────────────────────────────
Langues totales: 2
Couverture moyenne: 99%
Couverture minimale: 99%
Couverture maximale: 99%
Seuil de couverture: 80%

✅ Toutes les traductions respectent le seuil (80%)
```

### Format JSON :
```json
{
  "audit_timestamp": "2025-10-10T09:05:38+02:00",
  "project_root": "/path/to/nexus_backend",
  "coverage_threshold": 80,
  "summary": {
    "total_languages": 2,
    "average_coverage": 99,
    "minimum_coverage": 99,
    "maximum_coverage": 99,
    "languages_below_threshold": 0
  },
  "languages": [
    {
      "code": "fr",
      "total_lines": 857,
      "msgid_entries": 269,
      "translated_entries": 268,
      "coverage_percentage": 99,
      "meets_threshold": true
    }
  ]
}
```

## 🔄 Workflow de développement

### 1. Phase de développement
```bash
# Ajouter des balises de traduction dans les templates
{% trans "Your text" %}

# Utiliser gettext dans Python
from django.utils.translation import gettext as _
message = _("Your translatable text")

# Extraire les nouvelles chaînes
make i18n-extract
```

### 2. Phase de traduction
```bash
# Éditer les fichiers .po dans locale/*/LC_MESSAGES/
# Ajouter les traductions françaises pour les nouvelles entrées msgid

# Compiler les traductions
make i18n-compile
```

### 3. Assurance qualité
```bash
# Vérifier la couverture
make i18n-audit

# S'assurer que la couverture respecte les exigences (≥80%)
# Tester dans les deux langues
```

## 🚀 Intégration CI/CD

### GitHub Actions exemple :
```yaml
- name: Check translation coverage
  run: |
    chmod +x scripts/i18n-audit.sh
    make i18n-check

- name: Generate translation report
  run: |
    make i18n-audit-json > translation-report.json

- name: Upload translation artifacts
  uses: actions/upload-artifact@v3
  with:
    name: translation-report
    path: translation-report.json
```

### GitLab CI exemple :
```yaml
i18n_audit:
  stage: quality
  script:
    - chmod +x scripts/i18n-audit.sh
    - make i18n-check
  artifacts:
    when: always
    reports:
      junit: translation-report.json
```

## 📁 Structure des fichiers

```
nexus_backend/
├── locale/
│   ├── en/LC_MESSAGES/
│   │   ├── django.po     # Traductions anglaises
│   │   └── django.mo     # Traductions compilées
│   └── fr/LC_MESSAGES/
│       ├── django.po     # Traductions françaises
│       └── django.mo     # Traductions compilées
├── scripts/
│   ├── i18n-audit.sh     # Outil d'audit principal
│   ├── i18n-onboarding.sh # Guide d'onboarding
│   └── README.md         # Cette documentation
└── Makefile              # Cibles i18n-*
```

## 🔧 Configuration

### Variables d'environnement supportées :
- `LANG` : Détection automatique de la langue (fr_* pour français)
- `NO_COLOR` : Désactiver la sortie colorée

### Seuils configurables :
- Seuil de couverture par défaut : 80%
- Modifiable via `--min-coverage N`

## 🎨 Personnalisation

Les scripts sont conçus pour être facilement personnalisables :

1. **Messages multilingues** : Tableaux associatifs `MESSAGES_FR` et `MESSAGES_EN`
2. **Seuils** : Variable `DEFAULT_COVERAGE_THRESHOLD`
3. **Chemins** : Variables `LOCALE_DIR` et `PROJECT_ROOT`
4. **Couleurs** : Variables de couleur ANSI configurables

## 🐛 Dépannage

### Problèmes courants :

1. **"No translation files found"**
   - Vérifier que le dossier `locale/` existe
   - S'assurer que les fichiers `.po` sont présents

2. **Permissions d'exécution**
   ```bash
   chmod +x scripts/i18n-*.sh
   ```

3. **Erreurs de compilation**
   ```bash
   # Vérifier la syntaxe des fichiers .po
   msgfmt --check locale/fr/LC_MESSAGES/django.po
   ```

## 📚 Ressources

- [Documentation Django i18n](https://docs.djangoproject.com/en/stable/topics/i18n/)
- [GNU gettext Documentation](https://www.gnu.org/software/gettext/manual/)
- [Makefile du projet](../Makefile)

---

**Auteur :** Équipe de développement Nexus Telecom
**Version :** 1.0.0
**Licence :** MIT
