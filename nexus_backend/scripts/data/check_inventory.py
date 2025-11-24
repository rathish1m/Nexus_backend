#!/usr/bin/env python
import os

import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "nexus_backend.settings")
django.setup()

from main.models import StarlinkKit, StarlinkKitInventory

print("=== Kits disponibles ===")
for kit in StarlinkKit.objects.all():
    print(f"ID: {kit.id}, Name: {kit.name}, Model: {kit.model}")

print("\n=== Inventaire disponible ===")
for inv in StarlinkKitInventory.objects.filter(is_assigned=False):
    print(
        f"ID: {inv.id}, Kit: {inv.kit.name}, Serial: {inv.serial_number}, Assigned: {inv.is_assigned}"
    )

print("\n=== Statistiques ===")
total_kits = StarlinkKit.objects.count()
total_inventory = StarlinkKitInventory.objects.count()
available_inventory = StarlinkKitInventory.objects.filter(is_assigned=False).count()
print(f"Total kits: {total_kits}")
print(f"Total inventory items: {total_inventory}")
print(f"Available inventory items: {available_inventory}")

# Si pas d'inventaire disponible, créer des éléments d'inventaire
if available_inventory == 0:
    print("\n=== Création d'inventaire de test ===")
    for kit in StarlinkKit.objects.all():
        # Créer 5 éléments d'inventaire pour chaque kit
        for i in range(1, 6):
            serial = f"{kit.model.upper()}-{i:03d}"
            inventory_item = StarlinkKitInventory.objects.create(
                kit=kit, serial_number=serial, is_assigned=False
            )
            print(f"Créé: {inventory_item.kit.name} - {inventory_item.serial_number}")

    print("\n=== Nouvel inventaire après création ===")
    available_inventory = StarlinkKitInventory.objects.filter(is_assigned=False).count()
    print(f"Available inventory items: {available_inventory}")
