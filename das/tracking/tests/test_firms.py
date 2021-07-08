from unittest.mock import patch
from datetime import datetime, timedelta

import pytest
import pytz
import json

from django.test import TestCase


from tracking.models.firms import FirmsClient, FirmsPlugin


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
        expected = [(d.tm_year * 1000 + d.tm_yday, None), ]
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
        expected = [(todays_date.tm_year * 1000 +
                     todays_date.tm_yday, cached_headers), ]
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
            (yesterdays_date.tm_year * 1000 +
             yesterdays_date.tm_yday, cached_headers),
            (todays_date.tm_year * 1000 + todays_date.tm_yday, None),
        ]
        actual = f.calculate_valid_date_indexes(stored_headers=cached_headers)
        self.assertEqual(actual, expected)


def test_polyunion(firms_polygons):
    assert FirmsPlugin.union_geofilterfeatures(firms_polygons) is not None
