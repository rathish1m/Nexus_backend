# Installation Report - Guide d'Intégration Frontend

**Date**: 6 octobre 2025
**Status**: Backend complété ✅ | Frontend en attente ⏳

---

## 🎯 Vue d'Ensemble

La vue backend est maintenant prête pour sauvegarder le rapport d'installation complet. Ce guide explique comment intégrer le formulaire frontend (9 étapes) avec l'API backend.

---

## 🔌 API Endpoint

### URL
```
POST /tech/api/installation-report/<activity_id>/save/
```

### Authentification
- **Requis**: Utilisateur connecté avec rôle technicien
- **Header**: Cookie de session Django + CSRF Token

### Paramètres URL
- `activity_id` (int) - ID de l'InstallationActivity à mettre à jour

---

## 📤 Données à Envoyer (POST)

### STEP 1: Job & Site (7 champs)
```javascript
{
  "on_site_arrival": "2025-10-06T14:30",      // datetime-local
  "site_address": "123 Rue Example, Yaoundé",  // text
  "site_latitude": "3.8480",                   // decimal
  "site_longitude": "11.5021",                 // decimal
  "access_level": "moderate",                  // easy|moderate|difficult
  "power_availability": "stable",              // stable|intermittent|unavailable
  "site_notes": "Accès via portail principal"  // textarea
}
```

### STEP 2: Equipment - CPE Details (6 champs)
```javascript
{
  "dish_serial_number": "DISH-2024-001234",
  "router_serial_number": "RTR-2024-005678",
  "firmware_version": "v2.3.1",
  "power_source": "main_ac",                   // main_ac|generator|solar|ups
  "cable_length": "45.5",                      // decimal (mètres)
  "splices_connectors": "3"                    // integer
}
```

### STEP 2: Equipment - LAN / Wi-Fi (4 champs)
```javascript
{
  "wifi_ssid": "NEXUS_Customer_WiFi",
  "wifi_password": "SecurePass123!",
  "lan_ip": "192.168.1.1",                     // IPv4
  "dhcp_range": ".100 - .200"
}
```

### STEP 3: Mount & Alignment (9 champs)
```javascript
{
  "mount_type": "roof",                        // roof|wall|ground_pole|tripod
  "mount_height": "5.2",                       // decimal (mètres)
  "grounding": "yes",                          // yes|no|na
  "weatherproofing": "sealed",                 // taped|sealed|conduit|na
  "obstruction_percentage": "5",               // integer (0-100)
  "elevation_angle": "45.3",                   // decimal (degrés)
  "azimuth_angle": "180.5",                    // decimal (degrés)
  "obstruction_notes": "Un arbre à 20m",
  "mounting_notes": "Ancrage renforcé avec 4 boulons"
}
```

### STEP 4: Environment & Safety (6 champs)
```javascript
{
  "weather_conditions": "sunny",               // sunny|cloudy|rainy|windy|stormy|other
  "safety_helmet": "on",                       // checkbox (on/off)
  "safety_harness": "on",                      // checkbox (on/off)
  "safety_gloves": "on",                       // checkbox (on/off)
  "safety_ladder": "on",                       // checkbox (on/off)
  "hazards_noted": "Toit glissant, ligne électrique proche"
}
```

### STEP 5: Cabling & Routing (4 champs)
```javascript
{
  "cable_entry_point": "wall_drilled",         // wall_drilled|window_feed|conduit|existing_duct
  "cable_protection": "conduit",               // conduit|trunking|uv_protected|none
  "termination_type": "rj45",                  // rj45|poe_injector|direct|other
  "routing_notes": "Câble protégé dans conduit PVC"
}
```

### STEP 6: Power & Backup (4 champs)
```javascript
{
  "power_stability_test": "pass",              // pass|fail
  "ups_installed": "yes",                      // yes|no
  "ups_model": "APC BX950U-FR",
  "ups_runtime_minutes": "60"                  // integer
}
```

### STEP 7: Connectivity & Tests (9 champs)
```javascript
{
  "snr_db": "12.5",                            // decimal
  "speed_download_mbps": "150.25",             // decimal
  "speed_upload_mbps": "25.50",                // decimal
  "latency_ms": "35",                          // integer
  "test_tool": "Fast.com",
  "public_ip": "41.202.207.123",               // IPv4
  "qos_vlan": "VLAN 20, QoS Priority 5",
  "final_link_status": "connected",            // connected|not_connected
  "test_notes": "Tests effectués à 15h30, conditions optimales"
}
```

### STEP 9: Customer Sign-off (7 champs)
```javascript
{
  "customer_full_name": "Jean Dupont",
  "customer_id_document": "CNI123456789",
  "customer_acceptance": "on",                 // checkbox (on/off)
  "customer_signature": "data:image/png;base64,iVBORw0KGg...", // base64 canvas
  "customer_signoff_at": "2025-10-06T16:45",   // datetime-local
  "customer_rating": "5",                      // integer (1-5)
  "customer_comments": "Installation parfaite, technicien professionnel"
}
```

