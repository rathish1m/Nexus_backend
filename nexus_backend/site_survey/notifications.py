"""
Système de notifications pour les site surveys
Gère l'envoi d'emails et SMS lors des rejets de surveys
"""

import logging

from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

logger = logging.getLogger(__name__)


def send_billing_notification(billing):
    """
    Envoie une notification de facturation additionnelle au client
    """
    try:
        if not billing or not billing.survey.order.user:
            logger.warning("Billing notification: Missing billing or user data")
            return False

        customer = billing.survey.order.user
        customer_email = customer.email

        if not customer_email:
            logger.warning(f"Billing {billing.id}: No customer email found")
            return False

        # Context for template
        context = {
            "billing": billing,
            "customer": customer,
            "order": billing.survey.order,
            "survey": billing.survey,
            "customer_name": _get_customer_name(billing.survey.order),
            "order_reference": billing.survey.order.order_reference,
            "approval_url": f"{settings.SITE_URL}/site-survey/billing/approval/{billing.id}/",
            "support_email": getattr(settings, "SUPPORT_EMAIL", "support@nexus.com"),
            "support_phone": getattr(settings, "SUPPORT_PHONE", "+33 1 23 45 67 89"),
            "current_date": timezone.now().strftime("%d/%m/%Y"),
        }

        # Email subject
        subject = f"📋 Additional Equipment Required - Order #{billing.survey.order.order_reference}"

        # HTML email body
        html_message = render_to_string(
            "site_survey/emails/billing_notification.html", context
        )

        # Plain text version (fallback)
        plain_message = strip_tags(html_message)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "nexus@example.com"),
            recipient_list=[customer_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            f"Billing notification sent to customer {customer_email} for billing {billing.id}"
        )
        return True

    except Exception as e:
        logger.error(
            f"Error sending billing notification for billing {billing.id}: {str(e)}"
        )
        return False


def send_payment_confirmation(billing):
    """
    Envoie une confirmation de paiement au client
    """
    try:
        if not billing or not billing.survey.order.user:
            logger.warning("Payment confirmation: Missing billing or user data")
            return False

        customer = billing.survey.order.user
        customer_email = customer.email

        if not customer_email:
            logger.warning(
                f"Payment confirmation {billing.id}: No customer email found"
            )
            return False

        # Context for template
        context = {
            "billing": billing,
            "customer": customer,
            "order": billing.survey.order,
            "survey": billing.survey,
            "customer_name": _get_customer_name(billing.survey.order),
            "order_reference": billing.survey.order.order_reference,
            "billing_reference": billing.billing_reference,
            "amount_paid": billing.total_amount,
            "payment_date": (
                getattr(billing, "paid_at", None)
                or getattr(billing, "created_at", None)
                or timezone.now()
            ).strftime("%d/%m/%Y"),
            "support_email": getattr(settings, "SUPPORT_EMAIL", "support@nexus.com"),
            "support_phone": getattr(settings, "SUPPORT_PHONE", "+33 1 23 45 67 89"),
            "current_date": timezone.now().strftime("%d/%m/%Y"),
        }

        # Email subject
        subject = f"✅ Payment Confirmed - Additional Equipment Order #{billing.survey.order.order_reference}"

        # HTML email body
        html_message = render_to_string(
            "site_survey/emails/payment_confirmation.html", context
        )

        # Plain text version (fallback)
        plain_message = strip_tags(html_message)

        # Send email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "nexus@example.com"),
            recipient_list=[customer_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            f"Payment confirmation sent to customer {customer_email} for billing {billing.id}"
        )
        return True

    except Exception as e:
        logger.error(
            f"Error sending payment confirmation for billing {billing.id}: {str(e)}"
        )
        return False


def send_rejection_notification_to_technician(survey):
    """
    Envoie une notification au technician quand son survey est rejeté
    """
    try:
        if not survey.technician or not survey.technician.email:
            logger.warning(f"Survey {survey.id}: Pas d'email pour le technician")
            return False

        # Contexte pour le template
        context = {
            "survey": survey,
            "technician": survey.technician,
            "order": survey.order,
            "rejection_reason": survey.rejection_reason or "Aucune raison spécifiée",
            "survey_url": f"{settings.SITE_URL}/site-survey/surveys/{survey.id}/",
            "dashboard_url": f"{settings.SITE_URL}/site-survey/surveys/",
            "current_date": timezone.now().strftime("%d/%m/%Y à %H:%M"),
        }

        # Sujet de l'email
        subject = f"🔴 Site Survey #{survey.id} Rejeté - Action Requise"

        # Corps HTML de l'email
        html_message = render_to_string(
            "site_survey/emails/rejection_notification_technician.html", context
        )

        # Version texte (fallback)
        plain_message = strip_tags(html_message)

        # Envoi de l'email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "nexus@example.com"),
            recipient_list=[survey.technician.email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            f"Email de rejet envoyé au technician {survey.technician.email} pour survey {survey.id}"
        )

        # Tentative d'envoi SMS si numéro disponible
        if hasattr(survey.technician, "phone") and survey.technician.phone:
            send_rejection_sms_to_technician(survey)

        return True

    except Exception as e:
        logger.error(f"Erreur envoi email technician pour survey {survey.id}: {str(e)}")
        return False


