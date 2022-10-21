import datetime
from typing import NamedTuple
import tempfile

import dateutil.parser
import pytz
from django.core.management.base import BaseCommand
from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings

import utils.json as json
from core.utils import get_site_name
import utils.schema_utils as schema_utils
from activity.models import Event
from activity.views import generate_event_type_cache
from observations.models import Source, SourceProvider, UserSession
from tracking.models.plugin_base import SourcePlugin
from accounts.models.eula import UserAgreement


class SiteMetrics(NamedTuple):
    type: str  # The type of metric, monthly_aggregate
    version: str  # version of the format
    reports: list  # array of summary reports, carcass, fence, etc
    site: str  # ER site name
    created_at: datetime.datetime  # when the report was generated
    start_interval: datetime.datetime  # start date for the range of data
    end_interval: datetime.datetime  # end date for the range of data
    sensors: list  # sensor summary
    eula: list # eula compliance user list
    user_sessions: list  # er web sessions


REPORT_TYPE = "daily_aggregate"
REPORT_VERSION = "v1"


class Command(BaseCommand):
    help = 'Generate the site metrics, default is by day'

    def add_arguments(self, parser):
        parser.add_argument('--start', type=str,
                            help='start date')
        parser.add_argument('--site', type=str,
                            help='site name')
        parser.add_argument('--console', action='store_true', help='output to console')

    def handle(self, *args, **options):
        # calculate this in GMT, not the sites timezone
        now = datetime.datetime.now(pytz.UTC)
        start = datetime.datetime.now(pytz.UTC) - datetime.timedelta(days=1)
        site_name = get_site_name()
        if options["site"]:
            site_name = options["site"]
        if options['start']:
            start = dateutil.parser.parse(options['start'])
            if not start.tzinfo:
                start = start.replace(tzinfo=pytz.UTC)

        start, end, step = get_daily_interval(start)

        extracter = ExtractSiteMetrics(start, end)
        reports = extracter.run()
        devices = sumarize_sources(start, end)
        eula = get_eula_compliance_list()
        user_session = get_user_session_time(start, end)
        wrapper = SiteMetrics(REPORT_TYPE, REPORT_VERSION,
                              reports, site_name, now, start, end, devices, eula, user_session)
        result = json.dumps(wrapper)
        if options['console']:
            print(result)
        else:
            save_to_bucket(result, start, site_name)


def save_to_bucket(file_contents, start_date, site):
    bucket = S3Boto3Storage(
        bucket_name=settings.METRICS_BUCKET, default_acl='bucket-owner-full-control')
    filename = f"{site}_{start_date.year}-{start_date.month}-{start_date.day}.json"
    path = f"{REPORT_VERSION}/{start_date.year}/{start_date.month}/{filename}"
    with tempfile.TemporaryFile('w+b') as fh:
        fh.write(file_contents.encode('utf-8'))
        fh.seek(0)
        bucket.save(path, fh)


class EventField(NamedTuple):
    field_name: str
    field_name_display: str
    export_as_name: str
    export_as_name_display: str


class ExtractSiteMetrics:
    def __init__(self, start, end):
        self.start = start
        self.end = end
        self.event_type_map = generate_event_type_cache()
        self.renderer = schema_utils.get_schema_renderer_method()

    def run(self):
        events = []
        qs = Event.objects.all().prefetch_related('event_type')
        qs = qs.filter(updated_at__range=(self.start, self.end))
        qs = qs.values('id', 'priority', 'state',
                       'event_type_id', 'event_details__data',
                       'provenance',
                       'event_time', 'updated_at', 'created_at')
        for row in qs:
            events.append(self.get_event_properties(row))
        return events

    def get_event_properties(self, event):
        event_type = self.event_type_map[event['event_type_id']]

        rep = dict(id=event["id"],
                   event_type=event_type['value'],
                   event_type_display=event_type['display'],
                   event_time=event["event_time"],
                   updated_at=event["updated_at"],
                   created_at=event["created_at"],
                   provenance=event["provenance"],
                   state=event['state'],
                   state_display='Resolved' if event["state"] == Event.SC_RESOLVED else 'Active',
                   priority=event["priority"],
                   priority_display=Event.PRIORITY_LABELS_MAP.get(
                       event['priority'], '')
                   )

        rep['event_details'] = self.get_event_detail_properties(
            event, event_type)
        return rep

    def get_event_detail_properties(self, event, event_type):
        if not event['event_details__data']:
            return
        rep = {}
        current_schema = self.renderer(event_type['schema'])
        current_schema_order = \
            schema_utils.definition_key_order_as_dict(
                current_schema)

        details = schema_utils.get_display_values_for_event_details(
            event['event_details__data'].get('event_details', {}),
            current_schema)

        # only publish strings if they come from an enum
        for field, order in current_schema_order.items():
            if self.is_field_type(current_schema, field, "string") and not self.is_enum_field(current_schema, field):
                continue
            rep[field] = details.get(field, '')

            display = schema_utils.get_display_value_header_for_key(
                current_schema, field)
            rep[f"{field}_title"] = display
            field_display = details.get(display, '')
            if field_display:
                rep[f"{field}_display"] = field_display
        return rep

    def is_enum_field(self, schema, key):
        properties = schema['schema']['properties']
        if key in properties and 'enum' in properties[key]:
            return True

    def is_field_type(self, schema, key, field_type):
        properties = schema['schema']['properties']
        try:
            return properties[key]["type"] == field_type
        except KeyError:
            pass


