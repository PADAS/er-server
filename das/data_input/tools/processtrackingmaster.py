import django
django.setup()
import sys
import psycopg2
from functools import namedtuple
import observations.models
import data_input.models
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


TM_QUERY = '''
  with cf as (select distinct unnest(chronofiles) chronofile from trackingusers where organization ilike '%lewa%' or organization ilike '%nrt')
 select {0} from trackingmaster tm
   where chronofile in (select chronofile from cf)
    and tm.datasource in ('HTTP', 'SavannahTrackingAPI');
'''
cur.execute(TM_QUERY.format(','.join(TrackingMaster._fields)))

tm_list = []
for x in cur:
    _ = TrackingMaster(*x)
    tm_list.append(_)
cur.close()
t
cur = tm_db.cursor()
cur.execute('select {0} from regions'.format(','.join(Region._fields)))

region_map = {}
for x in cur:
    _ = Region(*x)
    region_map[_.chronofile] = _
cur.close()

DEFAULT_REGION=Region(-1, 'Unassigned', 'Kenya')
## Have tracking master list, so now just need to hydrate DAS database.


awtpluginconf, created = data_input.models.PluginConf.objects.get_or_create(plugin_name='awt-http-gsm', plugin_class='awt-http',
                                                                          defaults=dict(configuration={
                                                                              "api_url": "http://www.yrless.co.za/STE/yrserv/datanew.phtml"}))

savannahpc, created = data_input.models.PluginConf.objects.get_or_create(plugin_name='savannah', plugin_class='savannah-tracking',
                                                                          defaults=dict(configuration={'credentials': {'pwd': 'ndovu4', 'uid': 'ste'}, 'host': '41.207.72.20'}))

skygistics, created = data_input.models.PluginConf.objects.get_or_create(plugin_name='ste-skygistics', plugin_class='skygistics',
                                                                          defaults=dict(configuration={'credentials': {'username': 'awtian', 'password': 'kenya'}, 'host': 'http://skyq1.skygistics.com'}))

DATASOURCE_PLUGIN_MAP = {'HTTP': awtpluginconf,
                         'SavannahTrackingAPI': savannahpc}


def find_existing_source(**kwargs):
    try:
        return observations.models.Source.objects.get(**kwargs)
    except Exception as e:
        print(e)
        pass

for t in tm_list:
    existing = find_existing_source(manufacturer_id=t.collar_id)

    if existing:
        print("%s already exists, so bailing." % (t.collar_id,))
        continue

    afields = ('active', 'datasource',
               'frequency', 'animal_id',
               'name', 'species', 'data_starts',
               'data_stops', 'date_off_or_removed', 'comments',
               'predicted_expiry', 'rgb', 'sex', 'gmt', 'utm')

    _ = t._asdict()
    avals = (_.get(k, None) for k in afields)
    additional = dict(zip(afields, (str(x) for x in avals)))

    source = observations.models.Source(id=uuid.uuid4(), source_type='tracking-device', model_name=t.collar_type, manufacturer_id=t.collar_id, additional=additional)
    source.save()


    # print("Chronofile %s for region %s" % (t.chronofile, region_map.get(t.chronofile, DEFAULT_REGION)))

    sub_additional = dict((k,v) for k,v in additional.items() if k in ('animal_id', 'species', 'name', 'sex', 'comments'))
    sub_additional.update(region_map.get(t.chronofile, DEFAULT_REGION)._asdict())
    subject = observations.models.Subject(id=uuid.uuid4(), name=t.name, subject_type='wildlife', additional=sub_additional)

    subject.save()

    ss = observations.models.SubjectSource(id=uuid.uuid4(), assigned_range=DEFAULT_DATE_RANGE, source=source, subject=subject, additional={'note':'added automatically.'})
    ss.save()

    _pc = DATASOURCE_PLUGIN_MAP.get(t.datasource)
    dip_source = data_input.models.PluginConfSource(id=uuid.uuid4(), plugin_conf=_pc, source=source, additional={"note":"Added automatically"})
    dip_source.save()

    print('Done %s' % dip_source)







