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

from dashboard_bi import views

urlpatterns = [
    path("", views.dashboard_bi, name="dashboard_bi"),
    path("kpis/", views.kpis_monthly, name="kpis_monthly"),
    path("kpis/annual/", views.kpis_annual, name="kpis_annual"),
    path(
        "reports/export/customers",
        views.export_customers_csv,
        name="export_customers_csv",
    ),
    path("reports/export/orders", views.export_orders_csv, name="export_orders_csv"),
    path(
        "reports/export/subscriptions",
        views.export_subscriptions_csv,
        name="export_subscriptions_csv",
    ),
    path(
        "reports/export/revenue_monthly",
        views.export_revenue_monthly_csv,
        name="export_revenue_monthly_csv",
    ),
    path("reports/export/tickets", views.export_tickets_csv, name="export_tickets_csv"),
    path(
        "reports/export/inventory",
        views.export_inventory_csv,
        name="export_inventory_csv",
    ),
    path(
        "reports/export/generalledger",
        views.export_general_ledger_csv,
        name="export_general_ledger_csv",
    ),
    path(
        "reports/export/trialbalance",
        views.export_trial_balance_csv,
        name="export_trial_balance_csv",
    ),
]
