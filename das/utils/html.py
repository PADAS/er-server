import logging
import re

import html
import bleach


logger = logging.getLogger(__name__)


def clean_user_text(value, message):
    if value is not None:
        cleaned = bleach.clean(value)
        cleaned = html.unescape(cleaned)
        if value != cleaned:
            logger.info("User text was cleaned using bleach:  %s", message)
            return cleaned
    return value


def make_html_list(value):
    """Break a string down based on newline characters and for each line,
    enclose it in the <li> and </li> without the <ul> and </ul> tags.
    Similar to the unordered_list filter but not requiring a list"""
    paras = ''
    if value:
        value = re.sub(r'\r\n|\r|\n', '\n', value)  # normalize newlines
        paras = re.split('\n', value)
        paras = ['<li>%s</li>' % p.strip().replace('\n', '<br/>')
                 for p in paras]
        paras = '\n\n'.join(paras)
    return '<ul>{0}</ul>'.format(paras)
