import subprocess
from datetime import datetime, timedelta

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
    (37.42, 0.3),
    (37.35, 0.3),
    (37.55, 0.15),
    (37.50, 0.16),
    (37.45, 0.17),
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
    for event_attachment in EventAttachment.objects.filter(target_id=subject_id):
        event_attachment.event.delete()
        event_attachment.delete()

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
    analyzer = ContainmentAnalyzer.objects.create(polygon=polygon_feature)
    subject_analyzer = SubjectAnalyzer(subject=subject, content_object=analyzer)
    subject_analyzer.save()


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
            # sleep for a second, or continue on enter press
            subprocess.call('read -t 1', shell=True)

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

        input('setup complete, press enter to start demo')
        drive()
