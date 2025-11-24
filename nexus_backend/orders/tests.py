import json
from decimal import Decimal

import pytest

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from orders.views import admin_view_orders_details
from main.factories import OrderFactory
from main.models import (
    AccountEntry,
    BillingAccount,
    ConsolidatedInvoice,
    Invoice,
    InvoiceLine,
    InvoiceOrder,
    OrderLine,
    OrderTax,
    PaymentAttempt,
)

User = get_user_model()


class AdminViewOrdersTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            email="orders.admin@example.com",
            username="orders_admin",
            password="testpass123",
            full_name="Orders Admin",
            is_staff=True,
        )
        # Staff role required by require_staff_role on orders views
        self.user.roles = ["finance"]
        self.user.save()
        self.client.force_login(self.user)

    def test_admin_view_orders_includes_single_and_consolidated(self):
        # Single order with taxes and attached invoice
        single_order = OrderFactory(
            user=self.user,
            total_price=Decimal("126.00"),
        )
        OrderTax.objects.create(
            order=single_order,
            kind=OrderTax.Kind.VAT,
            rate=Decimal("16.00"),
            amount=Decimal("16.00"),
        )
        OrderTax.objects.create(
            order=single_order,
            kind=OrderTax.Kind.EXCISE,
            rate=Decimal("10.00"),
            amount=Decimal("10.00"),
        )
        inv_single = Invoice.objects.create(
            number="ORD-INV-0001",
            user=self.user,
            currency="USD",
            subtotal=Decimal("100.00"),
            tax_total=Decimal("26.00"),
            grand_total=Decimal("126.00"),
            status="issued",
            issued_at=timezone.now(),
        )
        InvoiceOrder.objects.create(invoice=inv_single, order=single_order)
        InvoiceLine.objects.create(
            invoice=inv_single,
            description="Single Order Line",
            unit_price=Decimal("126.00"),
        )

        # Consolidated invoice covering two orders with tax snapshot on orders
        cons_order_1 = OrderFactory(
            user=self.user,
            total_price=Decimal("50.00"),
        )
        cons_order_2 = OrderFactory(
            user=self.user,
            total_price=Decimal("50.00"),
        )
        for o in (cons_order_1, cons_order_2):
            OrderTax.objects.create(
                order=o,
                kind=OrderTax.Kind.VAT,
                rate=Decimal("16.00"),
                amount=Decimal("8.00"),
            )
        inv_cons = Invoice.objects.create(
            number="CONS-INV-0001",
            user=self.user,
            currency="USD",
            subtotal=Decimal("100.00"),
            tax_total=Decimal("16.00"),
            grand_total=Decimal("116.00"),
            status="paid",
            issued_at=timezone.now(),
        )
        InvoiceOrder.objects.create(invoice=inv_cons, order=cons_order_1)
        InvoiceOrder.objects.create(invoice=inv_cons, order=cons_order_2)
        InvoiceLine.objects.create(
            invoice=inv_cons,
            description="Consolidated Line",
            unit_price=Decimal("116.00"),
        )

        resp = self.client.get(reverse("admin_view_orders"))
        self.assertEqual(resp.status_code, 200)

        payload = json.loads(resp.content.decode())
        self.assertTrue(payload.get("success"))
        orders = payload.get("orders") or []

        single_row = next(o for o in orders if not o.get("is_consolidated"))
        cons_row = next(o for o in orders if o.get("is_consolidated"))

        # Single order assertions
        self.assertEqual(single_row["reference"], single_order.order_reference)
        self.assertEqual(single_row["invoice_number"], inv_single.number)
        self.assertEqual(single_row["invoice_line"], "Single Order Line")
        # tax_total is VAT + EXCISE from OrderTax rows
        self.assertEqual(single_row["tax_total"], "26.00")

        # Consolidated invoice assertions
        self.assertTrue(cons_row["is_consolidated"])
        self.assertEqual(cons_row["consolidated_number"], inv_cons.number)
        self.assertEqual(cons_row["invoice_number"], inv_cons.number)
        self.assertEqual(cons_row["invoice_line"], "Consolidated Line")
        # sum_tax_total aggregates VAT across linked orders
        self.assertEqual(cons_row["sum_tax_total"], "16.00")

    def test_admin_view_orders_filters_by_status_and_query(self):
        # Create two orders with different payment_status and references
        paid_order = OrderFactory(
            user=self.user,
            total_price=Decimal("50.00"),
            status="fulfilled",
            payment_status="paid",
        )
        unpaid_order = OrderFactory(
            user=self.user,
            total_price=Decimal("75.00"),
            status="pending_payment",
            payment_status="unpaid",
        )

        # Filter by payment_status=paid
        resp = self.client.get(reverse("admin_view_orders"), {"status": "paid"})
        self.assertEqual(resp.status_code, 200)
        payload = json.loads(resp.content.decode())
        orders = payload.get("orders") or []
        refs = {o["reference"] for o in orders}
        self.assertIn(paid_order.order_reference, refs)
        self.assertNotIn(unpaid_order.order_reference, refs)

        # Filter by query matching unpaid order reference
        resp_q = self.client.get(
            reverse("admin_view_orders"),
            {"q": unpaid_order.order_reference},
        )
        self.assertEqual(resp_q.status_code, 200)
        payload_q = json.loads(resp_q.content.decode())
        orders_q = payload_q.get("orders") or []
        refs_q = {o["reference"] for o in orders_q}
        self.assertIn(unpaid_order.order_reference, refs_q)
        # Paid order should not be included when filtering only by q=unpaid reference
        self.assertNotIn(paid_order.order_reference, refs_q)


class AdminOrderDetailsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.factory = RequestFactory()
        self.user = User.objects.create_user(
            email="orders.details@example.com",
            username="orders_details_admin",
            password="testpass123",
            full_name="Orders Details Admin",
            is_staff=True,
        )
        self.user.roles = ["finance"]
        self.user.save()
        self.client.force_login(self.user)

    def test_admin_view_orders_details_single_order_payload(self):
        order = OrderFactory(
            user=self.user,
            total_price=Decimal("100.00"),
        )
        # Kit + plan lines so designation becomes "Kit & Subscription"
        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.KIT,
            description="Starlink Kit",
            quantity=1,
            unit_price=Decimal("50.00"),
        )
        OrderLine.objects.create(
            order=order,
            kind=OrderLine.Kind.PLAN,
            description="Monthly Plan",
            quantity=1,
            unit_price=Decimal("50.00"),
        )
        # Snapshot taxes
        OrderTax.objects.create(
            order=order,
            kind=OrderTax.Kind.VAT,
            rate=Decimal("16.00"),
            amount=Decimal("16.00"),
        )
        OrderTax.objects.create(
            order=order,
            kind=OrderTax.Kind.EXCISE,
            rate=Decimal("5.00"),
            amount=Decimal("5.00"),
        )

        resp = self.client.get(reverse("admin_view_orders_details", args=[order.id]))
        self.assertEqual(resp.status_code, 200)

        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("success"))
        payload = data["order"]

        self.assertFalse(payload["is_consolidated"])
        self.assertEqual(payload["id"], order.id)
        self.assertEqual(payload["reference"], order.order_reference)
        self.assertEqual(payload["description"], "Kit & Subscription")
        # Float values derived from Decimal totals
        self.assertEqual(payload["vat"], 16.0)
        self.assertEqual(payload["exc"], 5.0)
        # Two line items: kit + plan
        self.assertEqual(len(payload["items"]), 2)

    def test_admin_view_orders_details_consolidated_payload(self):
        # Set up a consolidated invoice with two child invoices and linked orders
        cons = ConsolidatedInvoice.objects.create(
            number="CONS-001",
            user=self.user,
            total=Decimal("348.00"),
        )
        order1 = OrderFactory(user=self.user)
        order2 = OrderFactory(user=self.user)

        inv1 = Invoice.objects.create(
            number="INV-C-001",
            user=self.user,
            currency="USD",
            subtotal=Decimal("100.00"),
            tax_total=Decimal("16.00"),
            grand_total=Decimal("116.00"),
            status="paid",
            consolidated_of=cons,
        )
        inv2 = Invoice.objects.create(
            number="INV-C-002",
            user=self.user,
            currency="USD",
            subtotal=Decimal("200.00"),
            tax_total=Decimal("32.00"),
            grand_total=Decimal("232.00"),
            status="paid",
            consolidated_of=cons,
        )
        InvoiceOrder.objects.create(invoice=inv1, order=order1)
        InvoiceOrder.objects.create(invoice=inv2, order=order2)
        InvoiceLine.objects.create(
            invoice=inv1,
            description="Line 1",
            unit_price=Decimal("116.00"),
        )
        InvoiceLine.objects.create(
            invoice=inv2,
            description="Line 2",
            unit_price=Decimal("232.00"),
        )

        # Call the view directly with a non-numeric consolidated reference
        request = self.factory.get("/en/orders/details/CONS-001/")
        request.user = self.user
        resp = admin_view_orders_details(request, "CONS-001")
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content.decode())
        self.assertTrue(data.get("success"))
        order_payload = data["order"]

        self.assertTrue(order_payload["is_consolidated"])
        self.assertEqual(order_payload["consolidated_number"], cons.number)
        # Should aggregate order ids and refs
        assert set(order_payload["order_ids"]) == {order1.id, order2.id}
        assert set(order_payload["order_refs"]) == {
            order1.order_reference,
            order2.order_reference,
        }
        # Items include flattened lines from child invoices
        assert len(order_payload["items"]) == 2
        # Totals reflect sum of child invoices
        assert order_payload["subtotal"] == 300.0
        assert order_payload["tax_total"] == 48.0
        assert order_payload["total"] == 348.0


