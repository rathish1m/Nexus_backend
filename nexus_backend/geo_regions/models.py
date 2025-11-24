from django.contrib.gis.db import models


class Region(models.Model):
    name = models.CharField(max_length=255, unique=True)
    fence = models.PolygonField(srid=4326)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name
