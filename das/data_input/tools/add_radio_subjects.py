import django
django.setup()
import observations.models
import random
import datetime
import pytz

DEFAULT_DATE_RANGE = (datetime.datetime(2015, 9, 1, tzinfo=pytz.utc), datetime.datetime(2016, 12, 31, tzinfo=pytz.utc))

def gen_random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])

try:
    cur = observations.models.Source.objects.filter(source_type='gps-radio')
except Exception as e:
    exit()

for src in cur:

    try:
        sub_name = 'MT %s' % src.manufacturer_id
    except Exception as e:
        continue

    sub_addl = {
        'species': 'Ranger',
        'rgb': gen_random_rgb(),
        'note': 'generated Wed Dec-9',
    }
    sub, created = observations.models.Subject.objects.get_or_create(
        defaults={
            'additional': sub_addl,
        },
        name=sub_name,
        subject_type='person'
    )

    ss, created = observations.models.SubjectSource.objects.get_or_create(
        defaults=dict(
            assigned_range=DEFAULT_DATE_RANGE,
            additional=dict(note='Added by hand Dec 9.',),
        ),
        source=src,
        subject=sub,
    )

    print("Done for src %s" % src.manufacturer_id)





