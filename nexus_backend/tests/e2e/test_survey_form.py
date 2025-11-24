# End-to-end tests for the site survey form using Playwright.
import pytest
from playwright.sync_api import Page, expect


@pytest.mark.e2e
def test_survey_validation_errors_on_empty_submit(page: Page, live_server):
    """
    Vérifie que des erreurs de validation s'affichent lors de la soumission
    d'un formulaire de survey vide.
    """
    page.goto(f"{live_server.url}/tech/fe/")

    # Ouvre le modal de survey (adaptez le sélecteur si nécessaire)
    page.locator(".conduct-survey-button").first.click()

    # Clique sur "Submit Survey" sans remplir aucun champ
    page.locator('button:has-text("Submit Survey")').click()

    # Vérifie les messages d'erreur pour les champs critiques
    overall_assessment_error = page.locator("#overall_assessment_error_message")
    expect(overall_assessment_error).to_be_visible()
    expect(overall_assessment_error).to_have_text(
        "Veuillez fournir une évaluation globale."
    )

    # Vérifie le style du champ (ex: bordure rouge)
    overall_assessment_textarea = page.locator("#id_overall_assessment")
    expect(overall_assessment_textarea).to_have_class("validation-error")

    # Remplit le champ et vérifie que l'erreur disparaît
    overall_assessment_textarea.fill("Ceci est une évaluation de test.")
    expect(overall_assessment_error).not_to_be_visible()
    expect(overall_assessment_textarea).not_to_have_class("validation-error")


@pytest.mark.e2e
def test_additional_equipment_conditional_validation(page: Page, live_server):
    """
    Vérifie la validation conditionnelle pour le champ 'Additional Equipment Required?'.
    """
    page.goto(f"{live_server.url}/tech/fe/")
    page.locator(".conduct-survey-button").first.click()

    # Sélectionne "Yes, additional equipment needed"
    page.locator("#id_requires_additional_equipment").select_option("true")

    # Soumet le formulaire sans ajouter de justification de coûts
    page.locator('button:has-text("Submit Survey")').click()

    # S'attend à une erreur pour la justification des coûts manquante
    cost_justification_error = page.locator(
        "#additional_costs_justification_error_message"
    )
    expect(cost_justification_error).to_be_visible()
    expect(cost_justification_error).to_have_text(
        "Veuillez justifier les coûts supplémentaires."
    )

    # Remplit la justification et s'attend à ce que l'erreur disparaisse
    page.locator("#id_additional_costs_justification").fill(
        "Justification pour l'équipement supplémentaire."
    )
    expect(cost_justification_error).not_to_be_visible()
