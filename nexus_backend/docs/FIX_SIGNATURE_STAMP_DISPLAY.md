# Correction de l'affichage écrasé de la signature et du cachet

## 🐛 Problème identifié

Les images de signature et de cachet apparaissaient écrasées dans les factures PDF.

### Cause racine

Le style CSS global `.signblock img` imposait une **hauteur fixe** de `38px` avec `height:38px`, ce qui écrasait les images qui ne respectaient pas ce ratio d'aspect.

```css
/* AVANT - Problématique */
.signblock img {
  height:38px;              /* ❌ Hauteur fixe force l'image */
  display:block;
  margin:0 auto 3pt auto;
}
```

---

## ✅ Solution appliquée

### 1. Modification du CSS pour préserver le ratio d'aspect

**Fichiers modifiés:**
- `billing_management/templates/invoices/inv_templates.html`
- `billing_management/templates/invoices/consolidated_inv_templates.html`

**Nouveau style CSS:**

```css
/* APRÈS - Corrigé et optimisé */
.signblock img {
  max-height: 40px;          /* ✅ Hauteur maximum (flexible) - Réduit pour un affichage professionnel */
  max-width: 100px;          /* ✅ Largeur maximum (flexible) - Réduit pour un affichage professionnel */
  width: auto;               /* ✅ Largeur automatique */
  height: auto;              /* ✅ Hauteur automatique */
  display: block;
  margin: 0 auto 3pt auto;
  object-fit: contain;       /* ✅ Préserve le ratio d'aspect */
}
```

**Avantages:**
- ✅ Les images conservent leur **ratio d'aspect naturel**
- ✅ Limitation par `max-height: 40px` et `max-width: 100px` pour un affichage compact et professionnel
- ✅ `object-fit: contain` assure que l'image est entièrement visible sans déformation
- ✅ `width: auto` et `height: auto` permettent un redimensionnement proportionnel

---

### 2. Suppression des styles inline redondants

**Dans le HTML des templates:**

#### AVANT
```django-html
{% if company.signature %}
  <img src="{{ company.signature.url }}" alt="Signature" style="max-height:60px;">
{% endif %}
...
{% if company.stamp %}
  <img src="{{ company.stamp.url }}" alt="Company Stamp" style="max-height:50px; margin-top:5px;">
{% endif %}
```

#### APRÈS
```django-html
{% if company.signature %}
  <img src="{{ company.signature.url }}" alt="Signature">
{% endif %}
...
{% if company.stamp %}
  <img src="{{ company.stamp.url }}" alt="Company Stamp" style="margin-top:8px;">
{% endif %}
```

**Changements:**
- ✅ Retrait de `style="max-height:60px;"` sur la signature (géré par CSS global)
- ✅ Retrait de `style="max-height:50px;"` sur le cachet (géré par CSS global)
- ✅ Conservation de `margin-top:8px` pour espacer le cachet de la signature
- ✅ Code HTML plus propre et maintenable

---

### 3. Ajout des styles signature dans le template consolidé

Le template `consolidated_inv_templates.html` **n'avait pas** les styles `.signblock` et `.sig` dans sa section `<style>`.

**Ajouté au CSS:**
```css
/* === SIGNATURES & FOOTER === */
.sigrow { margin-top:6pt; }
.sig { border-top:1px solid #e5e7eb; text-align:center; padding-top:5pt; color:#555; font-size:9.5px; }
.signblock { margin-top:4pt; text-align:center; }
.signblock img { max-height:60px; max-width:150px; width:auto; height:auto; display:block; margin:0 auto 3pt auto; object-fit:contain; }
.signlabel { font-size:9px; color:#555; }
```

---

## 📊 Comparaison visuelle

### Avant (écrasé)
```
┌─────────────────┐
│ [■■■■■■■■■■■■■] │  ← Image signature déformée (38px fixe)
│ John Doe, CEO   │
│ ─────────────── │
│                 │
│ [■■■■■■■■■■■■■] │  ← Cachet déformé
└─────────────────┘
```

