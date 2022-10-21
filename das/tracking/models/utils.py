from copy import copy


def dictify(r, root=True):
    if root:
        return {r.tag: dictify(r, False)}
    d = copy(r.attrib)
    if r.text:
        d["_text"] = r.text
    for x in r.findall("./*"):
        if x.tag not in d:
            d[x.tag] = []
        d[x.tag].append(dictify(x, False))
    return d


def parse_cookie(cookie):
    items = [_.split('=') for _ in cookie.split(';')]
    cookies = dict(items)
    return cookies


def split_link(url):
    url, qs = url.split('?')
    params = dict([p.split('=') for p in qs.split('&')])
    return (url, params)


def to_float(record):
    """ Convert str/int records to float """
    try:
        return float(record)
    except Exception:
        return float()
