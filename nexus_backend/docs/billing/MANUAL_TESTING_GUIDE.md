# 🧪 Guide de Test Manuel - Fix Logo Invoice PDF

## Objectif
Vérifier visuellement que le logo s'affiche correctement sur les factures PDF générées.

---

## ✅ Pré-requis

### 1. Vérifier que le fichier logo existe
```bash
ls -lh static/images/logo/logo.png
```

**Résultat attendu :**
```
-rw-r--r-- 1 user user [TAILLE] [DATE] static/images/logo/logo.png
```

✅ **Confirmé** : Le fichier existe dans le projet

---

## 🧪 Procédure de Test Complète

### Étape 1 : Démarrer le serveur de développement

```bash
# Dans le répertoire du projet
cd /home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend

# Activer l'environnement virtuel si nécessaire
# source venv/bin/activate

# Lancer le serveur Django
python manage.py runserver
```

**Résultat attendu :**
```
System check identified no issues (0 silenced).
November 11, 2025 - XX:XX:XX
Django version X.X.X, using settings 'nexus_backend.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CONTROL-C.
```

---

### Étape 2 : Accéder à une facture PDF

#### Option A : Facture existante
Ouvrez votre navigateur et allez sur :
```
http://localhost:8000/en/billing/invoice/2025-IND-000001/pdf/
```

#### Option B : Lister les factures disponibles
Si la facture `2025-IND-000001` n'existe pas, trouvez-en une autre :

```bash
# Dans un autre terminal
python manage.py shell
```

```python
from main.models import Invoice

# Lister les factures existantes
invoices = Invoice.objects.filter(status='paid').order_by('-issued_at')[:5]
for inv in invoices:
    print(f"Number: {inv.number}, User: {inv.user.email}, Total: {inv.grand_total}")

# Sortir du shell
exit()
```

Utilisez ensuite un numéro de facture trouvé :
```
http://localhost:8000/en/billing/invoice/{NUMERO_FACTURE}/pdf/
```

---

### Étape 3 : Vérifications visuelles sur le PDF

Lorsque le PDF s'affiche dans votre navigateur, vérifiez les points suivants :

#### ✅ Checklist de validation

| # | Élément à vérifier | Statut | Notes |
|---|-------------------|--------|-------|
| 1 | **Logo visible** | ☐ | Logo apparaît en haut à gauche du PDF |
| 2 | **Position correcte** | ☐ | Logo dans la section header, colonne gauche |
| 3 | **Taille appropriée** | ☐ | Hauteur ~40px (ni trop grand, ni trop petit) |
| 4 | **Pas d'image cassée** | ☐ | Pas d'icône "broken image" ou carré vide |
| 5 | **Qualité d'image** | ☐ | Logo net et lisible |
| 6 | **Alt text correct** | ☐ | Si image ne charge pas, texte alternatif visible |

#### 📸 Aperçu de la structure attendue

```
┌─────────────────────────────────────────────────────┐
│  HEADER                                             │
│  ┌──────────────────┬──────────────────────────┐   │
│  │ [LOGO]           │  INVOICE · FACTURE       │   │
│  │ Company Name     │  Tax Invoice             │   │
│  │ Address          │  Currency: USD           │   │
│  │ Contact Info     │                          │   │
│  └──────────────────┴──────────────────────────┘   │
├─────────────────────────────────────────────────────┤
│  Bill To Information    │  Invoice Details         │
│  ...                    │  ...                     │
└─────────────────────────────────────────────────────┘
```

---

### Étape 4 : Test avec CompanySettings.logo vide

Pour vérifier que le **fallback fonctionne**, testez avec un logo d'entreprise vide :

```bash
python manage.py shell
```

```python
from main.models import CompanySettings

# Obtenir les paramètres de l'entreprise
cs = CompanySettings.get()

# Sauvegarder l'état actuel (au cas où)
current_logo = cs.logo

# Supprimer temporairement le logo uploadé
cs.logo = None
cs.save()

print("✓ Logo d'entreprise temporairement désactivé")
print("→ Rechargez maintenant la page PDF dans votre navigateur")
print("→ Vous devriez voir le logo statique de fallback")

# Pour restaurer après le test :
# cs.logo = current_logo
# cs.save()
```

**Retournez dans votre navigateur** et rafraîchissez la page PDF :
```
http://localhost:8000/en/billing/invoice/2025-IND-000001/pdf/
```

**Résultat attendu :**
- ✅ Le logo statique (`static/images/logo/logo.png`) s'affiche
- ✅ Pas d'espace vide ou d'image cassée
- ✅ Le PDF a toujours un aspect professionnel

