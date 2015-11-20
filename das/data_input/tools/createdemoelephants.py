import django
django.setup()
from functools import namedtuple
import observations

import data_input
import datetime
import pytz

DEFAULT_DATE_RANGE = (datetime.datetime(2015, 11, 1, tzinfo=pytz.utc), datetime.datetime(2018, 1, 1, tzinfo=pytz.utc))
import uuid

DEFAULT_DIPS_ADDITIONAL = {"boundaries": {"polygons": [[[25.029, 19.447], [25.017, 22.652], [26.242, 22.632], [26.963, 20.628], [26.971, 19.431], [25.029, 19.447]]]} }

Item = namedtuple('Item', ('name', 'manufacturer_id', 'species', 'sex'))
data = (('Russel', 'demo-collar-1', 'Elephant', 'Male'),
        ('Jimmy', 'demo-collar-2', 'Elephant', 'Male'),
        ('Carla', 'demo-collar-3', 'Elephant', 'Female'),
        ('Shirley', 'demo-collar-4', 'Elephant', 'Female'))
data = (Item(*d) for d in data)

plugin_conf, created = data_input.models.PluginConf.objects.get_or_create(plugin_name='demo-wildlife',
                                                                          defaults=dict(additional={
                                                                              "note": "Added to support demo plugin."}))

try:
    for item in data:
        src, created = observations.models.Source.objects.get_or_create(defaults=dict(model_name='Demo Collar',
                                                             additional={'note': 'Added as demo source'}),
                                               source_type='tracking-device',
                                               manufacturer_id=item.manufacturer_id)

        sub, created = observations.models.Subject.objects.get_or_create(defaults=dict(additional=dict(region='VulcanPA', country='Demo',
                                                                              species=item.species, sex=item.sex)),
                                                subject_type='wildlife',
                                                name=item.name)

        ss, created = observations.models.SubjectSource.objects.get_or_create(defaults=dict(assigned_range=DEFAULT_DATE_RANGE,
                                                additional=dict(note='Added for a demo animal.')),
                                                source=src,
                                                subject=sub)

        dips, created = data_input.models.PluginConfSource.objects.get_or_create(defaults=dict(additional=DEFAULT_DIPS_ADDITIONAL),
                                           source=src,
                                           plugin_conf=plugin_conf)
except Exception as e:
    print(e)






