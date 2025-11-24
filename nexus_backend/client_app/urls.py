"""
URL configuration for nexus_backend project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.urls import path

from client_app import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("landing/", views.landing_page, name="landing_page"),
    path("ajax/get_kyc_status/", views.get_kyc_status, name="get_kyc_status"),
    path("billing/", views.billing_page, name="billing_page"),
    path("support/", views.support, name="support"),
    path("settings/", views.settings, name="settings"),
    path("submit/personal-kyc/", views.submit_personal_kyc, name="submit_personal_kyc"),
    path("submit/business-kyc/", views.submit_business_kyc, name="submit_business_kyc"),
    path(
        "kyc/delete_company_document/",
        views.delete_company_document,
        name="delete_company_document",
    ),
    path(
        "kyc/delete_company_rep_id/",
        views.delete_company_rep_id,
        name="delete_company_rep_id",
    ),
    path(
        "kyc/delete_personal_document/",
        views.delete_personal_document,
        name="delete_personal_document",
    ),
    path(
        "kyc/delete_personal_visa/",
        views.delete_personal_visa,
        name="delete_personal_visa",
    ),
    path("orders/", views.orders_page, name="orders_page"),
    path(
        "orders/get_checkout_options/",
        views.get_checkout_options,
        name="get_checkout_options",
    ),
    path(
        "orders/get_plans_by_kit_type/",
        views.get_plans_by_kit_type,
        name="get_plans_by_kit_type",
    ),
    path("orders/checkout/", views.submit_order, name="submit_order"),
    path(
        "orders/get_installation_fee/",
        views.get_installation_fee,
        name="get_installation_fee",
    ),
    path("subscriptions/", views.subscriptions, name="subscription_list"),
    path(
        "subscriptions/details/<int:id>/",
        views.subscription_details,
        name="subscription_details",
    ),
    path(
        "subscriptions/subscriptions_details_fetch/",
        views.subscriptions_details_fetch,
        name="subscriptions_details_fetch",
    ),
    path(
        "payments/get_methods/", views.get_payment_methods, name="get_payment_methods"
    ),
    path("orders/list/", views.orders_list, name="orders_list"),
    path(
        "orders/details/<str:reference>/print/",
        views.get_order_details_print,
        name="get_order_details_print",
    ),
    path(
        "orders/invoice/details/<str:order_ref>/",
        views.get_invoice_details,
        name="get_invoice_details",
    ),
    path(
        "subscription/list/",
        views.get_user_subscriptions,
        name="get_user_subscriptions",
    ),
    path(
        "client/orders/<str:order_ref>/cancel/", views.cancel_order, name="cancel_order"
    ),
    path(
        "billing_details/payments/<int:order_Id>/",
        views.get_billing_details,
        name="get_billing_details",
    ),
    path("billing/history/", views.billing_history, name="billing_history"),
    path("billing/kpis/", views.billing_kpis, name="billing_kpis"),
    path("billing/unpaid_due_total/", views.unpaid_due_total, name="unpaid_due_total"),
    path("billing/net_due_total/", views.net_due_total, name="net_due_total"),
    path(
        "billing/current_balance_total/",
        views.current_balance_total,
        name="current_balance_total",
    ),
    path(
        "billing/approval/<int:billing_id>/",
        views.billing_approval_details,
        name="billing_approval_details",
    ),
    path("invoice/<int:payment_id>/", views.invoice_view, name="invoice-view"),
    path("support/", views.support_page, name="support_page"),
    path("billing/wallet_ledger/", views.wallet_ledger, name="wallet_ledger"),
    path(
        "invoices/<int:order_id>/pdf/",
        views.report_invoice_pdf,
        name="client_report_invoice_pdf",
    ),
    path(
        "invoices/additional/<int:billing_id>/pdf/",
        views.additional_billing_invoice_pdf,
        name="client_additional_invoice_pdf",
    ),
    # AJAX JSON endpoints used by the template
    path(
        "settings/profile/update/",
        views.settings_profile_update,
        name="settings_profile_update",
    ),
    path(
        "settings/password/update/",
        views.settings_password_update,
        name="settings_password_update",
    ),
    path(
        "settings/notifications/update/",
        views.settings_notifications_update,
        name="settings_notifications_update",
    ),
    path(
        "settings/2fa/toggle/",
        views.settings_twofa_toggle,
        name="settings_twofa_toggle",
    ),
    path(
        "settings/delete/",
        views.settings_delete_account,
        name="settings_delete_account",
    ),
    # Actions from the modal buttons
    path("subscriptions/pause/", views.subscriptions_pause, name="subscriptions_pause"),
    path(
        "subscriptions/resume/", views.subscriptions_resume, name="subscriptions_resume"
    ),
    path(
        "subscriptions/cancel/", views.subscriptions_cancel, name="subscriptions_cancel"
    ),
    # Quick ticket creation
    path(
        "tickets/quick-create/", views.tickets_quick_create, name="tickets_quick_create"
    ),
    path("tickets/<int:pk>/", views.ticket_detail, name="ticket_detail"),
    path("tickets/", views.tickets_list_api, name="tickets_list_api"),
    path(
        "orders/get_kits_by_location/",
        views.get_kits_by_location,
        name="get_kits_by_location",
    ),
    path("orders/get_plans/", views.get_plans, name="get_plans"),
    path("settings/kyc/update/", views.client_kyc_update, name="client_kyc_update"),
    path("feedbacks/<int:job_id>/", views.feedback_view, name="client_feedback_detail"),
]
