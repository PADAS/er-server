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
from django.contrib.auth.models import Permission
import pytz
import random

from accounts.models import PermissionSet, User
from activity.models import Event, EventAttachment
from analyzers.models import all_analyzers, ContainmentAnalyzer, SubjectAnalyzer, \
    GeofenceAnalyzer, ImmobilityAnalyzer, ProximityAnalyzer, SpeedAnalyzer
from mapping.models import FeatureType, PolygonFeature, LineFeature, PointFeature, FeatureSet
from observations.models import Subject, SubjectGroup, SubjectSource, Source, Observation
from tracking.pubsub_registry import notify_new_tracks


def gen_random_rgb():
    return ','.join([str(random.randint(50,200)) for i in range(3)])

# For observations, animal and ranger movements, this is how far we'll go back to start.
HISTORY_HOURS=24

feature_type, _ = FeatureType.objects.get_or_create(name='wat')
feature_set, _ = FeatureSet.objects.get_or_create(
    type=feature_type,
    name='Demo feature set name',
    description='Demo feature set description'
)

def delete_subject_analyzers():
    pass

def get_or_create_user(username='chrisd', email='chrisdo@vulcan.com', permission_set=None):
    user, created = User.objects.get_or_create(username=username, defaults=dict(mail=email))
    if permission_set:
        user.permission_sets.add(permission_set)
    user.save()
    return user

def varypoint(p):
    return [p[0]+random.random()*0.01, p[1]+random.random()* 0.01]

def load_track_geojson(name):
    filename = os.path.join(os.path.dirname(__file__), 'track_data/{0}.geojson'.format(name))
    with open(filename, 'r') as f:
        return json.load(f)

group = None
def create_actors():


    # (163, 'Permission to subscribe to an alert on this Subject.'),
    permission = Permission.objects.get(pk=163)
    permission_set = PermissionSet.objects.get_or_create(name='Demo PermissionSet')[0]
    permission_set.permissions.add(permission)

    users = (
        ('demouser', 'josephs@vulcan.com'),
        ('chrisd', 'chrisdo@vulcan.com'),
    )

    for username, email in users:
        get_or_create_user(username=username, email=email, permission_set=permission_set)

    global group
    group, created = SubjectGroup.objects.get_or_create(name='demo_group')
    group.permission_sets.add(permission_set)
    group.save()


