from unittest.mock import patch
from datetime import datetime, timedelta
import pytz
import json

from django.test import TestCase


from tracking.models.firms import FirmsClient


class TestFirmsPluginHelpers(TestCase):

    def setUp(self):
        today = datetime.now(tz=pytz.utc).timetuple()
        today_dateindex = today.tm_year * 1000 + today.tm_yday
        self.CACHED_HEADERS_FOR_TODAY = f'''
        {{"date": "Sun, 14 Jan 2019 23:23:23 GMT", "etag": "\\\"01ba7a21effd51afe306afd6c2636ed4\\\"", 
        "server": "openresty", "connection": "keep-alive", "content-type": "text/plain;charset=UTF-8", 
        "accept-ranges": "bytes", "last-modified": "Sun, 14 Jan 2019 23:00:52 GMT", "content-length": "2897324",
         "x-frame-options": "SAMEORIGIN",
         "content-disposition": "attachment;  filename=VIIRS_I_Northern_and_Central_Africa_VNP14IMGTDL_NRT_{today_dateindex}.txt;", 
         "strict-transport-security": "max-age=31536000; includeSubDomains",
          "access-control-allow-credentials": "true"}}
        '''

        yesterday = (datetime.now(tz=pytz.utc) - timedelta(days=1)).timetuple()
        yesterday_dateindex = yesterday.tm_year * 1000 + yesterday.tm_yday
        self.CACHED_HEADERS_FOR_YESTERDAY = f'''
        {{"date": "Sun, 14 Jan 2019 23:23:23 GMT", "etag": "\\\"01ba7a21effd51afe306afd6c2636ed4\\\"", 
        "server": "openresty", "connection": "keep-alive", "content-type": "text/plain;charset=UTF-8", 
        "accept-ranges": "bytes", "last-modified": "Sun, 14 Jan 2019 23:00:52 GMT", "content-length": "2897324",
         "x-frame-options": "SAMEORIGIN",
         "content-disposition": "attachment;  filename=VIIRS_I_Northern_and_Central_Africa_VNP14IMGTDL_NRT_{yesterday_dateindex}.txt;", 
         "strict-transport-security": "max-age=31536000; includeSubDomains",
          "access-control-allow-credentials": "true"}}
        '''

    def test_calculate_date_indexes(self):

        f = FirmsClient()

        d = datetime.now(tz=pytz.utc).timetuple()
        expected = [(d.tm_year * 1000 + d.tm_yday, None),]
        actual = f.calculate_valid_date_indexes()
        self.assertEqual(actual, expected)


    def test_calculate_date_indexes_from_cached_headers_for_today(self):

        f = FirmsClient()

        cached_headers = json.loads(self.CACHED_HEADERS_FOR_TODAY)

        todays_date = datetime.now(tz=pytz.utc)
        yesterdays_date = todays_date - timedelta(days=1)

        todays_date = todays_date.timetuple()
        yesterdays_date = yesterdays_date.timetuple()

        # Expecting a list with one item for today's date-index value.
        expected = [(todays_date.tm_year * 1000 + todays_date.tm_yday, cached_headers),]
        actual = f.calculate_valid_date_indexes(stored_headers=cached_headers)
        self.assertEqual(actual, expected)


    def test_calculate_date_indexes_from_cached_headers_for_yesterday(self):
        f = FirmsClient()

        cached_headers = json.loads(self.CACHED_HEADERS_FOR_YESTERDAY)

        todays_date = datetime.now(tz=pytz.utc)
        yesterdays_date = todays_date - timedelta(days=1)

        todays_date = todays_date.timetuple()
        yesterdays_date = yesterdays_date.timetuple()

        # Expecting a list with two items, for yesterday's and today's date index values.
        expected = [
            (yesterdays_date.tm_year * 1000 + yesterdays_date.tm_yday, cached_headers),
            (todays_date.tm_year * 1000 + todays_date.tm_yday, None),
                   ]
        actual = f.calculate_valid_date_indexes(stored_headers=cached_headers)
        self.assertEqual(actual, expected)


FAKE_CSV_DATA = '''latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,confidence,version,bright_ti5,frp,daynight
28.90925,20.96741,303.5,0.44,0.46,2019-01-14,00:42,N,nominal,1.0NRT,276,1.1,N
28.91343,20.96855,308.9,0.44,0.46,2019-01-14,00:42,N,nominal,1.0NRT,276.3,1.1,N
29.22948,19.69459,327.5,0.55,0.43,2019-01-14,00:42,N,nominal,1.0NRT,276,13.1,N
29.23335,19.6956,327.8,0.55,0.43,2019-01-14,00:42,N,nominal,1.0NRT,276.3,6.7,N
31.00086,8.01957,342.3,0.45,0.47,2019-01-14,00:42,N,nominal,1.0NRT,274,7.8,N
28.69769,22.37538,301.1,0.53,0.5,2019-01-14,00:42,N,nominal,1.0NRT,274.9,1.6,N
29.03839,20.78778,336.1,0.42,0.46,2019-01-14,00:42,N,nominal,1.0NRT,277.6,1.9,N
31.01192,8.16369,314.6,0.44,0.46,2019-01-14,00:42,N,nominal,1.0NRT,270.5,2.5,N
31.01095,8.17289,335.5,0.44,0.46,2019-01-14,00:42,N,nominal,1.0NRT,275.1,5.7,N
'''


