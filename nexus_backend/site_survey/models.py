from decimal import Decimal

from django.db import models
from django.utils import timezone

# Site Survey Models

# Module-level cache for VAT rate to avoid repetitive database queries
_vat_rate_cache = None
_vat_rate_cache_time = None
VAT_CACHE_DURATION = 300  # 5 minutes in seconds


def get_cached_vat_rate():
    """Get VAT rate with module-level caching to reduce database hits."""
    global _vat_rate_cache, _vat_rate_cache_time

    from django.utils import timezone

    # Check if cache is valid (exists and not expired)
    current_time = timezone.now().timestamp()
    if (
        _vat_rate_cache is not None
        and _vat_rate_cache_time is not None
        and (current_time - _vat_rate_cache_time) < VAT_CACHE_DURATION
    ):
        return _vat_rate_cache

    # Cache miss or expired - fetch from database
    try:
        from main.models import TaxRate

        vat_rate_obj = TaxRate.objects.filter(description="VAT").first()
        if vat_rate_obj:
            _vat_rate_cache = vat_rate_obj.percentage / Decimal("100")
        else:
            _vat_rate_cache = Decimal("0.00")  # Fallback if VAT not found

        _vat_rate_cache_time = current_time
        return _vat_rate_cache
    except Exception:
        # If there's any error, return zero and don't cache
        return Decimal("0.00")


class SiteSurveyChecklist(models.Model):
    """Predefined checklist items for site surveys"""

    CATEGORY_CHOICES = [
        ("location", "Location & Access"),
        ("signal", "Signal Quality"),
        ("mounting", "Mounting Options"),
        ("safety", "Safety Considerations"),
        ("technical", "Technical Requirements"),
        ("environmental", "Environmental Factors"),
    ]

    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    question = models.CharField(max_length=255)
    question_type = models.CharField(
        max_length=20,
        choices=[
            ("yes_no", "Yes/No"),
            ("text", "Text Response"),
            ("multiple_choice", "Multiple Choice"),
            ("rating", "Rating (1-5)"),
        ],
    )
    choices = models.JSONField(
        blank=True, null=True, help_text="For multiple choice questions"
    )
    is_required = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["category", "display_order"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.question}"


class SiteSurvey(models.Model):
    """Main site survey model"""

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("in_progress", "In Progress"),
        ("completed", "Completed"),
        ("requires_approval", "Requires Approval"),
        ("approved", "Approved"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"),
    ]

    order = models.OneToOneField(
        "main.Order", on_delete=models.CASCADE, related_name="site_survey"
    )
    technician = models.ForeignKey(
        "main.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="site_surveys",
    )
    assigned_by = models.ForeignKey(
        "main.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_surveys",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)

    # Survey details
    scheduled_date = models.DateField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="scheduled"
    )

    # Location information
    survey_latitude = models.FloatField(null=True, blank=True)
    survey_longitude = models.FloatField(null=True, blank=True)
    survey_address = models.TextField(blank=True)
    location_notes = models.TextField(blank=True)

    # Overall assessment
    overall_assessment = models.TextField(
        blank=True, help_text="Technician's overall assessment"
    )
    installation_feasible = models.BooleanField(null=True, blank=True)
    recommended_mounting = models.CharField(max_length=100, blank=True)

    # Additional costs assessment
    requires_additional_equipment = models.BooleanField(
        null=True, blank=True, help_text="Whether additional equipment/costs are needed"
    )
    estimated_additional_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated total for additional costs",
    )
    cost_justification = models.TextField(
        blank=True, help_text="Detailed justification for additional costs"
    )
    additional_costs_approved = models.BooleanField(
        null=True, blank=True, help_text="Whether customer approved additional costs"
    )

    # Approval workflow
    submitted_for_approval_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "main.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="approved_surveys",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_notes = models.TextField(blank=True)
    rejection_reason = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Site Survey for Order {self.order.order_reference}"

    def save(self, *args, **kwargs):
        # Track previous status to detect changes
        previous_status = None
        if self.pk:
            try:
                previous_status = SiteSurvey.objects.get(pk=self.pk).status
            except SiteSurvey.DoesNotExist:
                pass

        if self.status == "in_progress" and not self.started_at:
            self.started_at = timezone.now()
        elif self.status == "completed" and not self.completed_at:
            self.completed_at = timezone.now()
            if not self.submitted_for_approval_at:
                self.submitted_for_approval_at = timezone.now()
                self.status = "requires_approval"

        super().save(*args, **kwargs)

        # Create InstallationActivity when survey is approved for the first time
        if self.status == "approved" and previous_status != "approved":
            self.create_installation_activity()

        # Send notifications when survey is rejected for the first time
        if self.status == "rejected" and previous_status != "rejected":
            from .notifications import send_all_rejection_notifications

            send_all_rejection_notifications(self)

    def create_installation_activity(self):
        """
        Create InstallationActivity when survey is approved.

        Two scenarios:
        1. No additional costs: Create immediately after survey approval
        2. Has additional costs: Create only after additional billing is paid
        """
        from main.models import InstallationActivity

        # Check if survey requires additional costs
        if self.requires_additional_equipment:
            # Check if additional billing exists and is paid
            if hasattr(self, "additional_billing"):
                if self.additional_billing.status == "paid":
                    # Additional costs paid, create installation
                    installation_activity, created = (
                        InstallationActivity.objects.get_or_create(
                            order=self.order,
                            defaults={
                                "notes": f"Installation scheduled after survey approval and additional costs payment. Survey: {self.id}, Billing: {self.additional_billing.billing_reference}",
                                "location_confirmed": True,
                            },
                        )
                    )
                    return installation_activity, created
                else:
                    # Additional costs not paid yet, don't create installation
                    return None, False
            else:
                # Additional costs required but billing not generated yet
                return None, False
        else:
            # No additional costs, create installation immediately
            installation_activity, created = InstallationActivity.objects.get_or_create(
                order=self.order,
                defaults={
                    "notes": f"Installation scheduled after survey approval (no additional costs). Survey reference: {self.id}",
                    "location_confirmed": True,
                },
            )
            return installation_activity, created

    def can_create_installation(self):
        """
        Check if installation can be created based on survey status and billing
        """
        if self.status != "approved":
            return False

        if not self.requires_additional_equipment:
            return True

        if hasattr(self, "additional_billing"):
            return self.additional_billing.status == "paid"

        return False


