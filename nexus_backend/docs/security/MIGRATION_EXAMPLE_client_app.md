# Exemple de Migration RBAC - client_app/views.py
## Before & After Comparison

### Fichier: client_app/views.py

---

## ❌ AVANT (Vulnérable/Incomplet)

```python
# client_app/views.py (ligne 1-50)
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from main.models import User

# Vue 1: Dashboard - Protection partielle
@require_full_login
@customer_nonstaff_required  # ✅ Bien mais deprecated
def dashboard(request):
    user = request.user
    # ... logique métier ...
    return render(request, "client_app/dashboard.html", context)


# Vue 2: KYC Submission - VULNÉRABLE !
@login_required  # ❌ PROBLÈME : N'importe quel utilisateur authentifié peut accéder
def submit_personal_kyc(request):
    # ❌ Un staff avec is_staff=True peut soumettre un KYC client
    # ❌ Pas de vérification de rôle
    user = request.user
    # ... traitement KYC ...
    return JsonResponse({"success": True})


# Vue 3: Orders - VULNÉRABLE !
@login_required
def submit_order(request):
    # ❌ Un admin peut passer une commande comme un client
    # ❌ Données métier exposées
    user = request.user
    # ... traitement commande ...
    return JsonResponse({"order_id": order.id})


# Vue 4: Billing History - VULNÉRABLE !
@login_required
def billing_history(request):
    # ❌ Un technicien peut voir l'historique de facturation client
    user = request.user
    bills = Billing.objects.filter(customer=user)  # Mais si staff ?
    return render(request, "client_app/billing.html", {"bills": bills})
```

### Problèmes identifiés

| Vue | Problème | Sévérité | Impact |
|-----|----------|----------|--------|
| `submit_personal_kyc` | Seulement `@login_required` | 🔴 CRITIQUE | Staff peut soumettre KYC client |
| `submit_order` | Pas de check rôle | 🔴 CRITIQUE | Staff peut passer commandes |
| `billing_history` | Pas de protection client-only | 🔴 HAUTE | Staff voit factures clients |

---

## ✅ APRÈS (Sécurisé)

```python
# client_app/views.py - Version sécurisée
import logging
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.core.exceptions import PermissionDenied

# ✅ NOUVEAU : Import du système centralisé
from user.permissions import require_customer_only

from main.models import User


# Vue 1: Dashboard - Sécurisé avec nouveau decorator
@login_required(login_url="login_page")  # Layer 1: Authentication
@require_customer_only()                  # Layer 2: Role check + Staff block
def dashboard(request):
    """
    Dashboard client - Accessible UNIQUEMENT aux clients non-staff.

    Permissions:
        - is_authenticated: True
        - is_staff: False (explicitement bloqué)
        - role: 'customer'

    Security:
        - Staff users are explicitly denied even if they have 'customer' role
        - All access denials are logged for audit
    """
    user = request.user

    # ✅ À ce stade, on est SÛR que c'est un client légitime
    # ✅ user.is_staff == False est garanti

    # ... logique métier ...

    return render(request, "client_app/dashboard.html", context)


# Vue 2: KYC Submission - SÉCURISÉ
@login_required(login_url="login_page")
@require_customer_only()
def submit_personal_kyc(request):
    """
    Soumission KYC personnel - Réservé aux clients uniquement.

    Permissions:
        - Clients seulement (is_staff=False + role='customer')

    Security:
        - Staff cannot submit KYC on behalf of customers
        - All submissions are linked to authenticated customer
    """
    user = request.user

    # ✅ user.is_staff est TOUJOURS False ici
    # ✅ user.roles contient 'customer'

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # ... traitement KYC ...

    return JsonResponse({"success": True, "message": "KYC submitted successfully"})


# Vue 3: Orders - SÉCURISÉ
@login_required(login_url="login_page")
@require_customer_only()
def submit_order(request):
    """
    Passage de commande - Clients uniquement.

    Permissions:
        - Client role required
        - Staff explicitly blocked

    Security:
        - Order ownership automatically assigned to request.user
        - No staff can create orders through client interface
    """
    user = request.user

    # ✅ Protection : seuls les vrais clients peuvent commander

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    # ... traitement commande ...
    order.user = user  # ✅ Toujours un client légitime
    order.save()

    return JsonResponse({
        "success": True,
        "order_id": order.id,
        "message": "Order placed successfully"
    })


# Vue 4: Billing History - SÉCURISÉ
@login_required(login_url="login_page")
@require_customer_only()
def billing_history(request):
    """
    Historique de facturation - Vue client personnelle.

    Permissions:
        - Customer role only
        - Own data only (automatic filtering)

    Security:
        - Staff cannot view customer billing through this endpoint
        - Each customer sees only their own bills
    """
    user = request.user

    # ✅ Filtrage automatique sur le client authentifié
    bills = Billing.objects.filter(customer=user)

    # ✅ Impossible qu'un staff voie ces données via cette vue

    context = {
        "bills": bills,
        "total_amount": sum(b.amount for b in bills),
    }

    return render(request, "client_app/billing.html", context)


# Vue 5: Support Tickets - SÉCURISÉ avec feedback
@login_required(login_url="login_page")
@require_customer_only()
def create_support_ticket(request):
    """
    Création de ticket support - Client seulement.

    Permissions:
        - Customer role required

    Security:
        - Ticket ownership verified
        - Staff use different support interface (backoffice)
    """
    user = request.user

    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    subject = request.POST.get("subject")
    message = request.POST.get("message")

    # Validation
    if not subject or not message:
        return JsonResponse({
            "success": False,
            "error": "Subject and message are required"
        }, status=400)

    # Création du ticket
    from main.models import Ticket
    ticket = Ticket.objects.create(
        user=user,  # ✅ Toujours un client
        subject=subject,
        message=message,
        status="open"
    )

    return JsonResponse({
        "success": True,
        "ticket_id": ticket.id,
        "message": "Support ticket created successfully"
    })
```

