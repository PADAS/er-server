import django
django.setup()
import sys
import psycopg2
from functools import namedtuple
from observations import models as obs

from data_input import models as dip
import datetime
import pytz

DEFAULT_DATE_RANGE = (datetime.datetime(2015, 1, 1, tzinfo=pytz.utc), datetime.datetime(2018, 1, 1, tzinfo=pytz.utc))
import uuid


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

cur.execute('select {0} from trackingmaster;'.format(','.join(TrackingMaster._fields)))

tm_map = {}
for x in cur:
    _ = TrackingMaster(*x)
    tm_map[_.name] = _
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

for sub in obs.Subject.objects.filter(name__in=('IFAW16', 'IFAW15', 'IFAW09', 'Soshangane', 'IFAW11', 'Timurid', 'Abdi Boru', 'Leakey', '00582187VTI8514', '00582188VTI0919', '00582194VTI2137', '00582195VTIA53C', 'Kisima', '00582207VTID578', 'Melako', '01072804SKY5771', 'Caroline', 'Turungu', 'Bulesa', 'Madurba', 'Serelparua', 'Nasarge', 'Tassia', '01080996SKYF771', '01080997SKY7B76', '01080999SKY8380', '01081000SKY0785', 'Abdi Boru', '01081002SKY0F8F', '01081007SKYA3A8', '01081009SKYABB2', 'Loibor', '01081011SKYB3BC', '01081013SKYBBC6', '01081014SKY3FCB', '01081015SKYC3D0', '01081016SKY47D5', 'Timurid', 'Leparua', 'Kegol', '01081022SKY5FF3', 'Lucy', '01081025SKYEC02', 'Limo')):
    if 'species' not in sub.additional:

        tmsub = tm_map.get(sub.name)
        if tmsub:
            newaddt = dict(sex=tmsub.sex, species=tmsub.species)
            newaddt.update(region_map.get(_.chronofile, DEFAULT_REGION)._asdict())
            print('Updating sub.additional %s' % sub.additional)
            print('    with %s' % newaddt)
            sub.additional.update(newaddt)
            print (sub)
            sub.save()