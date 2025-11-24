from django.conf import settings
from django.db import models
from django.utils import timezone

try:
    import openlocationcode as olc
except Exception:
    olc = None


# Activation request model: created by a technician from the Field Engineer dashboard
class ActivationRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("confirmed", "Confirmed"),
        ("cancelled", "Cancelled"),
    ]

    # Optional link to an existing subscription/order if available
    subscription = models.ForeignKey(
        "main.Subscription",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activation_requests",
    )
    order = models.ForeignKey(
        "main.Order",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activation_requests",
    )

    requested_activity = models.OneToOneField(
        "main.InstallationActivity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="activation_request",
    )

    plan_name = models.CharField(max_length=255, blank=True, default="")
    client_name = models.CharField(max_length=255, blank=True, default="")
    kit_serial = models.CharField(max_length=255, blank=True, default="")
    plus_code = models.CharField(max_length=64, blank=True, default="")
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="requested_activations",
    )
    requested_at = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"ActivationRequest({self.id}) for {self.client_name or 'Unknown'} - {self.status}"

    def save(self, *args, **kwargs):
        """
        Sync denormalized fields from requested_activity and compute plus_code if missing.
        """
        if self.requested_activity:
            try:
                activity = self.requested_activity
                if activity.order:
                    order = activity.order
                    # Order model in this project stores the chosen plan in `order.plan`
                    try:
                        self.plan_name = (
                            order.plan.name
                            if getattr(order, "plan", None)
                            and getattr(order.plan, "name", None)
                            else ""
                        )
                    except Exception:
                        self.plan_name = ""

                    try:
                        # Prefer a full_name property if present, otherwise fall back to get_full_name(), then str(user)
                        user = getattr(order, "user", None)
                        if user:
                            name = getattr(user, "full_name", None)
                            if name:
                                self.client_name = name
                            else:
                                try:
                                    fullname = user.get_full_name()
                                    self.client_name = (
                                        fullname if fullname else str(user)
                                    )
                                except Exception:
                                    self.client_name = str(user)
                        else:
                            self.client_name = ""
                    except Exception:
                        self.client_name = ""

                    # Kits are stored on Order as `kit_inventory` (or via reverse `assigned_kit`), prefer kit_inventory
                    kit = getattr(order, "kit_inventory", None) or getattr(
                        order, "assigned_kit", None
                    )
                    try:
                        if kit and getattr(kit, "serial_number", None):
                            self.kit_serial = kit.serial_number
                        elif kit and getattr(kit, "kit_number", None):
                            # fallback to kit_number when serial_number isn't available
                            self.kit_serial = kit.kit_number
                        else:
                            self.kit_serial = ""
                    except Exception:
                        self.kit_serial = ""
                # Sync location from activity
                self.plus_code = activity.plus_code or ""
                self.latitude = activity.latitude
                self.longitude = activity.longitude
            except Exception:
                # If sync fails, leave fields as is
                pass

        if (
            (not self.plus_code or self.plus_code.strip() == "")
            and self.latitude is not None
            and self.longitude is not None
        ):
            try:
                if olc is not None:
                    # openlocationcode.encode expects (lat, lng)
                    self.plus_code = olc.encode(
                        float(self.latitude), float(self.longitude)
                    )
                else:
                    # library unavailable; leave plus_code empty
                    pass
            except Exception:
                # Don't prevent saving if encoding fails for any reason
                pass
        super().save(*args, **kwargs)


# Only installation-related models remain in tech app
