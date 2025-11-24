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

from app_settings import views

urlpatterns = [
    path("", views.system_settings, name="system_settings"),
    # Company settings (UI + AJAX update)
    path(
        "settings/company/update/",
        views.company_settings_update,
        name="settings_company_update",
    ),
    path(
        "settings/company/delete-file/",
        views.company_settings_delete_file,
        name="settings_company_delete_file",
    ),
    path("add_plan/", views.create_subscription_plan, name="create_subscription_plan"),
    path(
        "subscription/get_subscription_plans/",
        views.get_subscription_plans,
        name="get_subscriptions_plan",
    ),
    path(
        "subscription/get_subscription/<int:pk>/",
        views.get_subscription,
        name="get_subscription",
    ),
    # path(
    #     "subscription/get_subscription/<int:pk>/edit/",
    #     views.edit_subscription,
    #     name="edit_subscription",
    # ),
    path(
        "subscription/toggle_plan_status/<int:pk>/",
        views.toggle_plan_status,
        name="toggle_plan_status",
    ),
    path(
        "subscription/delete_plan/<int:pk>/",
        views.delete_plan,
        name="delete_plan",
    ),
    path("kit/get_kits/", views.get_kits, name="get_kits"),
    path("kit/add_kit/", views.add_kit, name="add_kit"),
    path("kit/get_kit/<int:pk>/", views.get_kit, name="get_kit"),
    path("kit/edit_kit/<int:pk>/", views.edit_kit, name="edit_kit"),
    path("kit/delete_kit/<int:pk>/", views.delete_kit, name="delete_kit"),
    path("taxes/add/", views.taxes_add, name="taxes_add"),
    path("taxes/list/", views.taxes_list, name="taxes_list"),
    path("taxes/choices/", views.taxes_choices, name="taxes_choices"),
    path("taxes/<int:pk>/", views.taxes_detail, name="taxes_detail"),
    path("payments_method/add/", views.payments_method_add, name="payments_method_add"),
    path(
        "payments_method/list/", views.payments_method_list, name="payments_method_list"
    ),
    path("payments_method/choices/", views.payment_choices, name="payment_choices"),
    path(
        "payments_method/<int:pk>/",
        views.payments_method_detail,
        name="payments_method_detail",
    ),
    path(
        "installation_fee/add/", views.installation_fee_add, name="installation_fee_add"
    ),
    path(
        "installation_fee/list/",
        views.installation_fee_list,
        name="installation_fee_list",
    ),
    path(
        "installation_fee/choices/",
        views.installation_fee_choices,
        name="installation_fee_choices",
    ),
    path(
        "installation_fee/<int:pk>/",
        views.installation_fee_detail,
        name="installation_fee_detail",
    ),
    path("region/add/", views.region_add, name="region_add"),
    path("region/list/", views.region_list, name="region_list"),
    # Starlink Kits Management
    path(
        "starlink_kit/management/",
        views.starlink_kit_management,
        name="starlink_kit_management",
    ),
    path(
        "starlink_kit/get_starlink_kits/",
        views.get_starlink_kits,
        name="get_starlink_kits",
    ),
    path(
        "starlink_kit/add_starlink_kit/",
        views.add_starlink_kit,
        name="add_starlink_kit",
    ),
    path(
        "starlink_kit/get_starlink_kit/<int:pk>/",
        views.get_starlink_kit,
        name="get_starlink_kit",
    ),
    path(
        "starlink_kit/edit_starlink_kit/<int:pk>/",
        views.edit_starlink_kit,
        name="edit_starlink_kit",
    ),
    path(
        "starlink_kit/delete_starlink_kit/<int:pk>/",
        views.delete_starlink_kit,
        name="delete_starlink_kit",
    ),
    # Subscription Plans Management
    path(
        "subscription_plan/management/",
        views.subscription_plan_management,
        name="subscription_plan_management",
    ),
    path(
        "subscription_plan/get_subscription_plans/",
        views.get_subscription_plans,
        name="get_subscription_plans",
    ),
    path(
        "subscription_plan/get_subscription_plans_paginated/",
        views.get_subscription_plans_paginated,
        name="get_subscription_plans_paginated",
    ),
    path(
        "subscription_plan/add_subscription_plan/",
        views.add_subscription_plan,
        name="add_subscription_plan",
    ),
    path(
        "subscription_plan/get_subscription_plan/<int:pk>/",
        views.get_subscription_plan,
        name="get_subscription_plan",
    ),
    path(
        "subscription_plan/<int:pk>/",
        views.edit_subscription_plan,
        name="edit_subscription_plan_by_pk",
    ),
    path(
        "subscription_plan/edit_subscription_plan/<int:pk>/",
        views.edit_subscription_plan,
        name="edit_subscription_plan",
    ),
    path(
        "subscription_plan/toggle_subscription_plan_status/<int:pk>/",
        views.toggle_subscription_plan_status,
        name="toggle_subscription_plan_status",
    ),
    path(
        "subscription_plan/delete_subscription_plan/<int:pk>/",
        views.delete_subscription_plan,
        name="delete_subscription_plan",
    ),
    # Site Survey Checklist Management
    path(
        "site_survey_checklist/get_checklist/",
        views.get_site_survey_checklist,
        name="get_site_survey_checklist",
    ),
    path(
        "site_survey_checklist/create/",
        views.create_checklist_item,
        name="create_checklist_item",
    ),
    path(
        "site_survey_checklist/update/",
        views.update_checklist_item,
        name="update_checklist_item",
    ),
    path(
        "site_survey_checklist/delete/",
        views.delete_checklist_item,
        name="delete_checklist_item",
    ),
    # Extra Charges Management
    path(
        "extra_charges/get_extra_charges/",
        views.get_extra_charges,
        name="get_extra_charges",
    ),
    path(
        "extra_charges/create/",
        views.create_extra_charge,
        name="create_extra_charge",
    ),
    path(
        "extra_charges/update/",
        views.update_extra_charge,
        name="update_extra_charge",
    ),
    path(
        "extra_charges/delete/",
        views.delete_extra_charge,
        name="delete_extra_charge",
    ),
    # Additional Billing Management
    path(
        "additional_billings/",
        views.additional_billings_management,
        name="additional_billings_management",
    ),
    path(
        "additional_billings/get/",
        views.get_additional_billings,
        name="get_additional_billings",
    ),
    path(
        "additional_billings/generate/",
        views.generate_survey_billing,
        name="generate_survey_billing",
    ),
    path(
        "additional_billings/update_status/",
        views.update_billing_status,
        name="update_billing_status",
    ),
    path(
        "backoffice/billing/config", views.billing_config_get, name="billing_config_get"
    ),
    path(
        "backoffice/billing/config/save",
        views.billing_config_save,
        name="billing_config_save",
    ),
    # ---- Coupons ----
    path("coupons/list/", views.coupon_list, name="coupon_list"),
    path("coupons/create/", views.coupon_create, name="coupon_create"),
    path("coupons/bulk_create/", views.coupon_bulk_create, name="coupon_bulk_create"),
    path("coupons/<int:coupon_id>/toggle/", views.coupon_toggle, name="coupon_toggle"),
    path("coupons/<int:coupon_id>/delete/", views.coupon_delete, name="coupon_delete"),
    # ---- Promotions ----
    # List (GET, returns JSON with promotions[])
    path("promotions/", views.promotion_list, name="promotion_list"),
    # Create (POST, body = promotion payload JSON)
    path("promotions/create/", views.promotion_create, name="promotion_create"),
    # Detail (GET a single promotion as JSON by id)
    path(
        "promotions/<int:promotion_id>/",
        views.promotion_detail,
        name="promotion_detail",
    ),
    # Update (POST, body = promotion payload JSON)
    path(
        "promotions/<int:promotion_id>/update/",
        views.promotion_update,
        name="promotion_update",
    ),
    # Toggle active/inactive (POST, no body needed)
    path(
        "promotions/<int:promotion_id>/toggle/",
        views.promotion_toggle,
        name="promotion_toggle",
    ),
    # Delete (POST, no body needed)
    path(
        "promotions/<int:promotion_id>/delete/",
        views.promotion_delete,
        name="promotion_delete",
    ),
    path("company/", views.company_settings_view, name="settings_company"),
    path(
        "company/update/", views.company_settings_update, name="settings_company_update"
    ),
]
