import logging

from django.conf import settings

from accounts.models import User
from core import alerts_storage
from utils import stats
from utils.tenant import get_tenant_settings

KEY_ALERT_LIMIT = "alert_limit_count_{}"
KEY_ALERT_90_PERCENT = "alert_limit_90_percent"
KEY_ALERT_100_PERCENT = "alert_limit_100_percent"

logger = logging.getLogger(__name__)


def allow_send_event_alert(user: User) -> bool:
    counter = get_or_set_user_alerts_counter(user)
    publish_user_alert_quota_percentage(user, counter)

    return counter < get_tenant_settings().env_settings.alert_rate_limit


def prepend_alert_warning_message(user: User) -> bool:
    return get_remaining_alert_count(user) <= settings.ALERTS_REMAINING_COUNTER_FOR_WARNING


def increment_alert_counter(user: User, notification_method: str):
    alerts_storage.increment_key_by_value(KEY_ALERT_LIMIT.format(user.id), 1)
    logger.info("Site %s message sent %s alert", get_tenant_settings().domain, notification_method)
    stats.increment("alert", tags=[f"method:{notification_method}"])


def get_or_set_user_alerts_counter(user: User) -> int:
    return get_alert_counter(user) or reset_alerts_counter(user)


def get_alert_counter(user: User) -> int:
    counter = alerts_storage.get_key(KEY_ALERT_LIMIT.format(user.id))

    try:
        return int(counter)
    except TypeError:
        return 0


def reset_alert_metrics():
    alerts_storage.delete(KEY_ALERT_100_PERCENT)
    alerts_storage.delete(KEY_ALERT_90_PERCENT)
    update_stats()


def reset_alerts_counter(user: User) -> int:
    key = KEY_ALERT_LIMIT.format(str(user.id))

    alerts_storage.insert_key(key=key, value=0, ttl=settings.ALERTS_RATE_LIMIT_DURATION_SECONDS)
    logger.info("Set alert counter for user: %s", user.username)
    return 0


def get_remaining_alert_count(user: User) -> int:
    return get_tenant_settings().env_settings.alert_rate_limit - get_or_set_user_alerts_counter(user) - 1


def update_stats():
    stats.update_gauge("alert_rate_limit", alerts_storage.get_set_size(KEY_ALERT_90_PERCENT), tags=[f"limit:90pct"])
    stats.update_gauge("alert_rate_limit", alerts_storage.get_set_size(KEY_ALERT_100_PERCENT), tags=[f"limit:100pct"])


def publish_user_alert_quota_percentage(user: User, counter: int) -> None:
    domain = get_tenant_settings().domain
    env_settings = get_tenant_settings().env_settings
    percentage = (counter / env_settings.alert_rate_limit) * 100

    if percentage >= 100:
        alerts_storage.insert_set(KEY_ALERT_100_PERCENT, str(user.id))
        alerts_storage.delete_set(KEY_ALERT_90_PERCENT, str(user.id))
    elif percentage >= 90:
        logger.info("Site %s user: %s hit %s%% alert limit.", domain, user.username, percentage)
        alerts_storage.insert_set(KEY_ALERT_90_PERCENT, str(user.id))
    update_stats()
