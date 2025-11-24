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

from django.conf.urls.i18n import i18n_patterns
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from nexus_backend import settings

#
# def trigger_error(request):
#     division_by_zero = 1 / 0

# URLs qui ne nécessitent pas de préfixe de langue
urlpatterns = [
    #
    # path('sentry-debug/', trigger_error),
    path("admin/rosetta/", include("rosetta.urls")),
    path("admin/", admin.site.urls),
    path("i18n/", include("django.conf.urls.i18n")),
    path("api/", include("api.urls")),  # APIs généralement sans préfixe de langue
    # path("user/", include("user.urls")),  # Moved to i18n_patterns for language support
]

# URLs avec préfixe de langue (fr/ ou en/)
urlpatterns += i18n_patterns(
    path("", include("main.urls")),
    path("backoffice/", include("backoffice.urls")),
    path("tech/", include("tech.urls")),
    path("site-survey/", include("site_survey.urls")),  # New site survey app
    path("user/", include("user.urls")),  # Added: user management with language prefix
    path("subscr/", include("subscriptions.urls")),
    path("sales/", include("sales.urls")),
    path("orders/", include("orders.urls")),
    path("stock/", include("stock.urls")),
    path("client/", include("client_app.urls")),
    path("customers/", include("customers.urls")),
    path("dashboard_bi/", include("dashboard_bi.urls")),
    path("kyc/", include("kyc_management.urls")),
    path("settings/", include("app_settings.urls")),
    path("billing_management/", include("billing_management.urls")),
    path("billing/", include("billing_management.urls")),
    path("geo_regions/", include("geo_regions.urls")),
    path("ticketing/", include("ticketing.urls")),
    prefix_default_language=True,  # Force l'utilisation des préfixes pour toutes les langues
)  # Serve media files during development
if settings.DEVELOPMENT_MODE == True:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
