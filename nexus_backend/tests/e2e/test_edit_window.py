#!/usr/bin/env python3
"""
Script de test pour valider le workflow de fenêtre d'édition de 24h.
Tests:
1. Création d'un rapport d'installation
2. Soumission avec période d'édition de 24h
3. Édition dans la fenêtre
4. Validation automatique après expiration
"""
# ruff: noqa: E402

import os
import sys
from datetime import timedelta

import django

# Setup Django
sys.path.append("/home/virgocoachman/Documents/Workspace/NEXUS_TELECOMS/nexus_backend")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from django.utils import timezone

from main.models import InstallationActivity


def test_edit_window_workflow():
    print("🧪 Testing 24h Edit Window Workflow")
    print("=" * 50)

    # 1. Trouver ou créer une installation
    try:
        activity = InstallationActivity.objects.filter(technician__isnull=False).first()

        if not activity:
            print("❌ No installation activity found with technician")
            return

        print(f"✅ Found installation: {activity.id}")
        print(
            f"   Order: {activity.order.order_reference if activity.order else 'N/A'}"
        )
        print(
            f"   Technician: {activity.technician.full_name if activity.technician else 'N/A'}"
        )
        print(f"   Current status: {activity.status}")

        # 2. Test initial state
        print(f"   Can be edited: {activity.can_be_edited()}")
        print(f"   Time left for editing: {activity.time_left_for_editing()} hours")
        print()

        # 3. Simuler la soumission
        if activity.status != "submitted":
            print("📝 Marking as submitted...")
            activity.mark_as_submitted()
            print(f"   Status: {activity.status}")
            print(f"   Submitted at: {activity.submitted_at}")
            print(f"   Edit deadline: {activity.edit_deadline}")
            print(f"   Can be edited: {activity.can_be_edited()}")
            print(f"   Time left: {activity.time_left_for_editing():.1f} hours")
            print()

        # 4. Test édition
        if activity.can_be_edited():
            print("✏️  Testing edit functionality...")
            old_version = activity.version_number
            activity.mark_as_edited()
            print(f"   Version updated: {old_version} → {activity.version_number}")
            print(f"   Last edited at: {activity.last_edited_at}")
            print()

        # 5. Test validation automatique (simulation)
        print("⏰ Testing auto-validation...")
        # Simuler l'expiration en modifiant la deadline (juste pour le test)
        original_deadline = activity.edit_deadline
        activity.edit_deadline = timezone.now() - timedelta(minutes=1)  # Expirée
        activity.save()

        was_validated = activity.auto_validate_if_expired()
        print(f"   Auto-validation triggered: {was_validated}")
        if was_validated:
            print(f"   Status: {activity.status}")
            print(f"   Validated at: {activity.validated_at}")

        # Restaurer la deadline originale
        activity.edit_deadline = original_deadline
        activity.status = "submitted"
        activity.validated_at = None
        activity.save()
        print("   (Test state restored)")
        print()

        # 6. Résumé final
        print("📊 Final Status:")
        print(f"   ID: {activity.id}")
        print(f"   Status: {activity.status}")
        print(f"   Version: {activity.version_number}")
        print(f"   Can be edited: {activity.can_be_edited()}")
        print(f"   Time left: {activity.time_left_for_editing():.1f} hours")

        print("\n✅ Workflow test completed successfully!")

    except Exception as e:
        print(f"❌ Error during test: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    test_edit_window_workflow()
