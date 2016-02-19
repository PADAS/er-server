from datetime import datetime, timedelta
import os
import subprocess
import yaml
from yaml import SafeLoader

from django.contrib.gis.geos import Point, Polygon, MultiPolygon
from django.core.management.base import BaseCommand
from django.db import transaction
import pytz

from activity.models import Event, EventAttachment
from analyzers.models import ContainmentAnalyzer, SubjectAnalyzer, \
    GeofenceAnalyzer, ImmobilityAnalyzer, ProximityAnalyzer, SpeedAnalyzer
from mapping.models import FeatureType, PolygonFeature
from observations.models import Subject, SubjectSource, Source, Observation
from tracking.pubsub_registry import notify_new_tracks



source, subject = None, None

points = (
    (37.35, 0.225),
    (37.40, 0.225),
    (37.45, 0.225),
    (37.50, 0.225),
    (37.55, 0.225),
    (37.55, 0.230),
    (37.55, 0.24),
    (37.55, 0.25),
    (37.50, 0.26),
    (37.45, 0.27),
    (37.41, 0.3),
    (37.37, 0.3),
    (37.55, 0.15),
    (37.52, 0.155),
    (37.50, 0.16),
    (37.47, 0.165),
    (37.45, 0.17),
    (37.42, 0.19),
    # stay in place for a 5h, triggering immobility
    (37.40, 0.2),
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
    Subject.objects.filter(name="Topsy").delete()

def delete_source():
    Source.objects.filter(manufacturer_id='topsy').delete()

def delete_observations():
    Observation.objects.filter(source_id=source_id).delete()

def delete_events():
    Event.objects.all().delete()
    EventAttachment.objects.all().delete()

def delete_analyzers():
    pass

def delete_subject_analyzers():
    pass

def create_actors():
    global source
    source = Source.objects.create(
        id=source_id,
        additional = {},
        manufacturer_id='topsy',
        model_name='topsy'
        )

    global subject
    subject = Subject.objects.create(
        id=subject_id,
        name = 'Topsy',
        additional = {'sex': 'Female', 'species': 'Elephant'},
        subject_type='wildlife',
        subject_subtype='elephant'
        )

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
        polygon=polygon_feature)

    ImmobilityAnalyzer.objects.create(
        subject=subject,
        radius=100,
        threshold_time=60*60,
        threshold_warning_cluster_ratio=0.2,
        threshold_critical_cluster_ratio=0.3,
        )


def drive():
    while True:
        delete_observations()
        delete_events()

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
    last_time = datetime.utcnow() - timedelta(hours=2)
    last_time = last_time.replace(tzinfo=pytz.UTC)
    time_increment = timedelta(minutes=5)
    while True:
        last_time = last_time + time_increment
        yield last_time


def add_demo_data(file=None):

    def default_demo_file():
        return os.path.join(os.path.dirname(__file__), 'march_2016_demo.yml')

    if not file:
        file = default_demo_file()
    with open(file) as fp:
        demo_data = yaml.load(fp, Loader=SafeLoader)

    times = get_time()
    print("add_demo_data")
    print(demo_data)
    for evt in demo_data['events']:
        event = Event(name=evt['name'])
        event.event_time = next(times)
        if evt.get('center', None):
            event.location = Point(*evt['center'])

        for k,v in evt.items():
            if hasattr(event, k):
                setattr(event, k, v)
        event.save()


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

        input('setup complete, press enter to start demo')

        for _ in generator:
            input('press enter to continue')
