from datetime import datetime, timedelta
import glob
import json
import os
import yaml
try:
    from yaml import CSafeLoader as SafeLoader
except ImportError:
    from yaml import SafeLoader


from django.contrib.gis.geos import Point, MultiPoint, Polygon, MultiPolygon, LineString, MultiLineString
from django.core.management.base import BaseCommand
from django.db import transaction
import pytz
import random

from accounts.models import PermissionSet, Permission, User
from activity.models import Event, EventAttachment
from analyzers.models import all_analyzers, ContainmentAnalyzer, SubjectAnalyzer, \
    GeofenceAnalyzer, ImmobilityAnalyzer, ProximityAnalyzer, SpeedAnalyzer
from mapping.models import FeatureType, PolygonFeature, LineFeature, PointFeature, FeatureSet
from observations.models import Subject, SubjectGroup, SubjectSource, Source, Observation
from tracking.pubsub_registry import notify_new_tracks

def gen_random_rgb():
    return ','.join([str(random.randint(0,175)) for i in range(3)])


HISTORY_HOURS=24
source, subject = None, None

points = [
          [
            37.46440887451172,
            0.2138895788924224
          ],
          [
            37.467498779296875,
            0.1895138145932037
          ],
          [
            37.483978271484375,
            0.17578097424708533
          ],
          [
            37.49256134033203,
            0.17028783523693297
          ],
          [
            37.501487731933594,
            0.1665113012564374
          ],
          [
            37.51007080078124,
            0.17818422205893264
          ],
          [
            37.515220642089844,
            0.18917049371396785
          ],
          [
            37.50663757324219,
            0.20015675841377878
          ],
          [
            37.49702453613281,
            0.2056498880292469
          ],
          [
            37.49359130859375,
            0.22212926533206975
          ],
          [
            37.48294830322265,
            0.23036894717780024
          ],
          [
            37.48,
            0.23
          ],
          [
            37.48,
            0.23
          ],
          [
            37.48,
            0.23
          ],
          [
            37.48,
            0.23
          ],
          [
            37.48,
            0.23
          ],
          [
            37.48,
            0.23
          ],
          [
            37.463035583496094,
            0.23929526379559607
          ],
          [
            37.44621276855469,
            0.24684829640586692
          ],
          [
            37.435569763183594,
            0.23689202526852574
          ],
          [
            37.43762969970703,
            0.22487582646616774
          ],
          [
            37.434539794921875,
            0.2070231701397364
          ],
          [
            37.449989318847656,
            0.21148633617335558
          ],
          [
            37.463035583496094,
            0.21869606319738805
          ]
        ]

source_id = '276600ae-06de-4fca-be79-58bb29695f5b'
subject_id = '276600ae-06de-4fca-be79-58bb29695f5c'

feature_type, _ = FeatureType.objects.get_or_create(name='wat')
feature_set, _ = FeatureSet.objects.get_or_create(
    type=feature_type,
    name='Demo feature set name',
    description='Demo feature set description'
)

def delete_subject():
    Subject.objects.filter(name='TEAM SIX').delete()
    SubjectGroup.objects.filter(name='demo_group').delete()

def delete_source():
    Source.objects.filter(manufacturer_id='TEAM SIX').delete()

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

    # add perms to ChrisJ and TedS
    user = User.objects.get_or_create(username='chrisj', email='chrisj@vulcan.com')[0]
    user.permission_sets.add(permission_set)
    user.save()

    user = User.objects.get_or_create(username='teds', email='teds@vulcan.com')[0]
    user.permission_sets.add(permission_set)
    user.save()

    user = User.objects.get_or_create(username='josephs', email='josephs@vulcan.com')[0]
    user.permission_sets.add(permission_set)
    user.save()

    user = User.objects.get_or_create(username='demouser', email='josephs@vulcan.com')[0]
    user.permission_sets.add(permission_set)
    user.save()

    return user

