from decimal import Decimal

import pytest

from django.db import connection
from django.urls import reverse

from main.factories import OrderFactory, UserFactory
from main.models import AccountEntry
from site_survey.models import (
    AdditionalBilling,
    ExtraCharge,
    SiteSurvey,
    SurveyAdditionalCost,
)

pytestmark = pytest.mark.skipif(
    not hasattr(connection.ops, "geo_db_type"),
    reason="Spatial database backend is not available for tests.",
)


@pytest.mark.django_db
def test_additional_billing_invoice_creation_and_download(client):
    user = UserFactory()
    order = OrderFactory(user=user)
    survey = SiteSurvey.objects.create(
        order=order,
        status="approved",
        requires_additional_equipment=True,
    )

    extra = ExtraCharge.objects.create(
        cost_type="equipment",
        item_name="Wall Mount Kit",
        description="Reinforced wall mount",
        unit_price=Decimal("145.00"),
    )

    SurveyAdditionalCost.objects.create(
        survey=survey,
        extra_charge=extra,
        quantity=1,
        justification="Required to secure the dish on concrete wall",
    )

    billing = AdditionalBilling.objects.create(
        survey=survey,
        order=order,
        customer=user,
        status="pending_approval",
    )

    billing.status = "approved"
    billing.save()

    external_ref = billing.invoice_external_ref
    invoice_entry = AccountEntry.objects.filter(external_ref=external_ref).first()

    assert invoice_entry is not None
    assert invoice_entry.entry_type == "invoice"
    assert invoice_entry.amount_usd == billing.total_amount

    client.force_login(user)
    response = client.get(reverse("client_additional_invoice_pdf", args=[billing.id]))
    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert billing.billing_reference in response["Content-Disposition"]
