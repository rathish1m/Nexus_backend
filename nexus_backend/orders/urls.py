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

from orders import views

urlpatterns = [
    path("", views.order_management, name="order_management"),
    path("list_orders/", views.admin_view_orders, name="admin_view_orders"),
    path(
        "details/<int:order_id>/",
        views.admin_view_orders_details,
        name="admin_view_orders_details",
    ),
    path(
        "pay/<int:order_id>/process_payment/",
        views.process_order_payment,
        name="process_order_payment",
    ),
    # Dedicated consolidated payment route (consolidated number can contain slashes like INV/000002)
    path(
        "pay/consolidated/<path:consolidated_number>/process_payment/",
        views.process_order_payment,
        name="process_consolidated_payment",
    ),
    # Process payment by invoice number (can include slashes like INV/000123)
    path(
        "pay/invoice/<path:invoice_id>/process_payment/",
        views.process_invoice_payment,
        name="process_invoice_payment",
    ),
    # Unified route: numeric order id or invoice-like reference (e.g., INV/000002)
    path(
        "pay/<path:identifier>/process_payment/",
        views.process_payment_unified,
        name="process_payment_unified",
    ),
    path(
        "invoices/<int:order_id>/pdf/",
        views.report_invoice_pdf,
        name="report_invoice_pdf",
    ),
]
