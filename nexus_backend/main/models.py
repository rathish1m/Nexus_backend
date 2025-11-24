import os
import random
import secrets
import string
import time
from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.contrib.postgres.indexes import GinIndex
from django.core.exceptions import ValidationError

# from django.contrib.gis.db import models as gis_models
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import F, Q, UniqueConstraint
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from nexus_backend.storage_backend import PrivateMediaStorage

try:
    import openlocationcode as olc
except Exception:
    olc = None
PROMO_LINE_SCOPE_VALUES = {"any", "kit", "plan", "install", "extra"}


ZERO = Decimal("0.00")


def _qmoney(x: Decimal) -> Decimal:
    return (x or Decimal("0.00")).quantize(ZERO, rounding=ROUND_HALF_UP)


#######
class OrderQuerySet(models.QuerySet):
    """Query helpers for `Order` filtering with consistent expiry semantics.

    Expiry rule: an order is expired iff timezone.now() >= expires_at.
    `unexpired()` keeps orders where expires_at is NULL or in the future strictly (> now).
    """

    def unexpired(self, now=None):
        from django.utils import timezone as _tz

        if now is None:
            now = _tz.now()
        return self.filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now)
        )

    def active_unpaid_for(self, user, now=None):
        return (
            self.filter(user=user, payment_status="unpaid")
            .exclude(status="cancelled")
            .unexpired(now)
        )


class OrderManager(models.Manager):
    """Default manager exposing `OrderQuerySet` helpers on `Order.objects`."""

    def get_queryset(self):  # type: ignore[override]
        return OrderQuerySet(self.model, using=self._db)

    # Passthrough helpers
    def unexpired(self, now=None):
        return self.get_queryset().unexpired(now)

    def active_unpaid_for(self, user, now=None):
        return self.get_queryset().active_unpaid_for(user, now)


class Country(models.Model):
    pass


class StarlinkKitInventoryQuerySet(models.QuerySet):
    def not_scrapped(self):
        return self.exclude(status="scrapped").exclude(condition="scrapped")

    def available(self):
        return (
            self.not_scrapped()
            .filter(current_location__isnull=False, is_assigned=False)
            .filter(models.Q(status="available") | models.Q(status=""))
        )

    def in_region(self, region_id):
        return self.filter(current_location__region_id=region_id) if region_id else self

    def at_location(self, location_id):
        return self.filter(current_location_id=location_id) if location_id else self

    def for_kit(self, kit_id):
        return self.filter(kit_id=kit_id) if kit_id else self

    def for_kit_type(self, kit_type):
        return self.filter(kit__kit_type=kit_type) if kit_type else self


# Stock Location####
class StockLocation(models.Model):
    """
    Physical or logical place: warehouse, van, technician bag, RMA, scrap, or 'Customer'.
    Use is_active=False to retire a location without losing history.
    """

    code = models.SlugField(
        max_length=50, unique=True, help_text="Short code, e.g. kin-main, van-john, rma"
    )
    name = models.CharField(max_length=100, unique=True)
    address = models.CharField(max_length=255, blank=True, default="")
    region = models.ForeignKey(
        "geo_regions.Region",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="stock_locations",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.code})"


class RegionSalesDefault(models.Model):
    region = models.ForeignKey(
        "geo_regions.Region",
        on_delete=models.PROTECT,
        related_name="sales_defaults",
    )
    agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="region_defaults",
    )
    is_primary = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["region", "agent"],
                name="uniq_region_agent_default",
            ),
            models.UniqueConstraint(
                fields=["region"],
                condition=Q(is_primary=True),
                name="uniq_primary_region_default",
            ),
        ]
        verbose_name = "Region sales default"
        verbose_name_plural = "Region sales defaults"

    def __str__(self) -> str:
        agent_name = (
            getattr(self.agent, "get_full_name", lambda: None)()
            or getattr(self.agent, "email", None)
            or self.agent_id
        )
        return f"{self.region} → {agent_name}"


class UserRole(models.TextChoices):
    TECHNICIAN = "technician", ("Technician")
    DISPATCHER = "dispatcher", ("Dispatcher")
    ADMIN = "admin", ("Admin")
    INSTALLER = "installer", ("Installer")
    SUPPORT = "support", ("Support")
    SALES = "sales", ("Sales Agent")
    COMPLIANCE = "compliance", ("Sales Agent")
    MANAGER = "manager", ("Manager")
    CUSTOMER = "customer", ("Customer")
    FINANCE = "finance", ("Finance")


class UserPreferences(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prefs"
    )
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    twofa_enabled = models.BooleanField(default=False)

    # Notification toggles
    notify_updates = models.BooleanField(default=True)
    notify_billing = models.BooleanField(default=True)
    notify_tickets = models.BooleanField(default=True)

    def avatar_url(self):
        return self.avatar.url if self.avatar else "/static/icons/account_avatar.png"

    def __str__(self):
        return f"Prefs({self.user_id})"


class User(AbstractUser):
    id_user = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=50)
    phone = models.CharField(max_length=50, blank=True, null=True, unique=True)
    email = models.EmailField(unique=True, blank=True, null=True)
    is_verified = models.BooleanField(default=False)
    groups = models.ManyToManyField(Group, related_name="customuser_set", blank=True)
    user_permissions = models.ManyToManyField(
        Permission, related_name="customuser_permissions", blank=True
    )
    is_tax_exempt = models.BooleanField(default=False)

    # ✅ Add this field for multi-role support
    roles = models.JSONField(
        default=list, blank=True, help_text="List of user roles (multi-role support)"
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = [
        "full_name",
        "username",
    ]  # 'username' is required for compatibility

    def __str__(self):
        return self.full_name or self.email or self.username

    def get_kyc_status(self):
        if hasattr(self, "personnal_kyc") and self.personnal_kyc:
            return self.personnal_kyc.status
        elif hasattr(self, "company_kyc") and self.company_kyc:
            return self.company_kyc.status
        return "not_submitted"

    def has_role(self, role):
        return role in self.roles

    def add_role(self, role):
        if role not in self.roles:
            self.roles.append(role)
            self.save()

    def remove_role(self, role):
        if role in self.roles:
            self.roles.remove(role)
            self.save()

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        super().save(*args, **kwargs)

    # Backwards-compat alias for code that expects a field named `id`
    # instead of the actual primary key `id_user`.
    @property
    def id(self):
        return self.id_user


class OTPVerification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="otp_codes")
    otp = models.CharField(max_length=6, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(blank=True, null=True)
    is_verified = models.BooleanField(default=False, blank=True, null=True)
    attempt_count = models.PositiveIntegerField(default=0)

    def generate_otp(self):
        """Generate and store a new secure OTP with expiration."""
        self.otp = f"{secrets.randbelow(1000000):06}"  # always 6 digits
        self.expires_at = timezone.now() + timedelta(minutes=5)
        self.is_verified = False
        self.attempt_count = 0
        self.save()

    def is_expired(self):
        """Check whether the OTP has expired."""
        return timezone.now() > self.expires_at

    def verify_otp(self, input_otp):
        """Securely verify the OTP and increment attempts."""
        if self.is_expired():
            return False, "OTP has expired."

        if self.attempt_count >= 5:
            return False, "Too many attempts. OTP locked."

        if self.otp == input_otp:
            self.is_verified = True
            self.save()
            return True, "OTP verified."
        else:
            self.attempt_count += 1
            self.save()
            return False, "Invalid OTP."

    def __str__(self):
        return f"OTP for {self.user.username} (Expires at {self.expires_at})"


class BaseKYC(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", ("Pending")
        APPROVED = "approved", ("Approved")
        REJECTED = "rejected", ("Rejected")

    # Predefined rejection reasons for consistency
    REJECTION_REASONS = [
        ("document_quality", "Poor document quality"),
        ("document_expired", "Document expired"),
        ("information_mismatch", "Information does not match document"),
        ("incomplete_documents", "Incomplete documentation"),
        ("invalid_document", "Invalid or fake document"),
        ("other", "Other (specify in remarks)"),
    ]

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name=("KYC Status"),
    )

    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_approved_by",
        verbose_name=("Approved By"),
    )

    approved_at = models.DateTimeField(
        null=True, blank=True, verbose_name=("Approval Date")
    )

    # Rejection tracking fields
    rejection_reason = models.CharField(
        max_length=50,
        choices=REJECTION_REASONS,
        blank=True,
        null=True,
        verbose_name="Rejection Reason",
    )

    rejected_at = models.DateTimeField(
        null=True, blank=True, verbose_name=("Rejection Date")
    )

    rejected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_rejected_by",
        verbose_name=("Rejected By"),
    )

    remarks = models.TextField(blank=True, verbose_name=("Remarks"))

    class Meta:
        abstract = True
        ordering = ["-approved_at"]
        verbose_name = "KYC Record"
        verbose_name_plural = "KYC Records"

    def is_pending(self):
        return self.status == self.Status.PENDING

    def is_approved(self):
        return self.status == self.Status.APPROVED

    def is_rejected(self):
        return self.status == self.Status.REJECTED

    def __str__(self):
        return f"KYC [{self.get_status_display()}]"


def personal_kyc_upload_path(instance, filename):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    name_slug = (
        slugify(instance.user.full_name)
        if instance.user and instance.user.full_name
        else "anonymous"
    )
    ext = os.path.splitext(filename)[-1]
    return f"kyc/personal/{name_slug}/{name_slug}_{instance.document_number}_{timestamp}{ext}"


def representative_id_upload_path(instance, filename):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    company_slug = slugify(instance.company_name or "unknown_company")
    ext = os.path.splitext(filename)[-1]
    return f"kyc/company/{company_slug}/representative/rep_id_{timestamp}{ext}"


def company_document_upload_path(instance, filename):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    # Handle both CompanyKYC and CompanyDocument instances
    if hasattr(instance, "company_kyc"):
        # This is a CompanyDocument instance
        company_name = instance.company_kyc.company_name
    else:
        # This is a CompanyKYC instance
        company_name = instance.company_name
    company_slug = slugify(company_name or "unknown_company")
    ext = os.path.splitext(filename)[-1]
    return f"kyc/company/{company_slug}/documents/company_doc_{timestamp}{ext}"


class PersonalKYC(BaseKYC):
    # ID Document Type Choices
    ID_DOCUMENT_TYPE_CHOICES = [
        ("voter_card", "Carte d'électeur"),
        ("drivers_license", "Permis de conduire"),
        ("passport", "Passeport"),
    ]

    user = models.OneToOneField(
        "User",
        on_delete=models.CASCADE,
        related_name="personnal_kyc",  # ✅ Must match the related_name used in User.get_kyc_status
        blank=True,
        null=True,
    )

    # Personal Information
    full_name = models.CharField(max_length=50, blank=True, null=True)
    date_of_birth = models.DateField(
        verbose_name="Date of Birth", blank=True, null=True
    )
    nationality = models.CharField(
        max_length=50, verbose_name="Nationality", blank=True, null=True
    )

    # Identity Document Information
    id_document_type = models.CharField(
        max_length=20,
        choices=ID_DOCUMENT_TYPE_CHOICES,
        verbose_name="ID Document Type",
        blank=True,
        null=True,
    )
    document_number = models.CharField(
        max_length=50, blank=True, null=True, unique=True
    )
    id_issue_date = models.DateField(
        verbose_name="ID Issue Date", blank=True, null=True
    )
    id_expiry_date = models.DateField(
        verbose_name="ID Expiry Date", blank=True, null=True
    )

    # Address Information
    address = models.CharField(max_length=70, blank=True, null=True)

    # Document Upload
    document_file = models.FileField(
        upload_to=personal_kyc_upload_path,
        storage=(
            PrivateMediaStorage() if getattr(settings, "USE_SPACES", False) else None
        ),
        blank=True,
        null=True,
    )
    visa_last_page = models.FileField(
        upload_to=personal_kyc_upload_path,
        storage=(
            PrivateMediaStorage() if getattr(settings, "USE_SPACES", False) else None
        ),
        blank=True,
        null=True,
        help_text="Last page of visa for non-Congolese nationals",
    )
    submitted_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    def __str__(self):
        return f"KYC – {self.full_name or (self.user.full_name if self.user else 'Unknown')}"

    # def clean(self):
    #     """Custom validation for date logic"""
    #     from django.core.exceptions import ValidationError
    #
    #     super().clean()
    #
    #     # Validate that expiry date is after issue date
    #     if self.id_issue_date and self.id_expiry_date:
    #         if self.id_expiry_date <= self.id_issue_date:
    #             raise ValidationError(
    #                 {"id_expiry_date": "Expiry date must be after issue date."}
    #             )
    #
    #     # Validate that date of birth is in the past
    #     if self.date_of_birth and self.date_of_birth >= timezone.now().date():
    #         raise ValidationError(
    #             {"date_of_birth": "Date of birth must be in the past."}
    #         )

    # def save(self, *args, **kwargs):
    #     self.full_clean()  # Run custom validation
    #     super().save(*args, **kwargs)


