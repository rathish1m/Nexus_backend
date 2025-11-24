# 📋 Workflow Après Rejet de Site Survey - Spécifications Techniques

## 🎯 État Actuel vs État Souhaité

### ❌ Problèmes Actuels Identifiés
- **Survey 31**: Rejeté avec raison "Installation not feasible" - aucun suivi automatique
- **Pas de notifications** automatiques aux parties prenantes
- **Pas de processus** de replanification ou d'escalation
- **Technicians et clients** dans l'ignorance du statut

### ✅ Workflow Recommandé

## 📧 Phase 1: Système de Notifications

### 1.1 Notification au Technician
**Déclencheur**: Changement de status vers "rejected"
```python
# site_survey/models.py - dans la méthode save()
if self.status == 'rejected' and original_status != 'rejected':
    send_rejection_notification_to_technician(self)
```

**Contenu email/SMS**:
```
Subject: Site Survey #{survey.id} Rejeté - Action Requise

Bonjour {technician.full_name},

Votre site survey pour la commande {order.order_reference} a été rejeté.

Raison: {rejection_reason}
Date de rejet: {rejected_at}

Actions recommandées:
- Réexaminer les exigences du site
- Proposer des solutions alternatives
- Contacter l'équipe support si besoin

Accéder au survey: {survey_url}
```

### 1.2 Notification au Client
**Contenu**:
```
Subject: Mise à Jour - Étude de Site en Cours de Révision

Cher(e) {customer.full_name},

Votre commande {order.reference} fait l'objet d'une révision technique.

Notre équipe travaille à identifier la meilleure solution pour votre installation.

Nous vous recontacterons sous 48h avec les prochaines étapes.

Support: support@nexus.com
```

## 🔄 Phase 2: Workflow de Replanification

### 2.1 Options Post-Rejet
Quand un survey est rejeté, l'admin doit choisir:

```python
class SurveyRejectionAction(models.TextChoices):
    RESCHEDULE_SAME = "reschedule_same", "Replanifier avec le même technician"
    ASSIGN_OTHER = "assign_other", "Assigner à un autre technician"
    ESCALATE = "escalate", "Escalader vers un superviseur"
    CANCEL_ORDER = "cancel", "Annuler la commande"
    PENDING_REVIEW = "pending", "En attente de révision"
```

### 2.2 Interface de Gestion des Rejets
**Nouvelle page**: `/site-survey/rejections/`

**Fonctionnalités**:
- Liste des surveys rejetés avec actions rapides
- Boutons d'action: Replanifier, Réassigner, Escalader
- Historique des rejets par technician
- Métriques de qualité

## 📊 Phase 3: Métriques et Suivi

### 3.1 KPIs à Implémenter
```python
# Dashboard métriques
class SurveyMetrics:
    rejection_rate_by_technician = models.FloatField()
    avg_resolution_time = models.DurationField()
    customer_satisfaction = models.FloatField()
    rework_frequency = models.IntegerField()
```

### 3.2 Rapports Automatiques
- **Rapport hebdomadaire**: Surveys rejetés et actions prises
- **Alerte qualité**: Si taux de rejet > 15% pour un technician
- **Escalation automatique**: Survey non traité après 48h

## 🛠️ Implémentation Technique

### Étape 1: Notifications (Priorité 1) ⭐
```python
# site_survey/notifications.py
def send_rejection_notification_to_technician(survey):
    # Email + SMS au technician

def send_rejection_notification_to_customer(survey):
    # Email au client

def send_rejection_alert_to_admin(survey):
    # Alerte admin pour suivi
```

### Étape 2: Workflow Actions (Priorité 2)
```python
# site_survey/models.py
class SurveyRejection(models.Model):
    survey = models.OneToOneField(SiteSurvey)
    action_taken = models.CharField(choices=SurveyRejectionAction.choices)
    assigned_to = models.ForeignKey(User, null=True)
    deadline = models.DateTimeField()
    notes = models.TextField()
```

### Étape 3: Interface de Gestion (Priorité 3)
- Dashboard rejets avec filtres et actions
- API pour actions rapides (replanifier/réassigner)
- Intégration avec calendrier pour replanification

## 📱 Interface Utilisateur

### Dashboard Admin - Section Rejets
```
🔴 Surveys Rejetés (3)
┌─────────────────────────────────────────────────┐
│ Survey #31 | ORD-T3EBNUHG5 | Technician        │
│ Raison: Installation not feasible                │
│ [Replanifier] [Réassigner] [Escalader]         │
└─────────────────────────────────────────────────┘
```

### Notifications Technician
```
📱 SMS: "Survey #31 rejeté. Vérifiez votre email pour les détails."
📧 Email: Détails complets + actions recommandées
```

## 🚀 Plan de Déploiement

1. **Week 1**: Implémentation notifications basiques
2. **Week 2**: Workflow de replanification
3. **Week 3**: Interface de gestion des rejets
4. **Week 4**: Métriques et rapports

## 💡 Bénéfices Attendus

- **Réduction du temps de résolution** de 72h à 24h
- **Amélioration de la satisfaction client** par transparence
- **Meilleur suivi qualité** des technicians
- **Processus standardisé** pour gérer les rejets
- **Visibilité complète** sur les problèmes de terrain