class DemoDriver():
    DEFAULT_DATE_RANGE = (
        datetime(2015, 11, 1, tzinfo=pytz.utc),
        datetime(3030, 1, 1, tzinfo=pytz.utc)
    )
    def __init__(self, name=None, source_id=None, subject_id=None, group=None, **kwargs):
        self.source_id = source_id
        self.subject_id = subject_id
        self.name = name
        self.manufacturer_id = kwargs.pop('manufacturer_id', name.lower().replace(' ', '_'))
        self.group = group
        self.subject_type = kwargs.pop('subject_type', 'person')
        self.subject_subtype = kwargs.pop('subject_subtype', 'ranger')
        self.kwargs = kwargs

    def hydrate(self):
        self.source = Source.objects.create(
            id=self.source_id,
            additional = {},
            manufacturer_id=self.manufacturer_id,
            model_name='Super model. The best money can buy!'
            )

        subadd = {'rgb': gen_random_rgb()}
        subadd.update(self.kwargs) # In case attributes includes species, sex, etc.

        self.subject = Subject(
            id=self.subject_id,
            name = self.name,
            additional=subadd,
            subject_type=self.subject_type,
            subject_subtype=self.subject_subtype,
            group=self.group
            )
        self.source.save()
        self.subject.save()

        self.subject_source = SubjectSource.objects.create(
            assigned_range=self.DEFAULT_DATE_RANGE,
            additional={'note': 'Added for a demo animal.'},
            source=self.source,
            subject=self.subject
        )

    def create_analyzers(self):

        PolygonFeature.objects.filter(name="TEAM SIX's Container").delete()

        FeatureType.objects.filter(name="TEAM SIX's Geofence FeatureType").delete()
        line_feature = LineFeature.objects.filter(name__contains='Major highway - A2').first()

        GeofenceAnalyzer.objects.create(
            subject=self.subject,
            fence=line_feature
        )

        ImmobilityAnalyzer.objects.create(
            subject=self.subject,
            radius=100,
            threshold_time=60*60*2,
            threshold_warning_cluster_ratio=1.0,
            threshold_critical_cluster_ratio=1.0,
            )

        PolygonFeature.objects.filter(name="TEAM SIX's Proximity Feature").delete()
        # SpeedAnalyzer.objects.create(subject=self.subject, max_speed=10000000)


    def drive(self):

        begin_time = datetime.now(tz=pytz.UTC) - timedelta(hours=HISTORY_HOURS)
        self.delete_driven_events(begin_time)

        # Outer loop is for restarting the whole thing.
        while True:
            self.delete_observations()

            t0 = datetime.now(tz=pytz.UTC) - timedelta(hours=HISTORY_HOURS)

            points = load_track_geojson(self.manufacturer_id)
            points = points['features'][0]['geometry']['coordinates']
            plist = [varypoint(p) for p in points]
            for i, point in enumerate(plist):
                dt = timedelta(minutes=i*30)
                t = t0 + dt

                _ = Observation.objects.create(
                    source_id=self.source.id,
                    location=Point(point),
                    recorded_at=t,
                    additional={}
                )
                transaction.on_commit(lambda: notify_new_tracks(self.source.id))
                transaction.commit()
                yield

    @staticmethod
    def get_time():
        last_time = datetime.now(tz=pytz.UTC) - timedelta(hours=HISTORY_HOURS*2)
        time_increment = timedelta(minutes=30)
        while True:
            last_time = last_time + time_increment
            yield last_time

    def delete_subject(self):
        Subject.objects.filter(id=self.subject_id).delete()

    def delete_source(self):
        Source.objects.filter(id=self.source_id).delete()

    def delete_observations(self):
        Observation.objects.filter(source_id=self.source_id).delete()

    def delete_events(self):
        # EventAttachment.objects.filter(target_id=self.subject.id).delete()
        EventAttachment.objects.all().delete()
        Event.objects.all().delete()

    def delete_driven_events(self, time):
        Event.objects.filter(event_time__gt=time).delete()

    def delete_analyzers(self):
        for klass in all_analyzers:
            klass.objects.filter(subject_id=self.subject_id).delete()

    def ignition(self):
        self.delete_analyzers()
        delete_subject_analyzers()
        self.delete_subject()
        self.delete_source()
        self.delete_observations()
        self.delete_events()
        self.hydrate()
        self.create_analyzers()

demodatafile = {}
def read_demo_data(file=None):

    global demodatafile

    def default_demo_file():
        return os.path.join(os.path.dirname(__file__), 'march_2016_demo_data/march_2016_demo.yml')

    if not file:
        file = default_demo_file()

    if demodatafile.get(file) is None:
        with open(file) as fp:
            demo_data = yaml.load(fp, Loader=SafeLoader)
            demodatafile[file] = demo_data

    return demodatafile[file]


def generate_events():
    demo_data = read_demo_data()
    yield from demo_data['events']

def inject_random_events():

    times = DemoDriver.get_time()
    while True:
        for e in sorted(list(generate_events()), key=lambda x: random.random()):
            store_event(e, None, next(times))
            yield

def add_demo_data(subject=None):

    #yes, twice
    for _ in range(2):

        times = DemoDriver.get_time()

        for evt in generate_events():
            store_event(evt, subject, next(times))

def store_event(evt, subject, t):
    event = Event(message=evt['message'])
    event.event_time = t
    if evt.get('center', None):
        event.location = Point(*evt['center'])

    for k,v in evt.items():
        if hasattr(event, k):
            setattr(event, k, v)
    event.save()

    if evt.get('subject_name', None):
        subject = Subject.objects.get(name=evt['subject_name'])
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

        import_geojson()

        create_actors()
        drivers = []
        for sub in read_demo_data()['subjects']:
            driver = DemoDriver(group=group, **sub)
            driver.ignition()
            drivers.append(driver)


        # We have some canned events that are associated with the first RADIO.
        add_demo_data(subject=drivers[0].subject)

        generators = list(driver.drive() for driver in drivers)
        # prime the DB with an observation
        for g in generators:
            next(g)
            next(g)

        input('removed old data. load web app and press enter to continue')

        randomevents = inject_random_events()
        next(randomevents)
        while True:
            for g in generators:
                if 0.7 > random.random():
                    next(g)

            # Inject a random event occasionally.
            if 0.4 > random.random():
                next(randomevents)

            input('press enter to continue')