class CompanyKYC(BaseKYC):
    # Legal Status Choices
    LEGAL_STATUS_CHOICES = [
        ("sa", _("Public Limited Company (SA)")),
        ("sarl", _("Limited Liability Company (SARL)")),
        ("eurl", _("Single-Person Limited Liability Company (EURL)")),
        ("sas", _("Simplified Joint Stock Company (SAS)")),
        ("sasu", _("Single-Person Simplified Joint Stock Company (SASU)")),
        ("ei", _("Individual Enterprise (EI)")),
        ("auto_entrepreneur", _("Self-Employed Entrepreneur")),
        ("association", _("Association")),
        ("cooperative", _("Cooperative")),
        ("gie", _("Economic Interest Group (GIE)")),
        ("other", _("Other")),
    ]

    # Business Sector Choices
    BUSINESS_SECTOR_CHOICES = [
        ("agriculture", _("Agriculture, Forestry and Fishing")),
        ("mining", _("Mining and Quarrying")),
        ("manufacturing", _("Manufacturing")),
        ("utilities", _("Electricity, Gas, Steam and Water Supply")),
        ("construction", _("Construction")),
        ("trade", _("Wholesale and Retail Trade")),
        ("transport", _("Transportation and Storage")),
        ("accommodation", _("Accommodation and Food Service")),
        ("information", _("Information and Communication")),
        ("finance", _("Financial and Insurance Activities")),
        ("real_estate", _("Real Estate Activities")),
        ("professional", _("Professional, Scientific and Technical Activities")),
        ("administrative", _("Administrative and Support Service Activities")),
        ("public_admin", _("Public Administration and Defence")),
        ("education", _("Education")),
        ("health", _("Human Health and Social Work Activities")),
        ("arts", _("Arts, Entertainment and Recreation")),
        ("other_services", _("Other Service Activities")),
        ("household", _("Household Activities")),
        ("extraterritorial", _("Extraterritorial Organizations")),
        ("other", _("Other")),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="company_kyc",
        blank=True,
        null=True,
    )
    company_name = models.CharField(max_length=100, blank=True, null=True)
    address = models.CharField(max_length=70, blank=True, null=True)

    # New fields
    established_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="Date Established",
        help_text="Date when the company was legally established",
    )
    business_sector = models.CharField(
        max_length=50,
        choices=BUSINESS_SECTOR_CHOICES,
        blank=True,
        null=True,
        verbose_name="Business Sector",
        help_text="Primary business sector/industry",
    )
    legal_status = models.CharField(
        max_length=50,
        choices=LEGAL_STATUS_CHOICES,
        blank=True,
        null=True,
        verbose_name="Legal Status",
        help_text="Legal form/status of the company",
    )

    # Existing fields
    rccm = models.CharField(max_length=50, blank=True, null=True)
    nif = models.CharField(max_length=50, blank=True, null=True)
    id_nat = models.CharField(max_length=50, blank=True, null=True)
    representative_name = models.CharField(max_length=100, blank=True, null=True)
    representative_id_file = models.FileField(
        upload_to=representative_id_upload_path,
        storage=(
            PrivateMediaStorage() if getattr(settings, "USE_SPACES", False) else None
        ),
        blank=True,
        null=True,
    )
    company_documents = models.FileField(
        upload_to=company_document_upload_path,
        storage=(
            PrivateMediaStorage() if getattr(settings, "USE_SPACES", False) else None
        ),
        blank=True,
        null=True,
    )
    submitted_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    # OPTIMISATION : Champ dénormalisé pour compter les documents
    documents_count = models.PositiveIntegerField(default=0, editable=False)

    def __str__(self):
        return f"{self.company_name} ({self.user.email})"

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(fields=["user", "status"]),
            models.Index(fields=["submitted_at", "status"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["rccm"],
                condition=Q(rccm__isnull=False) & ~Q(rccm=""),
                name="company_kyc_unique_rccm",
            ),
            UniqueConstraint(
                fields=["nif"],
                condition=Q(nif__isnull=False) & ~Q(nif=""),
                name="company_kyc_unique_nif",
            ),
            UniqueConstraint(
                fields=["id_nat"],
                condition=Q(id_nat__isnull=False) & ~Q(id_nat=""),
                name="company_kyc_unique_id_nat",
            ),
        ]


class CompanyDocument(models.Model):
    """Model to store multiple documents for a company KYC"""

    DOCUMENT_TYPES = [
        ("rccm", "RCCM Document"),
        ("nif", "NIF Document"),
        ("id_nat", "ID National"),
        ("statutes", "Company Statutes"),
        ("registration", "Registration Certificate"),
        ("other", "Other Document"),
    ]

    company_kyc = models.ForeignKey(
        CompanyKYC, on_delete=models.CASCADE, related_name="documents"
    )
    document_type = models.CharField(
        max_length=20, choices=DOCUMENT_TYPES, default="other"
    )
    document = models.FileField(
        upload_to=company_document_upload_path,
        storage=(
            PrivateMediaStorage() if getattr(settings, "USE_SPACES", False) else None
        ),
    )
    document_name = models.CharField(max_length=255, blank=True)
    is_verified = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.company_kyc.company_name} - {self.get_document_type_display()}"

    class Meta:
        unique_together = ["company_kyc", "document_type"]
        indexes = [
            models.Index(fields=["company_kyc", "document_type"]),
            models.Index(fields=["is_verified", "uploaded_at"]),
        ]
        ordering = ["-uploaded_at"]


def starlink_kit_image_upload_path(instance, filename):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    kit_slug = slugify(instance.name or "unknown_kit")
    ext = os.path.splitext(filename)[-1]
    return f"kits/{kit_slug}/images/kit_image_{timestamp}{ext}"


# KitType model removed - merged into StarlinkKit for performance optimization

# Kit type choices constant (moved from KitType model)
KIT_TYPE_CHOICES = [
    ("standard", "Standard Kit"),
    ("mini", "Mini Kit"),
]


class StarlinkKit(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    model = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    base_price_usd = models.DecimalField(max_digits=10, decimal_places=2)
    picture = models.FileField(
        upload_to=starlink_kit_image_upload_path, blank=True, null=True
    )

    # === TYPE DE KIT (CharField pour performance) ===
    KIT_TYPE_CHOICES = [
        ("standard", "Standard Kit"),
        ("mini", "Mini Kit"),
    ]

    kit_type = models.CharField(
        max_length=20,
        choices=KIT_TYPE_CHOICES,
        blank=False,
        null=False,
        help_text="Type of Starlink kit - required field",
    )
    is_active = models.BooleanField(default=True)

    # (Remove the clean method entirely; no replacement lines needed)
    def save(self, *args, validate=False, **kwargs):
        """
        Override save to optionally perform validation.
        Set validate=True to run full_clean() before saving.
        """
        if validate:
            self.full_clean()  # This calls clean() method
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.kit_type}) – ${self.base_price_usd}"

    @property
    def extra_charges(self):
        return ExtraCharge.objects.filter(kit_type_name=self.kit_type, is_active=True)

    @property
    def additional_data_rate(self):
        try:
            return AdditionalDataRate.objects.get(
                kit_type_name=self.kit_type, is_active=True
            )
        except AdditionalDataRate.DoesNotExist:
            return None


class AdditionalDataRate(models.Model):
    kit_type_name = models.CharField(
        max_length=20, choices=KIT_TYPE_CHOICES, default="standard"
    )
    price_per_gb = models.DecimalField(max_digits=6, decimal_places=2)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.kit_type_name}: ${self.price_per_gb}/GB"


class SubscriptionPlan(models.Model):
    PLAN_TYPE_CHOICES = [
        ("unlimited_standard", "Unlimited Standard Data"),
        ("limited_standard", "Limited Standard Data"),
        ("unlimited_with_priority", "Unlimited + Priority Data"),
        ("smart_education", "Smart Education Impact"),
        ("smart_health", "Smart Health / Community Impact"),
    ]

    SITE_TYPE_CHOICES = [
        ("fixed", "Fixed Site"),
        ("portable", "Portable Site"),
        ("flexible", "Flexible Site"),
    ]

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=100)

    # === FUSION AVEC SUBSCRIPTIONCATEGORY ===
    category_name = models.CharField(max_length=100, default="Standard Category")
    category_description = models.TextField(blank=True, default="")
    category_is_active = models.BooleanField(default=True)

    site_type = models.CharField(
        max_length=20,
        choices=SITE_TYPE_CHOICES,
        null=False,
        blank=False,
        help_text="Site type for the subscription plan",
    )

    plan_type = models.CharField(
        max_length=30, choices=PLAN_TYPE_CHOICES, blank=True, null=True
    )
    # Configuration des données
    standard_data_gb = models.IntegerField(
        null=True, blank=True, help_text="GB of standard data (null = unlimited)"
    )
    priority_data_gb = models.IntegerField(
        null=True, blank=True, help_text="GB of priority data included"
    )

    # === MÉTADONNÉES ===
    starlink_plan_code = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Original Starlink plan identifier",
    )
    monthly_price_usd = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Monthly subscription price in USD",
    )
    additional_priority_rate = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Additional rate per GB for priority data beyond included amount",
    )
    display_order = models.IntegerField(default=0, help_text="Display order")
    is_active = models.BooleanField(default=True)
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)

    def __str__(self):
        price_display = self.monthly_price_usd or "N/A"
        return f"{self.name} – {self.kit_type} – ${price_display}"

    @property
    def effective_price(self):
        """Return the effective price for billing"""
        return self.monthly_price_usd

    @property
    def kit_type(self):
        # Pour la compatibilité, on déduit le kit_type du nom de la catégorie
        # Par exemple, si category_name contient "standard", on retourne "standard"
        if "standard" in self.category_name.lower():
            return "standard"
        elif "mini" in self.category_name.lower():
            return "mini"
        else:
            return "standard"  # valeur par défaut

    def get_additional_charges(self):
        """Get all active extra charges for this plan's kit type"""
        return ExtraCharge.objects.filter(kit_type_name=self.kit_type, is_active=True)

    def get_additional_data_rate(self):
        """Get the additional data rate for this plan's kit type"""
        try:
            return AdditionalDataRate.objects.get(
                kit_type_name=self.kit_type, is_active=True
            )
        except AdditionalDataRate.DoesNotExist:
            return None


class ExtraCharge(models.Model):
    CHARGE_TYPE_CHOICES = [
        ("cable_15m", "15m Cable"),
        ("cable_45m", "45m Cable"),
        ("roof_mounting", "Roof Mounting"),
        ("installation", "Installation"),
        ("accessories", "Accessories"),
        ("router", "Router"),
    ]

    kit_type_name = models.CharField(
        max_length=20, choices=KIT_TYPE_CHOICES, default="standard"
    )
    charge_type = models.CharField(max_length=20, choices=CHARGE_TYPE_CHOICES)
    price_usd = models.DecimalField(max_digits=8, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["kit_type_name", "charge_type"]

    def __str__(self):
        return f"{self.kit_type_name} - {self.get_charge_type_display()}: ${self.price_usd}"


class StarlinkKitInventory(models.Model):
    kit_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    serial_number = models.CharField(max_length=100, unique=True, blank=True, null=True)
    model = models.CharField(max_length=50, blank=True, null=True)
    firmware_version = models.CharField(max_length=50, blank=True, null=True)

    objects = StarlinkKitInventoryQuerySet.as_manager()  # For inventory county

    kit = models.ForeignKey(
        StarlinkKit,
        on_delete=models.CASCADE,
        related_name="inventory_items",
        blank=True,
        null=True,
    )
    is_assigned = models.BooleanField(default=False)
    assigned_to_order = models.OneToOneField(
        "Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_kit",
    )

    # ✅ REQUIRED for stock-per-location
    current_location = models.ForeignKey(
        StockLocation,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kits_here",
        help_text="Where this kit currently resides (warehouse/van/customer/RMA, etc.)",
    )

    current_region_name = models.CharField(max_length=120, blank=True, default="")

    # (optional but useful)
    class Condition(models.TextChoices):
        NEW = "new", "New"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        DAMAGED = "damaged", "Damaged"
        SCRAPPED = "scrapped", "Scrapped"

    condition = models.CharField(
        max_length=12, choices=Condition.choices, default=Condition.NEW
    )
    status = models.CharField(
        max_length=20,
        default="available",
        blank=True,
        help_text="Human-readable status (available/assigned/scrapped/etc.)",
    )

    def __str__(self):
        return f"{self.kit_number or self.serial_number or self.pk} ({'Assigned' if self.is_assigned else 'Available'})"

    class Meta:
        indexes = [
            models.Index(fields=["current_location"]),
            models.Index(fields=["status"]),
            models.Index(fields=["condition"]),
        ]


class OptionalService(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    price_usd = models.DecimalField(max_digits=8, decimal_places=2)

    def __str__(self):
        return self.name


class OrderAddOn(models.Model):
    order = models.ForeignKey("Order", related_name="addons", on_delete=models.CASCADE)
    service = models.ForeignKey(OptionalService, on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.order} → {self.service.name}"


# Order Reference NUMBER unique
def generate_short_order_ref():
    """Generate short, unique order reference using base36 timestamp + random suffix."""
    timestamp = int(time.time())  # current time in seconds
    base36_ts = base36_encode(timestamp)
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=3))
    return f"ORD-{base36_ts}{suffix}"