def create_actors():
    global source
    source = Source.objects.create(
        id=source_id,
        additional = {},
        manufacturer_id='TEAM SIX',
        model_name='TEAM SIX'
        )

    global subject
    subject = Subject(
        id=subject_id,
        name = 'TEAM SIX',
        additional = {'rgb': gen_random_rgb()},
        subject_type='person',
        subject_subtype='ranger'
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

    PolygonFeature.objects.filter(name="TEAM SIX's Container").delete()
    polygon_feature = PolygonFeature.objects.filter(name__contains='Lewa').first()

    #ContainmentAnalyzer.objects.create(
    #    subject=subject,
    #    polygon=polygon_feature,
    #)

    FeatureType.objects.filter(name="TEAM SIX's Geofence FeatureType").delete()
    line_feature = LineFeature.objects.filter(name__contains='Major highway - A2').first()

    GeofenceAnalyzer.objects.create(
        subject=subject,
        fence=line_feature
    )

    ImmobilityAnalyzer.objects.create(
        subject=subject,
        radius=100,
        threshold_time=60*60*2,
        threshold_warning_cluster_ratio=1.0,
        threshold_critical_cluster_ratio=1.0,
        )

    PolygonFeature.objects.filter(name="TEAM SIX's Proximity Feature").delete()

    #ProximityAnalyzer.objects.create(
    #    subject=subject,
    #    polygon=proximity_polygon_feature,
    #    distance_m=100
    #)

    SpeedAnalyzer.objects.create(subject=subject, max_speed=10000000)


def drive():

    begin_time = datetime.now(tz=pytz.UTC) - timedelta(hours=HISTORY_HOURS)
    delete_driven_events(begin_time)

    # Outer loop is for restarting the whole thing.
    while True:
        delete_observations()

        t0 = datetime.now(tz=pytz.UTC) - timedelta(hours=HISTORY_HOURS)

        for i, point in enumerate(points):
            dt = timedelta(minutes=i*30)
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
    last_time = datetime.now(tz=pytz.UTC) - timedelta(hours=HISTORY_HOURS*2)
    time_increment = timedelta(minutes=30)
    while True:
        last_time = last_time + time_increment
        yield last_time


def add_demo_data(file=None):

    def default_demo_file():
        return os.path.join(os.path.dirname(__file__), 'march_2016_demo_data/march_2016_demo.yml')

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

def import_geojson():
    data_pattern = os.path.join(os.path.dirname(__file__), 'march_2016_demo_data/*.geojson')

    for data_file in glob.glob(data_pattern):
        with open(data_file) as f:
            geojson = json.load(f)
            for feature in geojson['features']:
                geom = feature['geometry']
                coords = geom['coordinates']

                if geom['type'] == 'MultiLineString':
                    lines = []
                    for l in coords:

                        ls = LineString(l)
                        lines.append(ls)
                    mls = MultiLineString(lines)
                    name = feature['properties'].get('roadclass')
                    LineFeature.objects.filter(name=name).delete()
                    LineFeature.objects.create(
                        name=name,
                        presentation=feature.get('properties'),
                        type=feature_type,
                        feature_geometry=mls,
                        featureset=feature_set
                    )

                elif geom['type'] == 'Point':
                    point = Point(geom['coordinates'])
                    mp = MultiPoint([point])
                    name = feature['properties'].get('name')
                    # FIXME: mapbox doesn't seem to want to style a MultiPoint,
                    # which is what PointFeature wants to store.
                    # may have to serialize this as a Point on outbound,
                    # or change PointFeature to reference Points
                    feature['properties']['marker-symbol'] = 1
                    PointFeature.objects.filter(name=name).delete()
                    PointFeature.objects.create(
                        name=name,
                        presentation=feature.get('properties'),
                        type=feature_type,
                        feature_geometry=mp,
                        featureset=feature_set
                    )

                else:
                    poly = Polygon(coords[0])
                    multi_polygon = MultiPolygon(poly)
                    name = feature['properties']['name']  # data_file[-80:]
                    PolygonFeature.objects.filter(name=name).delete()

                    PolygonFeature.objects.create(
                        name=name,
                        presentation=feature.get('properties'),
                        type=feature_type,
                        feature_geometry=multi_polygon,
                        featureset=feature_set
                    )

class Command(BaseCommand):

    help = 'Run the March 2016 demo track'

    def handle(self, *args, **options):
        delete_analyzers()
        delete_subject_analyzers()
        delete_subject()
        delete_source()
        delete_observations()
        delete_events()

        import_geojson()
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
