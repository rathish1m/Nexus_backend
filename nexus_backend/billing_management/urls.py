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

from billing_management import views

urlpatterns = [
    path("", views.billing_management, name="billing_management"),
    path("general_ledger/", views.general_ledger, name="general_ledger"),
    path("set-fx-rate/", views.set_fx_rate, name="billing_set_fx_rate"),
    # Ledger exports (per-customer)
    path(
        "ledger/search_customers/",
        views.ledger_search_customers,
        name="ledger_search_customers",
    ),
    path("ledger/export/", views.ledger_export, name="ledger_export"),
    path("ledger/statement/", views.ledger_statement, name="ledger_statement"),
    # Revenue reporting
    path("revenue/summary/", views.revenue_summary, name="revenue_summary"),
    path("revenue/table/", views.revenue_table, name="revenue_table"),
    # Region reconciliation tools
    path("regions/check_order/", views.check_order_region, name="check_order_region"),
    path("regions/fix_order/", views.fix_order_region, name="fix_order_region"),
    # Invoice-centric download and info endpoints
    path(
        "invoice/<path:invoice_id>/pdf/",
        views.invoice_pdf_by_number,
        name="invoice_pdf_by_number",
    ),
    path(
        "invoice/<path:invoice_id>/json/",
        views.invoice_json_by_number,
        name="invoice_json_by_number",
    ),
    path(
        "consolidated/<path:consolidated_number>/pdf/",
        views.consolidated_invoice_pdf,
        name="consolidated_invoice_pdf",
    ),
]
