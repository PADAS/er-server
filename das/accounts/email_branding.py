"""Shared helper for attaching the EarthRanger brand logo to outgoing emails.

The logo is embedded as a CID (Content-ID) inline attachment so HTML
templates can reference it as ``cid:earthranger-logo`` without loading
an external URL — improving deliverability and rendering across Gmail,
Outlook, and other email clients that strip inline SVG or block remote
images.
"""

from __future__ import annotations

import logging
from email.mime.image import MIMEImage

from django.contrib.staticfiles import finders
from django.core.mail import EmailMultiAlternatives

logger = logging.getLogger(__name__)

_LOGO_STATIC_PATH = "img/EarthRanger-Logo_icon.png"
_LOGO_CID = "earthranger-logo"
_LOGO_FILENAME = "EarthRanger-Logo_icon.png"


def attach_brand_logo(message: EmailMultiAlternatives) -> None:
    """Attach the EarthRanger logo PNG as a CID inline image to *message*.

    After this call the HTML alternative in *message* can reference the logo
    via ``src="cid:earthranger-logo"``.  Sets ``message.mixed_subtype`` to
    ``"related"`` so that the HTML alternative and its related inline images
    are bundled together correctly (multipart/related wrapping
    multipart/alternative).

    Raises ``FileNotFoundError`` if the static file cannot be located, which
    typically means ``STATICFILES_DIRS`` or ``INSTALLED_APPS`` are
    misconfigured.  The error propagates deliberately — a branded email that
    silently omits the logo is worse than a visible failure during development.
    """
    path = finders.find(_LOGO_STATIC_PATH)
    if path is None:
        raise FileNotFoundError(
            f"Could not locate static file '{_LOGO_STATIC_PATH}' via "
            "django.contrib.staticfiles.finders.  Check STATICFILES_DIRS "
            "and INSTALLED_APPS."
        )

    with open(path, "rb") as fh:
        data = fh.read()

    img = MIMEImage(data)
    img.add_header("Content-ID", f"<{_LOGO_CID}>")
    img.add_header("Content-Disposition", "inline", filename=_LOGO_FILENAME)
    message.attach(img)
    # multipart/related lets the HTML alternative resolve cid: references.
    message.mixed_subtype = "related"
    logger.debug("Attached brand logo '%s' as CID '%s'", _LOGO_FILENAME, _LOGO_CID)
