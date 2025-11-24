# Invoice Order Grouping Feature

## Overview

Cette fonctionnalité permet de grouper les lignes de factures par commande (Order), avec calcul des taxes et totaux TTC par commande.

## Architecture

### Service Layer

**Fichier:** `billing_management/services/invoice_grouping.py`

**Fonction principale:** `group_invoice_lines_by_order(invoice) -> dict`

**Entrée:** Instance d'Invoice
**Sortie:** Dictionnaire contenant:
```python
{
    'order_groups': [
        {
            'order': Order,                    # Instance de la commande
            'order_ref': str,                  # Référence de la commande (ex: "ORD-678ABC")
            'order_date': datetime,            # Date de création de la commande
            'lines': [InvoiceLine, ...],       # Lignes de facture pour cette commande
            'subtotal': Decimal,               # Sous-total (somme des line_total)
            'excise_amount': Decimal,          # Montant d'accise calculé
            'vat_amount': Decimal,             # Montant de TVA calculé
            'total_ttc': Decimal,              # Total TTC (subtotal + excise + vat)
        },
        ...
    ],
    'grouped_grand_total': Decimal         # Somme de tous les total_ttc
}
```

### Calcul des Taxes

Les taxes sont calculées **par commande** en utilisant les taux snapshotés dans la facture :

1. **Accise (Excise):**
   ```python
   excise_amount = subtotal * (invoice.excise_rate_percent / 100)
   ```

2. **TVA (VAT):**
   La TVA est calculée sur le montant après accise:
   ```python
   base_for_vat = subtotal + excise_amount
   vat_amount = base_for_vat * (invoice.vat_rate_percent / 100)
   ```

3. **Total TTC:**
   ```python
   total_ttc = subtotal + excise_amount + vat_amount
   ```

### Logique de Tri

Les commandes sont triées **chronologiquement** par `order.created_at` (ordre de création).

### Exclusions

- Les lignes avec `kind` = 'VAT' ou 'Excise' sont **exclues** du groupement
- Les lignes sans `order` associé sont **ignorées**

## Intégration dans les Vues

### Factures Simples

**Fichier:** `billing_management/views.py`
**Fonction:** `_build_invoice_context(inv, cs)`

```python
# Ligne 290
order_grouping = group_invoice_lines_by_order(inv)

# Ajouté au contexte (lignes 323-325)
context = {
    # ... autres champs ...
    "order_groups": order_grouping["order_groups"],
    "grouped_grand_total": _money_format(order_grouping["grouped_grand_total"]),
}
```

### Factures Consolidées

**Fichier:** `billing_management/views.py`
**Fonction:** `_build_consolidated_context(cons, cs)`

Pour chaque facture enfant (`child_blocks`), on ajoute les données groupées :

```python
# Ligne 545
order_grouping = group_invoice_lines_by_order(inv)

# Ajouté à chaque child_block (lignes 561-562)
child_blocks.append({
    # ... autres champs ...
    "order_groups": order_grouping["order_groups"],
    "grouped_grand_total": _money_format(order_grouping["grouped_grand_total"]),
})
```

## Utilisation dans les Templates

### Exemple de Structure HTML (à implémenter)

```django
{% if order_groups %}
  {# Affichage groupé par commande #}
  {% for group in order_groups %}
    <div class="order-section">
      <h3>Order {{ group.order_ref }} ({{ group.order_date|date:"d M Y" }})</h3>

      <table class="invoice-lines">
        <thead>
          <tr>
            <th>#</th>
            <th>Description</th>
            <th>Qty</th>
            <th>Unit Price</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          {% for line in group.lines %}
            <tr>
              <td>{{ forloop.counter }}</td>
              <td>{{ line.description }}</td>
              <td>{{ line.quantity }}</td>
              <td>${{ line.unit_price }}</td>
              <td>${{ line.line_total }}</td>
            </tr>
          {% endfor %}
        </tbody>
      </table>

      <div class="order-totals">
        <div class="subtotal">
          <span>Subtotal:</span>
          <span>${{ group.subtotal }}</span>
        </div>
        {% if group.excise_amount > 0 %}
        <div class="excise">
          <span>Excise ({{ invoice.excise_rate_percent }}%):</span>
          <span>${{ group.excise_amount }}</span>
        </div>
        {% endif %}
        <div class="vat">
          <span>VAT ({{ invoice.vat_rate_percent }}%):</span>
          <span>${{ group.vat_amount }}</span>
        </div>
        <div class="total-ttc">
          <strong>Total TTC:</strong>
          <strong>${{ group.total_ttc }}</strong>
        </div>
      </div>
    </div>
  {% endfor %}

  <div class="grand-total">
    <strong>GRAND TOTAL:</strong>
    <strong>{{ grouped_grand_total }}</strong>
  </div>
{% else %}
  {# Fallback: affichage traditionnel avec items #}
  {% for item in invoice.items %}
    <!-- Ancienne structure -->
  {% endfor %}
{% endif %}
```

