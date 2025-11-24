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

from main import flexpaie, views

urlpatterns = [
    path(
        "payments/cancel-expired/",
        flexpaie.trigger_cancel_expired_orders,
        name="trigger_cancel_expired_orders",
    ),
    # Accept both with and without trailing slash for POST callers
    path("payments/cancel-order/", flexpaie.cancel_order_now, name="cancel_order_now"),
    path("", views.home_page, name="home_page"),
    path("payments/flexpay/initiate/", views.mobile_payment, name="mobile_payment"),
    path(
        "payments/flexpay/card/initiate/",
        views.initiate_card_payment,
        name="initiate_card_payment",
    ),
    path("probe/", flexpaie.probe_payment_status, name="probe_payment_status"),
    path("probe/mobile/", flexpaie.mobile_probe, name="mobile_probe"),
]
