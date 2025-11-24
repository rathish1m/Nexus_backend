from django.contrib import admin

from geo_regions.models import Region

from .models import (
    AccountEntry,
    BillingAccount,
    CompanyDocument,
    CompanyKYC,
    InstallationActivity,
    InstallationPhoto,
    Order,
    OTPVerification,
    PaymentAttempt,
    PersonalKYC,
    RegionSalesDefault,
    StarlinkKit,
    StarlinkKitInventory,
    Subscription,
    SubscriptionPlan,
    User,
)


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    search_fields = ("email", "full_name", "phone", "username")


@admin.register(BillingAccount)
class BillingAccountAdmin(admin.ModelAdmin):
    search_fields = ("user__email", "user__full_name")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    search_fields = ("order_reference", "user__email", "user__full_name")


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    search_fields = ("user__email", "user__full_name", "plan__name")


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin):
    search_fields = ("reference", "order__order_reference", "order__user__email")


@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    search_fields = ("user__email", "user__full_name", "token")


@admin.register(PersonalKYC)
class PersonalKYCAdmin(admin.ModelAdmin):
    search_fields = ("user__email", "full_name", "document_number")


@admin.register(StarlinkKitInventory)
class StarlinkKitInventoryAdmin(admin.ModelAdmin):
    search_fields = ("serial_number", "kit__name")


@admin.register(StarlinkKit)
class StarlinkKitAdmin(admin.ModelAdmin):
    search_fields = ("name", "model")


@admin.register(SubscriptionPlan)
class SubscriptionPlanAdmin(admin.ModelAdmin):
    search_fields = ("name", "plan_type")


@admin.register(Region)
class RegionAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(AccountEntry)
class AccountEntryAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "account",
        "entry_type",
        "amount_usd",
        "region_snapshot",
        "sales_agent_snapshot",
        "snapshot_source",
        "created_at",
    )
    list_filter = (
        "entry_type",
        "snapshot_source",
        "region_snapshot",
        "sales_agent_snapshot",
        "created_at",
    )
    search_fields = (
        "account__user__email",
        "account__user__full_name",
        "description",
        "external_ref",
    )
    readonly_fields = ("created_at",)
    autocomplete_fields = (
        "account",
        "order",
        "subscription",
        "payment",
        "region_snapshot",
        "sales_agent_snapshot",
    )
    ordering = ("-created_at",)


