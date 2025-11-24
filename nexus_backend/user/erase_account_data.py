import uuid

from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from main.models import Subscription, User


def _safe_delete_field_file(field):
    """Delete a FileField/FieldFile safely (ignore storage errors)."""
    try:
        if field:
            field.delete(save=False)
    except Exception:
        pass


def _anonymized_email(user_id: int) -> str:
    """Unique, non-routable email to satisfy unique constraint without storing PII."""
    rand = uuid.uuid4().hex[:10]
    return f"deleted+u{user_id}-{rand}@example.invalid"


def erase_user_personal_data(user_id: int) -> None:
    """
    Synchronous PII erasure/anonymization:
    - remove avatar & KYC files, delete KYC rows
    - disable wallet
    - scrub user's direct PII (email/phone/names), keep row to preserve FKs and history
    """
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)

        # Preferences / avatar
        prefs = getattr(user, "prefs", None)
        if prefs:
            _safe_delete_field_file(getattr(prefs, "avatar", None))
            # keep notify toggles (non-PII)

        # Personal KYC
        pkyc = getattr(user, "personnal_kyc", None)
        if pkyc:
            _safe_delete_field_file(getattr(pkyc, "document_file", None))
            pkyc.delete()

        # Company KYC + related documents
        ckyc = getattr(user, "company_kyc", None)
        if ckyc:
            _safe_delete_field_file(getattr(ckyc, "representative_id_file", None))
            _safe_delete_field_file(getattr(ckyc, "company_documents", None))
            try:
                for doc in ckyc.documents.all():
                    _safe_delete_field_file(getattr(doc, "document", None))
                    doc.delete()
            except Exception:
                pass
            ckyc.delete()

        # Disable wallet (preserve ledger and balances)
        wallet = getattr(user, "wallet", None)
        if wallet and wallet.is_active:
            wallet.is_active = False
            wallet.save(update_fields=["is_active"])

        # Scrub PII on the user row (keep for referential integrity)
        user.full_name = "Deleted Account"
        user.first_name = ""
        user.last_name = ""
        user.phone = None  # unique=True on model, clear it
        user.email = _anonymized_email(user.id)  # keep email unique without PII
        user.is_verified = False
        user.roles = []
        user.username = f"deleted_{user.id}"  # keep non-identifying & unique

        user.save(
            update_fields=[
                "full_name",
                "first_name",
                "last_name",
                "phone",
                "email",
                "is_verified",
                "roles",
                "username",
            ]
        )


@login_required
@require_POST
def settings_delete_account(request: HttpRequest) -> JsonResponse:
    user = request.user

    # 1) Guard: no active subscriptions may remain
    if Subscription.objects.filter(user=user, status="active").exists():
        return JsonResponse(
            {
                "success": False,
                "message": _(
                    "You still have an active subscription. Please cancel it before deactivating your account."
                ),
            },
            status=409,
        )

    # 2) Soft-deactivate & logout (keep FKs intact)
    with transaction.atomic():
        user.is_active = False
        user.save(update_fields=["is_active"])

        # Ensure we only run erasure after the deactivation commit is durable
        uid = user.id
        transaction.on_commit(lambda: erase_user_personal_data(uid))

    try:
        logout(request)
    except Exception:
        pass

    return JsonResponse(
        {
            "success": True,
            "message": _(
                "Account scheduled for deactivation. Your personal data will now be removed or anonymized."
            ),
        }
    )
