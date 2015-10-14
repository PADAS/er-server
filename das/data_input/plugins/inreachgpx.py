__author__ = 'chris'
import logging
from dateutil.parser import parse as parse_date
import xml.etree.ElementTree as ET
from observations.models import Observation, Source

logger = logging.getLogger(__name__)

NS = '{http://www.topografix.com/GPX/1/1}'
def tag(t):
    return '%s%s' % (NS, t)


def process_tracks(tracks, fn=None):
    def _transform(_):
        lat = float(_.get('lat'))
        lon = float(_.get('lon'))
        ts = _.findtext(tag('time'))
        ts = parse_date(ts)
        ele = float(_.findtext(tag('ele')))
        desc = _.findtext(tag('desc'))

        # Trasform to look like the dicts we get from Inreach API.
        return dict(lat=lat, lon=lon, ts=ts, Altitude=ele, TextMessage=desc)

    for _ in tracks:
        t = _transform(_)

        print(t) if not fn else fn(t)

def process_gpx(root, fn=None):
    '''
    Process an entire gpx file, find and process each trk element.
    :param root:
    :return:
    '''

    def _handletrack(t):
        fn(t)

    for trk in root.findall(tag('trk')):
        _name = trk.find(tag('name'))
        _desc = trk.find(tag('desc'))
        logger.debug('Processing trk for name: %s, desc: %s' % (_name.text, _desc.text))

        for trkseg in generate_trkseg(trk):
            tracks = list(generate_track_list(trkseg))
            process_tracks(tracks, fn=_handletrack)

def generate_trkseg(trk):
        yield from trk.findall(tag('trkseg'))

def generate_track_list(trkseg):
    for ch in trkseg.findall(tag('trkpt')):
        yield ch


# def config_logging():
#     logger.setLevel(logging.DEBUG)
#     ch = logging.StreamHandler()
#     formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
#     ch.setFormatter(formatter)
#     logger.addHandler(ch)
#
# config_logging()

def process_gpx_file(filename, source_id):
    tree = ET.parse('/Users/chris/Desktop/explore.gpx')
    root = tree.getroot()

    if root.tag != '{http://www.topografix.com/GPX/1/1}gpx':
        raise ValueError("I'm expecting a gpx file, but this one starts with %s" % (root.tag,))

    try:
        source = Source.objects.get(id=source_id)
    except Exception:
        raise ValueError("I can't find source with id = %s" % (source_id,))

    def insertObservation(o):
        Observation.objects.add_observation(source, o)

    process_gpx(root, fn=insertObservation)




