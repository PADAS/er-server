from unittest.mock import patch
from django.test import TestCase

from tracking.models.sirtrack import SirTrackClient


class TestSirtrack(TestCase):

    def setUp(self):
        pass

    def test_client_parsing_csv_data(self):
        '''
        Use mocks to allow testing the logic that parses the CSV data coming from SirTrack API.
        '''
        with patch('tracking.models.sirtrack.SirTrackClient.get_csv_dataset') as mock_get_csv_dataset:
            def fake_data_generator():
                yield from FAKE_CSV_DATA.split('\n')

            mock_get_csv_dataset.side_effect = [fake_data_generator(), ]

            with patch('tracking.models.sirtrack.SirTrackClient.login') as mock_login:
                mock_login.return_value = 'asdfasfd'

                with patch('tracking.models.sirtrack.SirTrackClient.get_projects') as mock_get_projects:
                    mock_get_projects.return_value = FAKE_PROJECT_DATA

                    with patch('tracking.models.sirtrack.SirTrackClient.get_csv_links') as mock_get_csv_links:
                        mock_get_csv_links.return_value = ['link1', ]

                        client = SirTrackClient()
                        for item in client.fetch_observations():
                            pass

                mock_login.assert_called_once()

            mock_get_csv_dataset.assert_called()


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
300234063441220,63441220 CF3 (Sanwild),2017-12-10,10:31:46,,,,,,,,3.46,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-10,16:48:20,,,,,,,,,,false,0,3,1,1
300234063441220,63441220 CF3 (Sanwild),2017-12-10,16:52:01,-24.05827,30.58769,35,1.2,6,104,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-10,17:00:13,-24.05838,30.58768,26,1.4,4,16,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-10,17:20:10,-24.05848,30.58714,31,3.0,4,13,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-10,18:48:20,,,,,,,,,,false,254,0,0,255
300234063441220,63441220 CF3 (Sanwild),2017-12-11,17:00:38,,,,,,,,3.46,,true,4,1,4,1
300234063441220,63441220 CF3 (Sanwild),2017-12-21,09:59:37,-15.00756,35.28098,41,1.0,8,33,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-21,10:00:52,-15.00757,35.28097,40,1.0,8,14,,3.5,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-21,21:00:12,-15.00683,35.28112,48,1.2,6,18,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-21,22:00:06,-15.00683,35.28112,44,1.2,6,13,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-24,20:00:09,-15.00735,35.28121,42,1.0,8,14,,3.44,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-24,21:00:11,-15.00737,35.28117,46,1.4,6,16,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-25,06:01:55,-15.00738,35.28081,42,1.0,7,119,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2017-12-26,00:00:39,-15.00726,35.28111,44,1.4,7,43,,3.46,,,,,,
300234063441220,63441220 CF3 (Sanwild),2018-06-06,04:00:09,-15.03632,35.28810,43,1.6,5,14,,,,,,,,
300234063441220,63441220 CF3 (Sanwild),2018-06-06,10:01:01,-15.02566,35.28833,36,1.2,6,71,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-27,04:00:32,-14.99053,35.28711,45,1.0,6,41,,3.44,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-27,10:00:37,-15.00000,35.29246,44,2.4,5,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-28,02:01:08,-14.98406,35.28900,45,1.2,6,77,,,,,,,,
300234064528520,2018-08-28,04:00:31,-14.96896,35.28009,46,0.8,8,41,,3.48,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-28,10:00:38,-14.97097,35.28729,40,1.6,6,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-29,02:00:31,-14.97147,35.28510,44,1.0,6,40,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-29,04:00:31,-14.97043,35.28637,45,1.2,5,40,,3.42,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-29,10:00:37,-14.97238,35.28775,43,1.0,7,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-30,02:00:32,-14.97357,35.28336,42,2.0,6,41,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-30,04:00:02,-14.97746,35.28191,43,1.4,6,12,,3.42,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-30,10:00:37,-14.97211,35.28661,42,1.0,7,42,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-31,02:00:31,-14.97087,35.28477,45,1.2,5,40,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-31,04:00:31,-14.97241,35.28620,45,0.8,8,40,,3.46,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-08-31,10:01:28,-14.97703,35.28864,34,1.2,6,94,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-01,02:00:31,-14.97088,35.28483,49,0.8,10,41,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-01,04:00:01,-14.97242,35.28736,43,1.0,7,11,,3.5,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-01,10:00:38,-14.97095,35.28711,43,1.0,7,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-02,02:00:31,-14.96913,35.28500,44,1.6,5,40,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-02,04:00:32,-14.97059,35.28684,47,1.0,6,41,,3.5,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-02,10:01:58,-14.97249,35.28828,35,1.6,5,124,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-09-03,02:00:37,-14.96067,35.29048,45,1.2,8,45,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-28,02:00:31,-14.97620,35.29827,45,1.2,7,41,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-28,04:00:01,-14.97943,35.29501,42,1.6,6,11,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-28,10:00:38,-14.97793,35.29341,41,2.0,5,44,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-29,02:00:31,-14.96131,35.30769,45,1.2,5,40,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-29,04:01:55,-14.97734,35.31263,47,1.6,5,12,,3.44,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-29,10:00:37,-14.97656,35.31181,38,1.6,6,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-30,02:00:37,-14.96204,35.31343,45,0.8,8,47,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-30,04:00:03,-14.95483,35.30531,44,1.4,6,13,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-30,10:01:10,-14.94792,35.29990,35,3.0,5,76,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-31,02:01:02,-14.96844,35.30206,46,1.4,5,71,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-31,04:01:42,-14.98801,35.30097,45,5.2,5,24,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-10-31,10:00:37,-14.98870,35.29852,41,1.4,5,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-11-01,02:00:38,-14.96873,35.28223,46,1.4,6,48,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-11-01,04:01:53,-14.97281,35.28497,44,1.2,5,37,,3.48,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-11-01,10:00:38,-14.97036,35.28819,36,1.0,8,43,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-11-02,02:00:31,-14.96863,35.28030,44,1.0,7,40,,,,,,,,
300234064528520,64528520 CF2 (Amakala),2018-11-02,04:00:02,-14.96865,35.28036,47,1.4,7,12,,,,,,,,'''

ENCODED_FAKE_CSV_DATA = [bytes(x, 'utf-8') for x in FAKE_CSV_DATA.split('\n')]
