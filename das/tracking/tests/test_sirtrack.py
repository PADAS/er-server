from unittest.mock import patch
from django.test import TestCase

from tracking.models.sirtrack import SirTrackClient


class TestSirtrack(TestCase):

    def setUp(self):
        pass

    def generate_fake_feed(self):
        yield from FAKE_CSV_DATA

    def test_parse_csv(self):

        session_token = 'asdfoasdifuapsfuiaeopiufoaf'
        with patch('tracking.models.sirtrack.requests.post') as mock_post:

            mock_post.return_value.status_code = 200
            mock_post.return_value.headers = {
                'Set-Cookie': 'vosao_session={}'.format(session_token)}
            client = SirTrackClient()
            session_cookies = client.login()
            self.assertTrue('vosao_session' in session_cookies)

        with patch('tracking.models.sirtrack.requests.get') as mock_get:

            mock_get.return_value.status_code = 200
            mock_get.return_value.text = '{"projects": 1}'
            projects_data = client.get_projects(session_cookies)

            self.assertTrue('projects' in projects_data)

        with patch('tracking.models.sirtrack.SirTrackClient.get_kml') as mock_get_kml:

            mock_get_kml.return_value = FAKE_KML_DATA

            csv_links = client.get_csv_links(FAKE_PROJECT_DATA)
            csv_links = list(csv_links)
            print(csv_links)
            self.assertTrue(FAKE_KML_LINK in csv_links and len(csv_links) == 1)


FAKE_PROJECT_DATA = [
    {'geoJsonKey': 'foobar', 'name': 'fake', 'id': 1234}
]

FAKE_KML_LINK = 'https://tempuri.org/kmldata?key=$2a$10$DVNuP23MzlP6aAwVheI1.u'
FAKE_KML_DATA = '''<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:kml="http://www.opengis.net/kml/2.2" xmlns:gx="http://www.google.com/kml/ext/2.2" xmlns:xal="urn:oasis:names:tc:ciq:xsdschema:xAL:2.0">
  <kml:NetworkLink>
    <kml:name>Network link to project Liwonde NP_Cheetah.kmz</kml:name>
    <kml:description>It refreshes automatically every 15 minutes</kml:description>
    <kml:flyToView>1</kml:flyToView>
    <kml:Link>
      <kml:href>{link_href}</kml:href>
      <kml:refreshMode>onInterval</kml:refreshMode>
      <kml:refreshInterval>900.0</kml:refreshInterval>
      <kml:viewRefreshTime>0.0</kml:viewRefreshTime>
      <kml:viewBoundScale>0.0</kml:viewBoundScale>
    </kml:Link>
  </kml:NetworkLink>
</kml>
'''.format(link_href=FAKE_KML_LINK)

FAKE_KML_DATA = bytes(FAKE_KML_DATA, 'utf-8')


FAKE_CSV_DATA = '''Tag_ID,Tag_Name,UTC_Date,UTC_Time,Latitude,Longitude,CNR,HDOP,Sat Num,Time On,Temp (C),Min Volt,Activity,Event Active,Event SourceType,Event CurrentMode,Event ConfigurationNum,Event DataValue
300234064624450,64624450 CF01 (M Zebra),2016-11-23,22:04:02,,,,,,,,3.48,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,10:10:37,-24.29876,27.49209,43,1.2,6,42,,,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,10:20:07,-24.29879,27.49230,48,1.2,6,11,,,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,10:40:10,-24.29873,27.49232,49,1.2,6,14,,3.48,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,11:00:08,-24.29885,27.49226,47,1.6,5,12,,3.48,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,11:20:08,-24.29877,27.49229,48,1.4,5,13,,3.44,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,11:40:08,-24.29879,27.49227,51,1.6,5,13,,,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,12:00:08,-24.29887,27.49222,48,2.0,5,13,,,,,,,,
300234064624450,64624450 CF01 (M Zebra),2017-05-16,12:20:09,-24.29876,27.49231,47,2.2,5,14,,,,,,,,'''

FAKE_CSV_DATA = [bytes(x, 'utf-8') for x in FAKE_CSV_DATA.split('\n')]
