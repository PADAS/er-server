import html
import logging

import bleach

from django.utils.html import format_html

logger = logging.getLogger(__name__)


def clean_user_text(value, message):
    if value is not None:
        # strip=True removes disallowed tags entirely. Without it, bleach would
        # escape them (e.g. `<script>` -> `&lt;script&gt;`), and the subsequent
        # html.unescape would put them right back, leaving stored XSS intact.
        cleaned = bleach.clean(value, strip=True)
        cleaned = html.unescape(cleaned)
        if value != cleaned:
            logger.info("User text was cleaned using bleach:  %s", message)
            return cleaned
    return value


def clean_user_data(value, message):
    """Recursively run clean_user_text on every string inside dicts/lists.

    Non-string scalars (numbers, bools, None) are returned unchanged. Dict keys
    are not sanitized — only values.
    """
    if isinstance(value, str):
        return clean_user_text(value, message)
    if isinstance(value, dict):
        return {k: clean_user_data(v, f"{message}.{k}") for k, v in value.items()}
    if isinstance(value, list):
        return [clean_user_data(item, f"{message}[{i}]") for i, item in enumerate(value)]
    return value


def make_html_list(values):
    template = "<ul>" + ("<li>{}</li>" * len(values)) + "</ul>"
    return format_html(template.format(*values))
