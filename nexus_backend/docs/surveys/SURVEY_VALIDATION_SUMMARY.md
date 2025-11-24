## Résumé des Modifications - Validation des Approbations de Site Survey

### Problème Identifié
L'utilisateur a remarqué qu'il était possible d'approuver des site surveys marqués comme "Installation non feasible", ce qui pose un problème logique dans le workflow.

### Modifications Apportées

#### 1. Backend - API Enhancement (`site_survey/views.py`)
- **Ajout du champ `installation_feasible`** dans l'API `survey_dashboard_api`
- Ce champ permet au frontend de connaître l'état de faisabilité de chaque survey

```python
# Ligne ajoutée dans survey_data.append()
"installation_feasible": survey.installation_feasible,
```

#### 2. Backend - Validation Logic (`site_survey/views.py`)
- **Ajout de validation dans `survey_detail`** pour empêcher l'approbation des surveys non faisables
- Validation pour les requêtes JSON (AJAX) et les soumissions de formulaire
- Message d'erreur explicite : "Cannot approve survey - technician marked installation as NOT feasible. Please reject instead."

#### 3. Frontend - UI Enhancement (`survey_dashboard.html`)
- **Désactivation visuelle du bouton Approve** pour les surveys non faisables
- **Ajout d'un indicateur visuel** "⚠️ Installation NOT Feasible" en rouge
- **Bouton grisé** avec tooltip explicatif "Cannot approve - installation marked as not feasible"

```javascript
// Condition ajoutée dans la génération des boutons d'action
if (survey.installation_feasible === false) {
    // Bouton désactivé + warning visuel
} else {
    // Boutons normaux approve/reject
}
```

### Résultat
✅ **Protection complète contre les approbations incohérentes** :
1. **Côté serveur** : Validation stricte qui empêche l'approbation
2. **Côté client** : Interface utilisateur claire qui guide l'utilisateur
3. **Feedback visuel** : Indicateurs clairs pour les surveys non faisables

### Test de Validation
- Survey 30 : status=approved, feasible=False (problème existant détecté)
- Survey 28 : status=completed, feasible=True (cas normal)
- Les nouvelles surveys completed avec installation_feasible=False ne peuvent plus être approuvées

### Prochaines Étapes Recommandées
1. **Tester l'interface** sur http://localhost:8000/site-survey/surveys/
2. **Vérifier les surveys existantes** avec status=approved et feasible=False
3. **Former les utilisateurs** sur le nouveau workflow
4. **Considérer une migration de données** pour corriger les incohérences existantes
