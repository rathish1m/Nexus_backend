import random

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

try:
    from main.models import UserRole
except Exception:
    UserRole = None


def generate_random_phone():
    return "+2438" + "".join(str(random.randint(0, 9)) for _ in range(8))


class Command(BaseCommand):
    help = "Create test users for each available role (dry-run by default). Use --execute to actually create."

    def add_arguments(self, parser):
        parser.add_argument(
            "--per-role",
            action="store_true",
            dest="per_role",
            help="Create one test user per role.",
        )
        parser.add_argument(
            "--all-single",
            action="store_true",
            dest="all_single",
            help="Create a single user containing all roles.",
        )
        parser.add_argument(
            "--password",
            dest="password",
            default="Test1234!",
            help="Password to set for created users.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            dest="execute",
            help="Actually create users instead of dry-run.",
        )
        parser.add_argument(
            "--phone",
            dest="phone",
            default="",
            help="Phone number to assign (E.164). Default leaves phone blank.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        per_role = options.get("per_role")
        all_single = options.get("all_single")
        password = options.get("password")
        execute = options.get("execute")
        phone = options.get("phone") or None

        # Determine available roles
        if UserRole is not None:
            roles = [r.value for r in UserRole]
        else:
            roles = [
                "dispatcher",
                "technician",
                "sales",
                "support",
                "compliance",
                "admin",
                "manager",
                "finance",
            ]

        planned = []

        if not per_role and not all_single:
            per_role = True

        if per_role:
            for r in roles:
                email = f"test_{r}@example.local"
                planned.append(
                    {
                        "email": email,
                        "full_name": f"Test {r.capitalize()}",
                        "roles": [r],
                    }
                )

        if all_single:
            planned.append(
                {
                    "email": "test_all_roles@example.local",
                    "full_name": "Test All Roles",
                    "roles": roles,
                }
            )

        if not planned:
            self.stdout.write(self.style.WARNING("No users planned."))
            return

        # Dry run printout
        self.stdout.write(
            self.style.MIGRATE_HEADING("Planned user creations (dry-run):")
        )
        for p in planned:
            exists = User.objects.filter(email=p["email"]).exists()
            self.stdout.write(
                f" - {p['email']} (roles: {p['roles']}) {'[exists: SKIP]' if exists else ''}"
            )

        if not execute:
            self.stdout.write(
                self.style.SUCCESS(
                    "Dry-run complete. Re-run with --execute to actually create users."
                )
            )
            return

        # Execute creation
        created = []
        skipped = []
        with transaction.atomic():
            for p in planned:
                if User.objects.filter(email=p["email"]).exists():
                    skipped.append(p["email"])
                    continue
                user = User.objects.create_user(
                    username=p["email"],
                    email=p["email"],
                    full_name=p.get("full_name") or p["email"],
                    password=password,
                    is_staff=True,
                    roles=p.get("roles", []),
                )
                user.phone = phone or generate_random_phone()
                user.save(update_fields=["phone"])
                created.append(p["email"])

        self.stdout.write(self.style.SUCCESS(f"Created: {created}"))
        if skipped:
            self.stdout.write(
                self.style.WARNING(f"Skipped (already existed): {skipped}")
            )


# in case of creating test users skipping the old already created users, keep the old code commented out below

#         with transaction.atomic():
# for p in planned:
#     existing_user = User.objects.filter(email=p["email"]).first()
#     if existing_user:
#         existing_user.phone = phone or generate_random_phone()
#         existing_user.save(update_fields=["phone"])
#         skipped.append(p["email"])
#         continue

#     user = User.objects.create_user(
#         username=p["email"],
#         email=p["email"],
#         full_name=p.get("full_name") or p["email"],
#         password=password,
#         is_staff=True,
#         roles=p.get("roles", []),
#     )
#     user.phone = phone or generate_random_phone()
#     user.save(update_fields=["phone"])
#     created.append(p["email"])
