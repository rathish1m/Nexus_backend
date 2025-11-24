# RBAC IMPLEMENTATION GUIDE
## Migration stratégique vers un contrôle d'accès robuste basé sur les rôles

**Date**: 2025-11-05
**Auteur**: Security Audit Team
**Criticité**: 🔴 **HAUTE** - Vulnérabilités de sécurité identifiées

---

## ⚠️ RÉSUMÉ EXÉCUTIF

### Problème Critique

Votre application présente des **failles de sécurité majeures** dans le contrôle d'accès :

1. **Aucune séparation stricte client/staff** : Un utilisateur staff peut accéder aux endpoints clients
2. **Protection insuffisante** : Utilisation de `@login_required` seul sans vérification de rôle
3. **Logique éparpillée** : 3 implémentations différentes de vérification de rôles dans le code
4. **Pas de granularité** : `is_staff` utilisé comme proxy, pas de différenciation admin/technicien/sales

### Impact

- ❌ Un administrateur peut voir les données privées des clients via leurs endpoints
- ❌ Un technicien peut accéder aux fonctions financières s'il connaît l'URL
- ❌ Violation potentielle du RGPD (accès non autorisé aux données personnelles)

---

## 🎯 SOLUTION IMPLÉMENTÉE

### Système centralisé dans `user/permissions.py`

✅ **Single Source of Truth** pour tous les checks de rôles
✅ **Decorators réutilisables** pour Function-Based Views
✅ **Permission classes DRF** pour les APIs REST
✅ **Séparation stricte** client vs staff
✅ **Logging d'audit** de tous les refus d'accès

---

## 📋 PLAN DE MIGRATION PROGRESSIVE

### Phase 1: client_app (PRIORITÉ MAXIMALE) ⚠️

**Objectif** : Empêcher tout utilisateur staff d'accéder aux vues clients

#### Avant (VULNÉRABLE)

```python
# client_app/views.py
@login_required
def dashboard(request):
    # ❌ N'importe quel utilisateur authentifié peut accéder
    # ❌ Un admin/technicien peut voir les données clients
    return render(request, "client_app/dashboard.html")
```

#### Après (SÉCURISÉ)

```python
# client_app/views.py
from django.contrib.auth.decorators import login_required
from user.permissions import require_customer_only

@login_required(login_url="login_page")
@require_customer_only()
def dashboard(request):
    # ✅ Seuls les clients (is_staff=False + role='customer') peuvent accéder
    # ✅ Les staff sont explicitement bloqués même avec role customer
    return render(request, "client_app/dashboard.html")
```

#### Vues à migrer IMMÉDIATEMENT

```python
# Liste exhaustive des vues client_app à sécuriser

from user.permissions import require_customer_only

# Dashboard et vues principales
@require_customer_only()
def dashboard(request): ...

@require_customer_only()
def landing_page(request): ...

@require_customer_only()
def billing_page(request): ...

@require_customer_only()
def support(request): ...

@require_customer_only()
def settings(request): ...

# KYC
@require_customer_only()
def submit_personal_kyc(request): ...

@require_customer_only()
def submit_business_kyc(request): ...

@require_customer_only()
def get_kyc_status(request): ...

# Orders
@require_customer_only()
def orders_page(request): ...

@require_customer_only()
def submit_order(request): ...

@require_customer_only()
def cancel_order(request, order_ref): ...

@require_customer_only()
def get_order_details_print(request, reference): ...

# Subscriptions
@require_customer_only()
def subscriptions(request): ...

@require_customer_only()
def subscription_details(request, id): ...

# Billing
@require_customer_only()
def billing_history(request): ...

@require_customer_only()
def get_billing_details(request, order_Id): ...
```

---

### Phase 2: backoffice (HAUTE PRIORITÉ)

**Objectif** : Remplacer `is_staff` par des checks de rôles granulaires

#### Avant (INSUFFISANT)

```python
# backoffice/views.py
@login_required(login_url="login_page")
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
def backoffice_main(request):
    # ❌ Tous les staff ont accès (technicien = admin = finance)
    return render(...)
```

#### Après (GRANULAIRE)

```python
# backoffice/views.py
from user.permissions import require_staff_role

@require_staff_role(['admin', 'manager'])
def backoffice_main(request):
    # ✅ Seuls admin et manager peuvent accéder
    # ✅ Techniciens/sales bloqués
    return render(...)

@require_staff_role(['finance', 'admin', 'manager'])
def revenue_summary(request):
    # ✅ Données financières protégées
    return render(...)

@require_staff_role(['dispatcher', 'admin'])
def dispatch_dashboard(request):
    # ✅ Seuls dispatcher et admin
    return render(...)
```

