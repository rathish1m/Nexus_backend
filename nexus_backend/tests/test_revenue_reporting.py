from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from django.contrib.gis.geos import Polygon
from django.db import connection
from django.utils import timezone

from geo_regions.models import Region
from main.factories import OrderFactory, StaffUserFactory, UserFactory
from main.models import AccountEntry, BillingAccount, RegionSalesDefault
from main.services.posting import create_entry
from main.services.region_resolver import resolve_region_from_coords

pytestmark = pytest.mark.skipif(
    not hasattr(connection.ops, "geo_db_type"),
    reason="Spatial database backend is not available for tests.",
)


def make_square(x0: float, y0: float, size: float) -> Polygon:
    polygon = Polygon(
        (
            (x0, y0),
            (x0, y0 + size),
            (x0 + size, y0 + size),
            (x0 + size, y0),
            (x0, y0),
        )
    )
    polygon.srid = 4326
    return polygon


@pytest.mark.django_db
def test_resolve_region_from_coords_exact_match():
    region = Region.objects.create(name="Zone A", fence=make_square(0, 0, 1))
    resolved, tag = resolve_region_from_coords(0.5, 0.5)
    assert resolved == region
    assert tag == "auto"


@pytest.mark.django_db
def test_resolve_region_from_coords_prefers_smallest_polygon():
    outer = Region.objects.create(name="Outer Zone", fence=make_square(0, 0, 2))
    inner = Region.objects.create(name="Inner Zone", fence=make_square(0.25, 0.25, 0.5))

    resolved, tag = resolve_region_from_coords(0.5, 0.5)
    assert resolved == inner
    assert tag == "auto_ambiguous"
    assert resolved != outer


@pytest.mark.django_db
def test_create_entry_assigns_region_and_default_agent():
    region = Region.objects.create(name="Central", fence=make_square(-1, -1, 2))
    agent = StaffUserFactory()
    agent.roles = ["sales"]
    agent.save()

    RegionSalesDefault.objects.create(region=region, agent=agent, is_primary=True)

    customer = UserFactory()
    account, _ = BillingAccount.objects.get_or_create(user=customer)
    order = OrderFactory(user=customer, latitude=0.0, longitude=0.0)

    entry = create_entry(
        account=account,
        entry_type="invoice",
        amount_usd=Decimal("120.00"),
        order=order,
    )

    assert entry.region_snapshot == region
    assert entry.sales_agent_snapshot == agent
    assert entry.snapshot_source == "auto"


@pytest.mark.django_db
def test_revenue_summary_grouped_by_region():
    region = Region.objects.create(name="North", fence=make_square(-1, -1, 2))
    agent = StaffUserFactory()
    agent.roles = ["sales"]
    agent.save()

    customer = UserFactory()
    account, _ = BillingAccount.objects.get_or_create(user=customer)
    order = OrderFactory(user=customer, latitude=0.0, longitude=0.0, sales_agent=agent)

    create_entry(
        account=account,
        entry_type="invoice",
        amount_usd=Decimal("150.00"),
        order=order,
        region_override=region,
        sales_agent_override=agent,
    )

    finance_user = StaffUserFactory()
    finance_user.roles = ["finance"]
    finance_user.save()

    client = APIClient()
    client.force_authenticate(finance_user)

    month = timezone.now().strftime("%Y-%m")
    response = client.get(
        f"/api/revenue/summary/?group_by=region&from={month}&to={month}"
    )

    assert response.status_code == 200
    payload = response.json()
    # We expect at least region grouping; implementation may also include
    # additional dimensions like 'document'.
    assert "region" in payload["group_by"]
    assert payload["groups"]
    row = payload["groups"][0]
    assert row["region"] == region.name
    assert row["invoices"] == "150.00"


@pytest.mark.django_db
def test_revenue_summary_invalid_region_id_returns_400():
    finance_user = StaffUserFactory()
    finance_user.roles = ["finance"]
    finance_user.save()

    client = APIClient()
    client.force_authenticate(finance_user)

    month = timezone.now().strftime("%Y-%m")
    response = client.get(
        f"/api/revenue/summary/?from={month}&to={month}&region_id=not-an-int"
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("detail") == "Invalid region_id."


@pytest.mark.django_db
def test_revenue_summary_invalid_sales_agent_id_returns_400():
    finance_user = StaffUserFactory()
    finance_user.roles = ["finance"]
    finance_user.save()

    client = APIClient()
    client.force_authenticate(finance_user)

    month = timezone.now().strftime("%Y-%m")
    response = client.get(
        f"/api/revenue/summary/?from={month}&to={month}&sales_agent_id=bad-value"
    )
    assert response.status_code == 400
    body = response.json()
    assert body.get("detail") == "Invalid sales_agent_id."


@pytest.mark.django_db
def test_revenue_options_endpoint_lists_regions_and_agents():
    region = Region.objects.create(name="West", fence=make_square(0, 0, 1))
    agent = StaffUserFactory()
    agent.roles = ["sales", "manager"]
    agent.save()

    finance_user = StaffUserFactory()
    finance_user.roles = ["finance"]
    finance_user.save()

    client = APIClient()
    client.force_authenticate(finance_user)

    response = client.get("/api/revenue/options/")
    assert response.status_code == 200
    data = response.json()
    region_ids = {item["id"] for item in data["regions"]}
    agent_ids = {item["id"] for item in data["agents"]}
    assert region.id in region_ids
    assert agent.id in agent_ids


@pytest.mark.django_db
def test_revenue_correction_creates_reversal_and_new_entry():
    region_old = Region.objects.create(name="South", fence=make_square(-1, -1, 2))
    region_new = Region.objects.create(
        name="South-East", fence=make_square(-0.5, -0.5, 1)
    )
    agent = StaffUserFactory()
    agent.roles = ["sales"]
    agent.save()

    customer = UserFactory()
    account, _ = BillingAccount.objects.get_or_create(user=customer)
    order = OrderFactory(user=customer, latitude=0.0, longitude=0.0)

    original = create_entry(
        account=account,
        entry_type="invoice",
        amount_usd=Decimal("200.00"),
        order=order,
        region_override=region_old,
    )

    finance_user = StaffUserFactory()
    finance_user.roles = ["finance"]
    finance_user.save()

    client = APIClient()
    client.force_authenticate(finance_user)

    response = client.post(
        "/api/revenue/corrections/",
        {
            "entry_id": original.id,
            "region_id": region_new.id,
            "sales_agent_id": agent.id,
            "note": "Assign to new region and agent",
        },
        format="json",
    )

    assert response.status_code == 201
    body = response.json()
    reversal_id = body["reversal_id"]
    corrected_id = body["corrected_entry_id"]

    reversal_entry = AccountEntry.objects.get(pk=reversal_id)
    corrected_entry = AccountEntry.objects.get(pk=corrected_id)

    assert reversal_entry.amount_usd == Decimal("-200.00")
    assert reversal_entry.region_snapshot == region_old
    assert reversal_entry.snapshot_source == "manual_correction"

    assert corrected_entry.amount_usd == Decimal("200.00")
    assert corrected_entry.region_snapshot == region_new
    assert corrected_entry.sales_agent_snapshot == agent
    assert corrected_entry.snapshot_source == "manual_correction"

    account_entries = AccountEntry.objects.filter(account=account).order_by("id")
    assert account_entries.count() == 3