def base36_encode(number):
    """Encodes an integer into a base36 string."""
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    base36 = ""
    while number > 0:
        number, i = divmod(number, 36)
        base36 = chars[i] + base36
    return base36 or "0"


class Order(models.Model):
    # Custom manager with expiry-aware queryset helpers
    objects = OrderManager()

    ORDER_STATUS_CHOICES = [
        ("pending_payment", "Pending payment"),
        ("awaiting_confirmation", "Awaiting confirmation"),
        ("fulfilled", "Fulfilled"),
        ("cancelled", "Cancelled"),
        ("failed", "Failed"),
    ]

    PAYMENT_METHOD_CHOICES = [
        ("mobile", "Mobile Money"),
        ("bank_transfer", "Bank Transfer"),
        ("book_my_kit", "Book My Kit (Cash)"),
    ]

    PAYMENT_STATUS_CHOICES = [
        ("unpaid", "Unpaid"),
        ("awaiting_confirmation", "Awaiting confirmation"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]

    user = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        related_name="kit_orders",
        blank=True,
        null=True,
    )
    kit_inventory = models.OneToOneField(
        "StarlinkKitInventory", on_delete=models.SET_NULL, null=True, blank=True
    )
    plan = models.ForeignKey(
        "SubscriptionPlan", on_delete=models.SET_NULL, null=True, blank=True
    )

    region = models.ForeignKey(
        "geo_regions.Region",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Resolved region for this order",
    )
    sales_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="orders_as_sales",
    )

    latitude = models.FloatField(blank=True, null=True)
    longitude = models.FloatField(blank=True, null=True)

    total_price = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )

    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES, blank=True, null=True
    )
    payment_status = models.CharField(
        max_length=30, choices=PAYMENT_STATUS_CHOICES, default="unpaid"
    )
    proof_of_payment = models.FileField(upload_to="pop_uploads/", blank=True, null=True)

    status = models.CharField(
        max_length=50, choices=ORDER_STATUS_CHOICES, default="pending_payment"
    )
    created_at = models.DateTimeField(auto_now_add=True, blank=True, null=True)

    # Who initiated the order
    created_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="created_orders",
    )

    # ✅ Set ONLY by the view (do not compute in the model)
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Absolute expiry timestamp set by the view; the model never computes it.",
    )

    cancelled_reason = models.CharField(max_length=255, blank=True, default="")

    # Renewal flag
    is_subscription_renewal = models.BooleanField(
        default=False,
        help_text="True if this order was created to renew an existing subscription",
    )

    # Optional payment hold window (if used elsewhere)
    payment_hold_until = models.DateTimeField(null=True, blank=True)

    # Unique order reference
    order_reference = models.CharField(
        max_length=20, unique=True, editable=False, blank=True, null=True, db_index=True
    )

    delivery_date = models.DateTimeField(blank=True, null=True)
    delivered_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="delivered_orders",
    )
    is_installed = models.BooleanField(default=False)
    installation_date = models.DateTimeField(blank=True, null=True)
    installed_by = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installed_orders",
    )

    selected_extra_charges = models.ManyToManyField(
        ExtraCharge, blank=True, help_text="Extra charges selected for this order"
    )

    def __str__(self):
        name = None
        if self.user:
            # Prefer a real name if available, fall back to email, then “Guest”
            name = (
                getattr(self.user, "get_full_name", lambda: None)()
                or getattr(self.user, "full_name", None)
                or getattr(self.user, "email", None)
            )
        return f"Order {self.order_reference or '#'+str(self.id)} by {name or 'Guest'}"

    # ---------- Convenience ----------
    @property
    def is_tax_exempt(self) -> bool:
        """Read-only convenience; don’t store a duplicate flag on Order."""
        return bool(
            getattr(getattr(self.user, "profile", None), "is_tax_exempt", False)
        )

    @property
    def expires_at_iso(self):
        """Convenience for JSON responses."""
        return self.expires_at.isoformat() if self.expires_at else None

    def is_expired(self) -> bool:
        return bool(self.expires_at and timezone.now() >= self.expires_at)

    def start_subscription_payment_hold(self, days: int = 7):
        """Give the customer more time to pay (separate from expires_at)."""
        self.status = "pending_payment"
        self.payment_hold_until = timezone.now() + timezone.timedelta(days=days)
        self.save(update_fields=["status", "payment_hold_until"])

    # ---------- Persistence ----------
    def _ensure_reference(self):
        """Generate a unique short reference if missing."""
        if self.order_reference:
            return
        while True:
            ref = generate_short_order_ref()
            if not type(self).objects.filter(order_reference=ref).exists():
                self.order_reference = ref
                break

    def save(self, *args, **kwargs):
        """
        Keep save() side-effect free with respect to pricing:
        - DO NOT recompute totals here (call price_order in your service/view).
        - Still handle operational transitions (e.g., paid -> create InstallationActivity).
        """
        _prev_status = None
        prev_payment_status = None
        if self.pk:
            try:
                prev = (
                    type(self).objects.only("status", "payment_status").get(pk=self.pk)
                )
                _prev_status = prev.status
                prev_payment_status = prev.payment_status
            except type(self).DoesNotExist:
                pass

        self._ensure_reference()
        super().save(*args, **kwargs)

        # Operational hook: when payment flips to 'paid', create only SiteSurvey
        # InstallationActivity will be created only after survey approval
        if self.payment_status == "paid" and prev_payment_status != "paid":
            # Create a SiteSurvey for the order with initial coordinates from the order
            from site_survey.models import SiteSurvey

            site_survey, created = SiteSurvey.objects.get_or_create(
                order=self,
                defaults={
                    "survey_latitude": self.latitude,
                    "survey_longitude": self.longitude,
                    "survey_address": getattr(self, "address", ""),
                    "status": "scheduled",
                },
            )

    # ---------- Cancellations ----------
    def cancel(self, reason: str = "cancelled"):
        """
        Cancel this order and unlink it from all related operational tables.
        - Transactional and idempotent: safe to call multiple times.
        - Does NOT delete the Order or financial/audit records (invoices, wallet tx).
        - Unassigns inventory, closes technician assignments, cancels installation flow,
          clears M2M add-ons/extras, marks pending payment attempts as cancelled,
          and unlinks invoice-order mapping rows.

        Returns a detailed metrics dict describing the performed actions.
        """
        using = self._state.db or "default"

        # Track metrics
        freed_inventory = False
        movements_deleted = 0
        tech_assign_closed = 0
        subscription_cancelled = False
        installation_cancelled = False
        survey_cancelled = False
        attempts_marked_cancelled = 0
        addons_deleted = 0
        extras_cleared = 0
        invoice_links_unlinked = 0

        already_cancelled = self.status == "cancelled"

        with transaction.atomic(using=using):
            inv = None
            # --- Inventory release + movements cleanup ---
            # ALWAYS try to load and free inventory, even if FK is already None
            # (it may have been set to None elsewhere but inventory still marked as assigned)
            if self.kit_inventory_id:
                try:
                    inv = (
                        StarlinkKitInventory.objects.select_for_update()
                        .using(using)
                        .get(pk=self.kit_inventory_id)
                    )
                except StarlinkKitInventory.DoesNotExist:
                    # Inventory was deleted elsewhere; just clean up movements
                    inv = None

            if inv:
                base_q = StarlinkKitMovement.objects.using(using)
                # Delete movements tied to this order and assignment movements for this inventory
                deleted_by_order = base_q.filter(order_id=self.id).delete()[0]
                deleted_by_inv = base_q.filter(
                    inventory_item=inv,
                    movement_type="assigned",
                ).delete()[0]
                movements_deleted += deleted_by_order + deleted_by_inv

                # Close any active technician assignment for this inventory
                tech_assign_qs = (
                    TechnicianAssignment.objects.using(using)
                    .select_for_update()
                    .filter(inventory_item=inv, is_active=True)
                )
                tech_assign_closed += tech_assign_qs.update(
                    is_active=False, returned_at=timezone.now()
                )

                inv.is_assigned = False
                inv.assigned_to_order = None
                inv.status = "available"  # Explicitly mark as available again
                inv.save(
                    update_fields=["is_assigned", "assigned_to_order", "status"],
                    using=using,
                )
                freed_inventory = True

                # Clear the FK on the order row (even if already cancelled)
                type(self).objects.using(using).filter(pk=self.pk).update(
                    kit_inventory=None
                )
            else:
                # No inventory link found; still ensure no stray movements remain
                movements_deleted += (
                    StarlinkKitMovement.objects.using(using)
                    .filter(order_id=self.id)
                    .delete()[0]
                )

            # --- Subscription cleanup (delete when order is cancelled) ---
            subscriptions_deleted = 0
            sub = getattr(self, "subscription", None)
            try:
                # Prefer hard delete of any subscription(s) tied to this order.
                # OneToOne guarantees at most one, but we’re defensive here.
                if sub is not None:
                    sub_id = sub.id
                    try:
                        sub.delete(using=using)
                        subscriptions_deleted += 1
                    except Exception:
                        # Fallback to soft-cancel if deletion blocked by constraints
                        sub.status = "cancelled"
                        sub.ended_at = timezone.now().date()
                        sub.save(update_fields=["status", "ended_at"], using=using)
                        subscription_cancelled = True
                else:
                    # If reverse accessor is missing, try a direct queryset (defensive)
                    for s in Subscription.objects.using(using).filter(order=self):
                        try:
                            s.delete(using=using)
                            subscriptions_deleted += 1
                        except Exception:
                            s.status = "cancelled"
                            s.ended_at = timezone.now().date()
                            s.save(update_fields=["status", "ended_at"], using=using)
                            subscription_cancelled = True
            except Exception:
                # Never fail order cancellation if subscription deletion has issues
                pass

            # --- Installation activity / site survey cancellation ---
            try:
                ia = self.installation_activity
            except InstallationActivity.DoesNotExist:
                ia = None
            if ia and ia.status != "cancelled":
                ia.status = "cancelled"
                ia.save(update_fields=["status"], using=using)
                installation_cancelled = True

            # SiteSurvey may be in a different app; cancel if present
            try:
                from site_survey.models import (
                    SiteSurvey,
                )  # local import to avoid circular

                survey = SiteSurvey.objects.using(using).filter(order=self).first()
                if survey and getattr(survey, "status", None) != "cancelled":
                    survey.status = "cancelled"
                    survey.save(update_fields=["status"], using=using)
                    survey_cancelled = True
            except Exception:
                # Best-effort: absence of app/model should not fail cancellation
                pass

            # --- Payments: mark non-success attempts as cancelled (keep history) ---
            try:
                pa_qs = self.payment_attempts.using(using).exclude(
                    status__in=["completed", "succeeded", "paid"]
                )  # type: ignore[attr-defined]
                attempts_marked_cancelled += pa_qs.update(status="cancelled")
            except Exception:
                pass

            # --- Sales content: M2M extras and add-ons ---
            try:
                # Clear M2M selections
                before = self.selected_extra_charges.count()
                self.selected_extra_charges.clear()
                extras_cleared = before if before else 0
            except Exception:
                pass

            try:
                # OrderAddOn rows are config items; safe to delete to remove linkage
                addons_deleted += self.addons.using(using).all().delete()[0]  # type: ignore[attr-defined]
            except Exception:
                pass

            # --- Invoices mapping: unlink, do not delete invoices ---
            try:
                # Delete link rows (InvoiceOrder has order=PROTECT, non-null)
                invoice_links_unlinked += (
                    InvoiceOrder.objects.using(using).filter(order=self).delete()[0]
                )
                # Nullify optional traces on invoice lines
                InvoiceLine.objects.using(using).filter(
                    models.Q(order=self) | models.Q(order_line__order=self)
                ).update(order=None)
            except Exception:
                pass

            # --- Mark order itself (do not revert if already cancelled) ---
            # Per spec: keep payment_status='unpaid' when cancelling an unpaid order due to payment failure/expiry.
            # If the order was already paid, we won't alter payment_status here.
            new_payment_status = (
                "unpaid" if self.payment_status != "paid" else self.payment_status
            )
            if not already_cancelled:
                type(self).objects.using(using).filter(pk=self.pk).update(
                    status="cancelled",
                    payment_status=new_payment_status,
                    cancelled_reason=(reason or ""),
                    expires_at=None,
                    kit_inventory=None,
                )
            else:
                # Ensure payment_status reflects cancellation for unpaid orders and clear expiry anyway
                type(self).objects.using(using).filter(pk=self.pk).update(
                    payment_status=new_payment_status,
                    cancelled_reason=(reason or self.cancelled_reason or ""),
                    expires_at=None,
                    kit_inventory=None,
                )

        # --- Order-level audit event ---
        try:
            evt_type = (
                "manual_cancel"
                if (reason or "").startswith("manual")
                else "auto_cancel"
            )
            OrderEvent.objects.create(
                order=self,
                event_type=evt_type,
                message=(reason or "cancelled"),
                payload={
                    "freed_inventory": freed_inventory,
                    "movements_deleted": movements_deleted,
                    "tech_assign_closed": tech_assign_closed,
                    "subscriptions_deleted": subscriptions_deleted,
                    "subscription_cancelled": subscription_cancelled,
                    "installation_cancelled": installation_cancelled,
                    "survey_cancelled": survey_cancelled,
                    "attempts_marked_cancelled": attempts_marked_cancelled,
                    "addons_deleted": addons_deleted,
                    "extras_cleared": extras_cleared,
                    "invoice_links_unlinked": invoice_links_unlinked,
                },
            )
        except Exception:
            pass

        return {
            "changed": not already_cancelled,
            "freed_inventory": freed_inventory,
            "movements_deleted": movements_deleted,
            "tech_assign_closed": tech_assign_closed,
            "subscriptions_deleted": subscriptions_deleted,
            "subscription_cancelled": subscription_cancelled,
            "installation_cancelled": installation_cancelled,
            "survey_cancelled": survey_cancelled,
            "attempts_marked_cancelled": attempts_marked_cancelled,
            "addons_deleted": addons_deleted,
            "extras_cleared": extras_cleared,
            "invoice_links_unlinked": invoice_links_unlinked,
        }


