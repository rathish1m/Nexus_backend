# Documentation : Erreur JavaScript lors de l'injection de traductions Django dans le JS

## Problème rencontré

Lors du changement de langue (français), la page `/fr/kyc/` générait une erreur JavaScript :

> SyntaxError: missing } after property list

Cette erreur était causée par l'injection directe de traductions Django (ex: `{% trans "Personal Information" %}`) dans des objets JavaScript, sans échappement. Si la traduction contient des guillemets ou apostrophes (ex: `Informations Personnelles`), cela casse la syntaxe JS.

## Solution

Utiliser le filtre `escapejs` sur toutes les traductions injectées dans le JavaScript :

```django
// Mauvais
 title: '{% trans "Personal Information" %}'
// Correct
 title: '{% trans "Personal Information"|escapejs %}'
```

Ce filtre protège la syntaxe JavaScript contre les caractères spéciaux présents dans les traductions.

## À retenir pour l'équipe
- Toujours utiliser `|escapejs` pour les traductions Django insérées dans du code JavaScript.
- Vérifier les objets JS et les templates qui injectent des variables ou des labels traduits.
- Tester la page dans toutes les langues pour valider l'absence d'erreur JS.

## Référence
- [Django escapejs filter](https://docs.djangoproject.com/en/4.2/ref/templates/builtins/#escapejs)

---
Dernière mise à jour : 2025-10-11
