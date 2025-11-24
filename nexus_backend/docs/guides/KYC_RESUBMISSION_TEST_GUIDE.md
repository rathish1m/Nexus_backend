# Guide de tests automatisés — Workflow de resoumission KYC

## Objectif
Valider le workflow de resoumission KYC (Personnel et Entreprise) :
- Le bouton "Resoumettre KYC" affiche directement le bon formulaire selon le type rejeté.
- Les champs du formulaire sont préremplis avec les données du dernier KYC rejeté.

## Modèles concernés
- `PersonalKYC` (KYC personnel)
- `CompanyKYC` (KYC entreprise)
- Les deux sont liés à l'utilisateur par un champ `user` (OneToOneField).

## Vue et template
- Vue : `landing_page` (client_app/views.py)
- Template : `client_app/templates/partials/landing_page_content.html`
- Le contexte injecte les objets `personal_kyc` et `company_kyc` pour le préremplissage JS.

## Tests automatisés
- Fichier : `client_app/tests/test_kyc_resubmission.py`
- Deux cas testés :
  1. Création d'un utilisateur + KYC personnel rejeté
  2. Création d'un utilisateur + KYC entreprise rejeté
- Vérification que le rendu du template contient :
  - `window.kycType = "personal"` ou `window.kycType = "business"`
  - Les données du KYC rejeté (nom, date, adresse, etc.)

## Problème technique rencontré
- Les tests échouent avec l'erreur :
  `AttributeError: 'DatabaseOperations' object has no attribute 'geo_db_type'`
- Cause : Django tente d'utiliser des champs géographiques (GeoDjango) avec SQLite, qui ne les supporte pas.

## Solution recommandée
- Utiliser PostgreSQL + PostGIS comme backend de test pour Django.
- Adapter la configuration dans `settings.py` :
  ```python
  DATABASES = {
      'default': {
          'ENGINE': 'django.contrib.gis.db.backends.postgis',
          'NAME': 'nexus_test',
          'USER': 'postgres',
          'PASSWORD': 'mot_de_passe',
          'HOST': 'localhost',
          'PORT': '5432',
      }
  }
  ```
- Créer la base et activer l'extension PostGIS :
  ```sh
  sudo -u postgres createdb nexus_test
  sudo -u postgres psql -c "CREATE EXTENSION postgis;" nexus_test
  ```
- Lancer les migrations puis les tests :
  ```sh
  python manage.py migrate
  pytest client_app/tests/test_kyc_resubmission.py
  ```

## Documentation utile
- [Django GeoDjango Setup](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/install/)
- [Pytest-Django Database Setup](https://pytest-django.readthedocs.io/en/latest/database.html)
- [PostGIS Documentation](https://postgis.net/docs/)

## À faire
- Adapter les tests si la structure des modèles KYC évolue.
- Ajouter des tests pour la soumission et la correction du KYC si besoin.

---
Pour toute question ou blocage technique, contactez le référent backend ou frontend.