class OrderLine(models.Model):
    class Kind(models.TextChoices):
        KIT = "kit", "Kit"
        PLAN = "plan", "Subscription Plan"
        EXTRA = "extra", "Extra Charge"
        INSTALL = "install", "Installation Fee"
        ADJUST = "adjust", "Adjustment/Discount"

    order = models.ForeignKey(Order, related_name="lines", on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    description = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Optional traceability links (don’t enforce, just for referential context)
    kit_inventory = models.ForeignKey(
        "StarlinkKitInventory", on_delete=models.SET_NULL, null=True, blank=True
    )
    plan = models.ForeignKey(
        "SubscriptionPlan", on_delete=models.SET_NULL, null=True, blank=True
    )
    extra_charge = models.ForeignKey(
        "ExtraCharge", on_delete=models.SET_NULL, null=True, blank=True
    )

    def save(self, *args, **kwargs):
        self.line_total = (self.unit_price or Decimal("0.00")) * Decimal(
            self.quantity or 0
        )
        super().save(*args, **kwargs)


class OrderTax(models.Model):
    class Kind(models.TextChoices):
        VAT = "VAT", "VAT"
        EXCISE = "EXCISE", "Excise"

    order = models.ForeignKey(Order, related_name="taxes", on_delete=models.CASCADE)
    kind = models.CharField(max_length=20, choices=Kind.choices)
    rate = models.DecimalField(max_digits=6, decimal_places=2)  # snapshot %
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # snapshot $


class StarlinkKitMovement(models.Model):
    MOVEMENT_TYPE_CHOICES = [
        ("received", "Received"),  # Kit added to stock
        ("assigned", "Assigned to Order"),  # Sent to customer
        ("returned", "Returned"),  # Returned by customer
        ("transferred", "Transferred"),  # Moved between locations
        ("scrapped", "Scrapped / Defective"),  # Removed from usable stock
        ("adjusted", "Inventory Adjustment"),  # Manual count correction
    ]

    inventory_item = models.ForeignKey(
        "StarlinkKitInventory",
        on_delete=models.CASCADE,
        related_name="movements",
        blank=True,
        null=True,
    )
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    timestamp = models.DateTimeField(default=timezone.now)
    location = models.CharField(max_length=100, blank=True, null=True)
    note = models.TextField(blank=True, null=True)

    order = models.ForeignKey(
        Order,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kit_movements",
        help_text="Optional: Order associated with this movement",
    )

    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="User who recorded this movement",
    )

    class Meta:
        verbose_name = "Starlink Kit Movement"
        verbose_name_plural = "Starlink Kit Movements"
        ordering = ["-timestamp"]

    def __str__(self):
        parts = [
            f"Kit: {self.inventory_item.kit_number}",
            f"Action: {self.get_movement_type_display()}",
            f"Location: {self.location or '—'}",
            f"By: {self.created_by.username if self.created_by else 'System'}",
            f"At: {self.timestamp.strftime('%Y-%m-%d %H:%M')}",
        ]
        return " | ".join(parts)


class InstallationFee(models.Model):
    region = models.ForeignKey(
        "geo_regions.Region",
        on_delete=models.CASCADE,
        related_name="installation_fees",
        null=True,
        blank=True,
    )
    amount_usd = models.DecimalField(max_digits=8, decimal_places=2)

    class Meta:
        unique_together = ["region"]

    def __str__(self):
        return f"{self.region.name}: ${self.amount_usd}"


class TaxRate(models.Model):
    TAX_CHOICES = [
        ("VAT", "VAT"),
        ("EXCISE", "Excise"),
        ("CUSTOMS", "Customs Duty"),
        ("SERVICE", "Service Tax"),
        ("OTHER", "Other"),
    ]

    description = models.CharField(
        max_length=50,
        choices=TAX_CHOICES,
        default="VAT",
    )
    percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Enter percentage value, e.g. 16.00 for 16%",
    )

    def __str__(self):
        return f"{self.get_description_display()} - {self.percentage}%"


class PaymentMethod(models.Model):
    METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("MOBILE_MONEY", "Mobile Money"),
        ("CREDIT_CARD", "Credit Card"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("PAYPAL", "PayPal"),
    ]

    name = models.CharField(
        max_length=50, choices=METHOD_CHOICES, unique=True, blank=True, null=True
    )
    description = models.TextField(blank=True, null=True)
    enabled = models.BooleanField(default=True, verbose_name=("Is Enabled"))

    def __str__(self):
        return self.get_name_display()


class APIEndpoint(models.Model):
    ENVIRONMENT_CHOICES = [
        ("production", "Production"),
        ("staging", "Staging"),
        ("sandbox", "Sandbox"),
    ]
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable name (e.g. 'FlexPay Mobile Money')",
    )
    code = models.CharField(
        max_length=50,
        unique=True,
        help_text="Unique identifier (e.g. 'flexpay_mobile')",
    )
    url = models.URLField(help_text="Full API endpoint URL")
    method = models.CharField(
        max_length=10, default="POST", help_text="HTTP method (GET, POST, etc.)"
    )
    environment = models.CharField(
        max_length=20, choices=ENVIRONMENT_CHOICES, default="production"
    )
    active = models.BooleanField(default=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "API Endpoint"
        verbose_name_plural = "API Endpoints"

    def __str__(self):
        return f"{self.name} ({self.environment})"


class PaymentAttempt(models.Model):
    # Inside PaymentAttempt model
    PAYMENT_TYPE_CHOICES = [
        ("mobile", "Mobile Money"),
        ("card", "Card Payment"),
        ("cash", "Cash Payment"),
        ("terminal", "Terminal"),
    ]

    PAYMENT_FOR_CHOICES = [
        ("hardware", "Hardware"),
        ("subscription", "Subscription"),
    ]

    order = models.ForeignKey(
        "Order", on_delete=models.CASCADE, related_name="payment_attempts"
    )

    # FlexPay transaction identifiers
    code = models.CharField(
        max_length=100, blank=True, null=True
    )  # FlexPay response code
    reference = models.CharField(
        max_length=100, blank=True, null=True, unique=False
    )  # Your internal reference
    provider_reference = models.CharField(
        max_length=100, blank=True, null=True
    )  # FlexPay provider ref
    order_number = models.CharField(
        max_length=100, unique=True, blank=True, null=True
    )  # FlexPay generated ID

    # Transaction details
    amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    amount_customer = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True
    )
    currency = models.CharField(max_length=10, blank=True, null=True)
    status = models.CharField(
        max_length=20, blank=True, null=True
    )  # e.g. 'success', 'failed', 'pending'
    payment_type = models.CharField(
        max_length=50,
        choices=PAYMENT_TYPE_CHOICES,
        default="mobile",
        help_text="Type of payment attempted (mobile or card)",
    )
    payment_for = models.CharField(
        max_length=50,
        choices=PAYMENT_FOR_CHOICES,
        default="",
        help_text="What this payment is for",
    )

    # Metadata
    transaction_time = models.DateTimeField(
        blank=True, null=True
    )  # FlexPay createdAt timestamp
    raw_payload = models.JSONField(
        blank=True, null=True
    )  # Full JSON body for audit/debug

    created_at = models.DateTimeField(auto_now_add=True)
    # NEW FIELD: Link to the user who processed the payment
    processed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="processed_payments",
    )

    # Auditing: when and by whom a probe was last triggered
    last_probed_at = models.DateTimeField(null=True, blank=True)
    last_probed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_probes",
    )

    def __str__(self):
        return f"PaymentAttempt #{self.id} for Order {self.order.order_reference or self.order.id}"

    @property
    def is_successful(self):
        return self.status == "completed"


class Subscription(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("suspended", "Suspended"),
        ("cancelled", "Cancelled"),
    ]

    BILLING_CYCLE_CHOICES = [
        ("monthly", "Monthly"),
        ("quarterly", "Quarterly"),
        ("yearly", "Yearly"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="active_subscriptions",
        blank=True,
        null=True,
    )
    plan = models.ForeignKey(
        SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True
    )
    region = models.ForeignKey(
        "geo_regions.Region",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions",
        help_text="Resolved region for this subscription",
    )
    sales_agent = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="subscriptions_as_sales",
    )
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="active", blank=True, null=True
    )
    billing_cycle = models.CharField(
        max_length=20, choices=BILLING_CYCLE_CHOICES, default="monthly"
    )
    started_at = models.DateField(blank=True, null=True)
    next_billing_date = models.DateField(blank=True, null=True)
    last_billed_at = models.DateField(blank=True, null=True)
    ended_at = models.DateField(null=True, blank=True)
    order = models.OneToOneField(
        Order, on_delete=models.SET_NULL, null=True, blank=True
    )
    plus_code = models.CharField(max_length=64, blank=True, default="")
    # Flag set when an activation request has been created for the linked order/subscription
    activation_requested = models.BooleanField(
        default=False,
        help_text="True when an activation request has been created for this subscription",
    )
    activation_requested = models.BooleanField(
        default=False,
        help_text="Has the user requested activation for this subscription?",
    )

    def __str__(self):
        return f"{self.plan.name} for {self.user.full_name} – {self.status}"

    def save(self, *args, **kwargs):
        """
        Compute and persist plus_code for the subscription when missing.
        Prefer coordinates from the linked Order (order.latitude/order.longitude).
        If openlocationcode is not available, proceed without computing.
        """
        if (
            not self.plus_code or self.plus_code.strip() == ""
        ) and self.order is not None:
            try:
                lat = getattr(self.order, "latitude", None)
                lng = getattr(self.order, "longitude", None)
                if lat is not None and lng is not None and olc is not None:
                    self.plus_code = olc.encode(float(lat), float(lng))
            except Exception:
                # Don't fail the save if encoding fails
                pass
        super().save(*args, **kwargs)

    def get_payment_attempts(self):
        if self.order:
            return self.order.payment_attempts.filter(
                payment_for="subscription"
            ).order_by("-created_at")
        return PaymentAttempt.objects.none()


def installation_photo_upload_path(instance, filename):
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    order_slug = slugify(
        instance.installation_activity.order.order_reference
        or f"order_{instance.installation_activity.order.id}"
    )
    install_date = (
        instance.installation_activity.completed_at
        or instance.installation_activity.started_at
        or timezone.now()
    ).strftime("%Y%m%d")
    ext = os.path.splitext(filename)[-1]
    return f"installation_photos/{order_slug}/{install_date}/install_photo_{timestamp}{ext}"


