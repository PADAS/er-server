import django
django.setup()
import sys
import psycopg2
from functools import namedtuple
import observations.models
import data_input.models
import datetime
import pytz
import random
from data_input.plugins.inreach import InreachAccountClient
DEFAULT_DATE_RANGE = (datetime.datetime(2015, 12, 1, tzinfo=pytz.utc), datetime.datetime(2018, 1, 1, tzinfo=pytz.utc))
DEFAULT_REGION = {
    'country': 'Republic of the Congo',
    'region': 'Odzala',
}

def gen_random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])

import uuid

new_collar_ids = [
    '01125430SKYA34B',
    '01125432SKYAB55',
    '01125435SKY3764',
    '01125451SKY77B4',
    '01125454SKY03C3',
    '01125476SKY5C31',
    '01125485SKY005E',
    '01125486SKY8463',
    '01125490SKY9477',
    '01125492SKY9C81',
    '01125500SKYBCA9'
]

new_inreach_radios = [
    ('300434060090580', 'inReach SE', 'DeLorme 2 Plan', 'Odzala1@african-parks.org', 'Oct 29th 2015',
     '153 of 3000 bytes', 'No'),
    ('300434060991270', 'inReach SE', 'DeLorme 2 Plan', 'Odzala2@african-parks.org', 'Oct 29th 2015',
     '1565 of 3000 bytes', 'No'),
    ('300434061507410', 'inReach SE', 'DeLorme 2 Plan', 'Odzala3@african-parks.org', 'Oct 29th 2015',
     '270 of 3000 bytes', 'No'),
    ('300434060995620', 'inReach SE', 'DeLorme 2 Plan', 'Odzala4@african-parks.org', 'Oct 29th 2015',
     '3138 of 3000 bytes', 'No'),
    ('300434060494380', 'inReach SE', 'DeLorme 2 Plan', 'Odzala5@african-parks.org', 'Oct 29th 2015',
     '8757 of 3000 bytes', 'No'),
    (
    '300434061503540', 'inReach SE', 'DeLorme 2 Plan', 'Odzala6@african-parks.org', 'Oct 29th 2015', '52 of 3000 bytes',
    'No'),
    ('300434061505410', 'inReach SE', 'DeLorme 2 Plan', 'Odzala7@african-parks.org', 'Oct 29th 2015',
     '14982 of 3000 bytes', 'No'),
    ('300434061509420', 'inReach SE', 'DeLorme 2 Plan', 'Odzala8@african-parks.org', 'Oct 29th 2015',
     '5499 of 3000 bytes', 'No'),
    ('300434061701020', 'inReach SE', 'DeLorme 2 Plan', 'Odzala9@african-parks.org', 'Oct 29th 2015',
     '21546 of 3000 bytes', 'No'),
    ('300434060888530', 'inReach SE', 'DeLorme 2 Plan', 'Odzala10@african-parks.org', 'Oct 29th 2015',
     '31 of 3000 bytes', 'No'),
    ('300434061305720', 'inReach SE', 'DeLorme 2 Plan', 'Odzala11@african-parks.org', 'Oct 29th 2015',
     '327 of 3000 bytes', 'No'),
    ('300434061007070', 'inReach SE', 'DeLorme 2 Plan', 'Odzala12@african-parks.org', 'Oct 29th 2015',
     '108 of 3000 bytes', 'No'),
    ('300434060092440', 'inReach SE', 'DeLorme 2 Plan', 'Odzala13@african-parks.org', 'Oct 29th 2015',
     '122 of 3000 bytes', 'No'),
    ('300434061406090', 'inReach SE', 'DeLorme 2 Plan', 'Odzala14@african-parks.org', 'Oct 29th 2015',
     '9023 of 3000 bytes', 'No'),
    ('300434060198180', 'inReach SE', 'DeLorme 2 Plan', 'Odzala15@african-parks.org', 'Oct 29th 2015',
     '6338 of 3000 bytes', 'No'),
    ('300434061400010', 'inReach SE', 'DeLorme 2 Plan', 'Odzala16@african-parks.org', 'Oct 29th 2015',
     '161 of 3000 bytes', 'No'),
    ('300434061204460', 'inReach SE', 'DeLorme 2 Plan', 'Odzala17@african-parks.org', 'Oct 29th 2015',
     '1923 of 3000 bytes', 'No'),
    ('300434060899830', 'inReach SE', 'DeLorme 2 Plan', 'Odzala18@african-parks.org', 'Oct 29th 2015',
     '4591 of 3000 bytes', 'No'),
    ('300434061703020', 'inReach SE', 'DeLorme 2 Plan', 'Odzala19@african-parks.org', 'Oct 29th 2015',
     '4354 of 3000 bytes', 'No'),
    ('300434061304830', 'inReach SE', 'DeLorme 2 Plan', 'Odzala20@african-parks.org', 'Oct 29th 2015',
     '1134 of 3000 bytes', 'No'),
]

Dd = namedtuple('Dd', ('imei', 'device_name', 'service_plan', 'assigned_to', 'added', 'total_usage', 'synced'))

new_inreach_radios = [Dd(*x) for x in new_inreach_radios]

pluginconf, created = data_input.models.PluginConf.objects.get_or_create(plugin_name='ap-garamba-inreach', plugin_class='inreach-api',
                                                                          defaults=dict(configuration={
                                                                              "note":"Added automatically."}))


for x in new_inreach_radios:
    print(x)


if not pluginconf:
    exit()

def find_existing_source(**kwargs):
    try:
        return observations.models.Source.objects.get(**kwargs)
    except Exception as e:
        print(e)
        pass

for inreach_radio in new_inreach_radios:
    existing = find_existing_source(manufacturer_id=inreach_radio.imei)

    if existing:
        continue

    src_additional = dict(service_plan=inreach_radio.service_plan,
                          added=inreach_radio.added)
    source = observations.models.Source(id=uuid.uuid4(), source_type='gps-radio', model_name=inreach_radio.device_name,
                                        manufacturer_id=inreach_radio.imei, additional=src_additional)
    source.save()


    sub_additional = {
        'rgb': gen_random_rgb(),
    }
    name = inreach_radio.assigned_to.split('@')[0]
    subject = observations.models.Subject(id=uuid.uuid4(), name=name, subject_type='person', additional=sub_additional)

    subject.save()

    ss = observations.models.SubjectSource(id=uuid.uuid4(), assigned_range=DEFAULT_DATE_RANGE, source=source, subject=subject, additional={'note':'added automatically.'})
    ss.save()

    dip_source = data_input.models.PluginConfSource(id=uuid.uuid4(), plugin_conf=pluginconf, source=source, additional={"note":"Added automatically"})
    dip_source.save()

    print('Done %s' % dip_source)