---

## 📊 Comparaison des Protections

| Aspect | AVANT | APRÈS | Amélioration |
|--------|-------|-------|--------------|
| **Authentification** | ✅ `@login_required` | ✅ `@login_required` | Maintenu |
| **Vérification rôle** | ⚠️ Partiel (`customer_nonstaff_required` sur certaines vues) | ✅ Systématique (`@require_customer_only` sur TOUTES) | +100% |
| **Blocage staff** | ⚠️ `is_staff` check parfois absent | ✅ Toujours bloqué explicitement | +100% |
| **Logging audit** | ❌ Aucun | ✅ Automatique sur chaque refus | Nouveau |
| **Documentation** | ❌ Aucune | ✅ Docstrings complètes | Nouveau |
| **Maintenabilité** | ⚠️ Logique éparpillée | ✅ Centralisée dans `user.permissions` | +80% |

---

## 🔄 Migration Étape par Étape

### Étape 1: Importer le nouveau module

```python
# En haut du fichier client_app/views.py
from user.permissions import require_customer_only
```

### Étape 2: Remplacer les decorators

#### Pattern 1: Vue avec seulement `@login_required`

```python
# AVANT
@login_required
def ma_vue(request):
    ...

# APRÈS
@login_required(login_url="login_page")
@require_customer_only()
def ma_vue(request):
    ...
```

#### Pattern 2: Vue avec `@customer_nonstaff_required`

```python
# AVANT
@require_full_login
@customer_nonstaff_required
def ma_vue(request):
    ...

# APRÈS (simplification recommandée)
@login_required(login_url="login_page")
@require_customer_only()
def ma_vue(request):
    ...
```

### Étape 3: Ajouter la documentation

```python
@login_required(login_url="login_page")
@require_customer_only()
def ma_vue(request):
    """
    [Description de la vue]

    Permissions:
        - Customer role required
        - Staff explicitly blocked

    Security:
        - [Points de sécurité spécifiques]
    """
    ...
```

### Étape 4: Tester

```bash
# 1. Test unitaire
python -m pytest tests/test_client_app_permissions.py -v

# 2. Test manuel
# - Connexion en tant que client → Toutes les vues accessibles ✅
# - Connexion en tant que admin → Toutes les vues BLOQUÉES ✅
# - Vérifier les logs → Tentatives staff loggées ✅
```

---