class InstallationActivity(models.Model):
    """
    Activité d'installation complète pour un job assigné à un technicien.
    Ce modèle capture tous les détails de l'installation sur site.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("submitted", "Submitted (Under Review)"),
        ("validated", "Validated"),
    ]

    # ===== Relations de base =====
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name="installation_activity"
    )
    technician = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="installations",
    )

    # ===== Champs de base =====
    planned_at = models.DateField(blank=True, null=True)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    location_confirmed = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    # ===== STEP 1: Job & Site =====
    on_site_arrival = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Heure d'arrivée du technicien sur site (local)",
    )
    site_address = models.TextField(
        blank=True, help_text="Adresse complète du site d'installation"
    )
    site_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text="Latitude GPS du site",
    )
    site_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
        help_text="Longitude GPS du site",
    )

    ACCESS_LEVEL_CHOICES = [
        ("easy", "Easy"),
        ("moderate", "Moderate"),
        ("difficult", "Difficult"),
    ]
    access_level = models.CharField(
        max_length=20,
        choices=ACCESS_LEVEL_CHOICES,
        blank=True,
        help_text="Niveau d'accès au site",
    )

    POWER_AVAILABILITY_CHOICES = [
        ("stable", "Stable"),
        ("intermittent", "Intermittent"),
        ("unavailable", "Unavailable"),
    ]
    power_availability = models.CharField(
        max_length=20,
        choices=POWER_AVAILABILITY_CHOICES,
        blank=True,
        help_text="Disponibilité de l'alimentation électrique",
    )
    site_notes = models.TextField(
        blank=True, help_text="Notes sur le site (sécurité, toit, dangers, etc.)"
    )

    # ===== STEP 2: Equipment - CPE Details =====
    dish_serial_number = models.CharField(
        max_length=100, blank=True, help_text="Numéro de série de l'antenne"
    )
    router_serial_number = models.CharField(
        max_length=100, blank=True, help_text="Numéro de série du routeur"
    )
    firmware_version = models.CharField(
        max_length=50, blank=True, help_text="Version du firmware installé"
    )

    POWER_SOURCE_CHOICES = [
        ("main_ac", "Main AC"),
        ("generator", "Generator"),
        ("solar", "Solar"),
        ("ups", "UPS"),
    ]
    power_source = models.CharField(
        max_length=20,
        choices=POWER_SOURCE_CHOICES,
        blank=True,
        help_text="Source d'alimentation principale",
    )
    cable_length = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Longueur du câble en mètres",
    )
    splices_connectors = models.PositiveIntegerField(
        null=True, blank=True, help_text="Nombre d'épissures/connecteurs"
    )

    # ===== STEP 2: Equipment - LAN / Wi-Fi =====
    wifi_ssid = models.CharField(
        max_length=100, blank=True, help_text="SSID du réseau Wi-Fi"
    )
    wifi_password = models.CharField(
        max_length=100, blank=True, help_text="Mot de passe Wi-Fi"
    )
    lan_ip = models.GenericIPAddressField(
        protocol="IPv4", null=True, blank=True, help_text="Adresse IP LAN"
    )
    dhcp_range = models.CharField(
        max_length=50, blank=True, help_text="Plage DHCP (ex: .100 - .200)"
    )

    # ===== STEP 3: Mount & Alignment =====
    MOUNT_TYPE_CHOICES = [
        ("roof", "Roof"),
        ("wall", "Wall"),
        ("ground_pole", "Ground Pole"),
        ("tripod", "Tripod"),
    ]
    mount_type = models.CharField(
        max_length=20,
        choices=MOUNT_TYPE_CHOICES,
        blank=True,
        help_text="Type de montage",
    )
    mount_height = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Hauteur du montage en mètres",
    )

    GROUNDING_CHOICES = [
        ("yes", "Yes"),
        ("no", "No"),
        ("na", "N/A"),
    ]
    grounding = models.CharField(
        max_length=10,
        choices=GROUNDING_CHOICES,
        blank=True,
        help_text="Mise à la terre effectuée",
    )

    WEATHERPROOFING_CHOICES = [
        ("taped", "Taped"),
        ("sealed", "Sealed"),
        ("conduit", "Conduit"),
        ("na", "N/A"),
    ]
    weatherproofing = models.CharField(
        max_length=20,
        choices=WEATHERPROOFING_CHOICES,
        blank=True,
        help_text="Méthode d'étanchéité",
    )
    obstruction_percentage = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MaxValueValidator(100)],
        help_text="Pourcentage d'obstruction (0-100%)",
    )
    elevation_angle = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Angle d'élévation en degrés",
    )
    azimuth_angle = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Angle azimut en degrés",
    )
    obstruction_notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Notes sur les obstructions (arbres, bâtiments, etc.)",
    )
    mounting_notes = models.TextField(
        blank=True, help_text="Notes sur le montage (ancrage, scellant, contraintes)"
    )

    # ===== STEP 4: Environment & Safety =====
    WEATHER_CONDITIONS_CHOICES = [
        ("sunny", "Sunny"),
        ("cloudy", "Cloudy"),
        ("rainy", "Rainy"),
        ("windy", "Windy"),
        ("stormy", "Stormy"),
        ("other", "Other"),
    ]
    weather_conditions = models.CharField(
        max_length=20,
        choices=WEATHER_CONDITIONS_CHOICES,
        blank=True,
        help_text="Conditions météo pendant l'installation",
    )

    # Safety Equipment (stored as boolean fields)
    safety_helmet = models.BooleanField(default=False, help_text="Casque utilisé")
    safety_harness = models.BooleanField(default=False, help_text="Harnais utilisé")
    safety_gloves = models.BooleanField(default=False, help_text="Gants utilisés")
    safety_ladder = models.BooleanField(
        default=False, help_text="Sécurité échelle respectée"
    )

    hazards_noted = models.TextField(
        blank=True,
        help_text="Dangers notés (électrique, instabilité toit, animaux, etc.)",
    )

    # ===== STEP 5: Cabling & Routing =====
    CABLE_ENTRY_CHOICES = [
        ("wall_drilled", "Wall Drilled"),
        ("window_feed", "Window Feed"),
        ("conduit", "Conduit"),
        ("existing_duct", "Existing Duct"),
    ]
    cable_entry_point = models.CharField(
        max_length=20,
        choices=CABLE_ENTRY_CHOICES,
        blank=True,
        help_text="Point d'entrée du câble",
    )

    CABLE_PROTECTION_CHOICES = [
        ("conduit", "Conduit"),
        ("trunking", "Trunking"),
        ("uv_protected", "UV Protected"),
        ("none", "None"),
    ]
    cable_protection = models.CharField(
        max_length=20,
        choices=CABLE_PROTECTION_CHOICES,
        blank=True,
        help_text="Protection du câble",
    )

    TERMINATION_TYPE_CHOICES = [
        ("rj45", "RJ45"),
        ("poe_injector", "POE Injector"),
        ("direct", "Direct"),
        ("other", "Other"),
    ]
    termination_type = models.CharField(
        max_length=20,
        choices=TERMINATION_TYPE_CHOICES,
        blank=True,
        help_text="Type de terminaison",
    )
    routing_notes = models.CharField(
        max_length=255,
        blank=True,
        help_text="Notes sur le cheminement (chemin, pénétrations, scellant)",
    )

    # ===== STEP 6: Power & Backup =====
    POWER_STABILITY_CHOICES = [
        ("pass", "Pass"),
        ("fail", "Fail"),
    ]
    power_stability_test = models.CharField(
        max_length=10,
        choices=POWER_STABILITY_CHOICES,
        blank=True,
        help_text="Test de stabilité de l'alimentation",
    )

    UPS_INSTALLED_CHOICES = [
        ("no", "No"),
        ("yes", "Yes"),
    ]
    ups_installed = models.CharField(
        max_length=10,
        choices=UPS_INSTALLED_CHOICES,
        blank=True,
        help_text="UPS/Backup installé",
    )
    ups_model = models.CharField(
        max_length=100, blank=True, help_text="Modèle de l'UPS (si installé)"
    )
    ups_runtime_minutes = models.PositiveIntegerField(
        null=True, blank=True, help_text="Autonomie de l'UPS en minutes"
    )

    # ===== STEP 7: Connectivity & Tests =====
    snr_db = models.DecimalField(
        max_digits=5,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="SNR (Signal-to-Noise Ratio) en dB",
    )
    speed_download_mbps = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Vitesse de téléchargement en Mbps",
    )
    speed_upload_mbps = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
        help_text="Vitesse d'upload en Mbps",
    )
    latency_ms = models.PositiveIntegerField(
        null=True, blank=True, help_text="Latence en millisecondes"
    )
    test_tool = models.CharField(
        max_length=100,
        blank=True,
        help_text="Outil de test utilisé (ex: Fast.com, Ookla)",
    )
    public_ip = models.GenericIPAddressField(
        protocol="IPv4",
        null=True,
        blank=True,
        help_text="Adresse IP publique (si statique)",
    )
    qos_vlan = models.CharField(
        max_length=100,
        blank=True,
        help_text="Configuration QoS/VLAN (ex: VLAN 20, QoS 10Mbps)",
    )

    LINK_STATUS_CHOICES = [
        ("connected", "Connected"),
        ("not_connected", "Not Connected"),
    ]
    final_link_status = models.CharField(
        max_length=20,
        choices=LINK_STATUS_CHOICES,
        blank=True,
        help_text="État final de la connexion",
    )
    test_notes = models.TextField(
        blank=True, help_text="Notes sur les tests (environnement, heure, observations)"
    )

    # ===== STEP 9: Customer Sign-off =====
    customer_full_name = models.CharField(
        max_length=255, blank=True, help_text="Nom complet du client"
    )
    customer_id_document = models.CharField(
        max_length=100,
        blank=True,
        help_text="Numéro de document d'identité du client (optionnel)",
    )
    customer_acceptance = models.BooleanField(
        default=False,
        help_text="Le client confirme que l'installation est complète et fonctionnelle",
    )
    customer_signature = models.TextField(
        blank=True, help_text="Données de signature du client (base64 canvas data)"
    )
    customer_signoff_at = models.DateTimeField(
        null=True, blank=True, help_text="Heure de signature du client"
    )
    customer_rating = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Note d'installation (1-5 étoiles)",
    )
    customer_comments = models.TextField(
        blank=True, help_text="Commentaires du client sur l'installation"
    )

    # ===== Reseller Information =====
    reseller_name = models.CharField(
        max_length=255, blank=True, help_text="Nom du revendeur/partenaire"
    )
    reseller_id = models.CharField(
        max_length=100, blank=True, help_text="ID/Compte du revendeur"
    )

    SLA_TIER_CHOICES = [
        ("standard_48h", "Standard (48h)"),
        ("priority_24h", "Priority (24h)"),
        ("premium_same_day", "Premium (Same-day)"),
    ]
    sla_tier = models.CharField(
        max_length=20, choices=SLA_TIER_CHOICES, blank=True, help_text="Niveau de SLA"
    )
    reseller_notes = models.TextField(
        blank=True,
        help_text="Notes internes (commentaires, références stock, approbations)",
    )

    # ===== Metadata =====
    created_at = models.DateTimeField(auto_now_add=True, help_text="Date de création")
    updated_at = models.DateTimeField(auto_now=True, help_text="Dernière mise à jour")
    submitted_at = models.DateTimeField(
        null=True, blank=True, help_text="Date de soumission finale du rapport"
    )
    is_draft = models.BooleanField(
        default=True, help_text="Rapport en brouillon (non soumis)"
    )

    # ===== Edition Workflow =====
    edit_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date limite pour éditer le rapport après soumission (24h)",
    )
    validated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de validation finale (fin de la période d'édition)",
    )
    version_number = models.PositiveIntegerField(
        default=1, help_text="Numéro de version du rapport (pour l'historique)"
    )
    last_edited_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date de la dernière modification après soumission",
    )
    # Flag to indicate a technician has requested activation for this activity
    activation_requested = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True if an activation request was created for this activity",
    )

    class Meta:
        verbose_name = "Installation Activity"
        verbose_name_plural = "Installation Activities"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "technician"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_draft"]),
            models.Index(fields=["status"]),
            models.Index(fields=["submitted_at"]),
            models.Index(fields=["edit_deadline"]),
            models.Index(fields=["validated_at"]),
        ]

    def save(self, *args, **kwargs):
        """
        Automatically update the status based on timestamps.
        Preserve submitted/validated statuses for edit workflow.
        """
        # Ne pas écraser les statuts du workflow d'édition
        if self.status not in ["submitted", "validated"]:
            if self.completed_at:
                self.status = "completed"
            elif self.started_at:
                self.status = "in_progress"
            elif self.planned_at:
                self.status = "pending"
            else:
                self.status = "pending"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Installation for {self.order.order_reference} – {self.get_status_display()}"

    def mark_as_submitted(self):
        """Marquer le rapport comme soumis et initialiser la période d'édition de 24h"""
        from datetime import timedelta

        self.is_draft = False
        self.submitted_at = timezone.now()
        self.edit_deadline = timezone.now() + timedelta(hours=24)
        self.status = "submitted"
        self.save(update_fields=["is_draft", "submitted_at", "edit_deadline", "status"])

    def can_be_edited(self):
        """Vérifier si le rapport peut encore être édité (dans la fenêtre de 24h)"""
        if self.is_draft:
            return True
        if not self.submitted_at or not self.edit_deadline:
            return False
        return timezone.now() <= self.edit_deadline and self.status == "submitted"

    def time_left_for_editing(self):
        """Retourner le temps restant pour l'édition en heures"""
        if not self.can_be_edited():
            return 0

        # Si c'est un brouillon, il n'y a pas de limite de temps
        if self.is_draft:
            return 24.0  # Retourner 24h pour les brouillons

        # Si edit_deadline n'est pas défini, retourner 0
        if not self.edit_deadline:
            return 0

        time_left = self.edit_deadline - timezone.now()
        return max(0, time_left.total_seconds() / 3600)

    def mark_as_edited(self):
        """Marquer le rapport comme modifié (incrémente la version)"""
        if not self.can_be_edited():
            raise ValueError("Cannot edit report: deadline has passed")

        self.version_number += 1
        self.last_edited_at = timezone.now()
        self.save(update_fields=["version_number", "last_edited_at"])

    def auto_validate_if_expired(self):
        """Valider automatiquement si la période d'édition est expirée"""
        if (
            self.status == "submitted"
            and self.edit_deadline
            and timezone.now() > self.edit_deadline
            and not self.validated_at
        ):
            self.status = "validated"
            self.validated_at = timezone.now()
            self.save(update_fields=["status", "validated_at"])
            return True
        return False


