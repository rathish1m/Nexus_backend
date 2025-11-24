from rest_framework_gis.serializers import GeoFeatureModelSerializer

from .models import Region


class RegionSerializer(GeoFeatureModelSerializer):
    class Meta:
        model = Region
        geo_field = "fence"
        fields = ("id", "name", "created_at", "updated_at")
