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
DEFAULT_DATE_RANGE = (datetime.datetime(2015, 1, 1, tzinfo=pytz.utc), datetime.datetime(2018, 1, 1, tzinfo=pytz.utc))
import uuid

def gen_random_rgb():
    return ','.join([str(random.randint(0,255)) for i in range(3)])

TrackingMaster = namedtuple('TrackingMaster', ('chronofile', 'collar_type',
                                               'collar_id', 'active', 'datasource',
                                               'frequency', 'animal_id',
                                               'name', 'species', 'data_starts',
                                               'data_stops', 'date_off_or_removed', 'comments',
                                               'predicted_expiry', 'rgb', 'sex', 'gmt', 'utm'))
Region = namedtuple('Region', ('chronofile', 'region', 'country'))

# My local copy of animaltracking database.
tm_db = psycopg2.connect('dbname=animaltracking user=postgres password=postgres host=soa.here')
cur = tm_db.cursor()


TM_QUERY = '''
  select {0} from trackingmaster where collar_id in (
  '01081009SKYABB2',
'01081022SKY5FF3',
'01081025SKYEC02',
'01081007SKYA3A8',
'01072804SKY5771',
'01081000SKY0785',
'01081015SKYC3D0',
'01081016SKY47D5',
'01081011SKYB3BC',
'01081014SKY3FCB',
'01080999SKY8380',
'01080997SKY7B76',
'01081002SKY0F8F'
);
'''
cur.execute(TM_QUERY.format(','.join(TrackingMaster._fields)))

tm_list = []
for x in cur:
    _ = TrackingMaster(*x)
    tm_list.append(_)
cur.close()

cur = tm_db.cursor()
cur.execute('select {0} from regions'.format(','.join(Region._fields)))

region_map = {}
for x in cur:
    _ = Region(*x)
    region_map[_.chronofile] = _
cur.close()

DEFAULT_REGION=Region(-1, 'Unassigned', 'Kenya')
## Have tracking master list, so now just need to hydrate DAS database.

for t in tm_list:
    try:
        sub = observations.models.Subject.objects.get(name=t.collar_id)
    except:
        sub = None

    if not sub:
        print("Couldn't find %s" % t.collar_id)
        continue

    afields = ('active', 'datasource',
               'frequency', 'animal_id',
               'name', 'species', 'data_starts',
               'data_stops', 'date_off_or_removed', 'comments',
               'predicted_expiry', 'rgb', 'sex', 'gmt', 'utm')

    _ = t._asdict()
    avals = (_.get(k, None) for k in afields)
    additional = dict(zip(afields, (str(x) for x in avals)))

    sub_additional = dict((k,v) for k,v in additional.items() if k in ('animal_id', 'species', 'name', 'sex', 'comments'))
    sub_additional.update(region_map.get(t.chronofile, DEFAULT_REGION)._asdict())
    sub_additional['rgb'] = gen_random_rgb()
    sub.additional.update(sub_additional)

    sub.name = t.name

    sub.save()