### Format d'Affichage Recommandé

Pour chaque Order group:
```
Order ORD-678ABC (10 Nov 2025)
┌─────────────────────────────────────────┐
│ Description           Qty   Price  Total│
│ Kit Internet Fibre     1   $599   $599 │
│ Installation           1   $120   $120 │
├─────────────────────────────────────────┤
│ Subtotal:                          $719 │
│ Excise (10%):                       $72 │
│ VAT (16% on $791):                 $127 │
│ Total TTC:                         $918 │
└─────────────────────────────────────────┘
```

## Tests

**Fichier:** `billing_management/tests/test_invoice_order_grouping.py`

### Suite de Tests (14 tests)

1. `test_single_order_invoice_shows_order_reference` - Facture à 1 commande
2. `test_multi_order_invoice_groups_lines_correctly` - Facture consolidée
3. `test_order_group_calculates_subtotal_correctly` - Calcul du sous-total
4. `test_order_group_calculates_vat_per_order` - Calcul de la TVA
5. `test_order_group_calculates_excise_per_order` - Calcul de l'accise
6. `test_order_group_total_ttc_includes_all_taxes` - Total TTC complet
7. `test_grand_total_sums_all_order_ttc` - Somme des totaux
8. `test_order_groups_sorted_by_creation_date` - Tri chronologique
9. `test_order_with_no_excise_rate` - Gestion de l'accise nulle
10. `test_empty_invoice_returns_empty_groups` - Facture vide
11. `test_lines_without_order_are_skipped` - Lignes sans commande
12. `test_multiple_lines_same_order_grouped_together` - Plusieurs lignes/commande
13. `test_order_date_is_included_in_group` - Date de commande incluse
14. `test_decimal_precision_in_tax_calculations` - Précision décimale

### Lancer les Tests

```bash
# Tous les tests
pytest billing_management/tests/test_invoice_order_grouping.py -v

# Un test spécifique
pytest billing_management/tests/test_invoice_order_grouping.py::TestInvoiceOrderGrouping::test_multi_order_invoice_groups_lines_correctly -v
```

## Compatibilité

### Backward Compatibility

La fonctionnalité est **rétrocompatible** :

- Le contexte existant (`invoice.items`) est toujours disponible
- Les templates peuvent choisir d'utiliser `order_groups` ou `items`
- Si `order_groups` est vide, le template peut fallback sur `items`

### Migration Progressive

1. **Phase 1:** Ajouter le groupement au contexte ✅ (fait)
2. **Phase 2:** Modifier les templates pour utiliser `order_groups`
3. **Phase 3:** Tester avec des factures réelles
4. **Phase 4:** Déployer progressivement

## Notes Techniques

### Performance

- Utilise `select_related('order')` pour optimiser les requêtes
- Un seul query pour récupérer toutes les lignes
- Calculs en mémoire (pas de queries supplémentaires)

### Précision Décimale

- Tous les calculs utilisent `Decimal` avec `quantize(Decimal('0.01'))`
- Arrondi au centime (2 décimales)

### Cas Particuliers

1. **Facture sans commandes:** Retourne `order_groups = []`
2. **Lignes sans order:** Ignorées (ne cassent pas le groupement)
3. **Taxes nulles:** Affichées comme `Decimal('0.00')`
4. **Multiples lignes même commande:** Groupées ensemble avec subtotal cumulé

## Prochaines Étapes

1. ✅ Tests unitaires complets (14/14 passés)
2. ✅ Intégration dans les vues
3. ⏳ Modification des templates (`inv_templates.html` et `consolidated_inv_templates.html`)
4. ⏳ Tests end-to-end avec génération PDF
5. ⏳ Documentation utilisateur (comment lire la facture groupée)

## Références

- **Models:** `main/models.py` (Invoice, InvoiceLine, Order)
- **Views:** `billing_management/views.py`
- **Templates:** `billing_management/templates/invoices/`
- **Tests:** `billing_management/tests/test_invoice_order_grouping.py`