class InstallationPhoto(models.Model):
    PHOTO_TYPE_CHOICES = [
        ("before", "Before"),
        ("after", "After"),
        ("evidence", "Additional Evidence"),
    ]

    installation_activity = models.ForeignKey(
        InstallationActivity, on_delete=models.CASCADE, related_name="photos"
    )
    image = models.ImageField(
        upload_to=installation_photo_upload_path,
        storage=(
            PrivateMediaStorage() if getattr(settings, "USE_SPACES", False) else None
        ),
        blank=True,
        null=True,
    )
    photo_type = models.CharField(
        max_length=10,
        choices=PHOTO_TYPE_CHOICES,
        default="evidence",
        help_text="Type of photo: before, after, or additional evidence",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.installation_activity.order.order_reference} uploaded at {self.uploaded_at}"


# Add this new model to your models.py file to track which kit is assigned to which technician
class TechnicianAssignment(models.Model):
    technician = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="assigned_kits",
        help_text="Technician assigned the kit",
    )
    inventory_item = models.ForeignKey(
        StarlinkKitInventory,
        on_delete=models.CASCADE,
        related_name="technician_assignments",
        help_text="Starlink Kit Inventory item assigned",
    )
    assigned_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="kit_assignments_made",
        help_text="User who made the assignment",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    returned_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    note = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ("technician", "inventory_item")
        verbose_name = "Technician Assignment"
        verbose_name_plural = "Technician Assignments"
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.inventory_item.kit_number} → {self.technician.full_name}"


class BillingAccount(models.Model):
    """
    One per user. Balance is derived from AccountEntry (sum).
    Keep a cached balance if you want later; for now, compute on read.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="billing_account",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Billing Account"
        verbose_name_plural = "Billing Accounts"

    def __str__(self):
        return f"BillingAccount({self.user_id})"

    @property
    def balance_usd(self):
        """
        Positive = amount due (customer owes us).
        Negative = account credit (we owe customer).
        """
        agg = self.entries.aggregate(s=models.Sum("amount_usd"))
        return agg["s"] or Decimal("0.00")

    @property
    def credit_usd(self):
        bal = self.balance_usd
        return abs(bal) if bal < 0 else Decimal("0.00")

    @property
    def due_usd(self):
        bal = self.balance_usd
        return bal if bal > 0 else Decimal("0.00")


class AccountEntry(models.Model):
    """
    Immutable ledger entry for billing.
    +ve amount_usd = charge/debit (invoice, fee, tax)
    -ve amount_usd = credit (payment, refund, credit note)
    """

    ENTRY_TYPES = [
        ("invoice", "Invoice"),
        ("payment", "Payment"),
        ("credit_note", "Credit Note"),
        ("adjustment", "Adjustment"),
        ("tax", "Tax"),
    ]

    account = models.ForeignKey(
        BillingAccount, on_delete=models.CASCADE, related_name="entries", db_index=True
    )
    entry_type = models.CharField(max_length=20, choices=ENTRY_TYPES)
    amount_usd = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=255, blank=True, default="")

    # Optional links to business objects (for traceability)
    order = models.ForeignKey(
        "Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="billing_entries",
    )
    subscription = models.ForeignKey(
        "Subscription",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="billing_entries",
    )
    payment = models.ForeignKey(
        "PaymentAttempt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="entries",
    )

    # Dimensional snapshots (immutable once created)
    region_snapshot = models.ForeignKey(
        "geo_regions.Region",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="account_entries",
    )
    sales_agent_snapshot = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_dim_entries",
    )
    snapshot_source = models.CharField(
        max_length=32,
        default="auto",
        help_text="Origin tag for the captured region/agent (auto, manual, backfill, etc.)",
    )

    # New: period & external reference for idempotency and reporting
    period_start = models.DateField(null=True, blank=True)
    period_end = models.DateField(null=True, blank=True)  # typically exclusive end
    external_ref = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["account", "created_at"]),
            models.Index(fields=["entry_type"]),
            models.Index(fields=["subscription", "period_start", "period_end"]),
            models.Index(fields=["region_snapshot", "created_at"]),
            models.Index(fields=["sales_agent_snapshot", "created_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                check=Q(amount_usd__isnull=False),
                name="acct_entry_amount_not_null",
            ),
            # Prevent duplicate invoices for the same subscription & period
            models.UniqueConstraint(
                fields=["subscription", "entry_type", "period_start", "period_end"],
                condition=Q(entry_type="invoice"),
                name="uniq_invoice_per_subscription_period",
            ),
        ]

    def __str__(self):
        sign = "+" if self.amount_usd >= 0 else "-"
        return f"{self.account_id} {self.entry_type} {sign}${abs(self.amount_usd)}"


class Wallet(models.Model):
    """
    Ultra-simple stored-value wallet:
    - One per user
    - Single running balance in USD (change currency if you need)
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="wallet"
    )
    currency = models.CharField(max_length=10, default="USD")
    balance = models.DecimalField(
        max_digits=14, decimal_places=2, default=Decimal("0.00")
    )
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Wallet"
        verbose_name_plural = "Wallets"

    def __str__(self):
        return f"Wallet({self.user_id}) {self.currency} balance={self.balance}"

    # ---------- Public API ----------

    @transaction.atomic
    def add_funds(self, amount, *, note="", order=None, payment_attempt=None):
        """
        Credit the wallet: increases balance and records a transaction.
        Use credit_for_attempt(...) for idempotent credits tied to a gateway attempt.
        """
        amount = _qmoney(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        WalletTransaction.objects.create(
            wallet=self,
            tx_type=WalletTransaction.Type.CREDIT,
            amount=amount,
            currency=self.currency,
            note=note or "Top-up",
            order=order,
            payment_attempt=payment_attempt,
        )

        type(self).objects.filter(pk=self.pk).update(balance=F("balance") + amount)
        self.refresh_from_db(fields=["balance"])
        return self.balance

    @transaction.atomic
    def charge(self, amount, *, note="", order=None, payment_attempt=None):
        """
        Debit the wallet: decreases balance and records a transaction.
        Raises if insufficient funds.
        """
        amount = _qmoney(amount)
        if amount <= 0:
            raise ValueError("Amount must be positive.")

        # Lock & re-check
        self.refresh_from_db(fields=["balance"])
        if self.balance < amount:
            raise ValueError("Insufficient wallet balance.")

        WalletTransaction.objects.create(
            wallet=self,
            tx_type=WalletTransaction.Type.DEBIT,
            amount=amount,
            currency=self.currency,
            note=note or "Purchase",
            order=order,
            payment_attempt=payment_attempt,
        )

        type(self).objects.filter(pk=self.pk).update(balance=F("balance") - amount)
        self.refresh_from_db(fields=["balance"])
        return self.balance

    @transaction.atomic
    def credit_for_attempt(self, amount, *, note="", order=None, payment_attempt):
        """
        Idempotent credit: only one CREDIT will be recorded per (wallet, payment_attempt).
        Returns (credited: bool, balance: Decimal).
        """
        if not payment_attempt:
            raise ValueError("payment_attempt is required for idempotent credit.")

        # Fast existence check
        exists = self.transactions.filter(
            payment_attempt=payment_attempt, tx_type=WalletTransaction.Type.CREDIT
        ).exists()
        if exists:
            # Nothing to do; return current balance
            self.refresh_from_db(fields=["balance"])
            return False, self.balance

        # Otherwise create the credit via add_funds (records tx + updates balance)
        new_balance = self.add_funds(
            amount,
            note=note,
            order=order,
            payment_attempt=payment_attempt,
        )
        return True, new_balance


class WalletTransaction(models.Model):
    """
    Immutable mini-ledger for a wallet.
    Positive `amount`. Direction is in `tx_type`.
    """

    class Type(models.TextChoices):
        CREDIT = "credit", "Credit"
        DEBIT = "debit", "Debit"

    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    tx_type = models.CharField(max_length=10, choices=Type.choices)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    currency = models.CharField(max_length=10, default="USD")
    note = models.CharField(max_length=120, blank=True, default="")
    # Optional cross-links for reconciliation
    order = models.ForeignKey(
        "Order",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wallet_transactions",
    )
    payment_attempt = models.ForeignKey(
        "PaymentAttempt",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="wallet_transactions",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                check=Q(amount__gt=0), name="wallet_tx_amount_positive"
            ),
            # ✅ Idempotency: only one CREDIT per (wallet, payment_attempt)
            UniqueConstraint(
                fields=["wallet", "payment_attempt"],
                condition=Q(tx_type="credit"),
                name="uniq_wallet_credit_per_attempt",
            ),
        ]

    def __str__(self):
        return f"{self.tx_type} {self.amount} {self.currency} (W{self.wallet_id})"


# Ensure that the customer account has billing activated
@receiver(
    post_save,
    sender=settings.AUTH_USER_MODEL,
    dispatch_uid="ensure_billing_account_once",
)
def ensure_billing_account(sender, instance, created, **kwargs):
    from .models import BillingAccount  # avoid circulars if placed in same file

    if instance is None or instance.pk is None:
        return
    if getattr(instance, "billing_account", None) is not None:
        return
    BillingAccount.objects.get_or_create(user=instance)


# Auto-create a wallet for every user
@receiver(post_save, sender=CompanyDocument)
@receiver(post_delete, sender=CompanyDocument)
def update_document_count(sender, instance, **kwargs):
    """Maintain denormalized document count on CompanyKYC"""
    if instance.company_kyc:
        instance.company_kyc.documents_count = instance.company_kyc.documents.count()
        instance.company_kyc.save(update_fields=["documents_count"])


@receiver(
    post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="ensure_simple_wallet_once"
)
def ensure_simple_wallet(sender, instance, created, **kwargs):
    if not instance or not instance.pk:
        return
    if getattr(instance, "wallet", None) is None:
        Wallet.objects.get_or_create(user=instance)


@receiver(
    post_save, sender=settings.AUTH_USER_MODEL, dispatch_uid="ensure_user_prefs_once"
)
def ensure_user_prefs(sender, instance, created, **kwargs):
    if instance and instance.pk and not hasattr(instance, "prefs"):
        UserPreferences.objects.get_or_create(user=instance)


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PENDING = "pending", "Pending"
        CLOSED = "closed", "Closed"

    class Priority(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    class Category(models.TextChoices):
        TECHNICAL = "technical", "Technical"
        BILLING = "billing", "Billing"
        ACCOUNT = "account", "Account"
        OTHER = "other", "Other"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="tickets",
        db_index=True,
    )
    subject = models.CharField(max_length=200)
    category = models.CharField(
        max_length=20,
        choices=Category.choices,
        default=Category.TECHNICAL,
        db_index=True,
    )
    priority = models.CharField(
        max_length=10,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.OPEN,
        db_index=True,
    )
    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        ordering = ("-updated_at",)
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["status"]),
            models.Index(fields=["category"]),
            models.Index(fields=["priority"]),
        ]

    def __str__(self):
        return f"#{self.pk} · {self.subject}"

    def get_absolute_url(self):
        return reverse("ticket_detail", args=[self.pk])