@admin.register(RegionSalesDefault)
class RegionSalesDefaultAdmin(admin.ModelAdmin):
    list_display = ("region", "agent", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("region__name", "agent__full_name", "agent__email")
    autocomplete_fields = ("region", "agent")


# ===== CompanyDocument Inline =====
class CompanyDocumentInline(admin.TabularInline):
    model = CompanyDocument
    extra = 1
    fields = ("document", "document_name", "uploaded_at")
    readonly_fields = ("uploaded_at",)


# ===== CompanyKYC Admin =====
@admin.register(CompanyKYC)
class CompanyKYCAdmin(admin.ModelAdmin):
    list_display = (
        "company_name",
        "user",
        "business_sector",
        "legal_status",
        "established_date",
        "status",
        "submitted_at",
    )
    list_filter = (
        "status",
        "business_sector",
        "legal_status",
        "submitted_at",
        "approved_at",
        "rejected_at",
    )
    search_fields = (
        "company_name",
        "user__email",
        "user__full_name",
        "rccm",
        "nif",
        "representative_name",
    )
    readonly_fields = ("submitted_at", "approved_at", "rejected_at")

    fieldsets = (
        (
            "Company Information",
            {
                "fields": (
                    "user",
                    "company_name",
                    "address",
                    "established_date",
                    "business_sector",
                    "legal_status",
                )
            },
        ),
        (
            "Legal Documents",
            {
                "fields": (
                    "rccm",
                    "nif",
                    "id_nat",
                )
            },
        ),
        (
            "Representative Information",
            {
                "fields": (
                    "representative_name",
                    "representative_id_file",
                )
            },
        ),
        (
            "Documents",
            {"fields": ("company_documents",)},
        ),
        (
            "KYC Status",
            {
                "fields": (
                    "status",
                    "approved_by",
                    "approved_at",
                    "rejection_reason",
                    "rejected_by",
                    "rejected_at",
                    "remarks",
                    "submitted_at",
                )
            },
        ),
    )
    inlines = [CompanyDocumentInline]


# ===== Installation Activity Admin =====
class InstallationPhotoInline(admin.TabularInline):
    model = InstallationPhoto
    extra = 1
    fields = ("image", "caption", "uploaded_at")
    readonly_fields = ("uploaded_at",)


@admin.register(InstallationActivity)
class InstallationActivityAdmin(admin.ModelAdmin):
    list_display = (
        "order",
        "technician",
        "status",
        "customer_full_name",
        "final_link_status",
        "customer_rating",
        "is_draft",
        "submitted_at",
        "created_at",
    )
    list_filter = (
        "status",
        "is_draft",
        "final_link_status",
        "customer_rating",
        "sla_tier",
        "weather_conditions",
        "created_at",
    )
    search_fields = (
        "order__order_reference",
        "customer_full_name",
        "technician__full_name",
        "dish_serial_number",
        "router_serial_number",
    )
    readonly_fields = ("created_at", "updated_at", "submitted_at")

    fieldsets = (
        (
            "Base Information",
            {
                "fields": (
                    "order",
                    "technician",
                    "status",
                    "planned_at",
                    "started_at",
                    "completed_at",
                    "notes",
                    "location_confirmed",
                )
            },
        ),
        (
            "Site Information",
            {
                "fields": (
                    "on_site_arrival",
                    "site_address",
                    ("site_latitude", "site_longitude"),
                    "access_level",
                    "power_availability",
                    "site_notes",
                )
            },
        ),
        (
            "Equipment - CPE",
            {
                "fields": (
                    "dish_serial_number",
                    "router_serial_number",
                    "firmware_version",
                    "power_source",
                    ("cable_length", "splices_connectors"),
                )
            },
        ),
        (
            "Equipment - Network",
            {
                "fields": (
                    "wifi_ssid",
                    "wifi_password",
                    "lan_ip",
                    "dhcp_range",
                )
            },
        ),
        (
            "Mounting & Alignment",
            {
                "fields": (
                    "mount_type",
                    "mount_height",
                    "grounding",
                    "weatherproofing",
                    "obstruction_percentage",
                    ("elevation_angle", "azimuth_angle"),
                    "obstruction_notes",
                    "mounting_notes",
                )
            },
        ),
        (
            "Safety & Environment",
            {
                "fields": (
                    "weather_conditions",
                    (
                        "safety_helmet",
                        "safety_harness",
                        "safety_gloves",
                        "safety_ladder",
                    ),
                    "hazards_noted",
                )
            },
        ),
        (
            "Cabling",
            {
                "fields": (
                    "cable_entry_point",
                    "cable_protection",
                    "termination_type",
                    "routing_notes",
                )
            },
        ),
        (
            "Power & Backup",
            {
                "fields": (
                    "power_stability_test",
                    "ups_installed",
                    "ups_model",
                    "ups_runtime_minutes",
                )
            },
        ),
        (
            "Connectivity Tests",
            {
                "fields": (
                    "snr_db",
                    ("speed_download_mbps", "speed_upload_mbps"),
                    "latency_ms",
                    "test_tool",
                    "public_ip",
                    "qos_vlan",
                    "final_link_status",
                    "test_notes",
                )
            },
        ),
        (
            "Customer Sign-off",
            {
                "fields": (
                    "customer_full_name",
                    "customer_id_document",
                    "customer_acceptance",
                    "customer_signature",
                    "customer_signoff_at",
                    "customer_rating",
                    "customer_comments",
                )
            },
        ),
        (
            "Reseller Information",
            {
                "fields": (
                    "reseller_name",
                    "reseller_id",
                    "sla_tier",
                    "reseller_notes",
                )
            },
        ),
        (
            "Metadata",
            {
                "fields": (
                    "is_draft",
                    "created_at",
                    "updated_at",
                    "submitted_at",
                )
            },
        ),
    )

    inlines = [InstallationPhotoInline]
