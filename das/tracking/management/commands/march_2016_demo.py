from datetime import datetime, timedelta
import os
import yaml
try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader


from django.contrib.gis.geos import Point, Polygon, MultiPolygon, LineString, MultiLineString
from django.core.management.base import BaseCommand
from django.db import transaction
import pytz

from accounts.models import PermissionSet, Permission, User
from activity.models import Event, EventAttachment
from analyzers.models import all_analyzers, ContainmentAnalyzer, SubjectAnalyzer, \
    GeofenceAnalyzer, ImmobilityAnalyzer, ProximityAnalyzer, SpeedAnalyzer
from mapping.models import FeatureType, PolygonFeature, LineFeature
from observations.models import Subject, SubjectGroup, SubjectSource, Source, Observation
from tracking.pubsub_registry import notify_new_tracks


source, subject = None, None

points = (
    (37.35, 0.225),
    (37.351, 0.2251),
    (37.375, 0.230),
    (37.40, 0.225),
    (37.45, 0.235),
    (37.50, 0.225),
    (37.55, 0.227),
    (37.55, 0.230),
    (37.55, 0.24),
    (37.55, 0.25),
    (37.50, 0.26),
    (37.45, 0.27),
    (37.41, 0.3),
    (37.37, 0.3),
    (37.40, 0.29),
    (37.43, 0.28),
    (37.425, 0.27),
    (37.42, 0.26),
    (37.415, 0.25),
    (37.410, 0.23),
    # stay in place for a 5h, triggering immobility
    (37.40, 0.22),
    (37.40, 0.2),
    (37.40, 0.2),
    (37.40, 0.2),
    (37.40, 0.2),
    (37.40, 0.2),
    (37.35, 0.2),
)

source_id = '276600ae-06de-4fca-be79-58bb29695f5b'
subject_id = '276600ae-06de-4fca-be79-58bb29695f5c'

def delete_subject():
    Subject.objects.filter(name='Topsy').delete()
    SubjectGroup.objects.filter(name='demo_group').delete()

def delete_source():
    Source.objects.filter(manufacturer_id='topsy').delete()

def delete_observations():
    Observation.objects.filter(source_id=source_id).delete()

def delete_events():
    Event.objects.all().delete()
    EventAttachment.objects.all().delete()

def delete_driven_events(time):
    Event.objects.filter(event_time__gt=time).delete()

def delete_analyzers():
    for klass in all_analyzers:
        klass.objects.filter(subject_id=subject_id).delete()

def delete_subject_analyzers():
    pass

def get_or_create_user(username, email, permission_set):

    user = User.objects.get_or_create(username='demouser', email='josephs@vulcan.com')[0]
    user.permission_sets.add(permission_set)
    user.save()
    return user

def create_actors():
    global source
    source = Source.objects.create(
        id=source_id,
        additional = {},
        manufacturer_id='topsy',
        model_name='topsy'
        )

    global subject
    subject = Subject(
        id=subject_id,
        name = 'Topsy',
        additional = {'sex': 'Female', 'species': 'Elephant'},
        subject_type='wildlife',
        subject_subtype='elephant'
        )

    # (163, 'Permission to subscribe to an alert on this Subject.'),
    permission = Permission.objects.get(pk=163)
    permission_set = PermissionSet.objects.get_or_create(name='Demo PermissionSet')[0]
    permission_set.permissions.add(permission)

    users = (
        ('demouser', 'josephs@vulcan.com'),
        ('chrisj', 'chrisj@vulcan.com'),
        ('teds', 'teds@vulcan.com'),
    )

    for username, email in users:
        get_or_create_user(username, email, permission_set)

    group = SubjectGroup.objects.create(name='demo_group')
    group.permission_sets.add(permission_set)
    group.save()
    subject.group = group
    subject.save()

    DEFAULT_DATE_RANGE = (
        datetime(2015, 11, 1, tzinfo=pytz.utc),
        datetime(3030, 1, 1, tzinfo=pytz.utc)
    )

    subject_source = SubjectSource.objects.create(
        assigned_range=DEFAULT_DATE_RANGE,
        additional={'note': 'Added for a demo animal.'},
        source=source,
        subject=subject
    )


