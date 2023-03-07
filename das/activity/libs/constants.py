from django.conf import settings


class EventTestsConstants:
    url = "https://test.com"
    icon_url = "https:// test.com/super-icon.png"


class ActivityConstants:
    USERCONTENT_FORCE_DOWNLOAD = getattr(settings, "USERCONTENT_SETTINGS", {}).get("force_download_mimetypes", set())
