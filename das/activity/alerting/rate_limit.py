import logging

from django.conf import settings

from accounts.models import User
from core import alerts_storage
from utils.features import features
from utils.tenant import get_tenant_settings

KEY_ALERT_LIMIT = "alert_limit_count_{}"

logger = logging.getLogger(__name__)


def allow_send_event_alert(user: User) -> bool:
    counter = get_or_set_user_alerts_counter(user)

    get_user_alert_quota_percentage(user, counter)

    return counter < settings.ALERTS_RATE_LIMIT


def prepend_alert_warning_message(user: User) -> bool:
    return get_remaining_alert_count(user) <= settings.ALERTS_REMAINING_COUNTER_FOR_WARNING


def increment_alert_counter(user: User, notification_method: str):
    alerts_storage.increment_key_by_value(KEY_ALERT_LIMIT.format(user.id), 1)
    logger.info("Site %s message sent %s alert", _get_site(), notification_method)


def get_or_set_user_alerts_counter(user: User) -> int:
    return get_alert_counter(user) or reset_alerts_counter(user)


def get_alert_counter(user: User) -> int:
    counter = alerts_storage.get_key(KEY_ALERT_LIMIT.format(user.id))

    try:
        return int(counter)
    except TypeError:
        return 0


def reset_alerts_counter(user: User) -> int:
    key = KEY_ALERT_LIMIT.format(str(user.id))

    alerts_storage.insert_key(key=key, value=0, ttl=settings.ALERTS_RATE_LIMIT_DURATION_SECONDS)
    logger.info("Set alert counter for user: %s", user.username)
    return 0


def get_remaining_alert_count(user: User) -> int:
    return settings.ALERTS_RATE_LIMIT - get_or_set_user_alerts_counter(user) - 1


def get_user_alert_quota_percentage(user: User, counter) -> None:
    percentage = (counter / settings.ALERTS_RATE_LIMIT) * 100

    if percentage >= 90:
        logger.info("Site %s user: %s hit %s%% alert limit.", _get_site(), user.username, percentage)


def _get_site() -> str:
    if features.tms.is_on():
        return get_tenant_settings().url
    return settings.SERVER_FQDN
