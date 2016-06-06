import logging

import bleach


logger = logging.getLogger(__name__)


def clean_user_text(value, message):
    cleaned = bleach.clean(value)
    if value != cleaned:
        logger.info("User text was cleaned using bleach:  %s", message)
        return cleaned
    return value