def get_weekly_interval(start_date):
    """
    Want the interval to start on a Monday at 00:00.
    :param start_date:
    :param end_date:
    :return:
    """
    step = datetime.timedelta(days=7)
    dow = start_date.isoweekday()
    if dow > 1:
        start_date += datetime.timedelta(days=1 - dow)
    if not isinstance(start_date, datetime.datetime):
        start_date = datetime.datetime.combine(
            start_date, datetime.time.min, tzinfo=pytz.UTC)
    end_date = start_date + step
    return start_date, end_date, step


def get_daily_interval(start_date):
    """
    Want the interval to start on the first full day including or previous to start_date.
    in GMT
    :param start_date:
    :return:
    """
    step = datetime.timedelta(days=1)
    now = datetime.datetime.now(pytz.utc)
    now_day = datetime.datetime(
        year=now.year, month=now.month, day=now.day, tzinfo=pytz.utc)

    if start_date >= now_day:
        # need a full day
        start_date = start_date - step

    start_time = datetime.datetime(
        year=start_date.year, month=start_date.month, day=start_date.day, tzinfo=pytz.utc)

    end_time = start_time + step
    return start_time, end_time, step


class SourceProviderMetric(NamedTuple):
    provider_key: str
    provider_name: str
    count: int
    enabled_count: int
    disabled_count: int
    plugin_configuration_name: str
    plugin_name: str
    model_name: str
    source_type: str
    track_points: int


def sumarize_sources(start, end):
    # group on provider key
    providers = {}

    queryset = Source.objects.all()
    queryset = queryset.prefetch_related('source_plugins')
    queryset = queryset.prefetch_related('provider')
    for source in queryset:
        provider = providers.get(source.provider.provider_key, {})
        if not provider:
            provider["enabled_count"] = 0
            provider["disabled_count"] = 0
            provider['track_points'] = 0
            provider["count"] = 0
            provider['plugin_name'] = None
            provider['plugin_configuration_name'] = None
            providers[source.provider.provider_key] = provider

        provider["provider_key"] = source.provider.provider_key
        provider["provider_name"] = source.provider.display_name or source.provider.provider_key
        provider["count"] += 1
        provider["model_name"] = provider.get(
            "model_name", None) or source.model_name
        provider["source_type"] = provider.get(
            "source_type", None) or source.source_type
        provider['track_points'] += source.observation_set.filter(created_at__range=(start, end)).count()

        # plugin info
        if source.source_plugins and source.source_plugins.first():
            source_plugin = source.source_plugins.first()
            provider['plugin_name'] = source_plugin.plugin._meta.verbose_name
            provider['plugin_configuration_name'] = source_plugin.plugin.name
            if source_plugin.status == SourcePlugin.STATUS_ENABLED:
                provider["enabled_count"] += 1
            else:
                provider["disabled_count"] += 1

    return [SourceProviderMetric(**summary) for summary in providers.values()]


def get_total_seconds(time_range):
    if time_range.upper and time_range.lower:
        return (time_range.upper - time_range.lower).total_seconds()


def get_user_session_time(starttime, endtime):
    qs = UserSession.objects.filter(time_range__endswith__range=(starttime, endtime))
    return [dict(start_time=s.time_range.lower,
                 end_time=s.time_range.upper,
                 duration=get_total_seconds(s.time_range),
                 sid=s.id)
            for s in qs]


def get_eula_compliance_list():
    if not settings.ACCEPT_EULA:
        return []
    qs = UserAgreement.objects.all().filter(user__accepted_eula=True, user__is_active=True, eula__active=True)
    return [dict(username=agreement.user.username,
                 email=agreement.user.email,
                 version=agreement.eula.version,
                 date_accepted=agreement.date_accepted,
                 accepted_eula=agreement.user.accepted_eula,
                 role=agreement.user.get_role()
        ) for agreement in qs]
    
    