### Reseller Information (4 champs)
```javascript
{
  "reseller_name": "TechCom Partners",
  "reseller_id": "RSL-2024-042",
  "sla_tier": "priority_24h",                  // standard_48h|priority_24h|premium_same_day
  "reseller_notes": "Client VIP, suivi prioritaire"
}
```

### Contrôle de Soumission
```javascript
{
  "submit_final": "true"  // "true" = soumission finale | "false" = brouillon
}
```

---

## 📥 Réponse API

### Succès (200 OK)
```json
{
  "success": true,
  "message": "Rapport d'installation soumis avec succès !",
  "is_draft": false,
  "submitted_at": "2025-10-06T16:45:23.123456"
}
```

### Succès - Brouillon (200 OK)
```json
{
  "success": true,
  "message": "Brouillon sauvegardé avec succès !",
  "is_draft": true,
  "submitted_at": null
}
```

### Erreur - Installation non trouvée (404)
```json
{
  "success": false,
  "error": "Installation non trouvée ou vous n'avez pas accès à cette installation."
}
```

### Erreur - Serveur (500)
```json
{
  "success": false,
  "error": "Erreur lors de la sauvegarde: [détails de l'erreur]"
}
```

---

## 🎨 Exemple d'Implémentation Frontend

### 1. Fonction de Sauvegarde AJAX

```javascript
/**
 * Sauvegarde le rapport d'installation
 * @param {number} activityId - ID de l'installation
 * @param {boolean} submitFinal - true = soumission finale, false = brouillon
 */
async function saveInstallationReport(activityId, submitFinal = false) {
    const formData = new FormData();

    // STEP 1: Job & Site
    formData.append('on_site_arrival', document.getElementById('on_site_arrival').value);
    formData.append('site_address', document.getElementById('site_address').value);
    formData.append('site_latitude', document.getElementById('site_latitude').value);
    formData.append('site_longitude', document.getElementById('site_longitude').value);
    formData.append('access_level', document.getElementById('access_level').value);
    formData.append('power_availability', document.getElementById('power_availability').value);
    formData.append('site_notes', document.getElementById('site_notes').value);

    // STEP 2: Equipment - CPE
    formData.append('dish_serial_number', document.getElementById('dish_serial_number').value);
    formData.append('router_serial_number', document.getElementById('router_serial_number').value);
    formData.append('firmware_version', document.getElementById('firmware_version').value);
    formData.append('power_source', document.getElementById('power_source').value);
    formData.append('cable_length', document.getElementById('cable_length').value);
    formData.append('splices_connectors', document.getElementById('splices_connectors').value);

    // STEP 2: Equipment - LAN / Wi-Fi
    formData.append('wifi_ssid', document.getElementById('wifi_ssid').value);
    formData.append('wifi_password', document.getElementById('wifi_password').value);
    formData.append('lan_ip', document.getElementById('lan_ip').value);
    formData.append('dhcp_range', document.getElementById('dhcp_range').value);

    // STEP 3: Mount & Alignment
    formData.append('mount_type', document.getElementById('mount_type').value);
    formData.append('mount_height', document.getElementById('mount_height').value);
    formData.append('grounding', document.getElementById('grounding').value);
    formData.append('weatherproofing', document.getElementById('weatherproofing').value);
    formData.append('obstruction_percentage', document.getElementById('obstruction_percentage').value);
    formData.append('elevation_angle', document.getElementById('elevation_angle').value);
    formData.append('azimuth_angle', document.getElementById('azimuth_angle').value);
    formData.append('obstruction_notes', document.getElementById('obstruction_notes').value);
    formData.append('mounting_notes', document.getElementById('mounting_notes').value);

    // STEP 4: Environment & Safety
    formData.append('weather_conditions', document.getElementById('weather_conditions').value);
    formData.append('safety_helmet', document.getElementById('safety_helmet').checked ? 'on' : '');
    formData.append('safety_harness', document.getElementById('safety_harness').checked ? 'on' : '');
    formData.append('safety_gloves', document.getElementById('safety_gloves').checked ? 'on' : '');
    formData.append('safety_ladder', document.getElementById('safety_ladder').checked ? 'on' : '');
    formData.append('hazards_noted', document.getElementById('hazards_noted').value);

    // STEP 5: Cabling & Routing
    formData.append('cable_entry_point', document.getElementById('cable_entry_point').value);
    formData.append('cable_protection', document.getElementById('cable_protection').value);
    formData.append('termination_type', document.getElementById('termination_type').value);
    formData.append('routing_notes', document.getElementById('routing_notes').value);

    // STEP 6: Power & Backup
    formData.append('power_stability_test', document.getElementById('power_stability_test').value);
    formData.append('ups_installed', document.getElementById('ups_installed').value);
    formData.append('ups_model', document.getElementById('ups_model').value);
    formData.append('ups_runtime_minutes', document.getElementById('ups_runtime_minutes').value);

    // STEP 7: Connectivity & Tests
    formData.append('snr_db', document.getElementById('snr_db').value);
    formData.append('speed_download_mbps', document.getElementById('speed_download_mbps').value);
    formData.append('speed_upload_mbps', document.getElementById('speed_upload_mbps').value);
    formData.append('latency_ms', document.getElementById('latency_ms').value);
    formData.append('test_tool', document.getElementById('test_tool').value);
    formData.append('public_ip', document.getElementById('public_ip').value);
    formData.append('qos_vlan', document.getElementById('qos_vlan').value);
    formData.append('final_link_status', document.getElementById('final_link_status').value);
    formData.append('test_notes', document.getElementById('test_notes').value);

    // STEP 9: Customer Sign-off
    formData.append('customer_full_name', document.getElementById('customer_full_name').value);
    formData.append('customer_id_document', document.getElementById('customer_id_document').value);
    formData.append('customer_acceptance', document.getElementById('customer_acceptance').checked ? 'on' : '');
    formData.append('customer_signature', document.getElementById('customer_signature').value);
    formData.append('customer_signoff_at', document.getElementById('customer_signoff_at').value);
    formData.append('customer_rating', document.getElementById('customer_rating').value);
    formData.append('customer_comments', document.getElementById('customer_comments').value);

    // Reseller Information
    formData.append('reseller_name', document.getElementById('reseller_name').value);
    formData.append('reseller_id', document.getElementById('reseller_id').value);
    formData.append('sla_tier', document.getElementById('sla_tier').value);
    formData.append('reseller_notes', document.getElementById('reseller_notes').value);

    // Contrôle de soumission
    formData.append('submit_final', submitFinal ? 'true' : 'false');

    try {
        const response = await fetch(`/tech/api/installation-report/${activityId}/save/`, {
            method: 'POST',
            headers: {
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: formData
        });

        const result = await response.json();

        if (result.success) {
            // Succès
            showNotification('success', result.message);

            if (!result.is_draft) {
                // Rapport soumis, rediriger ou fermer le modal
                setTimeout(() => {
                    window.location.href = '/tech/fe/joblist/';
                }, 1500);
            }
        } else {
            // Erreur
            showNotification('error', result.error || 'Une erreur est survenue');
        }
    } catch (error) {
        console.error('Erreur:', error);
        showNotification('error', 'Erreur de connexion au serveur');
    }
}

/**
 * Helper pour récupérer le CSRF token
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Afficher une notification
 */
function showNotification(type, message) {
    // Implémentation selon votre système de notification
    alert(`[${type.toUpperCase()}] ${message}`);
}
```

