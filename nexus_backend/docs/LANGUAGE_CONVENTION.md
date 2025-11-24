# Language Convention - NEXUS Telecoms Backend

## 🌍 English as Single Source of Truth

**All technical content MUST be written in English.**

This document establishes the language convention for the NEXUS Telecoms backend codebase.

---

## 📜 Policy

### English is MANDATORY for:

1. **Code**
   - Variable names
   - Function names
   - Class names
   - Method names
   - Constants
   - Module names

2. **Documentation**
   - Code comments
   - Docstrings
   - README files
   - Technical guides
   - API documentation
   - Architecture docs
   - Test documentation

3. **Development Artifacts**
   - Commit messages
   - Pull request descriptions
   - Issue descriptions
   - Code review comments
   - Test case descriptions
   - Error messages (for developers)

4. **Configuration**
   - Configuration file comments
   - Environment variable names
   - Settings descriptions

---

## 🔄 Translation System

### User-Facing Content

User-facing content is **translated** from English to other languages:

```
English (Source) → French → Other Languages
locale/en.json   → locale/fr.json → locale/xx.json
```

**Translation workflow:**
1. Write English text in `locale/en.json`
2. Translate to French in `locale/fr.json`
3. Add other languages as needed
4. Use Django's i18n system for rendering

**Example:**
```json
// locale/en.json (SOURCE OF TRUTH)
{
  "order.status.pending": "Pending",
  "order.status.completed": "Completed"
}

// locale/fr.json (TRANSLATION)
{
  "order.status.pending": "En attente",
  "order.status.completed": "Terminé"
}
```

---

## ✅ Good Examples

### Code - Variable Names
```python
# ✅ GOOD
def create_order(user, subscription_plan, starlink_kit):
    """Create a new order with the specified parameters"""
    order = Order.objects.create(
        user=user,
        plan=subscription_plan,
        kit=starlink_kit,
        status='pending'
    )
    return order

# ❌ BAD
def creer_commande(utilisateur, plan_abonnement, kit_starlink):
    """Créer une nouvelle commande avec les paramètres spécifiés"""
    commande = Order.objects.create(
        user=utilisateur,
        plan=plan_abonnement,
        kit=kit_starlink,
        status='en_attente'
    )
    return commande
```

### Tests
```python
# ✅ GOOD
@pytest.mark.unit
def test_order_creation_with_valid_data(user):
    """Test that an order is created successfully with valid data"""
    order = Order.objects.create(
        user=user,
        subscription_plan_id=1,
        kit_id=1
    )
    assert order.status == 'pending'
    assert order.user == user

# ❌ BAD
@pytest.mark.unit
def test_creation_commande_donnees_valides(utilisateur):
    """Tester qu'une commande est créée avec succès"""
    commande = Order.objects.create(
        user=utilisateur,
        subscription_plan_id=1,
        kit_id=1
    )
    assert commande.status == 'en_attente'
```

### Commit Messages
```bash
# ✅ GOOD
git commit -m "feat: Add payment retry logic with exponential backoff"
git commit -m "fix: Resolve FlexPay webhook authentication issue"
git commit -m "test: Add unit tests for order cancellation workflow"

# ❌ BAD
git commit -m "feat: Ajouter logique de retry pour paiements"
git commit -m "fix: Résoudre problème authentification webhook"
```

### Documentation
```python
# ✅ GOOD
class PaymentService:
    """
    Service for handling payment operations.

    This service provides methods for:
    - Initiating payments via FlexPay
    - Retrying failed payments
    - Processing refunds
    - Checking payment status
    """

    @staticmethod
    def retry_payment(payment_id: int) -> Dict[str, Any]:
        """
        Retry a failed payment.

        Args:
            payment_id: ID of the payment to retry

        Returns:
            Dict containing success status and payment details

        Raises:
            ValueError: If maximum retry attempts exceeded
        """
        pass

# ❌ BAD
class ServicePaiement:
    """
    Service pour gérer les opérations de paiement.

    Ce service fournit des méthodes pour:
    - Initier des paiements via FlexPay
    - Réessayer les paiements échoués
    """
    pass
```

---

## 🚫 Common Mistakes to Avoid

### Mixing Languages
```python
# ❌ BAD - Mixed English/French
def create_commande(user, plan_id):
    """Create a new commande for the utilisateur"""
    nouvelle_order = Order.objects.create(
        user=user,
        subscription_plan_id=plan_id,
        status='pending'  # en_attente in French
    )
    return nouvelle_order

# ✅ GOOD - Pure English
def create_order(user, plan_id):
    """Create a new order for the user"""
    new_order = Order.objects.create(
        user=user,
        subscription_plan_id=plan_id,
        status='pending'
    )
    return new_order
```

### French Database Field Names
```python
# ❌ BAD
class Commande(models.Model):
    utilisateur = models.ForeignKey(User)
    montant_total = models.DecimalField()
    statut = models.CharField()

# ✅ GOOD
class Order(models.Model):
    user = models.ForeignKey(User)
    total_amount = models.DecimalField()
    status = models.CharField()
```

---

## 📝 Exception: User-Facing Content

**Only user-facing content should be translated:**

```python
# ✅ GOOD - Using translation system
from django.utils.translation import gettext as _

def get_order_status_display(order):
    """Get localized order status for display"""
    status_translations = {
        'pending': _('order.status.pending'),
        'completed': _('order.status.completed'),
        'cancelled': _('order.status.cancelled'),
    }
    return status_translations.get(order.status)

# User sees "En attente" if locale is French
# User sees "Pending" if locale is English
```

---

## 🎯 Rationale

### Why English?

1. **Industry Standard**: Python, Django, and the entire software ecosystem use English
2. **Collaboration**: Enables international team collaboration
3. **Tools**: Better support from IDEs, linters, AI assistants
4. **Documentation**: Access to global resources, Stack Overflow, etc.
5. **Maintenance**: Easier onboarding for new developers
6. **Consistency**: One language for technical content

### Why Separate Translation for Users?

1. **User Experience**: Users should see content in their language
2. **Internationalization**: Support for multiple markets (DRC, other African countries)
3. **Accessibility**: Better UX for non-English speakers
4. **Business**: Market expansion without code changes

---

## ✅ Checklist

Before committing code, verify:

- [ ] All variable names are in English
- [ ] All function/class names are in English
- [ ] All comments are in English
- [ ] All docstrings are in English
- [ ] Commit message is in English
- [ ] User-facing text uses i18n translation system
- [ ] No mixed language code

---

## 📚 Resources

- [PEP 8 - Style Guide for Python](https://www.python.org/dev/peps/pep-0008/)
- [Django i18n documentation](https://docs.djangoproject.com/en/stable/topics/i18n/)
- [Conventional Commits](https://www.conventionalcommits.org/)

---

## 🔄 Enforcement

This convention is enforced by:

1. **Code Review**: All PRs reviewed for language compliance
2. **Pre-commit Hooks**: Automated checks (where possible)
3. **Team Guidelines**: Regular reminders and training
4. **Documentation**: This document as reference

---

**Remember: English is the single source of truth for all technical content.**

**Questions?** Ask in team chat or create an issue.
