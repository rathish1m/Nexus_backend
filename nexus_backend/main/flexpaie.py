# payments/utils.py (or wherever your helper lives)
import json
import logging
from decimal import Decimal, InvalidOperation

import requests

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_POST

import nexus_backend.settings
from nexus_backend.celery_tasks.tasks import cancel_expired_orders

from .models import Order, OrderEvent, PaymentAttempt

logger = logging.getLogger(__name__)
FLEXPAY_CHECK_URL = nexus_backend.settings.FLEXPAY_CHECK_URL  # ensure this exists


def _parse_flexpay_datetime(s):
    # implement according to your current code
    try:
        # example: "2024-10-20 13:45:22"
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return timezone.now()


def record_coupon_redemption_if_any(order):
    # your existing implementation (no change)
    pass


def check_flexpay_transactions(
    order_number: str | None = None,
    trans_id: str | None = None,
    order_reference: str | None = None,
):
    """
    Poll FlexPay for PaymentAttempts that are not completed.
    If order_number/trans_id/order_reference provided, limit to those attempts.
    Mark ONLY the order linked to the current PaymentAttempt (same order_number) as paid
    when BOTH: response code == "0" AND transaction.status == "0".
    Also record coupon redemption (if any) once the order is paid.
    """
    qs = PaymentAttempt.objects.select_related("order").exclude(
        status__in=["completed", "succeeded", "paid"]
    )

    if order_number:
        qs = qs.filter(order_number=str(order_number).strip())
    elif trans_id:
        # We usually store FlexPay transid in `reference` or raw payload.
        qs = qs.filter(reference=str(trans_id).strip())
    elif order_reference:
        qs = qs.filter(order__order_reference=str(order_reference).strip())

    attempts = qs.order_by("-created_at")

    checked = 0
    updated_attempts = 0
    updated_orders = 0
    per_attempt = []  # optional: for frontend debugging/info

    for pa in attempts:
        current_order_number = pa.order_number
        if not current_order_number:
            logger.warning("PaymentAttempt %s has no order_number. Skipping.", pa.id)
            continue

        try:
            headers = {
                "Authorization": f"Bearer {nexus_backend.settings.FLEXPAY_API_KEY}",
                "Content-Type": "application/json",
            }

            resp = requests.get(
                f"{FLEXPAY_CHECK_URL.rstrip('/')}/{current_order_number}",
                headers=headers,
                timeout=15,
            )
            checked += 1

            if resp.status_code != 200:
                logger.error(
                    "FlexPay check HTTP %s for orderNumber=%s",
                    resp.status_code,
                    current_order_number,
                )
                per_attempt.append(
                    {
                        "attempt_id": pa.id,
                        "order_number": current_order_number,
                        "success": False,
                        "reason": f"http_{resp.status_code}",
                    }
                )
                continue

            data = resp.json() if resp.content else {}
            code = str(data.get("code", "")).strip()

            if code == "0":
                tx = data.get("transaction") or {}
                tx_status = str(tx.get("status", "")).strip()
                tx_reference = (tx.get("reference") or "").strip()

                print("TRANSACTION TEST")
                print(tx_status)
                print(tx_reference)

                # Optional matching
                expected_refs = set()
                if pa.reference:
                    expected_refs.add(str(pa.reference).strip())
                if pa.order and getattr(pa.order, "order_reference", None):
                    expected_refs.add(str(pa.order.order_reference).strip())
                if tx_reference and expected_refs and tx_reference not in expected_refs:
                    logger.warning(
                        "FlexPay reference mismatch for attempt %s: got '%s', expected one of %s. Skipping.",
                        pa.id,
                        tx_reference,
                        list(expected_refs),
                    )
                    per_attempt.append(
                        {
                            "attempt_id": pa.id,
                            "order_number": current_order_number,
                            "success": False,
                            "reason": "ref_mismatch",
                        }
                    )
                    continue

                amount = pa.amount
                amount_customer = pa.amount_customer
                try:
                    if tx.get("amount") is not None:
                        amount = Decimal(str(tx.get("amount")))
                except (InvalidOperation, TypeError):
                    logger.warning(
                        "Invalid amount in FlexPay tx for attempt %s: %s",
                        pa.id,
                        tx.get("amount"),
                    )
                try:
                    if tx.get("amountCustomer") is not None:
                        amount_customer = Decimal(str(tx.get("amountCustomer")))
                except (InvalidOperation, TypeError):
                    logger.warning(
                        "Invalid amountCustomer in FlexPay tx for attempt %s: %s",
                        pa.id,
                        tx.get("amountCustomer"),
                    )

                # Map FlexPay transaction.status → our domain status
                # FlexPay semantics (based on samples):
                #   "0" => succeeded (paid)
                #   "1" => failed
                #   "2" => pending / waiting for payment
                # Anything else or blank => treat as pending
                if tx_status == "0":
                    new_status = "paid"
                elif tx_status == "1":
                    new_status = "failed"
                elif tx_status == "2":
                    new_status = "pending"
                else:
                    new_status = "pending"

                with transaction.atomic():
                    pa.code = code
                    if tx_reference:
                        pa.reference = tx_reference
                    pa.amount = amount
                    pa.amount_customer = amount_customer
                    if tx.get("currency"):
                        pa.currency = tx.get("currency")
                    pa.transaction_time = _parse_flexpay_datetime(tx.get("createdAt"))
                    pa.raw_payload = data
                    pa.status = new_status
                    pa.save(
                        update_fields=[
                            "code",
                            "reference",
                            "amount",
                            "amount_customer",
                            "currency",
                            "transaction_time",
                            "raw_payload",
                            "status",
                        ]
                    )
                    updated_attempts += 1

                    # Only mark THIS order as paid when BOTH are "0"
                    if tx_status == "0" and pa.order:
                        order = pa.order
                        if order.payment_status != "paid":
                            order.payment_status = "paid"
                            order.status = "fulfilled"
                            order.save(update_fields=["payment_status", "status"])
                            updated_orders += 1
                            record_coupon_redemption_if_any(order)

                logger.info(
                    "FlexPay OK -> Completed orderNumber=%s (attempt %s)",
                    current_order_number,
                    pa.id,
                )
                per_attempt.append(
                    {
                        "attempt_id": pa.id,
                        "order_number": current_order_number,
                        "success": True,
                        "final_status": new_status,
                    }
                )

            elif code == "1":
                logger.info(
                    "FlexPay: no transaction yet for orderNumber=%s (attempt %s)",
                    current_order_number,
                    pa.id,
                )
                per_attempt.append(
                    {
                        "attempt_id": pa.id,
                        "order_number": current_order_number,
                        "success": True,
                        "final_status": "pending",
                    }
                )
            else:
                logger.warning(
                    "FlexPay unexpected response for %s: %s", current_order_number, data
                )
                per_attempt.append(
                    {
                        "attempt_id": pa.id,
                        "order_number": current_order_number,
                        "success": False,
                        "reason": "unexpected_code",
                    }
                )

        except requests.Timeout:
            logger.exception("FlexPay timeout for orderNumber=%s", current_order_number)
            per_attempt.append(
                {
                    "attempt_id": pa.id,
                    "order_number": current_order_number,
                    "success": False,
                    "reason": "timeout",
                }
            )
        except Exception as e:
            logger.exception(
                "FlexPay check error for orderNumber=%s: %s", current_order_number, e
            )
            per_attempt.append(
                {
                    "attempt_id": pa.id,
                    "order_number": current_order_number,
                    "success": False,
                    "reason": "exception",
                }
            )

    logger.info(
        "FlexPay checks done. checked=%s, attempts_updated=%s, orders_updated=%s",
        checked,
        updated_attempts,
        updated_orders,
    )
    return {
        "checked": checked,
        "attempts_updated": updated_attempts,
        "orders_updated": updated_orders,
        "attempts": per_attempt,
    }


