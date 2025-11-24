from django.core.management.base import BaseCommand
from django.db import transaction

from main.models import AccountEntry


class Command(BaseCommand):
    help = (
        "Set external_ref on AccountEntry rows for additional billing invoices/payments "
        "so revenue reporting groups them correctly. Idempotent."
    )

    def handle(self, *args, **options):
        updated = 0

        # Invoices: description like "Additional equipment invoice <REF>"
        invoice_qs = AccountEntry.objects.filter(
            entry_type="invoice",
            external_ref__isnull=True,
            description__istartswith="Additional equipment invoice ",
        )
        with transaction.atomic():
            for e in invoice_qs.select_related("order"):
                try:
                    ref = (
                        (e.description or "")
                        .split("Additional equipment invoice ", 1)[1]
                        .strip()
                    )
                except Exception:
                    continue
                if not ref:
                    continue
                ext = f"additional_billing:{ref}"
                if e.external_ref != ext:
                    e.external_ref = ext
                    e.save(update_fields=["external_ref"])
                    updated += 1

        # Payments: description like "Additional billing payment <REF>"
        payment_qs = AccountEntry.objects.filter(
            entry_type="payment",
            external_ref__isnull=True,
            description__istartswith="Additional billing payment ",
        )
        with transaction.atomic():
            for e in payment_qs.select_related("order"):
                try:
                    ref = (
                        (e.description or "")
                        .split("Additional billing payment ", 1)[1]
                        .strip()
                    )
                except Exception:
                    continue
                if not ref:
                    continue
                ext = f"additional_billing:{ref}"
                if e.external_ref != ext:
                    e.external_ref = ext
                    e.save(update_fields=["external_ref"])
                    updated += 1

        self.stdout.write(self.style.SUCCESS(f"Updated {updated} ledger rows."))
