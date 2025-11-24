from django.urls import path

from . import views

app_name = "site_survey"

urlpatterns = [
    # Site Survey URLs
    path("surveys/", views.survey_dashboard, name="survey_dashboard"),
    path("surveys/api/", views.survey_dashboard_api, name="survey_dashboard_api"),
    # More specific patterns MUST come before general ones
    path(
        "surveys/<int:survey_id>/conduct/", views.conduct_survey, name="conduct_survey"
    ),
    path(
        "surveys/<int:survey_id>/photos/",
        views.upload_survey_photos,
        name="upload_survey_photos",
    ),
    # General pattern comes after specific ones
    path("surveys/<int:survey_id>/", views.survey_detail, name="survey_detail"),
    path("my-surveys/", views.technician_survey_list, name="technician_survey_list"),
    path("get-location/", views.get_location, name="get_location"),
    path("survey/assign/", views.assign_to_technician, name="assign_to_technician"),
    path("survey/start/", views.start_site_survey, name="start_site_survey"),
    path(
        "survey/<int:survey_id>/checklist/",
        views.get_survey_checklist,
        name="get_survey_checklist",
    ),
    path(
        "survey/save-response/", views.save_survey_response, name="save_survey_response"
    ),
    path("survey/submit/", views.submit_survey, name="submit_survey"),
    # Survey reassignment for counter-expertise
    path("survey/reassign/", views.reassign_survey, name="reassign_survey"),
    path("technicians/", views.technicians_list, name="technicians_list"),
    # Additional Billing URLs
    path(
        "billing/extra-charges/",
        views.get_available_extra_charges,
        name="get_available_extra_charges",
    ),
    path("billing/add-cost/", views.add_additional_cost, name="add_additional_cost"),
    path(
        "billing/costs/<int:survey_id>/",
        views.get_additional_costs,
        name="get_additional_costs",
    ),
    path(
        "billing/generate/",
        views.generate_additional_billing,
        name="generate_additional_billing",
    ),
    path(
        "billing/approval/<int:billing_id>/",
        views.customer_billing_approval,
        name="customer_billing_approval",
    ),
    path(
        "billing/payment/<int:billing_id>/",
        views.billing_payment,
        name="billing_payment",
    ),
    path(
        "billing/simulate-payment/<int:billing_id>/",
        views.simulate_payment_processing,
        name="simulate_payment_processing",
    ),
    path(
        "billing/dashboard/",
        views.billing_management_dashboard,
        name="billing_management_dashboard",
    ),
]
