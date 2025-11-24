from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("main", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="KycDocumentAccessLog",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("kyc_type", models.CharField(max_length=20)),
                ("kyc_id", models.PositiveIntegerField()),
                (
                    "document_label",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                ("accessed_at", models.DateTimeField(auto_now_add=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=models.CASCADE,
                        related_name="kyc_document_access_logs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-accessed_at"],
            },
        ),
    ]