def send_rejection_notification_to_customer(survey):
    """
    Envoie une notification au client quand son survey est rejeté
    """
    try:
        # Récupérer l'email du client via la commande
        customer_email = None
        if survey.order and hasattr(survey.order, "customer"):
            customer_email = survey.order.customer.email
        elif survey.order and hasattr(survey.order, "email"):
            customer_email = survey.order.email

        if not customer_email:
            logger.warning(f"Survey {survey.id}: Pas d'email client trouvé")
            return False

        # Contexte pour le template
        context = {
            "survey": survey,
            "order": survey.order,
            "customer_name": _get_customer_name(survey.order),
            "order_reference": survey.order.order_reference if survey.order else "N/A",
            "support_email": getattr(settings, "SUPPORT_EMAIL", "support@nexus.com"),
            "support_phone": getattr(settings, "SUPPORT_PHONE", "+33 1 23 45 67 89"),
            "current_date": timezone.now().strftime("%d/%m/%Y"),
        }

        # Sujet de l'email
        subject = "📋 Mise à Jour - Étude de Site en Cours de Révision"

        # Corps HTML de l'email
        html_message = render_to_string(
            "site_survey/emails/rejection_notification_customer.html", context
        )

        # Version texte (fallback)
        plain_message = strip_tags(html_message)

        # Envoi de l'email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "nexus@example.com"),
            recipient_list=[customer_email],
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            f"Email de rejet envoyé au client {customer_email} pour survey {survey.id}"
        )
        return True

    except Exception as e:
        logger.error(f"Erreur envoi email client pour survey {survey.id}: {str(e)}")
        return False


def send_rejection_alert_to_admin(survey):
    """
    Envoie une alerte aux admins quand un survey est rejeté
    """
    try:
        admin_emails = getattr(settings, "ADMIN_NOTIFICATION_EMAILS", [])
        if not admin_emails:
            # Fallback: récupérer les emails des superusers
            from main.models import User

            admin_emails = list(
                User.objects.filter(is_superuser=True).values_list("email", flat=True)
            )

        if not admin_emails:
            logger.warning(f"Survey {survey.id}: Aucun email admin configuré")
            return False

        # Contexte pour le template
        context = {
            "survey": survey,
            "technician": survey.technician,
            "order": survey.order,
            "rejection_reason": survey.rejection_reason or "Aucune raison spécifiée",
            "dashboard_url": f"{settings.SITE_URL}/site-survey/surveys/",
            "survey_url": f"{settings.SITE_URL}/site-survey/surveys/{survey.id}/",
            "current_date": timezone.now().strftime("%d/%m/%Y à %H:%M"),
        }

        # Sujet de l'email
        subject = f"⚠️ Alerte: Survey #{survey.id} Rejeté - Suivi Requis"

        # Corps HTML de l'email
        html_message = render_to_string(
            "site_survey/emails/rejection_alert_admin.html", context
        )

        # Version texte (fallback)
        plain_message = strip_tags(html_message)

        # Envoi de l'email
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "nexus@example.com"),
            recipient_list=admin_emails,
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            f"Alerte admin envoyée pour survey {survey.id} à {len(admin_emails)} destinataires"
        )
        return True

    except Exception as e:
        logger.error(f"Erreur envoi alerte admin pour survey {survey.id}: {str(e)}")
        return False


def send_rejection_sms_to_technician(survey):
    """
    Envoie un SMS au technician (si service SMS configuré)
    """
    try:
        if not hasattr(survey.technician, "phone") or not survey.technician.phone:
            return False

        # Message SMS court
        message = f"Nexus: Votre survey #{survey.id} (commande {survey.order.order_reference if survey.order else 'N/A'}) a été rejeté. Consultez votre email pour les détails."

        # Si Twilio est configuré
        if hasattr(settings, "TWILIO_ACCOUNT_SID") and settings.TWILIO_ACCOUNT_SID:
            try:
                from twilio.rest import Client

                client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

                message_instance = client.messages.create(
                    body=message,
                    from_=settings.TWILIO_PHONE_NUMBER,
                    to=survey.technician.phone,
                )

                logger.info(
                    f"SMS envoyé au technician {survey.technician.phone} pour survey {survey.id}: {message_instance.sid}"
                )
                return True

            except Exception as twilio_error:
                logger.error(
                    f"Erreur Twilio pour survey {survey.id}: {str(twilio_error)}"
                )

        # Fallback: log du message SMS
        logger.info(f"SMS simulation pour {survey.technician.phone}: {message}")
        return True

    except Exception as e:
        logger.error(f"Erreur envoi SMS technician pour survey {survey.id}: {str(e)}")
        return False


