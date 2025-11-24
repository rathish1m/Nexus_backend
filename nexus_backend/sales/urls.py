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

from sales import views

urlpatterns = [
    path("", views.sales_dashboard, name="sales_dashboard"),
    path(
        "user_subscriptions_list/<int:user_id>/",
        views.user_subscriptions_list,
        name="user_subscriptions_list",
    ),
    path("register_customer/", views.register_customer, name="register_customer"),
    path("customer_list/", views.customer_list, name="customer_list"),
    path("get_kits_dropdown/", views.get_kits_dropdown, name="get_kits_dropdown"),
    path("submit_order_sales/", views.submit_order_sales, name="submit_order_sales"),
    path(
        "get_billing/<int:subscription_id>/",
        views.get_subscription_billing,
        name="get_subscription_billing",
    ),
    path(
        "customer_details/<int:customer_id>/",
        views.customer_details,
        name="sales_customer_details",
    ),
    path(
        "resubmit_personal_kyc/<int:customer_id>/",
        views.resubmit_personal_kyc,
        name="sales_resubmit_personal_kyc",
    ),
]
