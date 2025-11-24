# 🎨 Guide de Test - Alignement Logo / Nom d'Entreprise

## Objectif
Vérifier que le logo "NEXUS TELECOMS" a la même largeur que le texte "Nexus Telecoms SA" en dessous.

---

## 📐 Design Attendu

### Avant (problème)
```
┌────────────────────────────────────┐
│ [━]  ← Logo trop petit (1px)       │
│ Nexus Telecoms SA                  │
└────────────────────────────────────┘
```

### Après (solution)
```
┌────────────────────────────────────┐
│ ┌───────────────┐                  │
│ │ NEXUS LOGO    │  ← 200px         │
│ └───────────────┘                  │
│ Nexus Telecoms SA  ← 200px         │
│ (même largeur)                     │
└────────────────────────────────────┘
```

---

## ✅ Changements Appliqués

### CSS Modifié

**Logo Container:**
```css
.logo {
  width: 100%;
  max-width: 200px;      /* Largeur maximale alignée avec le titre */
  margin-bottom: 6pt;    /* Espacement avec le texte */
  overflow: hidden;
}
```

**Logo Image:**
```css
.logo img {
  width: 100% !important;       /* Remplit le conteneur */
  max-width: 200px !important;  /* Maximum 200px */
  height: auto !important;      /* Hauteur automatique (proportionnelle) */
  display: block !important;
  object-fit: contain;
}
```

**Titre de l'Entreprise (alignement):**
```css
.co h1 {
  max-width: 200px;  /* Même largeur que le logo */
}
```

---

## 🧪 Test Visuel

### 1. Redémarrer le serveur
```bash
# Arrêter avec Ctrl+C si déjà lancé, puis:
python manage.py runserver
```

### 2. Ouvrir le PDF dans le navigateur
```
http://localhost:8000/en/billing/invoice/2025-IND-000001/pdf/
```

### 3. Rafraîchir avec cache vide
**Ctrl + Shift + R** (hard refresh) pour être sûr d'avoir le nouveau CSS

---

## ✅ Checklist de Validation

Vérifiez visuellement dans le PDF :

| Critère | ✓/✗ | Notes |
|---------|-----|-------|
| **Logo visible** (pas 1px) | ☐ | Le logo doit être clairement visible |
| **Largeur du logo ≈ 200px** | ☐ | Mesure visuelle approximative |
| **Largeur "Nexus Telecoms SA" ≈ 200px** | ☐ | Texte du titre en dessous |
| **Logo et titre alignés** | ☐ | Même largeur, alignés à gauche |
| **Proportions logo conservées** | ☐ | Le logo n'est pas déformé |
| **Espacement approprié** | ☐ | 6pt entre logo et titre |

---

## 📏 Mesure Visuelle

Pour vérifier l'alignement :

1. **Dans le PDF**, regardez le bord droit du logo
2. **Regardez le bord droit** de "Nexus Telecoms SA"
3. **Ils devraient être alignés** (ou très proche)

```
Exemple visuel correct :
┌────────────────────┐
│ NEXUS             │
│ TELECOMS          │
└────────────────────┘
Nexus Telecoms SA
^                  ^
Bord gauche       Bord droit
  alignés           alignés
```

---

## 🎨 Référence Visuelle

Votre logo fourni :
- **Texte:** "NEXUS" (gris) + "TELECOMS" (bleu)
- **Largeur naturelle:** adaptative
- **Hauteur:** proportionnelle à la largeur (auto)

Le logo sera **redimensionné à 200px de large** maximum, avec la hauteur calculée automatiquement pour maintenir les proportions.

---

## 🔍 Dépannage

### Problème: Logo encore trop petit
**Solution:** Vérifiez que le cache du navigateur est vidé (Ctrl+Shift+R)

### Problème: Logo déformé
**Solution:** `height: auto` devrait empêcher cela. Si problème persiste, vérifiez `object-fit: contain`

### Problème: Alignement pas parfait
**Solution:** Ajustez `max-width` dans le CSS (actuellement 200px)
```css
.logo { max-width: 220px; }  /* Exemple d'ajustement */
.co h1 { max-width: 220px; }
```

---

## 📊 Résultat Attendu

**Largeur logo:** ~200px
**Largeur titre:** ~200px
**Ratio:** 1:1 (parfaitement alignés)
**Hauteur logo:** Automatique selon proportions (probablement 50-70px)

---

## ✅ Validation Finale

Une fois le test visuel réussi, cochez ici :

- [ ] Logo clairement visible (pas 1px)
- [ ] Logo et titre "Nexus Telecoms SA" ont la même largeur
- [ ] Alignement visuel satisfaisant
- [ ] Proportions du logo conservées
- [ ] Aspect professionnel général

---

**Prêt à tester ?** 🚀

Rafraîchissez votre page PDF et comparez avec les critères ci-dessus !
