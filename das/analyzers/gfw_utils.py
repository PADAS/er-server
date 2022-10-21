import logging
import urllib.parse as urlparse
from datetime import date, timedelta

from django.conf import settings

from accounts.models import User
from analyzers.gfw_alert_schema import GFWLayerSlugs
from analyzers.models import GlobalForestWatchSubscription as gfw_model

logger = logging.getLogger(__name__)

CARTO_URL = settings.CARTO_URL
DEFAULT_LOOKBACK_DAYS = 10

SQL_FORMAT = """SELECT pt.*
    FROM vnp14imgtdl_nrt_global_7d pt
    where acq_date >= \'{alert_date_begin}\'
        AND acq_date <= \'{alert_date_end}\'
        AND ST_INTERSECTS(ST_SetSRID(ST_GeomFromGeoJSON(\'{geoJSON}\'), 4326), the_geom)
        AND {confidence_level}
"""

GEOSTORE_FIELD = 'geostore'
GLAD_CONFIRM_FIELD = 'gladConfirmOnly'


def parse_url(url):
    parsed_dict = urlparse.parse_qs(urlparse.urlparse(url).query)
    return parsed_dict


def sub_id_from_unsubscribe_url(unsubscribe_url):
    subscription_url = unsubscribe_url.split('/')
    subscription_id = subscription_url[4]
    return subscription_id


def create_viirs_downloadable_url(alert_date_begin, alert_date_end, geojson, confidence_level):
    sql_str = SQL_FORMAT.format(alert_date_begin=alert_date_begin,
                                alert_date_end=alert_date_end,
                                geoJSON=geojson,
                                confidence_level=confidence_level)

    return {"URL": CARTO_URL, "param": {"q": sql_str, "format": "json"}}


def confidence_level_fmt(confidence_level):
    if gfw_model.HIGH == confidence_level:
        fmt = "(confidence=\'{}\')".format('high')
    elif gfw_model.HIGH_NOMINAL == confidence_level:
        fmt = "(confidence=\'{}\' OR confidence=\'{}\')".format('high', 'nominal')
    else:
        fmt = "(confidence=\'{}\' OR confidence=\'{}\' OR confidence=\'{}\')".format('high', 'nominal', 'low')
    return fmt


def prepare_downloadable_url(validated_data, subscription_id):
    data = validated_data.get
    alert_date_begin, alert_date_end = data('alert_date_begin'), data('alert_date_end')

    gfw_query = gfw_model.objects.get(subscription_id=subscription_id)

    geoJSON = gfw_query.subscription_geometry.geojson
    fire_confidence_level = gfw_query.Fire_confidence
    confidence_level = confidence_level_fmt(fire_confidence_level)

    viirs_downloadable_url = create_viirs_downloadable_url(alert_date_begin=alert_date_begin,
                                                           alert_date_end=alert_date_end,
                                                           geojson=geoJSON,
                                                           confidence_level=confidence_level)
    return dict(json=viirs_downloadable_url)


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


def get_correct_download_url(event_info, gfw_object, polling):
    pass


def get_gfw_endpoint() -> str:
    parsed_gfw_api_root = urlparse.urlparse(settings.GFW_API_ROOT)
    return f'{parsed_gfw_api_root.scheme}://{parsed_gfw_api_root.netloc}'


def make_download_url(geostore_id: str, start_date_str: str, end_date_str: str,
                      confirmed_only: bool = False, gfw_endpoint: str = None) -> str:
    if not gfw_endpoint:
        gfw_endpoint = get_gfw_endpoint()

    download_url_prefix = f'{gfw_endpoint}/glad-alerts/download/?aggregate_values=False' \
                          f'&aggregate_by=False&format=json'

    return f'{download_url_prefix}&period={start_date_str},{end_date_str}' \
           f'&geostore={geostore_id}&gladConfirmOnly={confirmed_only}'


def should_backfill_confirmed_alerts(today: date) -> bool:
    # a condition to check to determine if backfill should be run.
    return True if not today.day % settings.GFW_BACKFILL_INTERVAL_DAYS else False


def get_dict(start_date: date, end_date: date, gfw_object: gfw_model,
             confirmed_only: bool = False) -> dict:
    gfw_endpoint = get_gfw_endpoint()
    geostore_id = gfw_object.geostore_id
    start_date_str, end_date_str = start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

    return dict(
        alert_name=gfw_object.name,
        alert_link=f'{settings.GFW_WEB_ROOT}/map/geostore/{geostore_id}/grayscale/?fit_to_geom=true&begin={start_date_str}&end={end_date_str}',
        alert_date_begin=start_date_str,
        alert_date_end=end_date_str,
        downloadUrls={
            'json': make_download_url(geostore_id, start_date_str, end_date_str, confirmed_only, gfw_endpoint)
        }
    )


def generate_intervals(start_date: date, end_date: date, interval_size: int = 30) -> tuple:
    if start_date == end_date:
        yield start_date, end_date

    interval_start = start_date
    while interval_start < end_date:
        incr = min(interval_size, (end_date-interval_start).days)
        interval_end = interval_start+timedelta(days=incr)
        yield interval_start, interval_end
        interval_start = interval_end


def make_alert_infos(layer_slug: str, gfw_object: gfw_model) -> dict:
    end_date = date.today()
    start_date = end_date - timedelta(days=DEFAULT_LOOKBACK_DAYS)  # query for past 10 days by default
    confirmed_only = True if gfw_object.Deforestation_confidence == gfw_model.CONFIRMED else False
    # hostname in viirs alert doesn't matter here as its always rebuilt using settings.CARTO_URL in gfw_inbound
    yield get_dict(start_date, end_date, gfw_object, confirmed_only)

    if (layer_slug == GFWLayerSlugs.GLAD_ALERTS.value
            and should_backfill_confirmed_alerts(end_date)):
        start_date = end_date - timedelta(days=gfw_object.glad_confirmed_backfill_days)
        logger.info(f'scheduling GLAD backfill for subscription: {gfw_object.name} id: {gfw_object.id} '
                    f'period: {start_date} to {end_date}')
        for int_start, int_end in generate_intervals(start_date, end_date):
            yield get_dict(int_start, int_end, gfw_object, True)


def get_gfw_user():
    '''
    Get the system-generated user to associate with the Global Forest Watch events.
    :return:
    '''
    user, create = User.objects.get_or_create(username='gfwwebhookuser',
                                              defaults={'first_name': 'GFW',
                                                        'last_name': 'Webhook',
                                                        'password': User.objects.make_random_password()
                                                        })
    return user
