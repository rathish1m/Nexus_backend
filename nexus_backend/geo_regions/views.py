from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.contrib.auth.decorators import login_required
from django.contrib.gis.geos import Point
from django.shortcuts import render

from .models import Region
from .serializers import RegionSerializer


@login_required
def region_dashboard(request):
    return render(request, "geo_regions/region_dashboard.html")


class RegionViewSet(viewsets.ModelViewSet):
    queryset = Region.objects.all().order_by("name")  # Tri alphabétique
    serializer_class = RegionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.query_params.get("q")
        if query:
            queryset = queryset.filter(name__icontains=query)
        return queryset.order_by("name")  # Assurer le tri même après filtrage

    @action(detail=False, methods=["get"], url_path="check-point")
    def check_point(self, request):
        lat_str = request.query_params.get("lat")
        lon_str = request.query_params.get("lon")

        if not lat_str or not lon_str:
            return Response(
                {"error": 'Please provide both "lat" and "lon" query parameters.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            lat = float(lat_str)
            lon = float(lon_str)
            # Note: GeoDjango uses (x, y) -> (longitude, latitude)
            point = Point(lon, lat, srid=4326)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid latitude or longitude."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        containing_regions = Region.objects.filter(fence__contains=point)
        serializer = self.get_serializer(containing_regions, many=True)

        # Enrichir la réponse avec des informations de débogage
        debug_info = {
            "received_lat": lat,
            "received_lon": lon,
            "point_wkt": point.wkt,  # Well-Known Text representation
        }

        response_data = {"regions": serializer.data, "debug": debug_info}

        return Response(response_data)
