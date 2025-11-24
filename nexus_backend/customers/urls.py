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

from customers import views

app_name = "customers"

urlpatterns = [
    path("", views.customers_list, name="customers_list"),
    path("get_customers", views.get_customers, name="get_customers"),
    path(
        "details/",
        views.get_customer_details,
        name="get_customer_details",
    ),
    path("edit/", views.edit_customer, name="edit_customer"),
    path("toggle_status/", views.toggle_customer_status, name="toggle_customer_status"),
    path(
        "reset_password/", views.reset_customer_password, name="reset_customer_password"
    ),
    path("delete/", views.delete_customer, name="delete_customer"),
    path("purge/", views.purge_customer_data, name="purge_customer_data"),
]
