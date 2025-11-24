import json
from decimal import Decimal

import pytest

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from billing_management.views import invoice_json_by_number
from geo_regions.models import Region
from main.factories import OrderFactory
from main.models import (
    AccountEntry,
    BillingAccount,
    CompanySettings,
    Invoice,
    InvoiceLine,
    InvoiceOrder,
    FxRate,
)
from main.services.region_resolver import resolve_region_from_coords

User = get_user_model()


class InvoiceJSONViewTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.client = Client()

        # User + singleton company settings
        self.user = User.objects.create_user(
            email="invoice.json@example.com",
            username="invoice_json_user",
            password="testpass123",
            full_name="Invoice Json User",
        )

        self.company = CompanySettings.get()
        self.company.legal_name = "JSON Test Company"
        self.company.trade_name = "JSON Corp"
        self.company.vat_rate_percent = Decimal("16.00")
        self.company.excise_rate_percent = Decimal("0.00")
        self.company.default_currency = "USD"
        self.company.save()

        # Basic invoice snapshot
        self.invoice = Invoice.objects.create(
            number="JSON-INV-0001",
            user=self.user,
            currency="USD",
            subtotal=Decimal("100.00"),
            tax_total=Decimal("16.00"),
            grand_total=Decimal("116.00"),
            status="paid",
            bill_to_name="JSON Customer",
            bill_to_address="123 JSON Street",
            issued_at=timezone.now(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="JSON Service",
            quantity=1,
            unit_price=Decimal("100.00"),
        )

    def test_invoice_json_by_number_basic_payload(self):
        request = self.factory.get(
            reverse("invoice_json_by_number", args=[self.invoice.number])
        )
        request.user = self.user

        response = invoice_json_by_number(request, self.invoice.number)
        self.assertEqual(response.status_code, 200)

        payload = json.loads(response.content.decode())
        self.assertTrue(payload.get("success"))
        inv = payload["invoice"]

        self.assertEqual(inv["number"], self.invoice.number)
        self.assertEqual(inv["subtotal"], "100.00")
        self.assertEqual(inv["grand_total"], "116.00")
        self.assertEqual(inv["bill_to_name"], "JSON Customer")
        self.assertIn("company", payload)
        self.assertEqual(payload["company"]["legal_name"], "JSON Test Company")

    def test_invoice_json_by_number_not_found_returns_404(self):
        self.client = Client()
        self.client.force_login(self.user)
        url = reverse("invoice_json_by_number", args=["NON-EXISTENT-INV"])
        response = self.client.get(url)
        # Underlying helper raises Http404 when invoice cannot be found.
        self.assertEqual(response.status_code, 404)


class LedgerViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="ledger.user@example.com",
            username="ledger_user",
            password="testpass123",
            full_name="Ledger User",
        )
        # Ensure a billing account exists
        BillingAccount.objects.get_or_create(user=self.user)

    def test_ledger_search_customers_no_query_returns_empty(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("ledger_search_customers"))
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("results"), [])

    def test_ledger_search_customers_returns_match(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("ledger_search_customers"), {"q": "Ledger User"}
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertTrue(data.get("success"))
        results = data.get("results") or []
        self.assertTrue(any(r["id_user"] == self.user.id_user for r in results))

    def test_ledger_export_missing_user_id_returns_400(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("ledger_export"))
        self.assertEqual(response.status_code, 400)
        data = json.loads(response.content.decode())
        self.assertFalse(data.get("success"))

    def test_ledger_export_invalid_user_id_returns_404(self):
        self.client.force_login(self.user)
        response = self.client.get(
            reverse("ledger_export"),
            {
                "user_id": "999999",
                "from": timezone.now().date().strftime("%Y-%m-%d"),
                "to": timezone.now().date().strftime("%Y-%m-%d"),
                "format": "xlsx",
                "include_cdf": "0",
            },
        )
        # Unknown user id should simply yield an empty export, not an error.
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )

    def test_ledger_export_xlsx_happy_path(self):
        self.client.force_login(self.user)
        # Seed a couple of ledger entries for today
        AccountEntry.objects.create(
            account=self.user.billing_account,
            entry_type="invoice",
            amount_usd=Decimal("50.00"),
            description="Test invoice row",
        )
        AccountEntry.objects.create(
            account=self.user.billing_account,
            entry_type="payment",
            amount_usd=Decimal("-20.00"),
            description="Test payment row",
        )

        today = timezone.now().date().strftime("%Y-%m-%d")
        response = self.client.get(
            reverse("ledger_export"),
            {
                "user_id": str(self.user.id_user),
                "from": today,
                "to": today,
                "format": "xlsx",
                "include_cdf": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            response["Content-Type"],
        )
        # Response content should not be empty (contains XLSX bytes)
        self.assertTrue(len(response.content) > 0)

    def test_ledger_statement_json_happy_path(self):
        self.client.force_login(self.user)
        # Seed simple ledger entries
        AccountEntry.objects.create(
            account=self.user.billing_account,
            entry_type="invoice",
            amount_usd=Decimal("30.00"),
            description="Statement invoice",
        )
        AccountEntry.objects.create(
            account=self.user.billing_account,
            entry_type="payment",
            amount_usd=Decimal("-10.00"),
            description="Statement payment",
        )

        today = timezone.now().date().strftime("%Y-%m-%d")
        response = self.client.get(
            reverse("ledger_statement"),
            {
                "user_id": str(self.user.id_user),
                "from": today,
                "to": today,
                "format": "json",
                "include_cdf": "0",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content.decode())
        self.assertTrue(data.get("success"))
        stmt = data["statement"]
        self.assertEqual(stmt["user_id"], self.user.id_user)
        self.assertIn("opening_balance", stmt)
        self.assertIn("closing_balance", stmt)
        self.assertIn("rows", stmt)
        self.assertGreaterEqual(len(stmt["rows"]), 1)


@pytest.mark.django_db
def test_billing_revenue_summary_basic_totals(client):
    # Skip if spatial backend is not available (matches revenue reporting GIS usage).
    from django.db import connection

    if not hasattr(connection.ops, "geo_db_type"):
        pytest.skip("Spatial database backend is not available for tests.")

    # Finance staff user with required role
    user = User.objects.create_user(
        email="finance@example.com",
        username="finance_user",
        password="testpass123",
        full_name="Finance User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    # Seed a simple invoice in the period
    today = timezone.now().date()
    inv = Invoice.objects.create(
        number="REV-001",
        user=user,
        currency="USD",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("16.00"),
        grand_total=Decimal("116.00"),
        status="paid",
        issued_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )

    url = reverse("revenue_summary")
    response = client.get(
        url,
        {
            "from": today.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "include_cdf": "0",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["totals"]["grand_total"] == "116.00"


@pytest.mark.django_db
def test_billing_revenue_summary_missing_date_range_returns_400(client):
    # Finance staff user with required role
    user = User.objects.create_user(
        email="finance.missing@example.com",
        username="finance_missing",
        password="testpass123",
        full_name="Finance Missing",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    url = reverse("revenue_summary")
    resp = client.get(url, {"include_cdf": "0"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Missing date range" in data["message"]


@pytest.mark.django_db
def test_billing_revenue_summary_invalid_date_range_returns_400(client):
    user = User.objects.create_user(
        email="finance.invalid@example.com",
        username="finance_invalid",
        password="testpass123",
        full_name="Finance Invalid",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    url = reverse("revenue_summary")
    resp = client.get(
        url,
        {
            "from": "2025-02-01",
            "to": "2025-01-01",  # to < from
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Invalid date range" in data["message"]


@pytest.mark.django_db
def test_billing_revenue_summary_date_range_too_large_returns_400(client):
    user = User.objects.create_user(
        email="finance.range@example.com",
        username="finance_range",
        password="testpass123",
        full_name="Finance Range",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    url = reverse("revenue_summary")
    resp = client.get(
        url,
        {
            "from": "2020-01-01",
            "to": "2025-01-01",  # > 366 days
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Date range too large" in data["message"]


@pytest.mark.django_db
def test_billing_revenue_summary_collected_perspective_totals(client):
    user = User.objects.create_user(
        email="finance.collected@example.com",
        username="finance_collected",
        password="testpass123",
        full_name="Finance Collected",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    acct, _ = BillingAccount.objects.get_or_create(user=user)
    today = timezone.now().date()

    # One payment and one credit note within the window
    AccountEntry.objects.create(
        account=acct,
        entry_type="payment",
        amount_usd=Decimal("50.00"),
        description="Collected payment",
        created_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )
    AccountEntry.objects.create(
        account=acct,
        entry_type="credit_note",
        amount_usd=Decimal("-10.00"),
        description="Credit note",
        created_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )

    url = reverse("revenue_summary")
    resp = client.get(
        url,
        {
            "from": today.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "perspective": "collected",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    totals = data["totals"]
    # Collected should reflect only the payment, credits_adjustments the absolute credit magnitude
    assert totals["collected"] == "50.00"
    assert totals["credits_adjustments"] == "10.00"


@pytest.mark.django_db
def test_check_and_fix_order_region_flow(client, settings):
    # For region resolution tests, ensure GIS backend is available before running.
    from django.db import connection

    if not hasattr(connection.ops, "geo_db_type"):
        pytest.skip("Spatial database backend is not available for tests.")

    # Create staff user to allow fix_order_region
    staff = User.objects.create_user(
        email="staff.region@example.com",
        username="staff_region",
        password="testpass123",
        full_name="Staff Region User",
        is_staff=True,
    )
    client.force_login(staff)

    # Define a simple region polygon and an order inside it
    from django.contrib.gis.geos import Polygon

    poly = Polygon(
        (
            (0.0, 0.0),
            (0.0, 1.0),
            (1.0, 1.0),
            (1.0, 0.0),
            (0.0, 0.0),
        )
    )
    poly.srid = 4326
    region = Region.objects.create(name="Test Region", fence=poly)

    order = OrderFactory(user=staff, latitude=0.5, longitude=0.5)

    # Sanity check: low-level resolver sees the region
    resolved, tag = resolve_region_from_coords(order.latitude, order.longitude)
    assert resolved == region
    assert tag in ("auto", "auto_ambiguous")

    # 1) check_order_region endpoint
    check_url = reverse("check_order_region")
    resp = client.get(check_url, {"order_id": str(order.id)})
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["success"] is True
    assert payload["order_id"] == order.id
    assert payload["resolved_region"]["name"] == "Test Region"

    # 2) fix_order_region endpoint with force+override
    fix_url = reverse("fix_order_region")
    resp2 = client.post(
        fix_url,
        {
            "order_id": str(order.id),
            "force": "1",
            "override": "1",
        },
    )
    assert resp2.status_code == 200
    payload2 = resp2.json()
    assert payload2["success"] is True
    assert payload2["order_id"] == order.id
    assert payload2["saved_region"]["name"] == "Test Region"


@pytest.mark.django_db
def test_check_order_region_missing_order_id_returns_400(client):
    # Missing order_id should return a 400 with a clear message for authenticated users.
    user = User.objects.create_user(
        email="region.missing@example.com",
        username="region_missing",
        password="testpass123",
        full_name="Region Missing User",
        is_staff=True,
    )
    client.force_login(user)
    url = reverse("check_order_region")
    resp = client.get(url)
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Missing order_id" in data["message"]


@pytest.mark.django_db
def test_check_order_region_invalid_order_id_returns_400(client):
    user = User.objects.create_user(
        email="region.invalid@example.com",
        username="region_invalid",
        password="testpass123",
        full_name="Region Invalid User",
        is_staff=True,
    )
    client.force_login(user)
    url = reverse("check_order_region")
    resp = client.get(url, {"order_id": "not-an-int"})
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Invalid order_id" in data["message"]


@pytest.mark.django_db
def test_revenue_table_invoiced_month_happy_path(client):
    # Skip locally if spatial backend is not available; CI uses PostGIS.
    from django.db import connection

    if not hasattr(connection.ops, "geo_db_type"):
        pytest.skip("Spatial database backend is not available for tests.")

    # Finance staff user
    user = User.objects.create_user(
        email="rev.happy@example.com",
        username="rev_happy_user",
        password="testpass123",
        full_name="Rev Happy User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    # Simple invoice in period
    today = timezone.now().date()
    inv = Invoice.objects.create(
        number="REV-HAPPY-001",
        user=user,
        currency="USD",
        subtotal=Decimal("100.00"),
        vat_amount=Decimal("16.00"),
        excise_amount=Decimal("0.00"),
        tax_total=Decimal("16.00"),
        grand_total=Decimal("116.00"),
        status="paid",
        issued_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )

    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "from": today.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "group_by": "month",
            "perspective": "invoiced",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["group_by"] == "month"
    assert data["perspective"] == "invoiced"
    # One grouped row with the invoice subtotal/grand_total
    assert data["total_groups"] == 1
    row = data["rows"][0]
    assert row["usd"]["subtotal"] == "100.00"
    assert row["usd"]["tax_total"] == "16.00"
    assert row["usd"]["grand_total"] == "116.00"
    assert row["usd"]["net"] == "116.00"


@pytest.mark.django_db
def test_revenue_table_collected_day_happy_path(client):
    # Skip locally if spatial backend is not available; CI uses PostGIS.
    from django.db import connection

    if not hasattr(connection.ops, "geo_db_type"):
        pytest.skip("Spatial database backend is not available for tests.")

    # Finance staff user
    user = User.objects.create_user(
        email="rev.collected@example.com",
        username="rev_collected_user",
        password="testpass123",
        full_name="Rev Collected User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    # Seed a payment AccountEntry (positive amount_usd) for today
    acct, _ = BillingAccount.objects.get_or_create(user=user)
    today = timezone.now()
    AccountEntry.objects.create(
        account=acct,
        entry_type="payment",
        amount_usd=Decimal("50.00"),
        description="Collected payment",
        created_at=today,
    )

    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "from": today.date().strftime("%Y-%m-%d"),
            "to": today.date().strftime("%Y-%m-%d"),
            "group_by": "day",
            "perspective": "collected",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["group_by"] == "day"
    assert data["perspective"] == "collected"
    assert data["total_groups"] == 1
    row = data["rows"][0]
    # Collected/net should reflect the payment amount
    assert row["usd"]["collected"] == "50.00"
    assert row["usd"]["net"] == "50.00"


@pytest.mark.django_db
def test_revenue_table_group_by_region_multiple_regions(client):
    # For region-aware grouping tests, ensure GIS backend is available.
    from django.db import connection
    from django.contrib.gis.geos import Polygon

    if not hasattr(connection.ops, "geo_db_type"):
        pytest.skip("Spatial database backend is not available for tests.")

    # Finance staff user
    user = User.objects.create_user(
        email="rev.region@example.com",
        username="rev_region_user",
        password="testpass123",
        full_name="Rev Region User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    # Two simple regions with minimal polygons
    poly1 = Polygon(
        (
            (0.0, 0.0),
            (0.0, 1.0),
            (1.0, 1.0),
            (1.0, 0.0),
            (0.0, 0.0),
        )
    )
    poly1.srid = 4326
    poly2 = Polygon(
        (
            (2.0, 2.0),
            (2.0, 3.0),
            (3.0, 3.0),
            (3.0, 2.0),
            (2.0, 2.0),
        )
    )
    poly2.srid = 4326
    region1 = Region.objects.create(name="Region A", fence=poly1)
    region2 = Region.objects.create(name="Region B", fence=poly2)

    # Orders tied to regions
    order1 = OrderFactory(user=user, region=region1)
    order2 = OrderFactory(user=user, region=region2)

    today = timezone.now().date()

    # Invoices linked to each order via InvoiceOrder
    inv1 = Invoice.objects.create(
        number="REG-INV-001",
        user=user,
        currency="USD",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("16.00"),
        grand_total=Decimal("116.00"),
        status="paid",
        issued_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )
    inv2 = Invoice.objects.create(
        number="REG-INV-002",
        user=user,
        currency="USD",
        subtotal=Decimal("200.00"),
        tax_total=Decimal("32.00"),
        grand_total=Decimal("232.00"),
        status="paid",
        issued_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )
    InvoiceOrder.objects.create(invoice=inv1, order=order1)
    InvoiceOrder.objects.create(invoice=inv2, order=order2)

    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "from": today.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "group_by": "region",
            "perspective": "invoiced",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # group_by reflects requested key
    assert data["group_by"] == "region"

    labels = {row["label"] for row in data["rows"]}
    assert "Region A" in labels
    assert "Region B" in labels


@pytest.mark.django_db
def test_ledger_statement_empty_period_json(client):
    user = User.objects.create_user(
        email="stmt.empty@example.com",
        username="stmt_empty",
        password="testpass123",
        full_name="Stmt Empty User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    today = timezone.now().date()
    url = reverse("ledger_statement")
    resp = client.get(
        url,
        {
            "user_id": str(user.id_user),
            "from": today.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "format": "json",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    stmt = data["statement"]
    assert stmt["user_id"] == user.id_user
    assert stmt["opening_balance"] == "0.00"
    assert stmt["closing_balance"] == "0.00"
    assert stmt["total_debit"] == "0.00"
    assert stmt["total_credit"] == "0.00"
    assert isinstance(stmt["rows"], list)
    assert len(stmt["rows"]) == 0


@pytest.mark.django_db
def test_ledger_statement_with_cdf_block(client):
    user = User.objects.create_user(
        email="stmt.cdf@example.com",
        username="stmt_cdf",
        password="testpass123",
        full_name="Stmt CDF User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    acct, _ = BillingAccount.objects.get_or_create(user=user)
    today = timezone.now().date()
    # One simple invoice entry
    AccountEntry.objects.create(
        account=acct,
        entry_type="invoice",
        amount_usd=Decimal("100.00"),
        description="Statement invoice",
        created_at=timezone.make_aware(
            timezone.datetime.combine(today, timezone.datetime.min.time())
        ),
    )
    # FX rate for today so CDF is computed
    FxRate.objects.create(date=today, pair="USD/CDF", rate=Decimal("2000.0000"))

    url = reverse("ledger_statement")
    resp = client.get(
        url,
        {
            "user_id": str(user.id_user),
            "from": today.strftime("%Y-%m-%d"),
            "to": today.strftime("%Y-%m-%d"),
            "format": "json",
            "include_cdf": "1",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    stmt = data["statement"]
    # CDF block should be present with a non-empty rate
    assert stmt["cdf"] is not None
    assert "rate" in stmt["cdf"]
    assert stmt["cdf"]["rate"]



@pytest.mark.django_db
def test_revenue_table_invalid_group_by(client):
    user = User.objects.create_user(
        email="rev.table@example.com",
        username="rev_table_user",
        password="testpass123",
        full_name="Rev Table User",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    today = timezone.now().date().strftime("%Y-%m-%d")
    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "from": today,
            "to": today,
            "group_by": "invalid",
            "perspective": "invoiced",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Invalid group_by" in data["message"]


@pytest.mark.django_db
def test_revenue_table_invalid_perspective(client):
    user = User.objects.create_user(
        email="rev.table2@example.com",
        username="rev_table_user2",
        password="testpass123",
        full_name="Rev Table User 2",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    today = timezone.now().date().strftime("%Y-%m-%d")
    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "from": today,
            "to": today,
            "group_by": "month",
            "perspective": "invalid",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Invalid perspective" in data["message"]


@pytest.mark.django_db
def test_revenue_table_missing_date_range(client):
    user = User.objects.create_user(
        email="rev.table3@example.com",
        username="rev_table_user3",
        password="testpass123",
        full_name="Rev Table User 3",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "group_by": "month",
            "perspective": "invoiced",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Missing date range" in data["message"]


@pytest.mark.django_db
def test_revenue_table_date_range_too_large(client):
    user = User.objects.create_user(
        email="rev.table4@example.com",
        username="rev_table_user4",
        password="testpass123",
        full_name="Rev Table User 4",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    url = reverse("revenue_table")
    resp = client.get(
        url,
        {
            "from": "2020-01-01",
            "to": "2025-01-01",  # > 366 days span
            "group_by": "month",
            "perspective": "invoiced",
            "include_cdf": "0",
        },
    )
    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Date range too large" in data["message"]
