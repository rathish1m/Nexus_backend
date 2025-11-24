from __future__ import annotations

from typing import Optional, Tuple

from django.contrib.gis.db.models.functions import Area
from django.contrib.gis.geos import Point
from django.db import connection

from geo_regions.models import Region

RegionResolution = Tuple[Optional[Region], str]


def resolve_region_from_coords(
    lat: Optional[float], lng: Optional[float]
) -> RegionResolution:
    """
    Attempt to resolve a Region containing the given latitude/longitude.

    Returns a tuple (region|None, tag) where tag identifies the provenance:
      - \"auto\" when there is a single polygon containing the point
      - \"auto_ambiguous\" when multiple polygons match and we pick the smallest
      - \"no_coords\" when lat/lng are missing or invalid
      - \"no_match\" when no polygon contains the point
    """

    if lat is None or lng is None:
        return None, "no_coords"

    try:
        lat_f = float(lat)
        lng_f = float(lng)
    except (TypeError, ValueError):
        return None, "no_coords"

    # On non-spatial backends (e.g. SQLite in local tests), the GIS adapter
    # used by GeoDjango is not available. In that case, gracefully skip
    # polygon lookups and fall back to "no_match" instead of raising.
    if not hasattr(connection.ops, "Adapter"):
        return None, "no_match"

    point = Point(lng_f, lat_f, srid=4326)
    matches = Region.objects.filter(fence__contains=point)

    if not matches.exists():
        return None, "no_match"

    if matches.count() == 1:
        return matches.first(), "auto"

    # Multiple overlapping polygons: pick the one with the smallest area.
    region = matches.annotate(area=Area("fence")).order_by("area").first()
    return region, "auto_ambiguous"


__all__ = ["resolve_region_from_coords"]