## 🧪 Tests Automatisés Recommandés

```python
# tests/test_client_app_permissions.py
import pytest
from django.test import Client
from django.urls import reverse
from main.factories import UserFactory, StaffUserFactory


@pytest.mark.django_db
class TestClientAppPermissions:
    """Tests de sécurité pour client_app"""

    def test_customer_can_access_dashboard(self):
        """Clients peuvent accéder au dashboard"""
        customer = UserFactory(roles=['customer'])
        client = Client()
        client.force_login(customer)

        response = client.get(reverse('dashboard'))

        assert response.status_code == 200

    def test_staff_blocked_from_dashboard(self):
        """Staff BLOQUÉS du dashboard client"""
        admin = StaffUserFactory(roles=['admin'])
        client = Client()
        client.force_login(admin)

        response = client.get(reverse('dashboard'))

        # Doit être redirigé ou 403
        assert response.status_code in [302, 403]

    def test_staff_blocked_from_kyc_submission(self):
        """Staff ne peuvent pas soumettre KYC via interface client"""
        admin = StaffUserFactory(roles=['admin'])
        client = Client()
        client.force_login(admin)

        response = client.post(
            reverse('submit_personal_kyc'),
            {"full_name": "Test", "document_number": "123"}
        )

        assert response.status_code in [302, 403]

    def test_customer_can_see_own_billing_only(self):
        """Clients voient uniquement leurs factures"""
        customer1 = UserFactory(roles=['customer'])
        customer2 = UserFactory(roles=['customer'])

        # Créer factures pour chaque client
        from main.models import Billing
        bill1 = Billing.objects.create(customer=customer1, amount=100)
        bill2 = Billing.objects.create(customer=customer2, amount=200)

        # customer1 se connecte
        client = Client()
        client.force_login(customer1)

        response = client.get(reverse('billing_history'))

        # Doit voir uniquement sa facture
        assert response.status_code == 200
        bills_in_context = response.context['bills']
        assert len(bills_in_context) == 1
        assert bills_in_context[0].id == bill1.id
```

---

## 📈 Métriques de Succès

Après migration complète de `client_app/views.py` :

- ✅ **100%** des vues protégées avec `@require_customer_only()`
- ✅ **0** tentative staff réussie sur endpoints clients
- ✅ **Tous les tests** passent (unitaires + manuels)
- ✅ **Logs d'audit** actifs et centralisés
- ✅ **Documentation** complète avec docstrings

---

## 🚀 Prochaines Étapes

1. **Appliquer ce pattern** à toutes les autres vues de `client_app/`
2. **Répéter** pour `backoffice/` avec `@require_staff_role()`
3. **Sécuriser** les APIs REST avec `IsCustomerOnly` et `IsStaffWithRole`
4. **Monitorer** les logs pour détecter tentatives d'accès non autorisées

---

## 💡 Astuces de Migration

### Recherche Rapide des Vues à Migrer

```bash
# Trouver toutes les vues avec seulement @login_required
grep -n "@login_required" client_app/views.py | \
    grep -v "@require_customer_only" | \
    grep -v "customer_nonstaff_required"

# Résultat: Lignes où @login_required est seul → PRIORITÉ CRITIQUE
```

### Pre-commit Hook (optionnel)

```python
# .git/hooks/pre-commit
#!/usr/bin/env python3
import re
import sys

# Vérifier que toutes les vues client_app ont @require_customer_only
with open('client_app/views.py', 'r') as f:
    content = f.read()

    # Trouver toutes les vues
    view_pattern = r'def (\w+)\(request'
    views = re.findall(view_pattern, content)

    # Vérifier protection
    for view in views:
        if view.startswith('_'):  # Helper privé, skip
            continue

        # Chercher decorator avant la définition
        view_def_pattern = rf'@require_customer_only\(\)\s+def {view}\('
        if not re.search(view_def_pattern, content):
            print(f"⚠️  WARNING: {view} n'a pas @require_customer_only")
            sys.exit(1)

print("✅ Toutes les vues client_app sont protégées")
```

---

**Fichier généré le**: 2025-11-05
**Auteur**: Security Audit Team
**Référence**: RBAC_IMPLEMENTATION_GUIDE.md
