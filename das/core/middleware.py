import redis

from django.conf import settings
from django.http import HttpResponseServerError

# specifically we don't want tenant namespacing on our cache key, use redis directly
redis_client = redis.from_url(settings.REALTIME_BROKER_URL, decode_responses=True)
MAINTENANCEMESSAGE_KEY = "maintenancemodemessage"
MAINTENANCE_KEY = "maintenancemode"
MAINTENANCE_TTL = 3600 * 12
MAINTENANCE_MODE_ENABLED = "True"


class MaintenanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if is_under_maintenance():
            message = "EarthRanger server is offline."
            if additional_message := get_maintenance_message():
                message += f" {additional_message}"
            return HttpResponseServerError(message, status=503)

        # If not under maintenance, continue with the request
        response = self.get_response(request)
        return response


def is_under_maintenance():
    return redis_client.get(MAINTENANCE_KEY) == MAINTENANCE_MODE_ENABLED


def set_maintenance_mode():
    redis_client.set(MAINTENANCE_KEY, MAINTENANCE_MODE_ENABLED, ex=MAINTENANCE_TTL)


def unset_maintenance_mode():
    redis_client.delete(MAINTENANCE_KEY)


def set_maintenance_message(message):
    redis_client.set(MAINTENANCEMESSAGE_KEY, message, ex=MAINTENANCE_TTL)


def get_maintenance_message():
    return redis_client.get(MAINTENANCEMESSAGE_KEY)
