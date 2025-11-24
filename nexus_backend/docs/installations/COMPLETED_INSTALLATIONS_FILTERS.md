# Filtres pour Installations Finies

## 📋 Vue d'ensemble

La page "Installations finies" dans le backoffice dispose maintenant de filtres avancés pour faciliter la recherche et l'analyse des rapports d'installation soumis.

## 🔍 Filtres disponibles

### 1. **Filtre par Technicien**
- **Type** : Liste déroulante
- **Options** : Tous les techniciens actifs (technician + leadtechnician)
- **Fonctionnalité** : Affiche uniquement les installations réalisées par le technicien sélectionné
- **Par défaut** : "Tous les techniciens"

### 2. **Filtre par Date de Début**
- **Type** : Sélecteur de date (input date)
- **Champ filtré** : `completed_at__date__gte`
- **Fonctionnalité** : Affiche les installations terminées à partir de cette date

### 3. **Filtre par Date de Fin**
- **Type** : Sélecteur de date (input date)
- **Champ filtré** : `completed_at__date__lte`
- **Fonctionnalité** : Affiche les installations terminées jusqu'à cette date

## 🎨 Interface Utilisateur

### Section Filtres
```html
- Formulaire GET avec 3 champs de filtrage
- Design responsive (colonne mobile, ligne desktop)
- Bouton "Filtrer" (emerald-600)
- Bouton "Réinitialiser" (gray-200) - efface tous les filtres
```

### Badges de Filtres Actifs
Affichage visuel des filtres appliqués avec :
- Badge bleu pour le technicien sélectionné
- Badges emerald pour les dates
- Icône × pour supprimer un filtre individuel
- Indicateur "filtré" dans le header

### Pagination
- Conservation automatique des paramètres de filtrage
- Navigation entre les pages sans perdre les filtres
- 20 résultats par page

## 📊 Indicateurs Visuels

### Header
```
🔍 Badge "filtré" s'affiche dans le header quand au moins un filtre est actif
📊 Compteur total adapté aux filtres (ex: "45 rapports" au lieu de "200 rapports")
```

### Filtres Actifs
```
🏷️ Badge pour chaque filtre actif
🗑️ Bouton × pour supprimer un filtre individuellement
🎨 Couleurs distinctes : bleu (technicien), emerald (dates)
```

## 🔧 Implémentation Backend

### Vue : `completed_installations()` dans `backoffice/views.py`

```python
# Paramètres GET
- technician (ID du technicien)
- date_from (format: YYYY-MM-DD)
- date_to (format: YYYY-MM-DD)

# Filtres appliqués
- technician_id : filter(technician_id=technician_id)
- date_from : filter(completed_at__date__gte=date_from)
- date_to : filter(completed_at__date__lte=date_to)

# Context renvoyé
- installations (page_obj)
- total_completed (count avec filtres)
- technicians (liste complète pour dropdown)
- selected_technician, date_from, date_to (pour pré-remplir le formulaire)
```

### Template : `backoffice/templates/completed_installations.html`

Structure :
1. Header avec badge "filtré"
2. Section filtres (formulaire GET)
3. Badges filtres actifs (conditionnel)
4. Tableau des résultats
5. Pagination avec conservation des paramètres

## 🚀 Utilisation

### Exemple d'URLs générées

```
# Tous les rapports
/fr/backoffice/installations/completed/

# Filtre par technicien
/fr/backoffice/installations/completed/?technician=5

# Filtre par plage de dates
/fr/backoffice/installations/completed/?date_from=2024-01-01&date_to=2024-12-31

# Combinaison de filtres
/fr/backoffice/installations/completed/?technician=5&date_from=2024-01-01&date_to=2024-12-31

# Pagination avec filtres
/fr/backoffice/installations/completed/?page=2&technician=5&date_from=2024-01-01
```

### Cas d'usage

1. **Rapport mensuel par technicien**
   - Sélectionner le technicien
   - Définir date_from = 01/MM/YYYY
   - Définir date_to = 31/MM/YYYY
   - → Liste filtrée + export possible

2. **Analyse de performance**
   - Comparer plusieurs techniciens
   - Utiliser les filtres de dates pour périodes spécifiques
   - Vérifier les notes clients et temps d'installation

3. **Audit de qualité**
   - Filtrer par période
   - Analyser tous les techniciens ou un technicien spécifique
   - Vérifier les rapports soumis

## ✅ Fonctionnalités complètes

- ✅ Filtrage par technicien
- ✅ Filtrage par plage de dates d'installation
- ✅ Badges visuels des filtres actifs
- ✅ Réinitialisation rapide des filtres
- ✅ Conservation des filtres lors de la pagination
- ✅ Interface responsive (mobile/desktop)
- ✅ Support multilingue (fr/en)
- ✅ Indicateur "filtré" dans le header

## 🔐 Permissions

**Accès** : Admin et Lead Technician uniquement
```python
@login_required(login_url="login_page")
@user_passes_test(lambda u: u.is_staff, login_url="login_page")
```

**Menu** : Visible uniquement pour :
```django
{% if user|has_role:"admin" or user|has_role:"leadtechnician" %}
```

## 📝 Notes Techniques

- **Query optimization** : `.select_related("order", "order__user", "technician")` pour éviter N+1 queries
- **Pagination** : 20 items par page
- **Tri** : Par date de soumission DESC (`-submitted_at`)
- **Filtres** : Appliqués avant pagination pour compter correct
- **Template extends** : `backoffice/dispatch_console_base.html`

## 🎯 Prochaines améliorations possibles

- [ ] Export Excel/CSV des résultats filtrés
- [ ] Filtre par statut de commande
- [ ] Filtre par note client (rating)
- [ ] Recherche par référence de commande
- [ ] Graphiques statistiques basés sur les filtres
- [ ] Sauvegarde de filtres favoris