def _get_customer_name(order):
    """
    Utilitaire pour récupérer le nom du client à partir de la commande
    """
    if not order:
        return "Cher client"

    if hasattr(order, "customer") and order.customer:
        if hasattr(order.customer, "full_name") and order.customer.full_name:
            return order.customer.full_name
        elif hasattr(order.customer, "first_name") and order.customer.first_name:
            return f"{order.customer.first_name} {getattr(order.customer, 'last_name', '')}"

    # Fallback
    return "Cher client"


def send_all_rejection_notifications(survey):
    """
    Fonction principale qui envoie toutes les notifications lors d'un rejet
    """
    results = {
        "technician_email": False,
        "customer_email": False,
        "admin_alert": False,
        "technician_sms": False,
    }

    try:
        # Notification au technician
        results["technician_email"] = send_rejection_notification_to_technician(survey)

        # Notification au client
        results["customer_email"] = send_rejection_notification_to_customer(survey)

        # Alerte aux admins
        results["admin_alert"] = send_rejection_alert_to_admin(survey)

        # Log du résumé
        success_count = sum(1 for success in results.values() if success)
        logger.info(
            f"Survey {survey.id} rejeté: {success_count}/4 notifications envoyées avec succès"
        )

        return results

    except Exception as e:
        logger.error(f"Erreur globale notifications pour survey {survey.id}: {str(e)}")
        return results


