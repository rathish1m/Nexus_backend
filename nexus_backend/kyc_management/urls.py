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

from kyc_management import views

urlpatterns = [
    path("", views.kyc_management, name="kyc_management"),
    path("get_kyc/", views.get_kyc, name="get_kyc"),
    path("view_kyc/<str:kyc_type>/<int:kyc_id>/", views.view_kyc, name="view_kyc"),
    path("view_kyc/<str:kyc_type>/<int:kyc_id>/", views.view_kyc, name="view_kyc"),
    path(
        "document/view/<str:doc_kind>/<int:pk>/",
        views.kyc_document_view,
        name="kyc_document_view",
    ),
    path(
        "update-status/user/<int:user_id>/",
        views.update_kyc_status,
        name="update_kyc_status",
    ),
    path("user-info/<int:user_id>/", views.kyc_user_info, name="kyc_user_info"),
    path(
        "ajax/get_pending_kyc_count/",
        views.get_pending_kyc_count,
        name="get_pending_kyc_count",
    ),
    path("ajax/kyc_metrics/", views.kyc_metrics_api, name="kyc_metrics_api"),
]
