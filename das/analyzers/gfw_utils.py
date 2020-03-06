import json
import logging
import urllib.parse as urlparse

import requests
from django.conf import settings
from rest_framework import status

from analyzers.models import GlobalForestWatchSubscription as gfw_model

logger = logging.getLogger(__name__)

GEOSTORE_FIELD = 'geostore'
GLAD_CONFIRM_FIELD = 'gladConfirmOnly'


def parse_url(url):
    parsed_dict = urlparse.parse_qs(urlparse.urlparse(url).query)
    return parsed_dict


def callback_api_for_fire_alerts(validated_data):
    url_dict = {}
    api_root = settings.GFW_API_ROOT
    url_fmt = '{}/viirs-active-fires?geostore={}&period={},{}'

    data = validated_data.get
    alert_date_begin, alert_date_end = data('alert_date_begin'), data('alert_date_end')
    alert_link_url = data('alert_link')
    geostore_id = parse_url(alert_link_url)['geostore'][0]

    endpoint = url_fmt.format(api_root, geostore_id, alert_date_begin, alert_date_end)

    # Make api-call to fetch viir fire alerts
    response = get_viirs_fire_alerts(endpoint)
    if response:
        link_to_download_in_csv = response['data']['attributes']['downloadUrls']['csv']
        update_url = change_format_to_json(link_to_download_in_csv)
        url_dict['json'] = update_url
        return url_dict
    logger.debug("Error occured occured while fetching fire alerts.")


def get_viirs_fire_alerts(endpoint):
    try:
        response = requests.get(url=endpoint)
    except Exception as exc:
        logger.exception("Exception %s raise when calling %s" % (exc, endpoint))
    else:
        if response and response.status_code == status.HTTP_200_OK:
            logger.debug("Fetch fire alerts successfully %s", response.text)
            return json.loads(response.text)
        else:
            logger.error("Fetch fire alerts failed %s", response)


def change_format_to_json(link_to_download):
    # Changes the format param in link_to_download from csv to json.
    url_parts = list(urlparse.urlparse(link_to_download))
    query_dict = parse_url(link_to_download)
    query_dict['format'][0] = 'json'
    url_parts[4] = urlparse.urlencode(query_dict, doseq=True)
    return urlparse.urlunparse(url_parts)


def get_geostore_id(download_url):
    qs = urlparse.parse_qs(urlparse.urlparse(download_url).query)
    return qs.get(GEOSTORE_FIELD, [''])[0]


def rebuild_glad_download_url(download_url, gfw_object):
    confirmed_only = True if gfw_object.Deforestation_confidence == gfw_model.CONFIRMED else False
    query_params = urlparse.parse_qs(urlparse.urlparse(download_url).query)
    # update the geostore & gladConfirmOnly in the query string
    query_params[GEOSTORE_FIELD][0] = gfw_object.geostore_id
    query_params[GLAD_CONFIRM_FIELD][0] = str(confirmed_only)
    parsed_result = urlparse.urlparse(download_url)
    # create and return a new url
    new_parsed_result = urlparse.ParseResult(scheme=parsed_result.scheme, netloc=parsed_result.netloc,
                                             path=parsed_result.path, params=parsed_result.params,
                                             fragment=parsed_result.fragment,
                                             query=urlparse.urlencode(query_params, doseq=True))
    return urlparse.urlunparse(new_parsed_result)