#### Restaurer le logo d'origine (si nécessaire)
```python
# Dans le shell Django
cs = CompanySettings.get()
# Si vous aviez un logo avant :
# cs.logo = 'path/to/previous/logo.png'
# cs.save()
```

---

### Étape 5 : Tester une facture consolidée (optionnel)

Si vous avez des factures consolidées :
```
http://localhost:8000/en/billing/consolidated-invoice/{NUMERO}/pdf/
```

Vérifiez que le logo apparaît également sur ces factures.

---

## 🐛 Dépannage

### Problème 1 : "Invoice not found" (404)
**Cause :** La facture n'existe pas dans la base de données

**Solution :**
```bash
python manage.py shell
```
```python
from main.models import Invoice
# Lister toutes les factures
Invoice.objects.values_list('number', flat=True)[:10]
```

### Problème 2 : Logo ne s'affiche pas
**Vérifications :**

1. **Fichier existe ?**
   ```bash
   ls -lh static/images/logo/logo.png
   ```

2. **Collectstatic exécuté ?** (en production)
   ```bash
   python manage.py collectstatic --noinput
   ```

3. **Chemin correct dans le template ?**
   ```bash
   grep -n "static 'images/logo/logo.png'" billing_management/templates/invoices/inv_templates.html
   ```

### Problème 3 : Erreur 500 lors de la génération PDF
**Cause possible :** Problème avec WeasyPrint ou xhtml2pdf

**Vérifier les logs :**
```bash
# Dans le terminal où le serveur tourne
# Regarder les erreurs affichées
```

**Vérifier resolve_uri :**
```python
from billing_management.views import resolve_uri

# Tester la résolution
logo_url = "/static/images/logo/logo.png"
resolved = resolve_uri(logo_url)
print(f"URL: {logo_url}")
print(f"Resolved: {resolved}")
print(f"Exists: {os.path.exists(resolved)}")
```

---

## 📊 Résultats Attendus vs Obtenus

### Scénario 1 : CompanySettings.logo existe
| Élément | Attendu | Obtenu | ✓/✗ |
|---------|---------|--------|-----|
| Logo affiché | `company.logo.url` | _____ | ☐ |
| Position | Haut gauche | _____ | ☐ |
| Taille | 40px hauteur | _____ | ☐ |

### Scénario 2 : CompanySettings.logo est vide
| Élément | Attendu | Obtenu | ✓/✗ |
|---------|---------|--------|-----|
| Logo affiché | `static/images/logo/logo.png` | _____ | ☐ |
| Position | Haut gauche | _____ | ☐ |
| Taille | 40px hauteur | _____ | ☐ |
| Fallback actif | OUI | _____ | ☐ |

---

## ✅ Validation Finale

Une fois tous les tests réussis, cochez les éléments suivants :

- [ ] Logo visible sur facture normale avec `company.logo` présent
- [ ] Logo visible sur facture normale avec `company.logo` vide (fallback)
- [ ] Logo visible sur facture consolidée (si applicable)
- [ ] Aucune erreur dans les logs du serveur
- [ ] PDF téléchargeable sans erreur
- [ ] Qualité d'affichage professionnelle

---

## 📝 Rapport de Test

### Informations de test
- **Date :** ___________________
- **Testeur :** ___________________
- **Environnement :** ☐ Dev  ☐ Staging  ☐ Production
- **Navigateur :** ___________________

### Résultat global
- ☐ ✅ **SUCCÈS** - Tous les tests passent
- ☐ ⚠️  **PARTIEL** - Certains tests échouent (détailler ci-dessous)
- ☐ ❌ **ÉCHEC** - Le logo ne s'affiche pas

### Notes additionnelles
```
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________
```

---

## 🎯 Prochaines Étapes

Si tous les tests sont **VALIDÉS** :

1. ✅ Marquer l'issue/ticket comme résolu
2. ✅ Committer les changements :
   ```bash
   git add .
   git commit -m "fix: Add static logo fallback for invoice PDFs (TDD)"
   git push origin feat/add_sonarqube_and_testing_architecture
   ```
3. ✅ Créer une Pull Request avec référence à cette documentation

Si des tests **ÉCHOUENT** :
1. Noter les détails dans la section "Notes additionnelles"
2. Consulter la section Dépannage ci-dessus
3. Réviser le code dans `billing_management/templates/invoices/`

---

## 📚 Références

- **Documentation complète :** `docs/billing/INVOICE_LOGO_FIX_TDD.md`
- **Tests unitaires :** `billing_management/tests/test_invoice_logo_simple.py`
- **Templates modifiés :**
  - `billing_management/templates/invoices/inv_templates.html`
  - `billing_management/templates/invoices/consolidated_inv_templates.html`

---

**Bon test ! 🚀**