class BillingConfig(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # Existing
    anchor_day = models.PositiveSmallIntegerField(
        default=20, validators=[MinValueValidator(1), MaxValueValidator(28)]
    )
    prebill_lead_days = models.PositiveSmallIntegerField(
        default=5, validators=[MinValueValidator(0), MaxValueValidator(30)]
    )
    invoice_start_date = models.DateField(null=True, blank=True)

    # NEW — operational flags/knobs
    cutoff_days_before_anchor = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(30)],
        help_text="Days before anchor to enforce service cutoff (e.g. 1 = D-1).",
    )
    auto_suspend_on_cutoff = models.BooleanField(
        default=True,
        help_text="Suspend subscriptions automatically at cutoff if unpaid.",
    )
    auto_apply_wallet = models.BooleanField(
        default=True, help_text="Automatically apply wallet to renewal invoices."
    )
    align_first_cycle_to_anchor = models.BooleanField(
        default=True, help_text="Align a new subscription to the global anchor date."
    )
    first_cycle_included_in_order = models.BooleanField(
        default=True,
        help_text="First month already charged on initial hardware/order invoice.",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):  # pragma: no cover
        return (
            f"BillingConfig(anchor={self.anchor_day}, lead={self.prebill_lead_days}, "
            f"start={self.invoice_start_date}, cutoff={self.cutoff_days_before_anchor})"
        )

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj


class DiscountType(models.TextChoices):
    PERCENT = "percent", "Percent"
    AMOUNT = "amount", "Fixed Amount"


class StackPolicy(models.TextChoices):
    NONE = "none", "No stacking"
    PROMO_THEN_COUPON = "promo_then_coupon", "Promo first, then coupon"
    COUPON_THEN_PROMO = "coupon_then_promo", "Coupon first, then promo"


class Promotion(models.Model):
    """
    Automatic discount if rules match (no code).
    Supports scoping to order line kinds and (optionally) specific ExtraCharge types.
    """

    name = models.CharField(max_length=120, unique=True)
    active = models.BooleanField(default=True)

    # When/where it applies
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    # Targeting (all nullable => global)
    target_plan_types = models.JSONField(
        default=list, blank=True
    )  # ["unlimited_with_priority", ...]
    target_site_types = models.JSONField(
        default=list, blank=True
    )  # ["fixed","portable","flexible"]
    target_plan_ids = models.JSONField(
        default=list, blank=True
    )  # explicit plan ids if needed

    # NEW — scope within the order
    # e.g. ["plan"], ["kit","extra"], ["install"], or ["any"] (default behavior if empty)
    target_line_kinds = models.JSONField(default=list, blank=True)

    # NEW — restrict within EXTRA lines only (uses ExtraCharge.charge_type values)
    # e.g. ["router", "cable_45m", "installation"]
    target_extra_charge_types = models.JSONField(default=list, blank=True)

    # Discount
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT
    )
    value = models.DecimalField(
        max_digits=8, decimal_places=2, help_text="Percent (e.g. 10.00) or fixed USD"
    )

    # Caps & rules
    max_uses_total = models.PositiveIntegerField(null=True, blank=True)
    max_uses_per_user = models.PositiveIntegerField(null=True, blank=True)
    new_customers_only = models.BooleanField(default=False)

    # Stacking
    stack_policy = models.CharField(
        max_length=30,
        choices=StackPolicy.choices,
        default=StackPolicy.PROMO_THEN_COUPON,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["active", "starts_at", "ends_at"]),
            # Optional: Postgres JSON GIN indexes for faster filtering
            GinIndex(fields=["target_plan_types"], name="promo_gin_plan_types"),
            GinIndex(fields=["target_site_types"], name="promo_gin_site_types"),
            GinIndex(fields=["target_plan_ids"], name="promo_gin_plan_ids"),
            GinIndex(fields=["target_line_kinds"], name="promo_gin_line_kinds"),
            GinIndex(
                fields=["target_extra_charge_types"], name="promo_gin_extra_types"
            ),
        ]

    def __str__(self):
        return f"[Promo] {self.name}"

    def is_live(self) -> bool:
        now = timezone.now()
        if not self.active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True

    @property
    def effective_line_scopes(self):
        scopes = self.target_line_kinds or []
        scopes = [s.lower().strip() for s in scopes if s]
        return scopes or ["any"]

    @property
    def has_extra_type_filter(self) -> bool:
        return bool(self.target_extra_charge_types)

    def clean(self):
        # Date window sanity
        if self.starts_at and self.ends_at and self.starts_at >= self.ends_at:
            raise ValidationError({"ends_at": "ends_at must be after starts_at."})

        # Discount value sanity
        if self.discount_type == DiscountType.PERCENT:
            if self.value is None or self.value <= 0 or self.value > 100:
                raise ValidationError({"value": "Percent must be in (0, 100]."})
        else:
            if self.value is None or self.value <= 0:
                raise ValidationError({"value": "Fixed amount must be > 0."})

        # Scope values sanity
        invalid = [
            s
            for s in (self.target_line_kinds or [])
            if s not in PROMO_LINE_SCOPE_VALUES
        ]
        if invalid:
            raise ValidationError(
                {
                    "target_line_kinds": f"Invalid values: {invalid}. Allowed: {sorted(PROMO_LINE_SCOPE_VALUES)}"
                }
            )

        # Types arrays should be lists
        for fld in (
            "target_plan_types",
            "target_site_types",
            "target_plan_ids",
            "target_line_kinds",
            "target_extra_charge_types",
        ):
            val = getattr(self, fld, None)
            if val is not None and not isinstance(val, list):
                raise ValidationError({fld: "Must be a list."})

        # Extra type validation
        if self.target_extra_charge_types:
            bad = [
                x
                for x in self.target_extra_charge_types
                if x not in EXTRA_TYPES_ALLOWED
            ]
            if bad:
                raise ValidationError(
                    {
                        "target_extra_charge_types": f"Unknown extra types: {bad}. Allowed: {EXTRA_TYPES_ALLOWED}"
                    }
                )


class Coupon(models.Model):
    code = models.CharField(max_length=40, unique=True, db_index=True)

    # Status & audit
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_coupons",
    )

    # When/where it applies
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    # Targeting (plan/site/ids)
    target_plan_types = models.JSONField(default=list, blank=True)
    target_site_types = models.JSONField(default=list, blank=True)
    target_plan_ids = models.JSONField(default=list, blank=True)

    # NEW — scope within the order
    target_line_kinds = models.JSONField(default=list, blank=True)

    # NEW — restrict within EXTRA lines only using ExtraCharge.charge_type values
    target_extra_charge_types = models.JSONField(default=list, blank=True)

    # Discount (mutually exclusive)
    discount_type = models.CharField(
        max_length=10, choices=DiscountType.choices, default=DiscountType.PERCENT
    )
    percent_off = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    amount_off = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    # Usage limits
    max_redemptions = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Total times this code can be redeemed (None = unlimited)",
    )
    per_user_limit = models.PositiveIntegerField(
        null=True, blank=True, help_text="Max uses per user (None = unlimited)"
    )

    # Renewal logic
    applies_to_first_n_cycles = models.PositiveIntegerField(null=True, blank=True)

    # Optional minimum cart total
    min_cart_total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Minimum cart total required to apply this coupon.",
    )

    # Stacking
    stack_policy = models.CharField(
        max_length=30,
        choices=StackPolicy.choices,
        default=StackPolicy.PROMO_THEN_COUPON,
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["code"]),
            models.Index(fields=["is_active", "valid_from", "valid_to"]),
            # Optional Postgres JSON GIN indexes
            GinIndex(fields=["target_plan_types"], name="coupon_gin_plan_types"),
            GinIndex(fields=["target_site_types"], name="coupon_gin_site_types"),
            GinIndex(fields=["target_plan_ids"], name="coupon_gin_plan_ids"),
            GinIndex(fields=["target_line_kinds"], name="coupon_gin_line_kinds"),
            GinIndex(
                fields=["target_extra_charge_types"], name="coupon_gin_extra_types"
            ),
        ]
        ordering = ("-created_at",)

    def __str__(self):
        return f"[Coupon] {self.code}"

    # Normalize codes (case-insensitive lookup/uniqueness)
    def save(self, *args, **kwargs):
        if self.code:
            self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    # ---------- Helpers ----------
    @property
    def effective_line_scopes(self):
        scopes = self.target_line_kinds or []
        scopes = [s.lower().strip() for s in scopes if s]
        return scopes or ["any"]

    @property
    def has_extra_type_filter(self) -> bool:
        return bool(self.target_extra_charge_types)

    def redemptions_count(self) -> int:
        return self.redemptions.count()

    def redemptions_count_for_user(self, user) -> int:
        return self.redemptions.filter(user=user).count()

    def can_redeem(self, *, user) -> (bool, str):
        if not self.is_live():
            return False, "Coupon is not active or outside validity window."
        if (
            self.max_redemptions is not None
            and self.redemptions_count() >= self.max_redemptions
        ):
            return False, "Coupon redemption limit reached."
        if (
            self.per_user_limit is not None
            and self.redemptions_count_for_user(user) >= self.per_user_limit
        ):
            return False, "You have reached the per-user redemption limit."
        return True, "OK"

    # ---------- Validation ----------
    def clean(self):
        # Mutually exclusive discount fields
        if self.discount_type == DiscountType.PERCENT:
            if self.percent_off is None:
                raise ValidationError(
                    {"percent_off": "percent_off is required for percent discounts."}
                )
            if self.percent_off <= 0 or self.percent_off > 100:
                raise ValidationError(
                    {"percent_off": "percent_off must be in (0, 100]."}
                )
            self.amount_off = None
        else:
            if self.amount_off is None:
                raise ValidationError(
                    {"amount_off": "amount_off is required for fixed amount discounts."}
                )
            if self.amount_off <= 0:
                raise ValidationError({"amount_off": "amount_off must be > 0."})
            self.percent_off = None

        # Date window sanity
        if self.valid_from and self.valid_to and self.valid_from >= self.valid_to:
            raise ValidationError({"valid_to": "valid_to must be after valid_from."})

        # Scope values sanity
        invalid = [
            s
            for s in (self.target_line_kinds or [])
            if s not in PROMO_LINE_SCOPE_VALUES
        ]
        if invalid:
            raise ValidationError(
                {
                    "target_line_kinds": f"Invalid values: {invalid}. Allowed: {sorted(PROMO_LINE_SCOPE_VALUES)}"
                }
            )

        # Arrays must be lists
        for fld in (
            "target_plan_types",
            "target_site_types",
            "target_plan_ids",
            "target_line_kinds",
            "target_extra_charge_types",
        ):
            val = getattr(self, fld, None)
            if val is not None and not isinstance(val, list):
                raise ValidationError({fld: "Must be a list."})

        # Extra type validation
        if self.target_extra_charge_types:
            bad = [
                x
                for x in self.target_extra_charge_types
                if x not in EXTRA_TYPES_ALLOWED
            ]
            if bad:
                raise ValidationError(
                    {
                        "target_extra_charge_types": f"Unknown extra types: {bad}. Allowed: {EXTRA_TYPES_ALLOWED}"
                    }
                )

    # ---------- Lifecycle ----------
    def is_live(self) -> bool:
        now = timezone.now()
        if not self.is_active:
            return False
        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_to and now > self.valid_to:
            return False
        return True

    # Back-compat aliases
    @property
    def active(self) -> bool:
        return self.is_active

    @property
    def starts_at(self):
        return self.valid_from

    @property
    def ends_at(self):
        return self.valid_to


class CouponRedemption(models.Model):
    coupon = models.ForeignKey(
        Coupon, on_delete=models.CASCADE, related_name="redemptions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="coupon_redemptions",
    )
    order = models.ForeignKey(
        "main.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )
    subscription = models.ForeignKey(
        "main.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="coupon_redemptions",
    )

    # snapshot for audit
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=8, decimal_places=2)
    discounted_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["coupon", "user"]),
            models.Index(fields=["user", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["coupon", "order"],
                name="uniq_coupon_once_per_order",
                condition=Q(order__isnull=False),
            ),
        ]

    def __str__(self):
        return f"{self.coupon.code} by {self.user_id} (-${self.discounted_amount})"


# Allowed ExtraCharge types (used to validate target_extra_charge_types)
EXTRA_TYPES_ALLOWED = [c[0] for c in ExtraCharge.CHARGE_TYPE_CHOICES]