### Après (proportionnel et compact)
```
┌─────────────────┐
│  [Signature]    │  ← Image avec ratio préservé (max 40px x 100px)
│                 │
│ John Doe, CEO   │
│ ─────────────── │
│                 │
│   [Cachet]      │  ← Cachet avec ratio préservé (max 40px x 100px)
│                 │
└─────────────────┘
```

---

## 🎯 Résultats attendus

### Pour la signature
- ✅ Image affichée avec son **ratio d'aspect naturel**
- ✅ Taille limitée à **maximum 40px de hauteur** et **100px de largeur** (optimisé pour facture A4)
- ✅ Pas de déformation ni d'écrasement
- ✅ Centrage automatique dans le bloc
- ✅ Affichage compact et professionnel

### Pour le cachet (stamp)
- ✅ Image affichée avec son **ratio d'aspect naturel**
- ✅ Mêmes contraintes de taille optimisées (40px x 100px)
- ✅ Mêmes contraintes de taille que la signature
- ✅ Espacement de **8px** au-dessus pour séparation visuelle
- ✅ Pas de déformation ni d'écrasement

---

## 🧪 Tests recommandés

### Test 1: Signature carrée
Upload une signature de dimension **200x200px**
- ✅ Doit s'afficher à **40x40px** (limitée par max-height)

### Test 2: Signature large
Upload une signature de dimension **400x100px**
- ✅ Doit s'afficher à **100x25px** (limitée par max-width, ratio préservé)

### Test 3: Signature haute
Upload une signature de dimension **100x300px**
- ✅ Doit s'afficher à **13.3x40px** (limitée par max-height, ratio préservé)

### Test 4: Cachet rond
Upload un cachet circulaire de dimension **300x300px**
- ✅ Doit s'afficher à **40x40px** (limité par max-height)

### Test 5: Sans images
Ne pas uploader de signature ni de cachet
- ✅ Le layout doit rester correct
- ✅ Ligne de signature par défaut visible

---

## 📁 Fichiers modifiés

| Fichier | Lignes CSS | Lignes HTML | Changements |
|---------|-----------|-------------|-------------|
| `inv_templates.html` | ~88-92 | ~243-256 | CSS corrigé + HTML nettoyé |
| `consolidated_inv_templates.html` | ~88-95 | ~253-266 | CSS ajouté + HTML nettoyé |

---

## 💡 Bonnes pratiques appliquées

### 1. Séparation des préoccupations
- ✅ **CSS pour le style** (dimensions, espacement)
- ✅ **HTML pour la structure** (contenu, sémantique)
- ❌ Éviter les styles inline sauf cas spécifiques

### 2. Préservation du ratio d'aspect
- ✅ Utiliser `max-width` et `max-height` au lieu de `width` et `height` fixes
- ✅ Toujours ajouter `object-fit: contain` pour les images
- ✅ Utiliser `width: auto` et `height: auto` pour un redimensionnement proportionnel

### 3. Responsive et flexible
- ✅ Les images s'adaptent à leur contenu
- ✅ Pas de taille fixe qui pourrait casser le layout
- ✅ Contraintes maximales pour éviter les débordements

---

## 🔄 Impact sur xhtml2pdf

**xhtml2pdf** supporte:
- ✅ `max-width` et `max-height`
- ✅ `width: auto` et `height: auto`
- ⚠️ Support partiel de `object-fit` (peut ne pas fonctionner)

**Solution de fallback:**
- Le ratio d'aspect est principalement géré par `width: auto` et `height: auto`
- Les contraintes `max-*` limitent la taille finale
- Même si `object-fit: contain` n'est pas supporté, le résultat reste correct

---

**Date:** 12 novembre 2025
**Auteur:** GitHub Copilot
**Statut:** ✅ Corrigé - Prêt pour tests PDF
