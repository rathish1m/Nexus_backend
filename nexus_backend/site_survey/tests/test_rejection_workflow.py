# nexus_backend/site_survey/tests/test_rejection_workflow.py
from unittest.mock import patch

import pytest

from django.urls import reverse

# Assurez-vous que ces imports correspondent à votre structure réelle
# from site_survey.notifications import send_rejection_notification_to_technician # Si vous avez un tel module


# Mock de la fonction de notification si elle n'est pas dans models.py
# Si send_rejection_notification_to_technician est une méthode de SiteSurvey,
# le patch serait sur 'site_survey.models.SiteSurvey.send_rejection_notification_to_technician'
@patch(
    "site_survey.notifications.send_rejection_notification_to_technician"
)  # Adaptez le chemin si nécessaire
@pytest.mark.django_db
def test_rejection_notification_sent_on_status_change(
    mock_send_notification, survey_factory
):
    """
    Vérifie que la notification de rejet est envoyée uniquement lors du passage
    au statut 'rejected'.
    """
    # Création initiale d'un survey avec un statut non rejeté
    survey = survey_factory(status="approved")
    mock_send_notification.assert_not_called()

    # Changement vers le statut 'rejected'
    survey.status = "rejected"
    survey.save()

    # Vérification que la notification a été envoyée une fois
    mock_send_notification.assert_called_once_with(survey)

    # Réinitialisation du mock et sauvegarde sans changement de statut
    mock_send_notification.reset_mock()
    survey.notes = "Nouvelle note"
    survey.save()
    # La notification ne devrait pas être appelée à nouveau
    mock_send_notification.assert_not_called()


@pytest.mark.django_db
def test_submit_survey_with_missing_assessment_fails(survey_factory):
    """
    Vérifie qu'une soumission de survey sans 'Overall Assessment' échoue
    avec une erreur 400 via l'API.
    """
    # Create and log in a user for authentication using Django test client
    from django.test import Client

    from main.models import User

    client = Client()
    user = User.objects.create_user(
        username="test_user", email="test@example.com", full_name="Test User"
    )

    # Create survey with the user as technician to pass authorization
    survey = survey_factory(status="pending", technician=user)
    client.force_login(user)

    # Use the correct URL namespace for site_survey app
    url = reverse("site_survey:submit_survey")

    # Données incomplètes (overall_assessment est manquant)
    import json

    payload = {
        "survey_id": survey.id,
        "installation_feasible": True,
        "requires_additional_equipment": False,
        # Missing overall_assessment to trigger validation error
    }

    response = client.post(
        url, data=json.dumps(payload), content_type="application/json"
    )

    assert response.status_code == 400
    assert "errors" in response.json()
    assert "overall_assessment" in response.json()["errors"]
    assert (
        response.json()["errors"]["overall_assessment"]
        == "Veuillez fournir une évaluation globale."
    )
