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

from stock import views

urlpatterns = [
    path("", views.stock_management, name="stock_management"),
    path(
        "download-stock-sample/",
        views.download_stock_sample,
        name="download_stock_sample",
    ),
    path("upload_stock_excel/", views.upload_stock_excel, name="upload_stock_excel"),
    # Regions
    path("regions/", views.get_regions, name="get_regions"),
    path(
        "regions/configured/", views.get_configured_region, name="get_configured_region"
    ),
    # Locations
    path("stock/locations/", views.get_stock_locations, name="get_stock_locations"),
    path(
        "stock/locations/create/",
        views.create_stock_location,
        name="create_stock_location",
    ),
    # Kits (StarlinkKit)
    path("kits/", views.get_kits, name="get_kits"),
    # Inventory + operations
    path("stock/with-quantity/", views.stock_with_quantity, name="stock_with_quantity"),
    path("stock/add/", views.stock_add, name="stock_add"),
    path(
        "stock/move-between-regions/",
        views.move_stock_between_regions,
        name="move_stock_between_regions",
    ),
    path("regions/create/", views.create_region, name="create_region"),
    path("kits/", views.get_kits, name="get_kits_for_inventory"),
]