@login_required(login_url="login_page")
@require_POST
def probe_payment_status(request):
    """
    Trigger a targeted FlexPay status probe from the browser.
    Accepts: order_number (preferred), or trans_id, or order_reference.
    Persists the same data as check_flexpay, plus audit who/when probed.
    Returns a compact JSON with a top-level `status`: 'paid' | 'failed' | 'pending'.
    """
    try:
        data = json.loads(request.body or "{}")
        order_number = (data.get("order_number") or "").strip() or None
        trans_id = (data.get("trans_id") or "").strip() or None
        order_ref = (data.get("order_reference") or "").strip() or None

        result = check_flexpay_transactions(
            order_number=order_number, trans_id=trans_id, order_reference=order_ref
        )

        # Derive a consolidated status like mobile_probe
        orders_updated = int(result.get("orders_updated") or 0)
        attempts_list = result.get("attempts") or []
        status = "pending"
        if orders_updated > 0:
            status = "paid"
        else:
            # Look for explicit failure markers
            any_failed = any(
                (
                    isinstance(a, dict)
                    and str(a.get("final_status", "")).lower()
                    in {"failed", "declined", "cancelled"}
                )
                or (
                    isinstance(a, dict)
                    and str(a.get("reason", "")).lower() in {"ref_mismatch"}
                )
                for a in attempts_list
            )
            status = "failed" if any_failed else "pending"

        # --- Audit: mark attempts as probed and create probe logs + order events ---
        try:
            from .models import (
                OrderEvent,
                PaymentProbeLog,
            )  # local import to avoid cycles

            attempts = attempts_list
            ids = [
                a.get("attempt_id")
                for a in attempts
                if isinstance(a, dict) and a.get("attempt_id")
            ]
            now_ts = timezone.now()
            if ids:
                PaymentAttempt.objects.filter(id__in=ids).update(
                    last_probed_at=now_ts,
                    last_probed_by=request.user,
                    processed_by=request.user,
                )
                # Create per-attempt logs and order events
                logs = []
                for a in attempts:
                    if not isinstance(a, dict):
                        continue
                    aid = a.get("attempt_id")
                    if not aid:
                        continue
                    outcome = a.get("final_status") or a.get("reason") or ""
                    try:
                        logs.append(
                            PaymentProbeLog(
                                attempt_id=aid,
                                user=request.user
                                if request.user.is_authenticated
                                else None,
                                order_number=order_number
                                or (a.get("order_number") or ""),
                                trans_id=trans_id or "",
                                order_reference=order_ref or "",
                                outcome_status=str(outcome).lower(),
                                orders_updated=orders_updated,
                                raw_gateway_code=str(result.get("code") or ""),
                            )
                        )
                        # Order-level audit event
                        try:
                            pa = (
                                PaymentAttempt.objects.select_related("order")
                                .only("order_id")
                                .get(id=aid)
                            )
                            if pa.order_id:
                                OrderEvent.objects.create(
                                    order=pa.order,
                                    event_type="payment_probe",
                                    message=f"Probe result: {status}",
                                    attempt=pa,
                                    payload={
                                        "orders_updated": orders_updated,
                                        "outcome": str(outcome).lower(),
                                    },
                                )
                        except Exception:
                            pass
                    except Exception:
                        # Don't fail the endpoint on log issues
                        pass
                if logs:
                    PaymentProbeLog.objects.bulk_create(logs, ignore_conflicts=True)
        except Exception:
            logger.exception("probe_payment_status: auditing failed")

        return JsonResponse(
            {"success": (status == "paid"), "status": status, **result}, status=200
        )
    except Exception as e:
        return JsonResponse(
            {"success": False, "status": "pending", "message": str(e)}, status=500
        )


