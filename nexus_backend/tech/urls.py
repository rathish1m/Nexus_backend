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

from site_survey import views as survey_views
from tech import views

urlpatterns = [
    path("", views.tech_dashboard, name="tech_dashboard"),
    path("job/list/", views.installation_job_list, name="installation_job_list"),
    path("job/assign/", views.assign_to_technician, name="assign_to_technician"),
    path("fe/", views.fe_ops_dashboard, name="fe_ops_dashboard"),
    path("fe/joblist/", views.technician_job_list, name="technician_job_list"),
    path("get_technician/", views.get_technicians, name="get_technicians"),
    path("technicians/api/", views.technicians_api, name="technicians_api"),
    path("job/start/", views.job_start, name="job_start"),
    path("job/<int:job_id>/notes/", views.job_notes, name="job_notes"),
    path("job/<int:job_id>/complete/", views.job_complete, name="job_complete"),
    path(
        "job/<int:job_id>/upload-photos/",
        views.upload_installation_photos,
        name="upload_installation_photos",
    ),
    path(
        "api/installation-report/<int:activity_id>/save/",
        views.save_installation_report,
        name="save_installation_report",
    ),
    path(
        "api/installation-report/<int:activity_id>/data/",
        views.get_installation_report_data,
        name="get_installation_report_data",
    ),
    path(
        "api/installation-report/<int:activity_id>/edit/",
        views.edit_installation_report,
        name="edit_installation_report",
    ),
    path(
        "delete-installation-photo/<int:photo_id>/",
        views.delete_installation_photo,
        name="delete_installation_photo",
    ),
    path("surveys/summary/", views.surveys_summary, name="surveys_summary"),
    path("surveys/", survey_views.survey_dashboard, name="survey_dashboard"),
    path("activation/", views.activation_view, name="activation_view"),
    path(
        "activation/api/pending/",
        views.activation_pending_api,
        name="activation_pending_api",
    ),
    path(
        "activation/details/<str:activation_id>/",
        views.activation_detail,
        name="activation_detail",
    ),
    path("activation/api/kpis/", views.activation_kpis_api, name="activation_kpis_api"),
    path(
        "activation/<int:sub_id>/confirm/",
        views.confirm_activation,
        name="confirm_activation",
    ),
    path(
        "activation/<int:sub_id>/cancel/",
        views.cancel_activation,
        name="cancel_activation",
    ),
    path(
        "activation/request/<int:req_id>/confirm/",
        views.confirm_activation_request,
        name="confirm_activation_request",
    ),
    path(
        "activation/request/<int:req_id>/cancel/",
        views.cancel_activation_request,
        name="cancel_activation_request",
    ),
    path("activation/request/", views.request_activation, name="request_activation"),
    # Human-facing details page (server-rendered) without 'req-' prefix in URL
    path(
        "activation/<str:activation_id>/",
        views.activation_detail_page,
        name="activation_detail_page",
    ),
    # debug endpoint removed
]
