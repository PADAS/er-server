DATA_PAIRS = [
    ({
         "deviceId": "CDBB84",
         "time": 1569563495,
         "seqNumber": 172,
         "data": "80aed31501e97f8d3470e200",
         "reception": [{
             "id": "A9DC",
             "RSSI": -138.00,
             "SNR": 14.73
         }],
         "duplicate": "false"
     },
     {
         "deviceId": "CDBB84",
         "time": 1569563495,
         "seqNumber": 172,
         "computedLocation": {
             "lat": -11.847185868272895,
             "lng": 32.08352465774905,
             "radius": 60257,
             "source": 2,
             "status": 1
         }
     }),
    ({
         "deviceId": "CDBB5F",
         "time": 1572918753,
         "seqNumber": 214,
         "data": "80b03f8e01ea7ab8d0b0cb00",
         "reception": [{
             "id": "A9DC",
             "RSSI": -113.00,
             "SNR": 17.28
         }],
         "duplicate": "false"
     },
     {
         "deviceId": "CDBB5F",
         "time": 1572918753,
         "seqNumber": 214,
         "computedLocation": {
             "lat": -11.84564538358278,
             "lng": 32.082697269765156,
             "radius": 51217,
             "source": 2,
             "status": 1
         }
     }),
    ({
         "deviceId": "CE69E0",
         "time": 1572924693,
         "seqNumber": 179,
         "data": "80b0038901e9b31d9070e300",
         "reception": [{
             "id": "A9DC",
             "RSSI": -116.00,
             "SNR": 13.61
         }],
         "duplicate": "false"
     },
     {
         "deviceId": "CE69E0",
         "time": 1572924693,
         "seqNumber": 179,
         "computedLocation": {
             "lat": -11.84521334153998,
             "lng": 32.08320101161155,
             "radius": 49827,
             "source": 2,
             "status": 1
         }
     }),

    ({
         "deviceId": "CDBB65",
         "time": 1572924903,
         "seqNumber": 176,
         "data": "80ae24a301ea0e27d0b0dd00",
         "reception": [{
             "id": "A9DC",
             "RSSI": -142.00,
             "SNR": 11.38
         }],
         "duplicate": "false"
     },
     {
         "deviceId": "CDBB65",
         "time": 1572924903,
         "seqNumber": 176,
         "computedLocation": {
             "lat": -11.846398833705123,
             "lng": 32.08098662378488,
             "radius": 60360,
             "source": 2,
             "status": 1
         }
     }),
    ({
         "deviceId": "CE69E7",
         "time": 1572924956,
         "seqNumber": 176,
         "data": "80af2afd01eaab099070e500",
         "reception": [{
             "id": "A9DC",
             "RSSI": -142.00,
             "SNR": 10.42
         }],
         "duplicate": "false"
     },
     {
         "deviceId": "CE69E7",
         "time": 1572924956,
         "seqNumber": 176,
         "computedLocation": {
             "lat": -11.847343736631204,
             "lng": 32.08228097097307,
             "radius": 60231,
             "source": 2,
             "status": 1
         }
     }),
]



V2_DATA_PAIRS = [
    # ubi payload
    {
        'deviceId': '14159EB',
        'time': 1601024898,
        'seqNumber': 60,
        'data': '5506aacfdc12882347aef495',
        'reception': [{'id': '4F8A', 'RSSI': -144.0, 'SNR': 6.67}]
    },
    {
        'deviceId': '14159EB',
        'time': 1601024898,
        'seqNumber': 60,
        'computedLocation': {'lat': -21.54995963636364, 'lng': 29.91042409090909, 'radius': 23200, 'source': 2, 'status': 1}
    },

    # gps payload
    {
        'deviceId': '14159ED',
        'time': 1600971934,
        'seqNumber': 46,
        'data': '3588814542e701ca6d3f00',
        'reception': [{'id': '4F8A', 'RSSI': -127.0, 'SNR': 21.74}]
    },
    {
        'deviceId': '14159ED',
        'time': 1600971934,
        'seqNumber': 46,
        'computedLocation': {'lat': -21.552546121634077, 'lng': 30.101595780208857, 'radius': 21100, 'source': 2, 'status': 1}
    }

]
