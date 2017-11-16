import rest_framework.request


def add_base_url(request, url):
    if url and not url.startswith('http'):
        if not url.startswith('/'):
            url = '/' + url

        if isinstance(request, rest_framework.request.Request):
            request = request._request

        url = request.build_absolute_uri(url)
        # if we have trouble with base domains, migrate to using contrib.site
        #url2 = 'http://{0}{1}'.format(request._request.site, url)
    return url
