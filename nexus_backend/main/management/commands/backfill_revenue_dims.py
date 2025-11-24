from __future__ import annotations

from collections import Counter
from typing import Iterable, Optional

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils.dateparse import parse_date

from main.models import AccountEntry
from main.services.posting import resolve_region_from_context, resolve_sales_agent

ENTRY_TYPES = ["invoice", "payment", "credit_note", "adjustment", "tax"]


class Command(BaseCommand):
    help = "Backfill region and sales agent snapshots on AccountEntry rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Run without persisting (default).",
        )
        parser.add_argument(
            "--apply",
            dest="dry_run",
            action="store_false",
            help="Persist changes (disables dry-run).",
        )
        parser.set_defaults(dry_run=True)

        parser.add_argument(
            "--since",
            type=str,
            help="Filter entries created on/after YYYY-MM-DD.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            help="Only process the first N entries (after filters).",
        )
        parser.add_argument(
            "--only-type",
            choices=ENTRY_TYPES,
            help="Restrict to a single entry_type.",
        )
        parser.add_argument(
            "--verbose",
            action="store_true",
            help="Print per-entry diagnostics (can be noisy).",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        since: Optional[str] = options.get("since")
        limit: Optional[int] = options.get("limit")
        only_type: Optional[str] = options.get("only_type")
        verbose: bool = options.get("verbose", False)

        qs = AccountEntry.objects.filter(
            Q(region_snapshot__isnull=True) | Q(sales_agent_snapshot__isnull=True)
        ).select_related(
            "order",
            "order__installation_activity",
            "order__kit_inventory__current_location__region",
            "order__sales_agent",
            "order__region",
            "subscription",
            "subscription__order",
            "subscription__sales_agent",
            "subscription__region",
        )

        if since:
            since_date = parse_date(since)
            if since_date is None:
                raise CommandError(f"Invalid --since value: {since!r}")
            qs = qs.filter(created_at__date__gte=since_date)

        if only_type:
            qs = qs.filter(entry_type=only_type)

        qs = qs.order_by("id")

        if limit:
            qs = qs[:limit]

        total = qs.count()
        if total == 0:
            self.stdout.write(
                self.style.WARNING("No AccountEntry rows require backfill.")
            )
            return

        self.stdout.write(
            f"Scanning {total} AccountEntry rows "
            f"({'dry-run' if dry_run else 'apply'})..."
        )

        stats = Counter()
        region_outcomes = Counter()
        agent_outcomes = Counter()
        applied_ids: list[int] = []

        for entry in self._iter_queryset(qs):
            stats["scanned"] += 1
            region_assigned = False
            agent_assigned = False
            detail_bits: list[str] = []

            region = entry.region_snapshot
            region_tag = None

            if entry.region_snapshot_id is None:
                region, region_tag = resolve_region_from_context(
                    order=entry.order, subscription=entry.subscription
                )
                if region:
                    region_assigned = True
                    entry.region_snapshot = region
                    region_outcomes["assigned"] += 1
                    if region_tag:
                        detail_bits.append(region_tag)
                        if region_tag == "auto_ambiguous":
                            region_outcomes["ambiguous"] += 1
                    if verbose:
                        self.stdout.write(
                            f" - Entry #{entry.id}: region <= {region} ({region_tag})"
                        )
                else:
                    region_outcomes[region_tag or "unresolved"] += 1
                    if verbose:
                        self.stdout.write(
                            f" - Entry #{entry.id}: no region ({region_tag})"
                        )

            agent_source_tag = None
            if entry.sales_agent_snapshot_id is None:
                agent, agent_source_tag = resolve_sales_agent(
                    entry.order, entry.subscription, region or entry.region_snapshot
                )
                if agent:
                    agent_assigned = True
                    entry.sales_agent_snapshot = agent
                    agent_outcomes["assigned"] += 1
                    if agent_source_tag:
                        detail_bits.append(agent_source_tag)
                    if verbose:
                        self.stdout.write(
                            f" - Entry #{entry.id}: sales_agent <= {agent} ({agent_source_tag})"
                        )
                else:
                    agent_outcomes[agent_source_tag or "unresolved"] += 1
                    if verbose:
                        self.stdout.write(
                            f" - Entry #{entry.id}: no sales agent ({agent_source_tag})"
                        )

            if not region_assigned and not agent_assigned:
                continue

            stats["updated"] += 1
            if region_assigned:
                stats["region_assigned"] += 1
            if agent_assigned:
                stats["agent_assigned"] += 1

            snapshot_source = "backfill"
            if detail_bits:
                # Ensure total length fits within 32 chars
                suffix = ":".join(detail_bits)
                candidate = f"backfill:{suffix}"
                snapshot_source = candidate[:32] if len(candidate) > 32 else candidate
            entry.snapshot_source = snapshot_source

            if not dry_run:
                update_fields = ["snapshot_source"]
                if region_assigned:
                    update_fields.append("region_snapshot")
                if agent_assigned:
                    update_fields.append("sales_agent_snapshot")
                entry.save(update_fields=update_fields)
                applied_ids.append(entry.id)

        self._render_summary(
            stats, region_outcomes, agent_outcomes, applied_ids, dry_run
        )

    def _iter_queryset(self, qs) -> Iterable[AccountEntry]:
        for entry in qs.iterator(chunk_size=200):
            yield entry

    def _render_summary(
        self,
        stats: Counter,
        region_outcomes: Counter,
        agent_outcomes: Counter,
        applied_ids: list[int],
        dry_run: bool,
    ) -> None:
        if stats["scanned"] == 0:
            self.stdout.write(self.style.WARNING("Nothing scanned."))
            return

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Backfill summary"))
        self.stdout.write(f"  scanned:          {stats['scanned']}")
        self.stdout.write(f"  updated:          {stats['updated']}")
        self.stdout.write(f"    region filled:  {stats['region_assigned']}")
        self.stdout.write(f"    agent filled:   {stats['agent_assigned']}")

        if region_outcomes:
            self.stdout.write("  region outcomes:")
            for key, value in region_outcomes.most_common():
                self.stdout.write(f"    - {key}: {value}")

        if agent_outcomes:
            self.stdout.write("  agent outcomes:")
            for key, value in agent_outcomes.most_common():
                self.stdout.write(f"    - {key}: {value}")

        if not dry_run and applied_ids:
            self.stdout.write(
                f"  persisted entries: {len(applied_ids)} "
                f"(min id={min(applied_ids)}, max id={max(applied_ids)})"
            )
        elif dry_run and stats["updated"]:
            self.stdout.write("  NOTE: run with --apply to persist these changes.")
