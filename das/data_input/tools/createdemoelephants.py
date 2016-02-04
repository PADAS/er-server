import django
django.setup()
import datetime
import pytz
from functools import namedtuple

import tracking
import observations

from data_input.tools.utils import gen_random_rgb

DEFAULT_DATE_RANGE = (datetime.datetime(2015, 11, 1, tzinfo=pytz.utc), datetime.datetime(2018, 1, 1, tzinfo=pytz.utc))


DEFAULT_CURSOR_DATA = {"boundaries": {"polygons": [[[25.029, 19.447], [25.017, 22.652], [26.242, 22.632], [26.963, 20.628], [26.971, 19.431], [25.029, 19.447]]]} }

Item = namedtuple('Item', ('name', 'manufacturer_id', 'species', 'sex'))
data = (('Russel', 'demo-collar-1', 'Elephant', 'Male'),
        ('Jimmy', 'demo-collar-2', 'Elephant', 'Male'),
        ('Carla', 'demo-collar-3', 'Elephant', 'Female'),
        ('Shirley', 'demo-collar-4', 'Elephant', 'Female'),
        ('Roger', 'demo-collar-5', 'Elephant', 'Male')
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
            defaults=dict(additional=dict(region='VulcanPA', country='Demo',
                                          species=item.species, sex=item.sex, rgb=gen_random_rgb()))
        )

        ss, created = observations.models.SubjectSource.objects.get_or_create(defaults=dict(assigned_range=DEFAULT_DATE_RANGE,
                                                additional=dict(note='Added for a demo animal.')),
                                                source=src,
                                                subject=sub)

        ss = tracking.models.SourcePlugin(source=src, plugin=demosourceplugin, cursor_data=DEFAULT_CURSOR_DATA)

        ss.save()

except Exception as e:
    print(e)






