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

from user import views
from user.views_password_reset import password_reset_confirm

urlpatterns = [
    path("login_page/", views.login_page, name="login_page"),
    path("login/", views.login_request, name="login_request"),
    path("logout/", views.logout_request, name="logout_request"),
    path("register/", views.register, name="register"),
    path("verify/", views.verify_otp, name="verify_otp"),
    path("verify_2fa/", views.verify_2fa, name="verify_2fa"),
    path("otp/resend/", views.resend_otp, name="resend_otp"),
    path("users_management/", views.users_management, name="users_management"),
    path("get_roles_region/", views.get_roles_region, name="get_roles_region"),
    path("staff_creation/", views.staff_creation, name="staff_creation"),
    path("get_users_data/", views.get_users_data, name="get_users_data"),
    path("reset_password/", views.reset_user_password, name="reset_user_password"),
    path(
        "password_reset_request/",
        views.password_reset_request,
        name="password_reset_request",
    ),
    path(
        "password_reset_confirm/<uidb64>/<token>/",
        password_reset_confirm,
        name="password_reset_confirm",
    ),
    path("edit_user/", views.edit_user, name="edit_user"),
    path("get_user_details/", views.get_user_details, name="get_user_details"),
]