class FxRate(models.Model):
    """Daily FX rate for currency pair (e.g., USD/CDF).

    Stored per calendar date. When querying a rate for a given date, we usually
    want the latest rate on or before that date (typical daily fixing).
    """

    date = models.DateField(db_index=True)
    pair = models.CharField(max_length=15, default="USD/CDF", db_index=True)
    rate = models.DecimalField(max_digits=12, decimal_places=4)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("date", "pair")
        indexes = [models.Index(fields=["pair", "-date"])]
        ordering = ["-date", "pair"]

    def __str__(self):
        return f"{self.pair} {self.date}: {self.rate}"

    @classmethod
    def get_rate(cls, when_date, pair: str = "USD/CDF"):
        try:
            obj = (
                cls.objects.filter(pair=pair, date__lte=when_date)
                .only("rate", "date")
                .order_by("-date")
                .first()
            )
            return Decimal(obj.rate) if obj else None
        except Exception:
            return None


class CompanySettings(models.Model):
    """
    Singleton table storing all main company information used for invoicing,
    receipts, and official documentation — compliant with DRC regulations.
    """

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)

    # ---------- Identity ----------
    legal_name = models.CharField("Legal name", max_length=150, blank=True, default="")
    trade_name = models.CharField("Trade name", max_length=150, blank=True, default="")
    email = models.EmailField("Primary email", blank=True, default="")
    phone = models.CharField("Primary phone", max_length=50, blank=True, default="")
    website = models.URLField("Website", blank=True, default="")

    # ---------- Address ----------
    street_address = models.CharField(
        "Full address", max_length=255, blank=True, default=""
    )
    city = models.CharField("City", max_length=120, blank=True, default="")
    province = models.CharField(
        "Province / State", max_length=120, blank=True, default=""
    )
    country = models.CharField("Country", max_length=120, blank=True, default="DRC")
    postal_code = models.CharField("Postal code", max_length=40, blank=True, default="")
    timezone = models.CharField(
        "Timezone",
        max_length=64,
        blank=True,
        default="Africa/Lubumbashi",
        help_text="IANA timezone name (e.g., Africa/Lubumbashi, Africa/Kinshasa).",
    )

    # ---------- Legal Identifiers (DRC) ----------
    rccm = models.CharField("RCCM", max_length=60, blank=True, default="")
    id_nat = models.CharField("Id.Nat", max_length=60, blank=True, default="")
    nif = models.CharField("NIF (Tax ID)", max_length=60, blank=True, default="")
    arptc_license = models.CharField(
        "ARPTC License",
        max_length=120,
        blank=True,
        default="",
        help_text="License number (if applicable).",
    )

    # ---------- Tax Regime & Rates ----------
    TAX_REGIME_CHOICES = [
        ("normal", "Normal VAT regime"),
        ("simplified", "Simplified regime"),
        ("exempt", "VAT-exempt regime"),
    ]
    tax_regime = models.CharField(
        "Tax regime", max_length=20, choices=TAX_REGIME_CHOICES, default="normal"
    )
    vat_rate_percent = models.DecimalField(
        "VAT rate (%)",
        max_digits=5,
        decimal_places=2,
        default=Decimal("16.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Standard VAT rate (e.g., 16.00).",
    )
    excise_rate_percent = models.DecimalField(
        "Excise rate (%)",
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Excise duty rate in % (optional).",
    )

    # ---------- Invoice Numbering & Currency ----------
    invoice_prefix = models.CharField(
        "Invoice prefix", max_length=12, default="INV", blank=True
    )
    next_invoice_number = models.PositiveIntegerField("Next invoice number", default=1)
    reset_number_annually = models.BooleanField(
        "Reset numbering annually",
        default=False,
        help_text="If enabled, numbering resets to 1 each new calendar year.",
    )

    default_currency = models.CharField(
        "Default currency", max_length=3, default="USD", help_text="USD or CDF."
    )
    payment_terms_days = models.PositiveIntegerField(
        "Payment terms (days)", default=7, null=True, blank=True
    )
    show_prices_in_cdf = models.BooleanField(
        "Show equivalent amount in CDF",
        default=False,
        help_text="Display CDF equivalent on invoices.",
    )

    # ---------- Banking & Mobile Money ----------
    bank_name = models.CharField("Bank name", max_length=120, blank=True, default="")
    bank_account_name = models.CharField(
        "Account holder name", max_length=120, blank=True, default=""
    )
    bank_swift = models.CharField("SWIFT / BIC", max_length=40, blank=True, default="")
    bank_branch = models.CharField(
        "Bank branch", max_length=120, blank=True, default=""
    )
    bank_iban = models.CharField("IBAN", max_length=120, blank=True, default="")
    bank_account_number_usd = models.CharField(
        "Account number (USD)", max_length=120, blank=True, default=""
    )
    bank_account_number_cdf = models.CharField(
        "Account number (CDF)", max_length=120, blank=True, default=""
    )

    mm_provider = models.CharField(
        "Mobile Money provider",
        max_length=120,
        blank=True,
        default="",
        help_text="e.g., M-Pesa, Airtel Money, Orange Money.",
    )
    mm_number = models.CharField(
        "Mobile Money number", max_length=60, blank=True, default=""
    )

    # ---------- Invoice Texts ----------
    payment_instructions = models.TextField(
        "Payment instructions", blank=True, default=""
    )
    footer_text_fr = models.TextField("Invoice footer (FR)", blank=True, default="")
    footer_text_en = models.TextField("Invoice footer (EN)", blank=True, default="")

    # ---------- Visual Identity ----------
    logo = models.ImageField(
        "Company logo", upload_to="branding/logo/", blank=True, null=True
    )
    stamp = models.ImageField(
        "Company stamp", upload_to="branding/stamp/", blank=True, null=True
    )
    signature = models.ImageField(
        "Signature image", upload_to="branding/signature/", blank=True, null=True
    )
    signatory_name = models.CharField(
        "Signatory name", max_length=120, blank=True, default=""
    )
    signatory_title = models.CharField(
        "Signatory title/role", max_length=120, blank=True, default=""
    )

    # ---------- Legal Notes ----------
    tax_office_name = models.CharField(
        "Tax office / Directorate", max_length=150, blank=True, default=""
    )
    legal_notes = models.TextField("Additional legal notes", blank=True, default="")

    # ---------- Audit ----------
    updated_at = models.DateTimeField("Last updated", auto_now=True)

    class Meta:
        verbose_name = "Company Settings"
        verbose_name_plural = "Company Settings"

    def __str__(self):
        return f"{self.legal_name or '—'}"

    # ---------- Utility Methods ----------
    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(id=1)
        return obj

    def current_invoice_year(self) -> int:
        """Return the current year according to the configured timezone."""
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(self.timezone or "Africa/Lubumbashi")
            now_local = timezone.now().astimezone(tz)
        except Exception:
            now_local = timezone.localtime()
        return now_local.year

    def format_invoice_number(self, number: int, year: int | None = None) -> str:
        """
        Format the invoice number:
        - If annual reset: INV/2025/000123
        - Otherwise:       INV/000123
        """
        year_part = f"/{year}" if (self.reset_number_annually and year) else ""
        return f"{(self.invoice_prefix or 'INV').upper()}{year_part}/{number:06d}"


class ConsolidatedInvoice(models.Model):
    STATUS = [
        ("draft", "Draft"),
        ("issued", "Issued"),
        ("paid", "Paid"),
        ("overdue", "Overdue"),
        ("cancelled", "Cancelled"),
    ]
    number = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consolidated_invoices",
    )
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=10, default="USD")
    issued_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="issued")

    class Meta:
        ordering = ["-issued_at"]
        indexes = [
            models.Index(fields=["user", "-issued_at"]),
            models.Index(fields=["status"]),
        ]
        constraints = [
            UniqueConstraint(
                fields=["number"],
                name="uniq_consolidated_number_not_null",
                condition=~Q(number__isnull=True),
            )
        ]

    def __str__(self):
        return f"{self.number} – {self.user} – {self.total} {self.currency}"


class Invoice(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        ISSUED = "issued", "Issued"
        PAID = "paid", "Paid"
        OVERDUE = "overdue", "Overdue"
        CANCELLED = "cancelled", "Cancelled"

    number = models.CharField(
        max_length=40, null=True, blank=True, unique=True, db_index=True
    )  # e.g. INV/2025/000123
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices"
    )
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True
    )

    # Legal snapshots (don’t rely only on FKs)
    bill_to_name = models.CharField(max_length=180, blank=True, default="")
    bill_to_address = models.TextField(blank=True, default="")
    tax_regime = models.CharField(max_length=20, default="normal")
    vat_rate_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=Decimal("16.00")
    )
    excise_rate_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # Dates & totals
    issued_at = models.DateTimeField(null=True, blank=True, db_index=True)
    due_at = models.DateTimeField(null=True, blank=True)
    subtotal = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    tax_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    grand_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Separated tax amounts (snapshotted at issue time)
    vat_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    excise_amount = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Optional links
    consolidated_of = models.ForeignKey(
        "ConsolidatedInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="child_invoices",
    )

    class Meta:
        ordering = ["-issued_at", "-id"]
        indexes = [models.Index(fields=["user", "status", "-issued_at"])]
        constraints = [
            UniqueConstraint(
                fields=["number"],
                name="uniq_invoice_number_not_null",
                condition=~Q(number__isnull=True),
            )
        ]

    def __str__(self):
        return self.number


class InvoiceOrder(models.Model):
    """Join table: what orders are covered by this invoice (supports bulk & partials)."""

    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="order_links"
    )
    order = models.ForeignKey(
        "Order", on_delete=models.PROTECT, related_name="invoice_links"
    )
    # optional partial attribution:
    amount_excl_tax = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    class Meta:
        unique_together = [("invoice", "order")]
        indexes = [models.Index(fields=["order", "invoice"])]


class InvoiceLine(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="lines")
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("1.00")
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )
    # Optional classification
    kind = models.CharField(
        max_length=20, default="item"
    )  # item/plan/extra/tax_adjust/etc.
    # Optional traceability:
    order = models.ForeignKey("Order", null=True, blank=True, on_delete=models.SET_NULL)
    order_line = models.ForeignKey(
        "OrderLine", null=True, blank=True, on_delete=models.SET_NULL
    )

    def save(self, *args, **kwargs):
        self.line_total = _qmoney(
            (self.unit_price or ZERO) * Decimal(self.quantity or 0)
        )
        super().save(*args, **kwargs)


class CreditNote(models.Model):
    number = models.CharField(
        max_length=40, unique=True, db_index=True
    )  # e.g. CN/2025/000045
    invoice = models.ForeignKey(
        Invoice, on_delete=models.PROTECT, related_name="credit_notes"
    )
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(auto_now_add=True)
    reason = models.CharField(max_length=255, blank=True, default="")
    total = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )  # negative in ledger


class InvoicePayment(models.Model):
    invoice = models.ForeignKey(
        Invoice, on_delete=models.CASCADE, related_name="payments"
    )
    payment_attempt = models.ForeignKey(
        PaymentAttempt, on_delete=models.SET_NULL, null=True, blank=True
    )
    wallet_tx = models.ForeignKey(
        WalletTransaction, on_delete=models.SET_NULL, null=True, blank=True
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)


class PaymentProbeLog(models.Model):
    """
    Append-only audit of probe requests that check FlexPay status from the UI or API.
    Records who triggered the probe, what identifiers were provided, and the outcome.
    """

    attempt = models.ForeignKey(
        "PaymentAttempt", on_delete=models.CASCADE, related_name="probe_logs"
    )
    user = models.ForeignKey(
        "User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payment_probe_logs",
    )
    order_number = models.CharField(max_length=100, blank=True, default="")
    trans_id = models.CharField(max_length=100, blank=True, default="")
    order_reference = models.CharField(max_length=100, blank=True, default="")
    outcome_status = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="paid | failed | pending | error | mismatch | http_4xx/5xx | unexpected",
    )
    orders_updated = models.IntegerField(default=0)
    raw_gateway_code = models.CharField(max_length=20, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["attempt", "-created_at"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["outcome_status"]),
        ]

    def __str__(self):
        return f"ProbeLog({self.attempt_id}) {self.outcome_status} @{self.created_at}"


class OrderEvent(models.Model):
    """
    Append-only audit trail per Order.
    Captures key business events with optional link to a PaymentAttempt and payload for traceability.
    """

    order = models.ForeignKey("Order", on_delete=models.CASCADE, related_name="events")
    event_type = models.CharField(
        max_length=40,
        default="info",
        help_text="payment_probe | auto_cancel | manual_cancel | note | system",
    )
    message = models.CharField(max_length=255, blank=True, default="")
    payload = models.JSONField(blank=True, null=True)
    attempt = models.ForeignKey(
        "PaymentAttempt",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="order_events",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["order", "-created_at"]),
            models.Index(fields=["event_type"]),
        ]

    def __str__(self):
        return f"OrderEvent({self.order_id}, {self.event_type}) @ {self.created_at:%Y-%m-%d %H:%M:%S}"
