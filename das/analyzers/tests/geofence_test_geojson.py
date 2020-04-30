from datetime import timedelta, datetime
import pytz
"""
I created this test module to ease curating test data as Geo Json, 
and in particular using http://geojson.io. I 
"""

def generate_timestamp_series(start_time, interval):
    while True:
        yield start_time
        start_time = start_time + interval


subject_track_for_double_fence_hop = {
      "type": "FeatureCollection",
      "crs": {
        "type": "name",
        "properties": {
          "name": "EPSG:4326"
        }
      },
      "features": [
        {
          "type": "Feature",
          "properties": {
            "name": "Subject Track",
            "stroke": "#cc0000",
            "stroke-width": 3,
            "stroke-opacity": 1
          },
          "geometry": {
            "type": "LineString",
            "coordinates": [
              [
                35.30688285827637,
                -1.2205917170101857
              ],
              [
                35.303449630737305,
                -1.223251863291398
              ],
              [
                35.30722618103027,
                -1.2262552510841573
              ],
              [
                35.311689376831055,
                -1.2251397074397885
              ],
              [
                35.31057357788086,
                -1.221278206625234
              ],
              [
                35.3085994720459,
                -1.220334283359355
              ],
              [
                35.31426429748535,
                -1.216644398325722
              ],
              [
                35.31683921813965,
                -1.214155868359561
              ],
              [
                35.317697525024414,
                -1.211495713104045
              ],
              [
                35.31374931335449,
                -1.2133835654902756
              ],
              [
                35.31177520751953,
                -1.2160437188887168
              ]
            ]
          }
        }
      ]
    }


SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP = subject_track_for_double_fence_hop['features'][0]['geometry']['coordinates']

ts_series = generate_timestamp_series(datetime.now(tz=pytz.utc) - timedelta(minutes=60)
                                      * len(SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP), timedelta(hours=1))


SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP = [
    {'longitude': x, 'latitude': y, 'recorded_at': next(ts_series).isoformat()}
                                 for x, y in SUBJECT_TRACK_FOR_DOUBLE_FENCE_HOP
]


