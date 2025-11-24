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

from django.urls import include, path

from api import views

urlpatterns = [
    path(
        "payments/flexpay/mobile/callback/",
        views.flexpay_callback_mobile,
        name="flexpay_callback_mobile",
    ),
    path(
        "payments/flexpay/mobile/billing/callback/",
        views.flexpay_callback_additional_billing,
        name="flexpay_callback_additional_billing",
    ),
    path(
        "payments/flexpay/card/callback/",
        views.flexpay_callback_card,
        name="flexpay_callback_card",
    ),
    path("payments/flexpay/cancel/", views.flexpay_cancel, name="flexpay_cancel"),
    path("payments/flexpay/approve/", views.flexpay_approve, name="flexpay_approve"),
    path("payments/flexpay/approve/", views.flexpay_approve, name="flexpay_approve"),
    path("payments/flexpay/decline/", views.flexpay_decline, name="flexpay_decline"),
    path("feedbacks/", include("feedbacks.urls")),
    path(
        "revenue/summary/", views.RevenueSummaryView.as_view(), name="revenue-summary"
    ),
    path(
        "revenue/options/", views.RevenueOptionsView.as_view(), name="revenue-options"
    ),
    path(
        "revenue/entries/<int:pk>/",
        views.RevenueEntryDetailView.as_view(),
        name="revenue-entry-detail",
    ),
    path(
        "revenue/corrections/",
        views.RevenueCorrectionView.as_view(),
        name="revenue-corrections",
    ),
    path("orders/", views.api_create_order, name="api_create_order"),
    path(
        "orders/<int:order_id>/cancel/", views.api_cancel_order, name="api_cancel_order"
    ),
    path("orders/<int:order_id>/pay/", views.api_order_pay, name="api_order_pay"),
    path(
        "payments/<int:payment_id>/retry/",
        views.api_payment_retry,
        name="api_payment_retry",
    ),
    path("payments/webhook/", views.api_payment_webhook, name="api_payment_webhook"),
    path(
        "dashboard/statistics/",
        views.api_dashboard_statistics,
        name="api_dashboard_statistics",
    ),
]
