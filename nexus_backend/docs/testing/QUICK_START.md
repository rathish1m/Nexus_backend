# Guide de Démarrage Rapide - Infrastructure de Tests

## 🎯 Vous êtes ici

Vous venez de créer une infrastructure de tests complète avec:
- ✅ Configuration pytest optimisée
- ✅ Mocks pour services externes (FlexPay, Twilio, AWS)
- ✅ GitHub Actions CI/CD
- ✅ Pre-commit hooks
- ✅ Documentation complète
- ✅ Exemples de tests

## 🚀 Prochaines Étapes (30 minutes)

### Étape 1: Valider la Configuration (5 min)

```bash
cd /home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend

# Vérifier pytest est installé et configuré
pytest --version

# Lister les tests découverts
pytest --collect-only -q | head -20

# Voir les markers disponibles
pytest --markers
```

### Étape 2: Tester les Exemples (10 min)

```bash
# Test unitaire simple
pytest main/tests/examples/test_order_example.py -v

# Test avec coverage
pytest main/tests/examples/test_order_example.py --cov=main --cov-report=term-missing

# Tous les exemples
pytest main/tests/examples/ tests/integration/ -v
```

**Résultat attendu:** Tous les tests passent (certains peuvent échouer si les models n'ont pas les méthodes exactes, c'est normal - ce sont des exemples).

### Étape 3: Merger conftest.py (5 min)

```bash
# Sauvegarder l'ancien
cp conftest.py conftest_old.py

# Copier le nouveau
cp conftest_new.py conftest.py

# Vérifier
pytest --collect-only -q | head -10
```

### Étape 4: Installer Pre-commit (5 min)

```bash
# Installer pre-commit
pip install pre-commit

# Installer les hooks
pre-commit install

# Tester (ceci va prendre quelques minutes la première fois)
pre-commit run --all-files
```

**Note:** La première exécution peut échouer sur certains checks (normal, code existant). Les prochains commits seront protégés.

### Étape 5: Mesurer Coverage Actuel (5 min)

```bash
# Exécuter tous les tests avec coverage
pytest --cov=. --cov-report=html --cov-report=term-missing -q

# Ouvrir le rapport HTML
# Le rapport est dans: htmlcov/index.html

# Voir résumé dans terminal
coverage report --sort=cover
```

**Résultat attendu:** ~10% coverage actuel (baseline confirmé)

## 📊 Prochaine Session: Créer les Tests

### Option A: Approche Incrémentale (Recommandé)

**Semaine 1-2: Module `main` (Priority 1)**

Créer fichiers:
```
main/tests/
├── test_models.py          # Tests Order, User, Subscription
├── test_managers.py        # Tests custom managers
├── test_signals.py         # Tests post_save signals
└── test_utils.py           # Tests utility functions
```

Commencer par:
```python
# main/tests/test_models.py
import pytest
from main.models import Order
from main.factories import UserFactory

@pytest.mark.unit
def test_order_creation():
    user = UserFactory()
    order = Order.objects.create(
        user=user,
        subscription_plan_id=1,
        kit_id=1
    )
    assert order.status == 'pending'
```

**Target:** 68% → 85% coverage en 2 semaines

### Option B: Approche TDD pour Nouvelle Feature

Si vous avez une nouvelle feature à développer:

1. **Écrire le test AVANT le code (RED)**
```python
def test_new_feature():
    # Ce test va échouer car la feature n'existe pas
    result = my_new_feature()
    assert result == expected_value
```

2. **Écrire le code minimal (GREEN)**
```python
def my_new_feature():
    return expected_value
```

3. **Refactorer (REFACTOR)**
```python
def my_new_feature():
    # Améliorer qualité, ajouter validation, etc.
    # Les tests garantissent que ça marche toujours
    return improved_implementation()
```

## 📚 Documentation Disponible

1. **[TESTING_INFRASTRUCTURE_SUMMARY.md](./TESTING_INFRASTRUCTURE_SUMMARY.md)**
   - Vue d'ensemble complète de tous les fichiers créés
   - Fonctionnalités des mocks
   - Checklist de validation

2. **[tests/README.md](../../tests/README.md)**
   - Guide complet d'utilisation
   - Commandes pytest
   - Exemples pratiques
   - Troubleshooting

3. **[TDD_WORKFLOW.md](./TDD_WORKFLOW.md)**
   - Guide TDD complet
   - Cycle RED-GREEN-REFACTOR
   - Exemples concrets
   - Best practices

4. **[TESTING_ANALYSIS.md](./TESTING_ANALYSIS.md)**
   - Analyse détaillée du projet
   - Roadmap 3-6 mois
   - Architecture recommandée

## 🎓 Formation Équipe

### Workshop Suggéré (2h)

**Session 1: Introduction (30 min)**
- Présentation infrastructure
- Démonstration pytest
- Exemples simples

**Session 2: Mocks et Fixtures (30 min)**
- FlexPay mock hands-on
- Twilio mock hands-on
- AWS mock hands-on
- Fixtures réutilisables

**Session 3: TDD Pratique (45 min)**
- Live coding TDD
- RED-GREEN-REFACTOR
- Créer un test ensemble

**Session 4: CI/CD et Best Practices (15 min)**
- GitHub Actions
- Pre-commit hooks
- Code review avec coverage

## ✅ Checklist Validation

Avant de commencer à écrire des tests:

- [ ] pytest fonctionne (`pytest --version`)
- [ ] Tests exemples passent
- [ ] Coverage report fonctionne
- [ ] conftest.py mergé
- [ ] Pre-commit installé
- [ ] Documentation lue
- [ ] Équipe informée

## 🆘 Besoin d'Aide?

### Problème: pytest not found
```bash
pip install -r requirements-dev.txt
```

### Problème: Tests ne sont pas découverts
```bash
# Vérifier pytest.ini
cat pytest.ini

# Forcer découverte
pytest --collect-only -v
```

### Problème: Coverage ne fonctionne pas
```bash
# Vérifier .coveragerc
cat .coveragerc

# Réinitialiser coverage
coverage erase
pytest --cov=. --cov-report=html
```

### Problème: Imports ne fonctionnent pas dans tests
```bash
# Vérifier PYTHONPATH
echo $PYTHONPATH

# Ou utiliser
python -m pytest
```

## 🎯 Objectif Final

**3-6 mois:**
- ✅ 80%+ code coverage
- ✅ TDD pour toutes nouvelles features
- ✅ CI/CD automatisé
- ✅ Pre-commit hooks enforcing quality
- ✅ Équipe formée au TDD

**Première milestone (4 semaines):**
- 60% coverage sur modules critiques (main, client_app, billing_management, orders)
- 10-15 tests par module
- GitHub Actions fonctionnel

---

**🚀 Prêt à commencer? Lancez les commandes de l'Étape 1!**
