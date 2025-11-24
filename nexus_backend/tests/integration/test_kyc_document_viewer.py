import os
from urllib.parse import urlparse

import pytest
from django.conf import settings
from django.core.files.base import ContentFile
from django.urls import reverse

from main.models import PersonalKYC, User


@pytest.mark.django_db
def test_personal_kyc_pdf_viewer_generates_preview_and_logs_access(client):
    """
    Integration test: hitting the secure viewer endpoint for a personal KYC PDF
    should:
      - return HTML with an <img> preview (no raw PDF/media URL),
      - create a preview image file under MEDIA_ROOT,
      - log the access in KycDocumentAccessLog.
    """
    # Create compliance staff user
    staff = User.objects.create_user(
        email="compliance@example.com",
        full_name="Compliance Officer",
        username="compliance_user",
        password="testpass",
    )
    staff.roles = ["compliance"]
    staff.save()
    client.force_login(staff)

    # Create end user and a PersonalKYC with a fake PDF file
    end_user = User.objects.create_user(
        email="customer@example.com",
        full_name="Customer User",
        username="customer_user",
        password="testpass",
    )
    kyc = PersonalKYC.objects.create(user=end_user, status="pending")
    kyc.document_file.save("id_document.pdf", ContentFile(b"%PDF-1.4\n%fake test pdf"))
    kyc.save()

    url = reverse("kyc_document_view", args=["personal-main", kyc.id])
    response = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    assert response.status_code == 200
    html = response.content.decode("utf-8")

    # We expect an <img>-based viewer, not an iframe to the raw PDF
    assert "<img" in html
    assert ".pdf" not in html

    # Extract the preview image URL from the HTML and ensure the file exists
    # Very small and robust parse: look for src="..."
    marker = 'src="'
    assert marker in html
    start = html.index(marker) + len(marker)
    end = html.index('"', start)
    img_url = html[start:end]

    # Map URL path back to MEDIA_ROOT path
    parsed = urlparse(img_url)
    media_url = settings.MEDIA_URL
    assert parsed.path.startswith(media_url)
    rel_path = parsed.path[len(media_url) :].lstrip("/")
    abs_path = os.path.join(settings.MEDIA_ROOT, rel_path)
    assert os.path.exists(abs_path)

    # Access log should have one entry for this view
    from kyc_management.models import KycDocumentAccessLog

    assert (
        KycDocumentAccessLog.objects.filter(
            user=staff, kyc_type="personal", kyc_id=kyc.id
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_kyc_document_view_requires_compliance_role(client):
    """
    Non-compliance users must not be able to hit the viewer endpoint.
    """
    user = User.objects.create_user(
        email="normal@example.com",
        full_name="Normal User",
        username="normal_user",
        password="testpass",
    )
    # No special roles
    user.roles = []
    user.save()
    client.force_login(user)

    # Minimal KYC for target user
    target = User.objects.create_user(
        email="target@example.com",
        full_name="Target User",
        username="target_user",
        password="testpass",
    )
    kyc = PersonalKYC.objects.create(user=target, status="pending")

    url = reverse("kyc_document_view", args=["personal-main", kyc.id])
    response = client.get(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    # require_staff_role raises PermissionDenied -> Django returns 403
    assert response.status_code == 403
