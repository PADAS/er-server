import logging
import re

import html
import bleach

from django.utils.html import format_html

logger = logging.getLogger(__name__)


def clean_user_text(value, message):
    if value is not None:
        cleaned = bleach.clean(value)
        cleaned = html.unescape(cleaned)
        if value != cleaned:
            logger.info("User text was cleaned using bleach:  %s", message)
            return cleaned
    return value


def make_html_list(values):
    template = '<ul>' + ('<li>{}</li>' * len(values)) + '</ul>'
    return format_html(template.format(*values))