#### Mapping Rôles → Permissions

| Vue | Rôles autorisés | Justification |
|-----|----------------|---------------|
| `backoffice_main` | admin, manager | Vue d'ensemble générale |
| `dispatch_dashboard` | dispatcher, admin | Logistique spécifique |
| `revenue_summary` | finance, admin, manager | Données sensibles |
| `items_list` | dispatcher, admin, manager | Gestion stock |
| `completed_installations` | admin, manager, dispatcher | Suivi installations |

---

### Phase 3: APIs REST (CRITIQUE)

**Objectif** : Sécuriser tous les endpoints DRF

#### Avant (DRF Views)

```python
# api/views.py
from rest_framework.permissions import IsAuthenticated

class BillingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    # ❌ Tous les utilisateurs authentifiés peuvent lire/modifier
```

#### Après (SÉCURISÉ)

```python
# api/views.py
from rest_framework.permissions import IsAuthenticated
from user.permissions import IsStaffWithRole

class BillingViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsStaffWithRole]
    required_staff_roles = ['finance', 'admin', 'manager']

    # ✅ Seuls finance/admin/manager peuvent accéder
    # ✅ Clients et autres staff bloqués
```

#### Permission au niveau objet (si nécessaire)

```python
from user.permissions import IsCustomerOnly
from rest_framework.permissions import BasePermission

class IsOwnerOrStaff(BasePermission):
    """
    - Les clients peuvent voir uniquement LEURS données
    - Les staff peuvent voir toutes les données (avec role check)
    """
    def has_object_permission(self, request, view, obj):
        # Staff avec bon rôle
        if request.user.is_staff:
            from user.permissions import user_has_any_role
            return user_has_any_role(request.user, ['admin', 'support'])

        # Client propriétaire
        return obj.user == request.user


class OrderViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, IsOwnerOrStaff]

    def get_queryset(self):
        if self.request.user.is_staff:
            return Order.objects.all()
        return Order.objects.filter(user=self.request.user)
```

---

## 🔧 IMPLÉMENTATION PRATIQUE

### Étape 1: Import du module

```python
# En haut de chaque fichier views.py
from user.permissions import (
    require_customer_only,      # Pour client_app
    require_staff_role,          # Pour backoffice
    require_role,                # Pour rôle unique
    require_any_role,            # Pour plusieurs rôles acceptables
    IsCustomerOnly,              # DRF - clients seulement
    IsStaffWithRole,             # DRF - staff avec rôles
)
```

### Étape 2: Application systématique

**Rule of Thumb:**