class SiteSurveyResponse(models.Model):
    """Individual responses to checklist items"""

    survey = models.ForeignKey(
        SiteSurvey, on_delete=models.CASCADE, related_name="responses"
    )
    checklist_item = models.ForeignKey(SiteSurveyChecklist, on_delete=models.CASCADE)
    response_text = models.TextField(blank=True)
    response_rating = models.PositiveIntegerField(
        null=True, blank=True, help_text="For rating questions (1-5)"
    )
    response_choice = models.CharField(
        max_length=100, blank=True, help_text="For multiple choice questions"
    )
    additional_notes = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["survey", "checklist_item"]

    def __str__(self):
        return f"Response to: {self.checklist_item.question}"


class SiteSurveyPhoto(models.Model):
    """Photos taken during site survey"""

    PHOTO_TYPE_CHOICES = [
        ("site_overview", "Site Overview"),
        ("proposed_mounting", "Proposed Mounting Location"),
        ("obstructions", "Obstructions"),
        ("access_path", "Access Path"),
        ("power_source", "Power Source"),
        ("safety_concern", "Safety Concern"),
        ("other", "Other"),
    ]

    survey = models.ForeignKey(
        SiteSurvey, on_delete=models.CASCADE, related_name="photos"
    )
    photo = models.ImageField(upload_to="site_survey_photos/")
    photo_type = models.CharField(
        max_length=20, choices=PHOTO_TYPE_CHOICES, default="other"
    )
    description = models.CharField(max_length=255, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_photo_type_display()} - {self.survey}"