@pytest.mark.django_db
def test_process_order_payment_cash_happy_path(client):
    user = User.objects.create_user(
        email="orders.pay@example.com",
        username="orders_pay_admin",
        password="testpass123",
        full_name="Orders Pay Admin",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    # Ensure a billing account exists for ledger entries
    BillingAccount.objects.get_or_create(user=user)

    order = OrderFactory(
        user=user,
        total_price=Decimal("100.00"),
        status="pending_payment",
        payment_status="unpaid",
    )
    # One simple hardware line
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.KIT,
        description="Hardware Line",
        quantity=1,
        unit_price=Decimal("100.00"),
    )

    # Attach an invoice via InvoiceOrder so _get_invoice_for_order can resolve it
    inv = Invoice.objects.create(
        number="ORD-INV-100",
        user=user,
        currency="USD",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("0.00"),
        grand_total=Decimal("100.00"),
        status="issued",
        issued_at=timezone.now(),
    )
    InvoiceOrder.objects.create(invoice=inv, order=order)

    url = reverse("process_order_payment", args=[order.id])
    resp = client.post(
        url,
        {
            "paymentMethod": "cash",
            "amount": "100.00",
            "currency": "USD",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    order.refresh_from_db()
    assert order.payment_status == "paid"
    assert order.status == "fulfilled"

    # A payment attempt should have been created using the invoice number as reference
    attempts = PaymentAttempt.objects.filter(order=order)
    assert attempts.count() == 1
    assert attempts.first().reference == inv.number

    # Ledger entry for the payment should reference the invoice as well
    entries = AccountEntry.objects.filter(order=order, entry_type="payment")
    assert entries.count() == 1
    assert "Invoice ORD-INV-100" in entries.first().description


@pytest.mark.django_db
def test_process_order_payment_cash_amount_mismatch_returns_400(client):
    user = User.objects.create_user(
        email="orders.pay.mismatch@example.com",
        username="orders_pay_mismatch",
        password="testpass123",
        full_name="Orders Pay Mismatch",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    BillingAccount.objects.get_or_create(user=user)

    order = OrderFactory(
        user=user,
        total_price=Decimal("100.00"),
        status="pending_payment",
        payment_status="unpaid",
    )
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.KIT,
        description="Hardware Line",
        quantity=1,
        unit_price=Decimal("100.00"),
    )

    inv = Invoice.objects.create(
        number="ORD-INV-200",
        user=user,
        currency="USD",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("0.00"),
        grand_total=Decimal("100.00"),
        status="issued",
        issued_at=timezone.now(),
    )
    InvoiceOrder.objects.create(invoice=inv, order=order)

    url = reverse("process_order_payment", args=[order.id])
    resp = client.post(
        url,
        {
            "paymentMethod": "cash",
            "amount": "50.00",  # incorrect amount
            "currency": "USD",
        },
    )

    assert resp.status_code == 400
    data = resp.json()
    assert data["success"] is False
    assert "Amount must equal the invoice total due." in data["message"]


@pytest.mark.django_db
def test_process_order_payment_terminal_sets_amount_from_due(client):
    user = User.objects.create_user(
        email="orders.pay.terminal@example.com",
        username="orders_pay_terminal",
        password="testpass123",
        full_name="Orders Pay Terminal",
        is_staff=True,
    )
    user.roles = ["finance"]
    user.save()
    client.force_login(user)

    BillingAccount.objects.get_or_create(user=user)

    order = OrderFactory(
        user=user,
        total_price=Decimal("150.00"),
        status="pending_payment",
        payment_status="unpaid",
    )
    OrderLine.objects.create(
        order=order,
        kind=OrderLine.Kind.KIT,
        description="Hardware Line",
        quantity=1,
        unit_price=Decimal("150.00"),
    )

    inv = Invoice.objects.create(
        number="ORD-INV-300",
        user=user,
        currency="USD",
        subtotal=Decimal("150.00"),
        tax_total=Decimal("0.00"),
        grand_total=Decimal("150.00"),
        status="issued",
        issued_at=timezone.now(),
    )
    InvoiceOrder.objects.create(invoice=inv, order=order)

    url = reverse("process_order_payment", args=[order.id])
    resp = client.post(
        url,
        {
            "paymentMethod": "terminal",
            "terminal_reference": "TERM-12345",
        },
    )

    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True

    order.refresh_from_db()
    assert order.payment_status == "paid"
    assert order.status == "fulfilled"
    assert order.payment_method == "terminal"

    # PaymentAttempt should have amount equal to invoice due and currency USD
    pa = PaymentAttempt.objects.get(order=order)
    assert pa.amount == Decimal("150.00")
    assert pa.currency == "USD"
