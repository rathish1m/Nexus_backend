from rest_framework.routers import DefaultRouter

from django.urls import include, path

from .views import RegionViewSet, region_dashboard

router = DefaultRouter()
router.register(r"", RegionViewSet, basename="region")

urlpatterns = [
    path("map/", region_dashboard, name="region_dashboard"),
    path("", include(router.urls)),
]