@login_required(login_url="login_page")
@require_POST
def trigger_cancel_expired_orders(request):
    try:
        # Fire-and-forget cancellation sweep for any expired holds
        cancel_expired_orders.delay()
        return JsonResponse({"success": True}, status=200)
    except Exception as e:
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_POST
def cancel_order_now(request):
    """
    Immediately cancel a specific order regardless of expiration.
    Accepts JSON with either `order_reference` (preferred) or `order_number` and optional `reason`.
    Idempotent and unlinks the order across related tables (inventory, assignments, etc.).

    Auditability: records a `cancel_request` OrderEvent with actor, IP/UA, reason, and before/after status.
    """
    try:
        data = json.loads(request.body or "{}")
        order_ref = (data.get("order_reference") or "").strip() or None
        order_number = (data.get("order_number") or "").strip() or None
        reason = (data.get("reason") or "").strip() or "payment_failed"

        # Request context for audit
        user = getattr(request, "user", None)
        ua = request.META.get("HTTP_USER_AGENT", "")[:255]
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (
            fwd.split(",")[0].strip() if fwd else request.META.get("REMOTE_ADDR", "")
        )[:64]
        idem_key = (
            request.headers.get("Idempotency-Key")
            or request.headers.get("X-Idempotency-Key")
            or data.get("idem_key")
        )

        print("CANCEL ORDER")
        print(order_ref, order_number)

        order = None
        attempt = None

        # If we have an explicit order reference, look up the Order directly
        if order_ref:
            order = (
                Order.objects.filter(order_reference=order_ref)
                .select_related("kit_inventory")
                .first()
            )

        # If not found yet and we have a payment order_number, resolve via PaymentAttempt
        if not order and order_number:
            pa = (
                PaymentAttempt.objects.select_related("order")
                .filter(order_number=order_number)
                .order_by("-created_at")
                .first()
            )
            if pa:
                attempt = pa
                order = pa.order

        if not order:
            return JsonResponse(
                {"success": False, "message": "Order not found"}, status=404
            )

        prev_status = order.status
        res = order.cancel(reason=reason)
        new_status = "cancelled"

        # Write audit trail for the cancel request
        try:
            OrderEvent.objects.create(
                order=order,
                attempt=attempt,
                event_type="cancel_request",
                message=reason or "cancelled",
                payload={
                    "actor_user_id": getattr(user, "id", None),
                    "actor_username": getattr(user, "username", None),
                    "actor_email": getattr(user, "email", None),
                    "ip": ip,
                    "user_agent": ua,
                    "source": "cancel_order_now",
                    "order_reference": order.order_reference,
                    "order_number": order_number or "",
                    "prev_status": prev_status,
                    "new_status": new_status,
                    "idempotency_key": idem_key or "",
                    "result_metrics": res,
                },
            )
        except Exception:
            # Do not fail the API if audit creation has an issue
            logger.exception("cancel_order_now audit logging failed")

        payload = {
            "success": True,
            "result": res,
            "order_reference": order.order_reference,
            "status": new_status,
        }
        return JsonResponse(payload, status=200)
    except Exception as e:
        logger.exception("cancel_order_now error")
        return JsonResponse({"success": False, "message": str(e)}, status=500)


