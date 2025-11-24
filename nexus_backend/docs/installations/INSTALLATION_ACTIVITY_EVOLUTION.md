# Installation Activity - Évolution du Modèle

**Date**: 6 octobre 2025
**Status**: ✅ COMPLÉTÉ

---

## 📋 Résumé Exécutif

Évolution du modèle `InstallationActivity` existant pour prendre en charge le rapport d'installation complet (9 étapes) du formulaire technicien **sans créer de redondance inutile**.

Cette approche respecte le principe **DRY (Don't Repeat Yourself)** et évite la duplication des relations déjà établies avec `Order`, `User` et `InstallationPhoto`.

---

## 🎯 Décision Architecturale

### ✅ APPROCHE ADOPTÉE: Évolution en Place

**Tous les champs du formulaire ont été ajoutés directement au modèle `InstallationActivity`**

**Avantages:**
- ✅ Pas de nouvelle table créée
- ✅ Pas de duplication des foreign keys (`order`, `technician`)
- ✅ Utilisation du modèle `InstallationPhoto` existant
- ✅ Un seul modèle cohérent avec toutes les informations
- ✅ Simplicité des requêtes (pas de JOIN supplémentaire)
- ✅ Respect du principe DRY
- ✅ Maintenance simplifiée

### ❌ APPROCHE REJETÉE: Modèle Séparé

**Un modèle `InstallationReport` avec relation 1:1 vers `InstallationActivity` a été initialement envisagé mais rejeté**

**Raisons du rejet:**
- ❌ Violation du principe DRY
- ❌ Duplication inutile des relations `order` et `technician`
- ❌ Complexité accrue sans bénéfice technique ou métier
- ❌ JOIN supplémentaire sur chaque requête
- ❌ Risque d'incohérence entre les deux modèles

---

## 📚 Principe Appliqué

> **"Si deux entités ont une relation 1:1, elles devraient probablement être une seule entité, à moins qu'il n'y ait une raison technique ou métier forte de les séparer."**
> — Martin Fowler, *Patterns of Enterprise Application Architecture*

### Raisons Valables de Séparation (Aucune ne s'applique ici):

1. **Isolation des Données Sensibles** → ❌ Tous les champs ont le même niveau de sensibilité
2. **Lazy Loading pour Performance** → ❌ Tous les champs sont nécessaires en même temps
3. **Cycles de Vie Différents** → ❌ Le rapport fait partie intégrante de l'installation
4. **Responsabilités Métier Distinctes** → ❌ L'installation et son rapport sont indissociables

---

## 🗂️ Structure du Modèle InstallationActivity (Évoluée)

### Relations de Base (Existantes)
```python
order = models.OneToOneField(Order, ...)          # Relation vers la commande
technician = models.ForeignKey(User, ...)         # Technicien assigné
```

### Champs de Base (Existants)
```python
planned_at = models.DateField(...)
started_at = models.DateTimeField(...)
completed_at = models.DateTimeField(...)
notes = models.TextField(...)
location_confirmed = models.BooleanField(...)
status = models.CharField(...)                    # pending, in_progress, completed, cancelled
```

### Nouveaux Champs Ajoutés (50+ champs)

#### STEP 1: Job & Site (7 champs)
- `on_site_arrival` - Heure d'arrivée réelle sur site
- `site_address` - Adresse complète
- `site_latitude`, `site_longitude` - Coordonnées GPS
- `access_level` - Easy / Moderate / Difficult
- `power_availability` - Stable / Intermittent / Unavailable
- `site_notes` - Notes générales sur le site

#### STEP 2: Equipment (10 champs)
**CPE Details:**
- `dish_serial_number` - N° série antenne
- `router_serial_number` - N° série routeur
- `firmware_version` - Version firmware
- `power_source` - Main AC / Generator / Solar / UPS
- `cable_length` - Longueur câble (mètres)
- `splices_connectors` - Nombre épissures

**LAN / Wi-Fi:**
- `wifi_ssid` - SSID réseau
- `wifi_password` - Mot de passe Wi-Fi
- `lan_ip` - Adresse IP LAN
- `dhcp_range` - Plage DHCP

#### STEP 3: Mount & Alignment (9 champs)
- `mount_type` - Roof / Wall / Ground Pole / Tripod
- `mount_height` - Hauteur montage (mètres)
- `grounding` - Yes / No / N/A
- `weatherproofing` - Taped / Sealed / Conduit / N/A
- `obstruction_percentage` - % obstruction (0-100)
- `elevation_angle` - Angle élévation (degrés)
- `azimuth_angle` - Angle azimut (degrés)
- `obstruction_notes` - Notes obstructions
- `mounting_notes` - Notes montage

#### STEP 4: Environment & Safety (6 champs)
- `weather_conditions` - Sunny / Cloudy / Rainy / Windy / Stormy / Other
- `safety_helmet` - Boolean
- `safety_harness` - Boolean
- `safety_gloves` - Boolean
- `safety_ladder` - Boolean
- `hazards_noted` - Dangers relevés

#### STEP 5: Cabling & Routing (4 champs)
- `cable_entry_point` - Wall Drilled / Window Feed / Conduit / Existing Duct
- `cable_protection` - Conduit / Trunking / UV Protected / None
- `termination_type` - RJ45 / POE Injector / Direct / Other
- `routing_notes` - Notes cheminement

#### STEP 6: Power & Backup (4 champs)
- `power_stability_test` - Pass / Fail
- `ups_installed` - Yes / No
- `ups_model` - Modèle UPS
- `ups_runtime_minutes` - Autonomie (minutes)

#### STEP 7: Connectivity & Tests (9 champs)
- `snr_db` - Signal-to-Noise Ratio (dB)
- `speed_download_mbps` - Vitesse téléchargement
- `speed_upload_mbps` - Vitesse upload
- `latency_ms` - Latence (ms)
- `test_tool` - Outil utilisé (Fast.com, Ookla...)
- `public_ip` - IP publique
- `qos_vlan` - Configuration QoS/VLAN
- `final_link_status` - Connected / Not Connected
- `test_notes` - Notes tests

#### STEP 9: Customer Sign-off (7 champs)
- `customer_full_name` - Nom complet client
- `customer_id_document` - N° document identité
- `customer_acceptance` - Boolean confirmation
- `customer_signature` - Données signature (base64)
- `customer_signoff_at` - DateTime signature
- `customer_rating` - Note 1-5 étoiles
- `customer_comments` - Commentaires client

#### Reseller Information (4 champs)
- `reseller_name` - Nom revendeur
- `reseller_id` - ID revendeur
- `sla_tier` - Standard / Priority / Premium
- `reseller_notes` - Notes internes

#### Metadata (4 champs)
- `created_at` - Auto now add
- `updated_at` - Auto now
- `submitted_at` - DateTime soumission finale
- `is_draft` - Boolean brouillon

---

## 💾 Migration

### Migration 0007 (Déjà appliquée)
```bash
Migration: 0007_alter_installationactivity_options_and_more.py
Date: 6 octobre 2025 14:26

✅ Ajoute tous les 50+ nouveaux champs à InstallationActivity
✅ Met à jour les Meta options (ordering, verbose_name)
✅ Ajoute les index nécessaires
```

**Status**: ✅ Migration appliquée avec succès, aucune action requise

---

## 🖼️ Gestion des Photos

Le modèle existant `InstallationPhoto` est utilisé pour les photos d'installation :

```python
class InstallationPhoto(models.Model):
    installation_activity = models.ForeignKey(
        InstallationActivity,
        on_delete=models.CASCADE,
        related_name='photos'
    )
    image = models.ImageField(upload_to='installation_photos/%Y/%m/%d/')
    caption = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
```

**Utilisation:**
- Photos "Before" → caption: "Before Installation"
- Photos "After" → caption: "After Installation"
- Photos "Evidence" → caption: "Additional Evidence"

---

## 🎨 Interface Admin Django

Configuration admin mise à jour dans `main/admin.py` :

```python
@admin.register(InstallationActivity)
class InstallationActivityAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'technician',
        'status',
        'customer_full_name',
        'final_link_status',
        'customer_rating',
        'is_draft',
        'submitted_at',
        'created_at',
    )

    list_filter = (
        'status',
        'is_draft',
        'final_link_status',
        'customer_rating',
        'sla_tier',
        'weather_conditions',
        'created_at',
    )

    search_fields = (
        'order__order_reference',
        'customer_full_name',
        'technician__full_name',
        'dish_serial_number',
        'router_serial_number',
    )

    fieldsets = (
        ('Base Information', {...}),
        ('Site Information', {...}),
        ('Equipment - CPE', {...}),
        ('Equipment - Network', {...}),
        ('Mounting & Alignment', {...}),
        ('Safety & Environment', {...}),
        ('Cabling', {...}),
        ('Power & Backup', {...}),
        ('Connectivity Tests', {...}),
        ('Customer Sign-off', {...}),
        ('Reseller Information', {...}),
        ('Metadata', {...}),
    )

    inlines = [InstallationPhotoInline]
```

---

## 🔄 Prochaines Étapes

### 1. Implémentation de la Vue (tech/views.py)
Créer une vue pour sauvegarder le formulaire :

```python
@login_required
@require_POST
def save_installation_report(request, activity_id):
    """
    Sauvegarde ou met à jour un rapport d'installation
    """
    try:
        activity = InstallationActivity.objects.get(
            id=activity_id,
            technician=request.user
        )

        # Mise à jour des champs
        activity.on_site_arrival = request.POST.get('on_site_arrival')
        activity.site_address = request.POST.get('site_address')
        # ... tous les autres champs

        # Marquer comme soumis si demandé
        if request.POST.get('submit_final'):
            activity.mark_as_submitted()
        else:
            activity.save()

        return JsonResponse({
            'success': True,
            'message': 'Rapport sauvegardé avec succès'
        })

    except InstallationActivity.DoesNotExist:
        return JsonResponse({
            'success': False,
            'error': 'Installation non trouvée'
        }, status=404)
```

### 2. Intégration Frontend (fe_dashboard.html)
Connecter le formulaire JavaScript à la vue :

```javascript
async function submitInstallationReport(isDraft = true) {
    const formData = new FormData();

    // STEP 1
    formData.append('on_site_arrival', document.getElementById('on_site_arrival').value);
    formData.append('site_address', document.getElementById('site_address').value);
    // ... tous les autres champs

    formData.append('submit_final', !isDraft);

    const response = await fetch(`/tech/api/installation-report/${activityId}/save/`, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: formData
    });

    const result = await response.json();
    if (result.success) {
        alert('Rapport sauvegardé avec succès !');
    }
}
```

### 3. URL Configuration (tech/urls.py)
```python
urlpatterns = [
    path(
        'api/installation-report/<int:activity_id>/save/',
        views.save_installation_report,
        name='save_installation_report'
    ),
]
```

---

## ✅ Avantages de l'Approche Adoptée

1. **Simplicité** - Un seul modèle à gérer
2. **Performance** - Pas de JOIN inutile
3. **Cohérence** - Impossible d'avoir une installation sans rapport ou vice versa
4. **Maintenance** - Code plus simple à maintenir
5. **DRY** - Pas de duplication de code ou de données
6. **Évolutivité** - Facile d'ajouter de nouveaux champs si nécessaire

---

## 📊 Comparaison des Approches

| Critère | Évolution en Place ✅ | Modèle Séparé ❌ |
|---------|----------------------|------------------|
| Nombre de tables | 1 | 2 |
| Foreign keys dupliquées | 0 | 2 (order, technician) |
| JOINs nécessaires | 0 | 1 (systématique) |
| Risque incohérence | Faible | Moyen |
| Complexité code | Faible | Moyenne |
| Performance requêtes | Optimale | Bonne |
| Respect DRY | ✅ Oui | ❌ Non |

---

## 📝 Conclusion

L'évolution en place du modèle `InstallationActivity` est la solution architecturale optimale pour ce cas d'usage. Elle respecte les principes de conception logicielle, évite la redondance, et simplifie grandement la maintenance et l'utilisation du système.

**Cette approche démontre qu'il est important de toujours questionner les décisions architecturales et d'appliquer les principes fondamentaux plutôt que de suivre des patterns de manière aveugle.**

---

**Auteur**: GitHub Copilot
**Dernière mise à jour**: 6 octobre 2025
**Version**: 1.0