def send_reassignment_notifications(
    site_survey, previous_technician, new_technician, reason, admin_user
):
    """
    Envoie toutes les notifications lors d'une réassignation pour contre-expertise
    """
    results = {
        "previous_technician": False,
        "new_technician": False,
        "customer": False,
        "admin_confirmation": False,
    }

    try:
        base_context = {
            "survey": site_survey,
            "customer": (
                site_survey.customer if hasattr(site_survey, "customer") else None
            ),
            "previous_technician": previous_technician,
            "new_technician": new_technician,
            "reason": reason,
            "admin_user": admin_user,
            "survey_detail_url": f"/site-survey/survey/{site_survey.id}/",
            "dashboard_url": "/site-survey/dashboard/",
        }

        # 1. Notifier l'ancien technicien
        if (
            previous_technician
            and hasattr(previous_technician, "email")
            and previous_technician.email
        ):
            try:
                subject = (
                    f"📋 Votre Survey #{site_survey.id} Réassigné pour Contre-Expertise"
                )

                context = {
                    **base_context,
                    "survey_id": site_survey.id,
                    "order_reference": (
                        site_survey.order.order_reference
                        if hasattr(site_survey, "order") and site_survey.order
                        else "N/A"
                    ),
                    "address": site_survey.address,
                    "customer_name": (
                        _get_customer_name(site_survey.order)
                        if hasattr(site_survey, "order")
                        else "Client"
                    ),
                }

                # Template simple pour l'instant (sera créé plus tard)
                message = f"""
                Bonjour {previous_technician.full_name or previous_technician.username},

                Votre site survey #{site_survey.id} a été réassigné à un autre technicien pour une contre-expertise.

                Détails:
                - Commande: {context['order_reference']}
                - Adresse: {context['address']}
                - Nouveau technicien: {new_technician.full_name or new_technician.username}
                - Raison: {reason}

                Cette décision a été prise par l'administration pour s'assurer de la qualité de nos évaluations.

                Cordialement,
                L'équipe NEXUS
                """

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[previous_technician.email],
                    fail_silently=False,
                )

                results["previous_technician"] = True
                logger.info(
                    f"Notification réassignation envoyée à l'ancien technicien {previous_technician.email}"
                )

            except Exception as e:
                logger.error(f"Erreur notification ancien technicien: {str(e)}")

        # 2. Notifier le nouveau technicien
        if new_technician and hasattr(new_technician, "email") and new_technician.email:
            try:
                subject = f"🔧 Nouvelle Assignment Survey #{site_survey.id} - Contre-Expertise Requise"

                context = {
                    **base_context,
                    "survey_id": site_survey.id,
                    "order_reference": (
                        site_survey.order.order_reference
                        if hasattr(site_survey, "order") and site_survey.order
                        else "N/A"
                    ),
                    "address": site_survey.address,
                    "scheduled_date": site_survey.scheduled_date,
                    "customer_name": (
                        _get_customer_name(site_survey.order)
                        if hasattr(site_survey, "order")
                        else "Client"
                    ),
                }

                message = f"""
                Bonjour {new_technician.full_name or new_technician.username},

                Un site survey vous a été assigné pour une contre-expertise.

                Détails de la mission:
                - Survey ID: #{site_survey.id}
                - Commande: {context['order_reference']}
                - Client: {context['customer_name']}
                - Adresse: {context['address']}
                - Date prévue: {context['scheduled_date']}
                - Raison de la réassignation: {reason}

                Cette réassignation fait suite à un besoin de contre-expertise pour s'assurer de la qualité de l'évaluation.

                Merci de procéder à cette évaluation avec attention.

                Cordialement,
                L'équipe NEXUS
                """

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[new_technician.email],
                    fail_silently=False,
                )

                results["new_technician"] = True
                logger.info(
                    f"Notification réassignation envoyée au nouveau technicien {new_technician.email}"
                )

            except Exception as e:
                logger.error(f"Erreur notification nouveau technicien: {str(e)}")

        # 3. Notifier le client (optionnel)
        if (
            hasattr(site_survey, "customer")
            and site_survey.customer
            and hasattr(site_survey.customer, "email")
            and site_survey.customer.email
        ):
            try:
                subject = "📞 Mise à jour de votre Survey Starlink - Technicien Spécialisé Assigné"

                customer_name = (
                    _get_customer_name(site_survey.order)
                    if hasattr(site_survey, "order")
                    else "Cher client"
                )

                message = f"""
                {customer_name},

                Nous vous informons qu'un technicien spécialisé a été assigné à votre évaluation de site pour l'installation Starlink.

                Cette décision a été prise pour nous assurer de vous fournir la meilleure évaluation possible de votre site.

                Le nouveau technicien prendra contact avec vous très prochainement pour convenir d'un nouveau rendez-vous.

                Nous nous excusons pour tout désagrément et vous remercions de votre compréhension.

                Cordialement,
                L'équipe NEXUS
                """

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[site_survey.customer.email],
                    fail_silently=False,
                )

                results["customer"] = True
                logger.info(
                    f"Notification réassignation envoyée au client {site_survey.customer.email}"
                )

            except Exception as e:
                logger.error(f"Erreur notification client: {str(e)}")

        # 4. Confirmation aux admins
        try:
            from main.models import User

            admin_users = User.objects.filter(is_staff=True, is_active=True)
            admin_emails = [
                admin.email
                for admin in admin_users
                if admin.email and admin.id_user != admin_user.id_user
            ]

            if admin_emails:
                subject = f"✅ Réassignation Survey #{site_survey.id} Confirmée - Contre-Expertise Initiée"

                message = f"""
                Réassignation confirmée:

                Survey: #{site_survey.id}
                Ancien technicien: {previous_technician.full_name or previous_technician.username if previous_technician else 'Aucun'}
                Nouveau technicien: {new_technician.full_name or new_technician.username}
                Raison: {reason}
                Réassigné par: {admin_user.full_name or admin_user.username}

                Le nouveau technicien a été notifié et le survey est maintenant en statut 'scheduled'.
                """

                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=admin_emails,
                    fail_silently=False,
                )

                results["admin_confirmation"] = True
                logger.info(
                    f"Confirmation réassignation envoyée à {len(admin_emails)} admin(s)"
                )

        except Exception as e:
            logger.error(f"Erreur confirmation admin: {str(e)}")

        # Résumé
        success_count = sum(1 for success in results.values() if success)
        logger.info(
            f"Survey {site_survey.id} réassigné: {success_count}/4 notifications envoyées avec succès"
        )

        return results

    except Exception as e:
        logger.error(
            f"Erreur globale notifications réassignation pour survey {site_survey.id}: {str(e)}"
        )
        return results


def send_sms_notification(phone_number, message):
    """
    Utilitaire pour envoyer des SMS (Twilio ou simulation)
    """
    try:
        if hasattr(settings, "TWILIO_ACCOUNT_SID") and settings.TWILIO_ACCOUNT_SID:
            from twilio.rest import Client

            client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

            message_instance = client.messages.create(
                body=message, from_=settings.TWILIO_PHONE_NUMBER, to=phone_number
            )

            logger.info(f"SMS envoyé à {phone_number}: {message_instance.sid}")
            return True
        else:
            # Simulation SMS
            logger.info(f"SMS simulation pour {phone_number}: {message}")
            return True

    except Exception as e:
        logger.error(f"Erreur envoi SMS à {phone_number}: {str(e)}")
        return False
