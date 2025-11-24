# Invoice Templates Update - Order Grouping

**Date:** 2025-11-12
**Feature:** Order Grouping in Invoice Templates
**Status:** ✅ Implemented

## Summary

Les templates de facture ont été mis à jour pour afficher les lignes groupées par commande (Order) avec calculs de taxes et totaux TTC par commande.

## Files Modified

### 1. `billing_management/templates/invoices/inv_templates.html`

#### CSS Additions (Lines ~76-106)

Ajouté les styles pour le groupement par commande :

```css
/* === ORDER GROUPING === */
.order-group { margin-bottom: 8pt; }
.order-header {
  background: #f8fafc;
  border-left: 3px solid #2563eb;
  padding: 4pt 6pt;
  margin-bottom: 2pt;
  font-size: 10.5px;
  font-weight: 600;
  color: #1e293b;
}
.order-header .order-ref { color: #2563eb; }
.order-totals {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 2pt;
  padding: 4pt 8pt;
  margin-top: 2pt;
  font-size: 10px;
}
.order-totals table { width: 100%; border-spacing: 0; }
.order-totals td { padding: 2pt 0; }
.order-totals .order-ttc {
  font-weight: 700;
  font-size: 11px;
  color: #2563eb;
  border-top: 1px solid #cbd5e1;
  padding-top: 3pt;
  margin-top: 2pt;
}
```

#### HTML Structure Changes (Lines ~173-270)

**Avant:**
```django
<table>
  <thead>...</thead>
  <tbody>
    {% for item in invoice.items %}
      <tr>...</tr>
    {% endfor %}
  </tbody>
</table>
```

**Après:**
```django
{% if order_groups %}
  {# Display grouped by order #}
  {% for group in order_groups %}
    <div class="order-group">
      <div class="order-header">
        Order {{ group.order_ref }} · {{ group.order_date|date:"d M Y" }}
      </div>

      <table>
        <thead>...</thead>
        <tbody>
          {% for line in group.lines %}
            <tr>...</tr>
          {% endfor %}
        </tbody>
      </table>

      <div class="order-totals">
        <table>
          <tr>Subtotal: ${{ group.subtotal }}</tr>
          <tr>Excise: ${{ group.excise_amount }}</tr>
          <tr>VAT: ${{ group.vat_amount }}</tr>
          <tr class="order-ttc">Total TTC: ${{ group.total_ttc }}</tr>
        </table>
      </div>
    </div>
  {% endfor %}
{% else %}
  {# Fallback: traditional item display #}
  <table>...</table>
{% endif %}
```

### 2. `billing_management/templates/invoices/consolidated_inv_templates.html`

#### CSS Additions (Lines ~87-118)

Ajouté les mêmes styles de groupement, adaptés pour la taille plus compacte des factures consolidées :

```css
/* === ORDER GROUPING === */
.order-group { margin-bottom: 6pt; }
.order-header {
  background: #f8fafc;
  border-left: 3px solid #2563eb;
  padding: 3pt 5pt;
  margin-bottom: 2pt;
  font-size: 9.5px;
  font-weight: 600;
  color: #1e293b;
}
.order-header .order-ref { color: #2563eb; }
.order-totals {
  background: #f8fafc;
  border: 1px solid #e5e7eb;
  border-radius: 2pt;
  padding: 3pt 6pt;
  margin-top: 2pt;
  font-size: 9px;
}
.order-totals table { width: 100%; border-spacing: 0; }
.order-totals td { padding: 1pt 0; font-size: 9px; }
.order-totals .order-ttc {
  font-weight: 700;
  font-size: 10px;
  color: #2563eb;
  border-top: 1px solid #cbd5e1;
  padding-top: 2pt;
  margin-top: 1pt;
}
```

#### HTML Structure Changes (Lines ~218-286)

**Avant:**
```django
{% for child in consolidated.children %}
  <tr class="child-hdr">...</tr>

  {% for item in child.items %}
    <tr>...</tr>
  {% endfor %}

  <tr>Invoice Total: {{ child.grand_total }}</tr>
{% endfor %}
```

**Après:**
```django
{% for child in consolidated.children %}
  <tr class="child-hdr">...</tr>

  {% if child.order_groups %}
    {# Display grouped by order #}
    {% for group in child.order_groups %}
      <tr>
        <td colspan="4">
          <div class="order-group">
            <div class="order-header">
              Order {{ group.order_ref }} · {{ group.order_date|date:"d M Y" }}
            </div>

            <table>
              <tbody>
                {% for line in group.lines %}
                  <tr>...</tr>
                {% endfor %}
              </tbody>
            </table>

            <div class="order-totals">
              <table>
                <tr>Subtotal: ${{ group.subtotal }}</tr>
                <tr>Excise: ${{ group.excise_amount }}</tr>
                <tr>VAT: ${{ group.vat_amount }}</tr>
                <tr class="order-ttc">Total TTC: ${{ group.total_ttc }}</tr>
              </table>
            </div>
          </div>
        </td>
      </tr>
    {% endfor %}
  {% else %}
    {# Fallback: traditional item display #}
    {% for item in child.items %}
      <tr>...</tr>
    {% endfor %}
  {% endif %}

  <tr>Invoice Total: {{ child.grand_total }}</tr>
{% endfor %}
```

## Visual Changes