def create_analyzers():

    # create a breachable container
    polygon = Polygon(((37, 1), (37.49, 1), (37.49, -1), (37, -1), (37, 1)))
    dr_polygon = MultiPolygon(polygon)
    feature_type, _ = FeatureType.objects.get_or_create(name="Topsy's Container's FeatureType")

    PolygonFeature.objects.filter(name="Topsy's Container").delete()
    polygon_feature = PolygonFeature.objects.create(
        name="Topsy's Container",
        presentation={},
        feature_geometry=dr_polygon,
        type=feature_type
    )

    ContainmentAnalyzer.objects.create(
        subject=subject,
        polygon=polygon_feature
    )

    # Western edge of Lewa
    multi_line_string = MultiLineString(
        LineString(
            (37.350, 0.200),
            (37.400, 0.310),
        )
    )

    FeatureType.objects.filter(name="Topsy's Geofence FeatureType").delete()
    feature_type, _ = FeatureType.objects.get_or_create(name="Topsy's Geofence FeatureType")

    line_feature = LineFeature.objects.create(
        presentation={},
        feature_geometry=multi_line_string,
        type=feature_type
    )

    GeofenceAnalyzer.objects.create(
        subject=subject,
        fence=line_feature
    )

    ImmobilityAnalyzer.objects.create(
        subject=subject,
        radius=100,
        threshold_time=60*60,
        threshold_warning_cluster_ratio=0.2,
        threshold_critical_cluster_ratio=0.3,
        )


def drive():
    begin_time = datetime.now(tz=pytz.UTC) - timedelta(hours=24*3-1)

    delete_driven_events(begin_time)

    while True:
        delete_observations()

        t0 = datetime.now(tz=pytz.UTC) - timedelta(hours=24*3-1)

        for i, point in enumerate(points):
            dt = timedelta(hours=i)
            t = t0 + dt

            _ = Observation.objects.create(
                source_id=source.id,
                location=Point(point),
                recorded_at=t,
                additional={}
            )
            transaction.on_commit(lambda: notify_new_tracks(source.id))
            transaction.commit()
            yield


def get_time():
    last_time = datetime.utcnow() - timedelta(hours=24*5)
    last_time = last_time.replace(tzinfo=pytz.UTC)
    time_increment = timedelta(minutes=30)
    while True:
        last_time = last_time + time_increment
        yield last_time


def add_demo_data(file=None):

    def default_demo_file():
        return os.path.join(os.path.dirname(__file__), 'march_2016_demo.yml')

    if not file:
        file = default_demo_file()

    #yes, twice
    for _ in range(2):
        with open(file) as fp:
            demo_data = yaml.load(fp, Loader=SafeLoader)

        times = get_time()

        for evt in reversed(demo_data['events']):
            event = Event(name=evt['name'])
            event.event_time = next(times)
            if evt.get('center', None):
                event.location = Point(*evt['center'])

            for k,v in evt.items():
                if hasattr(event, k):
                    setattr(event, k, v)
            event.save()

            if evt.get('subject_name', None):
                Subject.objects.get(name=evt['subject_name'])
                EventAttachment.objects.create(target=subject, event=event)


class Command(BaseCommand):

    help = 'Run the March 2016 demo track'

    def handle(self, *args, **options):
        delete_analyzers()
        delete_subject_analyzers()
        delete_subject()
        delete_source()
        delete_observations()
        delete_events()

        create_actors()
        create_analyzers()

        add_demo_data()

        generator = drive()
        # prime the DB with an observation
        next(generator)
        next(generator)

        input('removed old data. load web app and press enter to continue')

        for _ in generator:
            input('press enter to continue')
