import pytest

from django.contrib.auth import get_user_model
from django.urls import reverse

from main.models import CompanyKYC, PersonalKYC


@pytest.mark.django_db
def test_kyc_resubmission_personal(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="testuser",
        password="testpass",
        email="testuser@example.com",
        full_name="Jean Dupont",
        is_staff=False,
        roles=["customer"],  # Add customer role
    )
    client.force_login(user)
    # Crée un KYC personnel rejeté
    kyc = PersonalKYC.objects.create(
        user=user,
        status="rejected",
        full_name="Jean Dupont",
        date_of_birth="1990-01-01",
        nationality="FR",
        remarks="Test motif rejet",
    )
    response = client.get(reverse("landing_page"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'window.kycType = "personal"' in content
    assert "window.kycData = {" in content
    assert "Jean Dupont" in content
    assert "1990-01-01" in content
    assert "FR" in content
    assert "Test motif rejet" in content


@pytest.mark.django_db
def test_kyc_resubmission_business(client):
    User = get_user_model()
    user = User.objects.create_user(
        username="testbiz",
        password="testpass",
        email="testbiz@example.com",
        full_name="Biz User",
        is_staff=False,
        roles=["customer"],  # Add customer role
    )
    client.force_login(user)
    # Crée un KYC entreprise rejeté
    kyc = CompanyKYC.objects.create(
        user=user,
        status="rejected",
        company_name="ACME SARL",
        address="1 rue de Paris",
        remarks="Test motif rejet entreprise",
    )
    response = client.get(reverse("landing_page"))
    assert response.status_code == 200
    content = response.content.decode()
    assert 'window.kycType = "business"' in content
    assert "window.kycData = {" in content
    assert "ACME SARL" in content
    assert "1 rue de Paris" in content
    assert "Test motif rejet entreprise" in content