1. **client_app/** → `@require_customer_only()`
2. **backoffice/** → `@require_staff_role([roles...])`
3. **Vues métier spécifiques** → `@require_any_role([roles...])`
4. **APIs DRF** → `permission_classes = [IsAuthenticated, IsStaffWithRole]`

### Étape 3: Validation

Après chaque modification, vérifiez :

```bash
# 1. Pas d'erreurs de syntaxe
python manage.py check

# 2. Testez manuellement
# - Connectez-vous comme client → accès client_app OK, backoffice BLOQUÉ
# - Connectez-vous comme staff → accès backoffice OK, client_app BLOQUÉ
# - Testez avec différents rôles (admin, technicien, etc.)

# 3. Logs d'audit
tail -f logs/security.log | grep "Access denied"
# Vous devez voir les tentatives d'accès non autorisées
```

---

## 📊 CHECKLIST DE MIGRATION

### client_app ☑️

- [ ] `dashboard` - @require_customer_only()
- [ ] `landing_page` - @require_customer_only()
- [ ] `billing_page` - @require_customer_only()
- [ ] `support` - @require_customer_only()
- [ ] `settings` - @require_customer_only()
- [ ] `submit_personal_kyc` - @require_customer_only()
- [ ] `submit_business_kyc` - @require_customer_only()
- [ ] `get_kyc_status` - @require_customer_only()
- [ ] `orders_page` - @require_customer_only()
- [ ] `submit_order` - @require_customer_only()
- [ ] `subscriptions` - @require_customer_only()
- [ ] `subscription_details` - @require_customer_only()
- [ ] `billing_history` - @require_customer_only()

### backoffice ☑️

- [ ] `backoffice_main` - @require_staff_role(['admin', 'manager'])
- [ ] `dispatch_dashboard` - @require_staff_role(['dispatcher', 'admin'])
- [ ] `revenue_summary` - @require_staff_role(['finance', 'admin', 'manager'])
- [ ] `items_list` - @require_staff_role(['dispatcher', 'admin'])
- [ ] `completed_installations` - @require_staff_role(['admin', 'manager', 'dispatcher'])

### APIs REST ☑️

- [ ] `BillingViewSet` - IsStaffWithRole + required_staff_roles
- [ ] `OrderViewSet` - IsOwnerOrStaff (custom)
- [ ] `SubscriptionViewSet` - IsOwnerOrStaff
- [ ] Feedbacks déjà OK (feedbacks/permissions.py existe)

---

## 🧪 TESTS DE SÉCURITÉ

### Test manuel rapide

```python
# 1. Créer un admin
python manage.py createsuperuser

# 2. Créer un client
# Via interface /register

# 3. Tests d'accès
# Connexion admin → essayer d'accéder /client/dashboard/
# ✅ Devrait être BLOQUÉ avec message "customer-only"

# Connexion client → essayer d'accéder /backoffice/
# ✅ Devrait être BLOQUÉ avec redirect vers login
```

### Tests automatisés

```python
# tests/test_rbac_security.py
import pytest
from django.test import Client
from django.urls import reverse

@pytest.mark.django_db
def test_staff_cannot_access_client_dashboard(admin_user):
    """Test critique : staff bloqué des endpoints clients"""
    client = Client()
    client.force_login(admin_user)

    response = client.get(reverse('dashboard'))

    # Devrait être redirigé ou 403
    assert response.status_code in [302, 403]

@pytest.mark.django_db
def test_customer_cannot_access_backoffice(customer_user):
    """Test critique : client bloqué du backoffice"""
    client = Client()
    client.force_login(customer_user)

    response = client.get(reverse('backoffice_main'))

    assert response.status_code in [302, 403]
```

---

## 🚨 POINTS D'ATTENTION

### 1. Migration user/auth.py

**IMPORTANT** : Vous avez déjà un fichier `user/auth.py` avec des fonctions de rôles.

```python
# user/auth.py (ANCIEN)
def has_role(user, role):
    # Logique existante
    ...
```

**Action** :
- ✅ `user/permissions.py` est la **nouvelle référence**
- ⚠️ Ne PAS supprimer `user/auth.py` immédiatement (risque de casser du code)
- 📝 Ajouter des deprecation warnings

```python
# user/auth.py
import warnings
from user.permissions import user_has_role as _new_has_role

def has_role(user, role):
    warnings.warn(
        "has_role from user.auth is deprecated. Use user.permissions.user_has_role",
        DeprecationWarning,
        stacklevel=2
    )
    return _new_has_role(user, role)
```

### 2. Compatibilité Template Tags

Si vous utilisez `{% load role_tags %}` dans les templates :

```python
# user/templatetags/role_tags.py
from django import template
from user.permissions import user_has_role  # Import from new location

register = template.Library()

@register.filter
def has_role(user, role):
    """Template filter utilisant la nouvelle implémentation"""
    return user_has_role(user, role)
```

### 3. Backward Compatibility

Dans `user/permissions.py`, on a déjà :

```python
# Alias pour compatibilité
has_role = user_has_role
```

---

## 📈 MÉTRIQUES DE SUCCÈS

Après implémentation complète, vous devez observer :

- ✅ **0 accès cross-boundary** (staff → client ou client → staff)
- ✅ **Logs d'audit** de toutes les tentatives refusées
- ✅ **Tous les tests passent** (pytest + tests manuels)
- ✅ **Aucune régression fonctionnelle** pour les utilisateurs légitimes

---

## 🔗 RÉFÉRENCES

### Documentation Django

- [User Authentication Permissions](https://docs.djangoproject.com/en/5.2/topics/auth/default/#permissions-and-authorization)
- [Custom Permissions](https://docs.djangoproject.com/en/5.2/topics/auth/customizing/#custom-permissions)

### Documentation DRF

- [Permissions](https://www.django-rest-framework.org/api-guide/permissions/)
- [Custom Permission Classes](https://www.django-rest-framework.org/api-guide/permissions/#custom-permissions)

### Standards de sécurité

- [OWASP Access Control](https://owasp.org/www-project-top-ten/2017/A5_2017-Broken_Access_Control)
- [RBAC Best Practices](https://csrc.nist.gov/projects/role-based-access-control)

---

## 📞 SUPPORT

Pour toute question sur cette migration :

1. Consulter `user/permissions.py` (documentation inline complète)
2. Voir les tests dans `user/tests/test_permissions.py`
3. Créer une issue GitHub avec tag `[security]`

---

**✅ STATUS**: Système de permissions créé et testé
**⏳ PROCHAINE ÉTAPE**: Migration des vues existantes (commencer par client_app)
**🎯 DEADLINE RECOMMANDÉE**: 7 jours max (criticité haute)
