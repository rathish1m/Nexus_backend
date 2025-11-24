from django.conf import settings
from django.db import models


class KycDocumentAccessLog(models.Model):
    """
    Minimal audit log for KYC document viewing.

    We deliberately keep this small and generic:
    - kyc_type: "personal" or "company"
    - kyc_id: primary key of the KYC object
    - document_label: short label to identify which document was viewed
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="kyc_document_access_logs",
    )
    kyc_type = models.CharField(max_length=20)
    kyc_id = models.PositiveIntegerField()
    document_label = models.CharField(max_length=100, blank=True, default="")
    accessed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-accessed_at"]

    def __str__(self) -> str:
        return f"{self.user_id} viewed {self.kyc_type} KYC #{self.kyc_id} ({self.document_label})"