class ExtraCharge(models.Model):
    """Predefined additional equipment/services with fixed pricing"""

    COST_TYPE_CHOICES = [
        ("equipment", "Additional Equipment"),
        ("cable", "Extra Cables"),
        ("extender", "Signal Extender"),
        ("router", "Router/Gateway"),
        ("mounting", "Specialized Mounting"),
        ("labor", "Additional Labor"),
        ("power", "Power Infrastructure"),
        ("access", "Access Infrastructure"),
        ("safety", "Safety Equipment"),
        ("other", "Other"),
    ]

    cost_type = models.CharField(max_length=20, choices=COST_TYPE_CHOICES)
    item_name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    unit_price = models.DecimalField(
        max_digits=10, decimal_places=2, help_text="Fixed price per unit"
    )
    is_active = models.BooleanField(
        default=True, help_text="Whether this item is available for selection"
    )
    display_order = models.PositiveIntegerField(
        default=0, help_text="Order in which items appear in selection lists"
    )

    # Optional fields for detailed specifications
    brand = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    specifications = models.JSONField(
        blank=True, null=True, help_text="Additional technical specifications"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["cost_type", "display_order", "item_name"]
        verbose_name = "Extra Charge"
        verbose_name_plural = "Extra Charges"

    def __str__(self):
        return f"{self.item_name} ({self.get_cost_type_display()}) - ${self.unit_price}"

    def get_full_description(self):
        """Returns formatted description with brand/model if available"""
        parts = []
        if self.brand:
            parts.append(f"Brand: {self.brand}")
        if self.model:
            parts.append(f"Model: {self.model}")
        if self.description:
            parts.append(self.description)
        return " | ".join(parts) if parts else "No description available"


class SurveyAdditionalCost(models.Model):
    """Additional equipment/costs identified during site survey"""

    survey = models.ForeignKey(
        SiteSurvey, on_delete=models.CASCADE, related_name="additional_costs"
    )
    extra_charge = models.ForeignKey(
        ExtraCharge,
        on_delete=models.CASCADE,
        null=True,  # Temporarily nullable for migration
        blank=True,
        help_text="Predefined equipment/service from the catalog",
    )
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        editable=False,
        help_text="Price automatically set from ExtraCharge",
    )
    total_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    is_required = models.BooleanField(
        default=True, help_text="Whether this item is absolutely necessary"
    )
    justification = models.TextField(
        help_text="Technician's justification for this additional cost"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["extra_charge__cost_type", "extra_charge__item_name"]
        verbose_name = "Survey Additional Cost"
        verbose_name_plural = "Survey Additional Costs"

    def save(self, *args, **kwargs):
        # Automatically set unit price from ExtraCharge
        if self.extra_charge_id:
            self.unit_price = self.extra_charge.unit_price
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.extra_charge.item_name} x{self.quantity} - {self.survey.order.order_reference}"

    @property
    def cost_type(self):
        """Get cost type from related ExtraCharge"""
        return self.extra_charge.cost_type if self.extra_charge else None

    @property
    def item_name(self):
        """Get item name from related ExtraCharge"""
        return self.extra_charge.item_name if self.extra_charge else None

    @property
    def description(self):
        """Get description from related ExtraCharge"""
        return self.extra_charge.get_full_description() if self.extra_charge else None