### 2. Boutons de Sauvegarde dans le Formulaire

```html
<!-- Bouton Brouillon (n'importe quelle étape) -->
<button type="button"
        class="btn btn-secondary"
        onclick="saveInstallationReport(currentActivityId, false)">
    💾 Sauvegarder Brouillon
</button>

<!-- Bouton Soumission Finale (dernière étape) -->
<button type="button"
        class="btn btn-success"
        onclick="saveInstallationReport(currentActivityId, true)">
    ✅ Soumettre Rapport Final
</button>
```

---

## 🔒 Sécurité

### Validation Backend
- ✅ Vérification que le technicien est propriétaire de l'installation
- ✅ Protection CSRF requise
- ✅ Authentification obligatoire
- ✅ Gestion des erreurs avec messages appropriés

### Validation Frontend (Recommandé)
```javascript
function validateForm() {
    // Champs obligatoires pour soumission finale
    const required = [
        'customer_full_name',
        'customer_acceptance',
        'final_link_status'
    ];

    for (const field of required) {
        const element = document.getElementById(field);
        if (!element || !element.value) {
            alert(`Le champ ${field} est obligatoire pour soumettre le rapport final`);
            return false;
        }
    }

    return true;
}

// Utilisation
async function submitFinalReport() {
    if (validateForm()) {
        await saveInstallationReport(currentActivityId, true);
    }
}
```

---

## 📝 Checklist d'Intégration

### Backend ✅
- [x] Vue `save_installation_report` créée
- [x] Route configurée dans `tech/urls.py`
- [x] Tous les 50+ champs gérés
- [x] Brouillon vs soumission finale
- [x] Gestion des erreurs

### Frontend ⏳
- [ ] Implémenter fonction `saveInstallationReport()`
- [ ] Ajouter boutons de sauvegarde (brouillon + final)
- [ ] Implémenter `getCookie()` pour CSRF
- [ ] Ajouter validation côté client
- [ ] Tester toutes les étapes du formulaire
- [ ] Gérer les notifications de succès/erreur
- [ ] Tester signature canvas → base64

---

## 🧪 Tests Recommandés

1. **Sauvegarde brouillon** - Vérifier que les données sont sauvegardées partiellement
2. **Soumission finale** - Vérifier que `is_draft` devient `false` et `submitted_at` est renseigné
3. **Champs vides** - Vérifier que les champs optionnels vides sont gérés correctement
4. **Sécurité** - Tester qu'un technicien ne peut pas modifier le rapport d'un autre
5. **Signature** - Vérifier que le canvas signature est bien converti en base64

---

**Prochaine étape**: Intégrer le JavaScript dans `fe_dashboard.html` pour connecter le formulaire à l'API 🚀
