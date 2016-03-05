import copy
import django
django.setup()
import datetime
import pytz
from functools import namedtuple

import tracking
import observations

from data_input.tools.utils import gen_random_rgb

DEFAULT_DATE_RANGE = (datetime.datetime(2016, 2, 29, tzinfo=pytz.utc), datetime.datetime(2018, 1, 1, tzinfo=pytz.utc))


DEFAULT_CURSOR_DATA = {"boundaries": {"polygons": [
          [
            [
              37.30339050292968,
              0.20324664405209258
            ],
            [
              37.35008239746093,
              0.2070231701397364
            ],
            [
              37.35694885253906,
              0.23414546644179296
            ],
            [
              37.368621826171875,
              0.264357582554732
            ],
            [
              37.39093780517578,
              0.29491294337497587
            ],
            [
              37.431793212890625,
              0.2993760791533651
            ],
            [
              37.48878479003906,
              0.3113922048362213
            ],
            [
              37.510414123535156,
              0.2897631691010714
            ],
            [
              37.5457763671875,
              0.25680456008937463
            ],
            [
              37.547149658203125,
              0.2066798496232364
            ],
            [
              37.497711181640625,
              0.19157373972537947
            ],
            [
              37.501487731933594,
              0.15243512290551367
            ],
            [
              37.48603820800781,
              0.12943256813597956
            ],
            [
              37.423553466796875,
              0.12325277359316192
            ],
            [
              37.35179901123047,
              0.13801561359874617
            ],
            [
              37.30510711669922,
              0.1514051582644001
            ],
            [
              37.29789733886719,
              0.17715425874914836
            ],
            [
              37.30339050292968,
              0.20324664405209258
            ]
          ]
        ]} }

Item = namedtuple('Item', ('name', 'manufacturer_id', 'species', 'sex', 'location'))
data = (('Shiora', 'demo-lewa-1', 'Elephant', 'Male', dict(longitude=37.32536315917969, latitude=0.172004441348131)),
        ('Great Bull', 'demo-lewa-2', 'Elephant', 'Male', dict(longitude=37.38475799560547, latitude=0.25199808891591424)),
        ('Linda', 'demo-lewa-3', 'Elephant', 'Female', dict(longitude=37.40947723388672, latitude=0.2756871075980271)),
        ('Teresai', 'demo-lewa-4', 'Elephant', 'Female', dict(longitude=37.492218017578125, latitude=0.1713177989220863)),
        ('Stimpy', 'demo-lewa-5', 'Elephant', 'Male', dict(longitude=37.51384735107421, latitude=0.23826530447815852))
        )
data = (Item(*d) for d in data)

demosourceplugin, created = tracking.models.DemoSourcePlugin.objects.get_or_create(name='demo-elephants')

try:
    for item in data:
        src, created = observations.models.Source.objects.get_or_create(defaults=dict(model_name='Demo Collar',
                                                             additional={'note': 'Added as demo source'}),
                                               source_type='tracking-device',
                                               manufacturer_id=item.manufacturer_id)

        sub, created = observations.models.Subject.objects.get_or_create(
            subject_type='wildlife',
            name=item.name,
            defaults=dict(additional=dict(region='Lewa', country='Kenya',
                                          species=item.species, sex=item.sex, rgb=gen_random_rgb()))
        )

        ss, created = observations.models.SubjectSource.objects.get_or_create(defaults=dict(assigned_range=DEFAULT_DATE_RANGE,
                                                additional=dict(note='Added for a demo animal.')),
                                                source=src,
                                                subject=sub)

        cursor_data = copy.copy(DEFAULT_CURSOR_DATA)
        cursor_data['last_location'] = item.location
        ss = tracking.models.SourcePlugin(source=src, plugin=demosourceplugin, cursor_data=DEFAULT_CURSOR_DATA)

        ss.save()

except Exception as e:
    print(e)