class AdditionalBilling(models.Model):
    """Additional billing generated after site survey completion"""

    STATUS_CHOICES = [
        ("draft", "Draft"),
        ("pending_approval", "Pending Customer Approval"),
        ("approved", "Approved by Customer"),
        ("rejected", "Rejected by Customer"),
        ("processing", "Payment Processing"),
        ("pending_verification", "Pending Payment Verification"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]

    survey = models.OneToOneField(
        SiteSurvey, on_delete=models.CASCADE, related_name="additional_billing"
    )
    order = models.ForeignKey(
        "main.Order", on_delete=models.CASCADE, related_name="additional_billings"
    )
    customer = models.ForeignKey(
        "main.User", on_delete=models.CASCADE, related_name="additional_billings"
    )

    # Billing details
    billing_reference = models.CharField(
        max_length=20, unique=True, editable=False, blank=True
    )
    subtotal = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, editable=False
    )
    tax_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, editable=False
    )
    total_amount = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, editable=False
    )

    # Status and workflow
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="draft")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    sent_for_approval_at = models.DateTimeField(null=True, blank=True)
    customer_responded_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Customer interaction
    customer_notes = models.TextField(
        blank=True, help_text="Customer's feedback or rejection reason"
    )
    admin_notes = models.TextField(blank=True, help_text="Admin notes for internal use")

    # Payment details
    payment_method = models.CharField(max_length=50, blank=True)
    payment_reference = models.CharField(max_length=100, blank=True)
    payment_proof = models.FileField(
        upload_to="additional_billing_payments/", null=True, blank=True
    )

    # Expiry
    expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When this billing proposal expires"
    )

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Track previous status to detect changes
        previous_status = None
        if self.pk:
            try:
                previous_status = AdditionalBilling.objects.get(pk=self.pk).status
            except AdditionalBilling.DoesNotExist:
                pass

        # Generate billing reference if not exists
        if not self.billing_reference:
            self.billing_reference = self._generate_billing_reference()

        # Calculate totals
        self._calculate_totals()

        # Set timestamps based on status changes
        if self.status == "pending_approval" and not self.sent_for_approval_at:
            self.sent_for_approval_at = timezone.now()
        elif self.status == "approved" and not self.approved_at:
            self.approved_at = timezone.now()
            self.customer_responded_at = timezone.now()
        elif self.status == "rejected" and not self.rejected_at:
            self.rejected_at = timezone.now()
            self.customer_responded_at = timezone.now()
        elif self.status == "paid" and not self.paid_at:
            self.paid_at = timezone.now()

        super().save(*args, **kwargs)

        # Ensure an invoice snapshot exists once the customer approves (or pays) the billing
        if self.status in {"approved", "paid"}:
            self.ensure_invoice_entry()

        # Create InstallationActivity when additional billing is paid for the first time
        if self.status == "paid" and previous_status != "paid":
            # Trigger installation creation through the survey
            if self.survey.status == "approved":
                self.survey.create_installation_activity()

    def _generate_billing_reference(self):
        """Generate unique billing reference"""
        import random
        import string

        prefix = "ADD"
        timestamp = timezone.now().strftime("%y%m%d")
        random_suffix = "".join(random.choices(string.digits, k=4))
        return f"{prefix}{timestamp}{random_suffix}"

    def _calculate_totals(self):
        """Calculate billing totals from associated costs"""
        if not self.survey_id:
            return

        # Sum all additional costs
        total_costs = sum(
            cost.total_price for cost in self.survey.additional_costs.all()
        )

        self.subtotal = total_costs

        # Apply only VAT for additional equipment (not Excise or other taxes)
        # Check if customer exists and is tax exempt
        is_tax_exempt = False
        if self.customer:
            is_tax_exempt = getattr(self.customer, "is_tax_exempt", False)

        if is_tax_exempt:
            self.tax_amount = Decimal("0.00")
        else:
            # Use cached VAT rate to avoid repetitive database queries
            vat_rate = get_cached_vat_rate()
            self.tax_amount = self.subtotal * vat_rate

        self.total_amount = self.subtotal + self.tax_amount

    def get_cost_breakdown(self):
        """Get detailed breakdown of all costs"""
        return (
            self.survey.additional_costs.select_related("extra_charge")
            .all()
            .order_by("extra_charge__cost_type", "extra_charge__item_name")
        )

    def get_tax_breakdown(self):
        """Get detailed breakdown of applicable taxes (VAT only for additional equipment)"""
        from main.models import TaxRate

        tax_breakdown = []

        # Check if customer exists and is not tax exempt
        if not self.customer:
            return tax_breakdown

        is_tax_exempt = getattr(self.customer, "is_tax_exempt", False)

        if not is_tax_exempt and self.subtotal > 0:
            # Only VAT applies to additional equipment
            vat_rate = TaxRate.objects.filter(description="VAT").first()
            if vat_rate:
                rate = vat_rate.percentage / Decimal("100")
                tax_amount = self.subtotal * rate
                tax_breakdown.append(
                    {
                        "description": vat_rate.get_description_display(),
                        "percentage": float(vat_rate.percentage),
                        "amount": float(tax_amount),
                    }
                )

        return tax_breakdown

    def resolve_region_override(self):
        """
        Best-effort region assignment used for ledger snapshots.
        """
        region = None
        order = getattr(self, "order", None)
        if order and getattr(order, "region_id", None):
            return order.region

        survey = getattr(self, "survey", None)
        if (
            survey
            and getattr(survey, "survey_latitude", None) is not None
            and getattr(survey, "survey_longitude", None) is not None
        ):
            try:
                from main.services.region_resolver import resolve_region_from_coords

                region, _ = resolve_region_from_coords(
                    float(survey.survey_latitude), float(survey.survey_longitude)
                )
            except Exception:
                region = None

        if region and order and not getattr(order, "region_id", None):
            order.region = region
            order.save(update_fields=["region"])

        return region

    @property
    def invoice_external_ref(self) -> str | None:
        """External reference used when storing the invoice in the ledger."""
        if not self.pk and not self.billing_reference:
            return None
        ref = self.billing_reference or f"ADD-{self.pk}"
        return f"additional_billing:{ref}"

    def ensure_invoice_entry(self):
        """
        Idempotently create the AccountEntry invoice snapshot for this additional billing.
        """
        if not self.customer_id or not self.invoice_external_ref:
            return None

        from main.models import AccountEntry, BillingAccount
        from main.services.posting import create_entry

        external_ref = self.invoice_external_ref
        if AccountEntry.objects.filter(external_ref=external_ref).exists():
            return None

        acct, _ = BillingAccount.objects.get_or_create(user=self.customer)
        entry = create_entry(
            account=acct,
            entry_type="invoice",
            amount_usd=self.total_amount,
            description=f"Additional equipment invoice {self.billing_reference}",
            order=self.order,
            external_ref=external_ref,
            region_override=self.resolve_region_override(),
        )
        return entry

    @property
    def has_invoice(self) -> bool:
        """Return True when an invoice ledger entry already exists."""
        cache = getattr(self, "_has_invoice_cache", None)
        if cache is not None:
            return cache

        external_ref = self.invoice_external_ref
        if not external_ref:
            self._has_invoice_cache = False
            return False

        from main.models import AccountEntry

        exists = AccountEntry.objects.filter(external_ref=external_ref).exists()
        self._has_invoice_cache = exists
        return exists

    def can_be_approved(self):
        """Check if billing can be approved by customer"""
        return self.status == "pending_approval" and not self.is_expired()

    def is_expired(self):
        """Check if billing proposal has expired"""
        return self.expires_at and timezone.now() > self.expires_at

    def __str__(self):
        return f"Additional Billing {self.billing_reference} - {self.order.order_reference}"
