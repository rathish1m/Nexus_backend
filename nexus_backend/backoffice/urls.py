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

from backoffice import views

urlpatterns = [
    path("", views.backoffice_main, name="backoffice_main"),
    path("dispatch/dashboard/", views.dispatch_dashboard, name="dispatch_dashboard"),
    path(
        "dispatch/order/delivered/",
        views.deliver_order_dispatch,
        name="deliver_order_dispatch",
    ),
    path("dispatch/items_list/", views.items_list, name="items_list"),
    path(
        "dispatch/serial_number/", views.save_serial_number, name="save_serial_number"
    ),
    path("regions/get/", views.get_regions, name="get_regions"),
    path(
        "installations/completed/",
        views.completed_installations,
        name="completed_installations",
    ),
    path(
        "billing/start/<int:installation_id>/",
        views.start_billing,
        name="start_billing",
    ),
    path(
        "installations/report/<int:installation_id>/",
        views.installation_report_detail,
        name="installation_report_detail",
    ),
    path(
        "installations/report/<int:installation_id>/pdf/",
        views.installation_report_pdf,
        name="installation_report_pdf",
    ),
    path("feedbacks/", views.feedback_list, name="backoffice_feedback_list"),
    path(
        "feedbacks/<int:pk>/", views.feedback_detail, name="backoffice_feedback_detail"
    ),
    path("revenue/", views.revenue_summary, name="backoffice_revenue_summary"),
]
