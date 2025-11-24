from django.db.models.signals import post_save
from django.dispatch import receiver

from tech.models import ActivationRequest


@receiver(post_save, sender=ActivationRequest)
def mark_subscription_activation_requested(
    sender, instance: ActivationRequest, created, **kwargs
):
    """When an ActivationRequest is created, mark its subscription as activation_requested=True.

    This implements Option B: persist activation_requested on Subscription so the UI can show 'Requested'
    even after page reloads.
    """
    if not created:
        return

    # avoid circular import
    try:
        from main.models import Subscription
    except Exception:
        Subscription = None

    sub = getattr(instance, "subscription", None)
    if sub and Subscription is not None:
        try:
            if not getattr(sub, "activation_requested", False):
                sub.activation_requested = True
                sub.save(update_fields=["activation_requested"])
        except Exception:
            # best-effort; do not raise from signal
            pass


from django.dispatch import receiver

from tech.models import ActivationRequest


@receiver(post_save, sender=ActivationRequest)
def mark_subscription_activation_requested(sender, instance, created, **kwargs):
    """When an ActivationRequest is created, mark the associated Subscription.activation_requested=True."""
    try:
        if created and instance.subscription:
            Subscription = instance.subscription.__class__
            sub = instance.subscription
            if not getattr(sub, "activation_requested", False):
                sub.activation_requested = True
                sub.save(update_fields=["activation_requested"])
    except Exception:
        # avoid breaking saves
        pass
