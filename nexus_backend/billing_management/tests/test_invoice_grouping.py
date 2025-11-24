import pytest

from billing_management.views import _build_invoice_context
from main.models import Invoice, InvoiceLine, Order


@pytest.mark.django_db
def test_invoice_grouping_structure():
    """
    TDD: Vérifie que le contexte regroupe bien les lignes par commande, avec Order Ref et date, pour un rendu unique.
    """
    # Préparer une facture avec deux commandes et plusieurs lignes
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(
        email="grouping@test.com", username="grouping", password="testpass123"
    )

    invoice = Invoice.objects.create(number="TDD-TEST-0001", currency="USD", user=user)
    order1 = Order.objects.create(order_reference="ORD-TEST-1", user=user)
    order2 = Order.objects.create(order_reference="ORD-TEST-2", user=user)
    InvoiceLine.objects.create(
        invoice=invoice,
        order=order1,
        description="Produit A",
        quantity=1,
        unit_price=100,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        order=order1,
        description="Produit B",
        quantity=1,
        unit_price=200,
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        order=order2,
        description="Produit C",
        quantity=1,
        unit_price=300,
    )

    # Appeler le context builder
    # Use singleton CompanySettings for context
    from main.models import CompanySettings

    cs = CompanySettings.get()
    context = _build_invoice_context(invoice, cs)
    order_groups = context.get("order_groups")
    assert order_groups is not None
    assert len(order_groups) == 2

    # Vérifier structure de chaque groupe
    for group in order_groups:
        assert "order" in group
        assert "lines" in group
        assert hasattr(group["order"], "order_reference")
        assert len(group["lines"]) >= 1

    # Vérifier que les lignes sont bien regroupées
    assert order_groups[0]["order"].order_reference == "ORD-TEST-1"
    assert len(order_groups[0]["lines"]) == 2
    assert order_groups[1]["order"].order_reference == "ORD-TEST-2"
    assert len(order_groups[1]["lines"]) == 1
