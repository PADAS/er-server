__author__ = 'chris'


import http.client
import time, datetime

SAVANNAH = {
    'uid': 'ste', 'pwd': 'ndovu4'
}

def fetch_observations(collar_id, start_time, end_time=None):
    '''
    Fetch observations from Savannah data-source for a particular collar.
    :param collar_id: collar_id from trackingmaster record.
    :param start_time: unix timestamp for earliest data to fetch.
    :param end_time: <not used>
    :return: generator, yielding individual records.
    '''

    conn = http.client.HTTPConnection("41.207.72.20")

    payload = dict(uid=SAVANNAH['uid'], pwd=SAVANNAH['pwd'])
    payload.update(dict(unixtime=str(start_time), collar=collar_id))

    payload = ['='.join((k, v)) for k, v in payload.items()]
    payload = '&'.join(payload)

    headers = { 'accept': "*/*",
                'content-type': 'application/x-www-form-urlencoded'
                }

    conn.request("POST", "/savannah/get_data.asp", payload, headers)

    res = conn.getresponse()
    for line in res:
        yield line.decode('utf-8').strip()


SAMPLE_LINE='ST2010-1234,37.54771,0.5735083,6/26/2015 5:30:18 AM,0.47,0,,873'

SAMPLE_COLLARS = [
    {"collar_id": "ST2010-1352", "name": "Nutmeg"},
    {"collar_id": "ST2010-1234", "name": "Habiba"},
    {"collar_id": "ST2010-1316", "name": "Soutine"},
    {"collar_id": "ST2010-1351", "name": "Orchid"},
    {"collar_id": "ST2010-1230", "name": "Luna"},
    {"collar_id": "ST2010-1231", "name": "Salma"},
    {"collar_id": "ST2010-1354", "name": "Wendy"},
    {"collar_id": "ST2010-1356", "name": "Amity"},
    {"collar_id": "ST2010-1358", "name": "Tony"},
    {"collar_id": "ST2010-1359", "name": "Taurus"},
    {"collar_id": "ST2010-1360", "name": "Annabelle"},
]

from collections import namedtuple
from dateutil.parser import parse
Fix = namedtuple('Fix', ['collar_id', 'lon', 'lat', 'ts', 'speed', 'heading', 'temperature', 'height'])
def parse_line(s):
    dt = Fix._make(s.split(','))
    dt = dt._replace(ts=parse(dt.ts))
    return dt

def adhoc():
    for collar_id in (c['collar_id'] for c in SAMPLE_COLLARS):
        start_time = int(time.mktime(datetime.datetime(2015, 1, 1).timetuple()))

        obs_data = fetch_observations(collar_id, start_time)

        for line in obs_data:
            _ = parse_line(line)
            yield _



if __name__ == '__main__':
    import json
    from data import util
    for _ in adhoc():
        print (json.dumps(_._asdict(), cls=util.ExtendedJSONEncoder))
