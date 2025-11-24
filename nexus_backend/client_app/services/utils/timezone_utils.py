from datetime import timedelta
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

from django.utils import timezone


def get_expiry_time(lat, lng):
    tf = TimezoneFinder()
    tz_name = tf.timezone_at(lng=lng, lat=lat)
    if tz_name:
        tz = ZoneInfo(tz_name)
        return timezone.localtime(timezone.now(), tz) + timedelta(hours=1)
    return timezone.now() + timedelta(hours=1)