### Before (Traditional Display)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Description          Qty  Price    Total
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Kit Internet Fibre    1   $599     $599
Installation          1   $120     $120
Monthly Plan          1   $50      $50
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
                    Subtotal:      $769
                    Excise (10%):   $77
                    VAT (16%):     $135
                    Total Due:     $981
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### After (Order Grouped Display)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Order ORD-678ABC · 10 Nov 2025
┌────────────────────────────────────┐
│ Description      Qty  Price  Total │
│ Kit Internet      1   $599   $599  │
│ Installation      1   $120   $120  │
├────────────────────────────────────┤
│ Subtotal:                    $719  │
│ Excise (10%):                 $72  │
│ VAT (16% on $791):           $127  │
│ Total TTC:                   $918  │
└────────────────────────────────────┘

Order ORD-679XYZ · 11 Nov 2025
┌────────────────────────────────────┐
│ Description      Qty  Price  Total │
│ Monthly Plan      1    $50    $50  │
├────────────────────────────────────┤
│ Subtotal:                     $50  │
│ Excise (10%):                  $5  │
│ VAT (16% on $55):              $9  │
│ Total TTC:                    $64  │
└────────────────────────────────────┘
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Features

### ✅ Order Header
- Affiche le numéro de commande (ex: "ORD-678ABC")
- Affiche la date de création de la commande
- Style visuel distinctif (bordure bleue à gauche)

### ✅ Per-Order Line Items
- Lignes regroupées par commande
- Même format de tableau que l'affichage traditionnel
- Quantités, prix unitaires, totaux de ligne

### ✅ Per-Order Tax Calculations
- **Subtotal:** Somme des line_total pour la commande
- **Excise:** Calculé sur le subtotal avec le taux snapshoté
- **VAT:** Calculé sur (subtotal + excise) avec le taux snapshoté
- **Total TTC:** Subtotal + Excise + VAT

### ✅ Visual Hierarchy
- Background gris clair (#f8fafc) pour distinguer les sections
- Couleur bleue (#2563eb) pour les références de commandes
- Total TTC en gras et couleur bleue pour emphase

### ✅ Backward Compatibility
- Si `order_groups` est vide ou absent, fallback sur `invoice.items`
- Aucune breaking change pour les factures existantes
- Transition progressive possible

### ✅ Responsive Layout
- Limite MAX_ROWS respectée (12 lignes par page)
- Pagination automatique si trop de groupes
- Optimisé pour impression A4

## Context Variables Used

### From `_build_invoice_context()`

```python
{
    'order_groups': [
        {
            'order': Order,
            'order_ref': 'ORD-678ABC',
            'order_date': datetime,
            'lines': [InvoiceLine, ...],
            'subtotal': Decimal('719.00'),
            'excise_amount': Decimal('71.90'),
            'vat_amount': Decimal('126.86'),
            'total_ttc': Decimal('917.76'),
        },
        ...
    ],
    'grouped_grand_total': '$1,234.56',
}
```

### From `_build_consolidated_context()`

```python
{
    'consolidated': {
        'children': [
            {
                'number': 'INV/2025/001',
                'issued_at': '10 Nov 2025',
                'items': [...],  # Fallback
                'grand_total': '$918.00',
                # New:
                'order_groups': [...],
                'grouped_grand_total': '$918.00',
            },
            ...
        ],
    },
}
```

## Testing Checklist

- [x] CSS styles appliqués correctement
- [x] Groupement fonctionne pour factures simples
- [x] Groupement fonctionne pour factures consolidées
- [x] Fallback sur `items` si `order_groups` vide
- [x] Calculs de taxes corrects par commande
- [x] Format de date correct
- [x] Devises affichées correctement
- [ ] PDF généré avec xhtml2pdf (à tester)
- [ ] Impression A4 (à tester)
- [ ] Factures multi-pages (à tester)

## Known Limitations

1. **xhtml2pdf CSS Support:**
   - Pas de support pour `border-radius` (ignoré)
   - `object-fit` peut ne pas fonctionner (utilisé pour images)
   - Certaines propriétés CSS3 avancées non supportées

2. **Pagination:**
   - Limite MAX_ROWS=12 peut couper des groupes de commandes
   - Pas de page break intelligent entre groupes

3. **Performance:**
   - Factures avec beaucoup de commandes peuvent déborder
   - Recommandé: limiter à 10-15 commandes par facture

## Next Steps

1. **Test PDF Generation:**
   ```bash
   # Tester la génération de PDF avec une vraie facture
   python manage.py shell
   >>> from billing_management.views import invoice_pdf_by_number
   >>> # Tester avec une facture existante
   ```

2. **Visual Inspection:**
   - Générer des PDFs de test
   - Vérifier l'alignement des colonnes
   - Vérifier la lisibilité sur différentes imprimantes

3. **User Acceptance Testing:**
   - Montrer aux utilisateurs finaux
   - Collecter feedback sur la clarté
   - Ajuster les styles si nécessaire

4. **Documentation Utilisateur:**
   - Guide pour lire les nouvelles factures
   - Explication du groupement par commande
   - FAQ sur les totaux TTC

## Rollback Plan

Si problème avec les nouveaux templates:

1. **Désactiver temporairement:**
   ```python
   # Dans views.py, commenter les lignes:
   # "order_groups": order_grouping["order_groups"],
   # "grouped_grand_total": _money_format(order_grouping["grouped_grand_total"]),
   ```

2. **Restaurer templates:**
   ```bash
   git checkout HEAD~1 -- billing_management/templates/invoices/
   ```

3. **Version hybride:**
   - Garder les deux affichages
   - Ajouter un toggle dans CompanySettings
   - `use_order_grouping = BooleanField(default=False)`

## References

- **Service:** `billing_management/services/invoice_grouping.py`
- **Views:** `billing_management/views.py` (lines 290, 545)
- **Tests:** `billing_management/tests/test_invoice_order_grouping.py`
- **Documentation:** `docs/billing/INVOICE_ORDER_GROUPING.md`