@login_required(login_url="login_page")
@require_POST
def mobile_probe(request):
    """
    Single-shot verification for MOBILE MONEY payments initiated via FlexPay.
    Caller provides whatever identifiers it has; we run a focused check and
    respond with a concise outcome for the UI.
    Persists the same data as check_flexpay, plus audit who/when probed.
    Response contract:
      { success: bool, status: 'paid'|'failed'|'pending', orders_updated?: int }
    """
    try:
        data = json.loads(request.body or "{}")
        order_number = (data.get("order_number") or "").strip() or None
        trans_id = (data.get("trans_id") or "").strip() or None
        order_ref = (data.get("order_reference") or "").strip() or None

        result = check_flexpay_transactions(
            order_number=order_number,
            trans_id=trans_id,
            order_reference=order_ref,
        )

        # --- Audit: mark attempts as probed and create probe logs + order events ---
        try:
            from .models import (
                OrderEvent,
                PaymentProbeLog,
            )  # local import to avoid cycles

            attempts = result.get("attempts") or []
            ids = [
                a.get("attempt_id")
                for a in attempts
                if isinstance(a, dict) and a.get("attempt_id")
            ]
            now_ts = timezone.now()
            if ids:
                PaymentAttempt.objects.filter(id__in=ids).update(
                    last_probed_at=now_ts,
                    last_probed_by=request.user,
                    processed_by=request.user,
                )
                logs = []
                # outcome for mobile is summarized below, but we still log per-attempt info
                for a in attempts:
                    if not isinstance(a, dict):
                        continue
                    aid = a.get("attempt_id")
                    if not aid:
                        continue
                    outcome = a.get("final_status") or a.get("reason") or ""
                    try:
                        logs.append(
                            PaymentProbeLog(
                                attempt_id=aid,
                                user=request.user
                                if request.user.is_authenticated
                                else None,
                                order_number=order_number
                                or (a.get("order_number") or ""),
                                trans_id=trans_id or "",
                                order_reference=order_ref or "",
                                outcome_status=str(outcome).lower(),
                                orders_updated=int(result.get("orders_updated") or 0),
                                raw_gateway_code=str(result.get("code") or ""),
                            )
                        )
                        # Order-level audit event
                        try:
                            pa = (
                                PaymentAttempt.objects.select_related("order")
                                .only("order_id")
                                .get(id=aid)
                            )
                            if pa.order_id:
                                OrderEvent.objects.create(
                                    order=pa.order,
                                    event_type="payment_probe",
                                    message=f"Probe result: {str(outcome).lower()}",
                                    attempt=pa,
                                    payload={
                                        "orders_updated": int(
                                            result.get("orders_updated") or 0
                                        )
                                    },
                                )
                        except Exception:
                            pass
                    except Exception:
                        pass
                if logs:
                    PaymentProbeLog.objects.bulk_create(logs, ignore_conflicts=True)
        except Exception:
            logger.exception("mobile_probe: auditing failed")

        # Heuristic outcome mapping
        orders_updated = int(result.get("orders_updated") or 0)
        attempts = result.get("attempts") or []

        status = "pending"
        success = False

        if orders_updated > 0:
            status = "paid"
            success = True
        else:
            # Inspect attempts for explicit failure markers if available
            any_failed = any(
                (
                    isinstance(a, dict)
                    and str(a.get("final_status", "")).lower()
                    in {"failed", "declined", "cancelled"}
                )
                or (
                    isinstance(a, dict)
                    and str(a.get("reason", "")).lower() in {"ref_mismatch"}
                )
                for a in attempts
            )
            if any_failed:
                status = "failed"
                success = False
            else:
                status = "pending"
                success = False

        # Trigger cancellation sweep when failure is detected
        if status == "failed":
            try:
                cancel_expired_orders.delay()
            except Exception:
                logger.exception(
                    "Failed to enqueue cancel_expired_orders on failed probe"
                )

        payload = {
            "success": success,
            "status": status,
            "orders_updated": orders_updated,
        }
        return JsonResponse(payload, status=200)
    except Exception as e:
        return JsonResponse(
            {"success": False, "status": "pending", "message": str(e)}, status=200
        )
