from enum import Enum

from rest_framework.request import Request


class StrEnum(str, Enum):
    """Enum that can be used as a string."""

    def __str__(self) -> str:  # noqa: D401 (simple override)
        return str(self.value)


def add_base_url(request, url):
    if url and not url.startswith("http"):
        if not url.startswith("/"):
            url = "/" + url

        if isinstance(request, Request):
            request = request._request

        url = request.build_absolute_uri(url)
        # if we have trouble with base domains, migrate to using contrib.site
        # url2 = 'http://{0}{1}'.format(request._request.site, url)
    return url
