from datetime import datetime, timedelta

import pytz

EQUATOR_CRISS_CROSS_TRACK = [
    {
        "longitude": 37.50,
        "recorded_at": "2016-01-01 00:00:00",
        "latitude": 0.1
    },
    {
        "longitude": 37.52,
        "recorded_at": "2016-01-01 12:00:00",
        "latitude": -0.1
    },
    {
        "longitude": 37.55,
        "recorded_at": "2016-01-02 00:00:00",
        "latitude": 0.1
    },
]

OLCHODA_TRACK = [
    {
        "longitude": 35.3144,
        "latitude": -1.232583,
        "recorded_at": "2017-07-25T06:00:13+00:00"
    },
    {
        "longitude": 35.31327,
        "latitude": -1.234058,
        "recorded_at": "2017-07-25T06:30:20+00:00"
    },
    {
        "longitude": 35.3131,
        "latitude": -1.234298,
        "recorded_at": "2017-07-25T07:00:24+00:00"
    },
    {
        "longitude": 35.31177,
        "latitude": -1.23477,
        "recorded_at": "2017-07-25T07:30:31+00:00"
    },
    {
        "longitude": 35.31173,
        "latitude": -1.23495,
        "recorded_at": "2017-07-25T08:00:13+00:00"
    },
    {
        "longitude": 35.31142,
        "latitude": -1.234977,
        "recorded_at": "2017-07-25T08:30:22+00:00"
    },
    {
        "longitude": 35.31142,
        "latitude": -1.234952,
        "recorded_at": "2017-07-25T09:00:21+00:00"
    },
    {
        "longitude": 35.31141,
        "latitude": -1.234985,
        "recorded_at": "2017-07-25T09:30:23+00:00"
    },
    {
        "longitude": 35.30947,
        "latitude": -1.236385,
        "recorded_at": "2017-07-25T10:00:27+00:00"
    },
    {
        "longitude": 35.30937,
        "latitude": -1.236318,
        "recorded_at": "2017-07-25T10:30:22+00:00"
    },
    {
        "longitude": 35.30828,
        "latitude": -1.237117,
        "recorded_at": "2017-07-25T11:00:25+00:00"
    },
    {
        "longitude": 35.3083,
        "latitude": -1.237158,
        "recorded_at": "2017-07-25T11:30:25+00:00"
    },
    {
        "longitude": 35.3075,
        "latitude": -1.237168,
        "recorded_at": "2017-07-25T12:00:41+00:00"
    },
    {
        "longitude": 35.30787,
        "latitude": -1.2375,
        "recorded_at": "2017-07-25T12:30:50+00:00"
    },
    {
        "longitude": 35.30799,
        "latitude": -1.237427,
        "recorded_at": "2017-07-25T13:00:19+00:00"
    },
    {
        "longitude": 35.30833,
        "latitude": -1.237515,
        "recorded_at": "2017-07-25T13:30:13+00:00"
    },
    {
        "longitude": 35.30907,
        "latitude": -1.236992,
        "recorded_at": "2017-07-25T14:00:15+00:00"
    },
    {
        "longitude": 35.31158,
        "latitude": -1.235433,
        "recorded_at": "2017-07-25T14:30:15+00:00"
    },
    {
        "longitude": 35.31388,
        "latitude": -1.232857,
        "recorded_at": "2017-07-25T15:00:19+00:00"
    },
    {
        "longitude": 35.316,
        "latitude": -1.231265,
        "recorded_at": "2017-07-25T15:30:24+00:00"
    },
    {
        "longitude": 35.31751,
        "latitude": -1.229603,
        "recorded_at": "2017-07-25T16:00:21+00:00"
    },
    {
        "longitude": 35.32063,
        "latitude": -1.224525,
        "recorded_at": "2017-07-25T16:30:20+00:00"
    },
    {
        "longitude": 35.32038,
        "latitude": -1.218092,
        "recorded_at": "2017-07-25T17:00:27+00:00"
    },
    {
        "longitude": 35.31777,
        "latitude": -1.214073,
        "recorded_at": "2017-07-25T17:30:29+00:00"
    },
    {
        "longitude": 35.3151,
        "latitude": -1.20428,
        "recorded_at": "2017-07-25T18:00:24+00:00"
    },
    {
        "longitude": 35.31466,
        "latitude": -1.203903,
        "recorded_at": "2017-07-25T18:30:41+00:00"
    },
    {
        "longitude": 35.31459,
        "latitude": -1.203885,
        "recorded_at": "2017-07-25T19:00:19+00:00"
    },
    {
        "longitude": 35.3144,
        "latitude": -1.204475,
        "recorded_at": "2017-07-25T19:30:25+00:00"
    },
    {
        "longitude": 35.31266,
        "latitude": -1.206733,
        "recorded_at": "2017-07-25T20:00:25+00:00"
    },
    {
        "longitude": 35.31369,
        "latitude": -1.204202,
        "recorded_at": "2017-07-25T20:30:24+00:00"
    },
    {
        "longitude": 35.31461,
        "latitude": -1.203878,
        "recorded_at": "2017-07-25T21:00:17+00:00"
    },
    {
        "longitude": 35.3127,
        "latitude": -1.201242,
        "recorded_at": "2017-07-25T21:30:16+00:00"
    },
    {
        "longitude": 35.31152,
        "latitude": -1.201912,
        "recorded_at": "2017-07-25T22:00:24+00:00"
    },
    {
        "longitude": 35.30999,
        "latitude": -1.202253,
        "recorded_at": "2017-07-25T22:30:23+00:00"
    },
    {
        "longitude": 35.31082,
        "latitude": -1.20466,
        "recorded_at": "2017-07-25T23:00:27+00:00"
    },
    {
        "longitude": 35.3116,
        "latitude": -1.204933,
        "recorded_at": "2017-07-25T23:30:32+00:00"
    },
    {
        "longitude": 35.31269,
        "latitude": -1.20678,
        "recorded_at": "2017-07-26T00:00:13+00:00"
    },
    {
        "longitude": 35.31127,
        "latitude": -1.208292,
        "recorded_at": "2017-07-26T00:30:17+00:00"
    },
    {
        "longitude": 35.31029,
        "latitude": -1.202573,
        "recorded_at": "2017-07-26T01:00:15+00:00"
    },
    {
        "longitude": 35.31003,
        "latitude": -1.202297,
        "recorded_at": "2017-07-26T01:30:19+00:00"
    },
    {
        "longitude": 35.31017,
        "latitude": -1.201818,
        "recorded_at": "2017-07-26T02:00:19+00:00"
    },
    {
        "longitude": 35.31163,
        "latitude": -1.202573,
        "recorded_at": "2017-07-26T02:30:27+00:00"
    },
    {
        "longitude": 35.31387,
        "latitude": -1.203637,
        "recorded_at": "2017-07-26T03:00:26+00:00"
    },
    {
        "longitude": 35.31401,
        "latitude": -1.2036,
        "recorded_at": "2017-07-26T03:30:27+00:00"
    },
    {
        "longitude": 35.32084,
        "latitude": -1.200803,
        "recorded_at": "2017-07-26T04:00:24+00:00"
    },
    {
        "longitude": 35.32338,
        "latitude": -1.199012,
        "recorded_at": "2017-07-26T04:30:24+00:00"
    },
    {
        "longitude": 35.32907,
        "latitude": -1.19252,
        "recorded_at": "2017-07-26T05:00:41+00:00"
    },
    {
        "longitude": 35.33263,
        "latitude": -1.188183,
        "recorded_at": "2017-07-26T05:30:24+00:00"
    }
]

JOLIE_TRACK = [
    {
        "recorded_at": "2017-11-01T03:00:33+00:00",
        "latitude": -1.96511666666667,
        "longitude": 10.4426666666667
    },
    {
        "recorded_at": "2017-11-01T04:00:32+00:00",
        "latitude": -1.96511666666667,
        "longitude": 10.44265
    },
    {
        "recorded_at": "2017-11-01T05:01:07+00:00",
        "latitude": -1.9642,
        "longitude": 10.4425333333333
    },
    {
        "recorded_at": "2017-11-01T06:01:06+00:00",
        "latitude": -1.96301666666667,
        "longitude": 10.4421666666667
    },
    {
        "recorded_at": "2017-11-01T07:00:34+00:00",
        "latitude": -1.96213333333333,
        "longitude": 10.4437833333333
    },
    {
        "recorded_at": "2017-11-01T08:00:33+00:00",
        "latitude": -1.96238333333333,
        "longitude": 10.4463
    },
    {
        "recorded_at": "2017-11-01T09:02:04+00:00",
        "latitude": -1.96336666666667,
        "longitude": 10.45215
    },
    {
        "recorded_at": "2017-11-01T10:01:31+00:00",
        "latitude": -1.96536666666667,
        "longitude": 10.4540166666667
    },
    {
        "recorded_at": "2017-11-01T11:01:06+00:00",
        "latitude": -1.96806666666667,
        "longitude": 10.4555666666667
    },
    {
        "recorded_at": "2017-11-01T12:00:57+00:00",
        "latitude": -1.97021666666667,
        "longitude": 10.45765
    },
    {
        "recorded_at": "2017-11-01T13:03:01+00:00",
        "latitude": -1.96803333333333,
        "longitude": 10.4567333333333
    },
    {
        "recorded_at": "2017-11-01T14:00:32+00:00",
        "latitude": -1.96761666666667,
        "longitude": 10.4515
    },
    {
        "recorded_at": "2017-11-01T15:00:32+00:00",
        "latitude": -1.96686666666667,
        "longitude": 10.4496333333333
    },
    {
        "recorded_at": "2017-11-01T16:00:32+00:00",
        "latitude": -1.96738333333333,
        "longitude": 10.4467666666667
    },
    {
        "recorded_at": "2017-11-01T17:00:34+00:00",
        "latitude": -1.96715,
        "longitude": 10.4449
    },
    {
        "recorded_at": "2017-11-01T18:01:58+00:00",
        "latitude": -1.96771666666667,
        "longitude": 10.4438
    },
    {
        "recorded_at": "2017-11-01T19:00:32+00:00",
        "latitude": -1.96463333333333,
        "longitude": 10.4411
    },
    {
        "recorded_at": "2017-11-01T20:00:32+00:00",
        "latitude": -1.96455,
        "longitude": 10.43875
    },
    {
        "recorded_at": "2017-11-01T21:02:28+00:00",
        "latitude": -1.963,
        "longitude": 10.4389833333333
    },
    {
        "recorded_at": "2017-11-01T22:01:03+00:00",
        "latitude": -1.96263333333333,
        "longitude": 10.44115
    },
    {
        "recorded_at": "2017-11-01T23:00:32+00:00",
        "latitude": -1.96273333333333,
        "longitude": 10.4412166666667
    },
    {
        "recorded_at": "2017-11-02T00:00:55+00:00",
        "latitude": -1.96113333333333,
        "longitude": 10.4427333333333
    },
    {
        "recorded_at": "2017-11-02T01:02:31+00:00",
        "latitude": -1.95996666666667,
        "longitude": 10.4424333333333
    },
    {
        "recorded_at": "2017-11-02T02:01:58+00:00",
        "latitude": -1.9603,
        "longitude": 10.4423333333333
    },
    {
        "recorded_at": "2017-11-02T04:01:03+00:00",
        "latitude": -1.95361666666667,
        "longitude": 10.4452666666667
    },
    {
        "recorded_at": "2017-11-02T05:01:21+00:00",
        "latitude": -1.95015,
        "longitude": 10.44465
    },
    {
        "recorded_at": "2017-11-02T06:00:57+00:00",
        "latitude": -1.95063333333333,
        "longitude": 10.4439833333333
    },
    {
        "recorded_at": "2017-11-02T07:00:57+00:00",
        "latitude": -1.95086666666667,
        "longitude": 10.44405
    },
    {
        "recorded_at": "2017-11-02T08:01:01+00:00",
        "latitude": -1.95176666666667,
        "longitude": 10.4444333333333
    },
    {
        "recorded_at": "2017-11-02T09:01:05+00:00",
        "latitude": -1.95125,
        "longitude": 10.44945
    },
    {
        "recorded_at": "2017-11-02T10:02:37+00:00",
        "latitude": -1.95948333333333,
        "longitude": 10.4543833333333
    },
    {
        "recorded_at": "2017-11-02T11:02:27+00:00",
        "latitude": -1.9664,
        "longitude": 10.4565
    },
    {
        "recorded_at": "2017-11-02T13:01:45+00:00",
        "latitude": -1.96786666666667,
        "longitude": 10.4524166666667
    },
    {
        "recorded_at": "2017-11-02T14:00:32+00:00",
        "latitude": -1.96681666666667,
        "longitude": 10.451
    }
]

DAS4022_TRACKS = [
    {
        "recorded_at": "2019-06-09T03:30:21+00:00",
        "latitude": -2.007108,
        "longitude": 34.64523
    },
    {
        "recorded_at": "2019-06-09T03:00:19+00:00",
        "latitude": -2.005027,
        "longitude": 34.6455
    },
    {
        "recorded_at": "2019-06-09T02:30:14+00:00",
        "latitude": -2.002923,
        "longitude": 34.64616
    },
    {
        "recorded_at": "2019-06-09T02:00:24+00:00",
        "latitude": -2.001173,
        "longitude": 34.64214
    },
    {
        "recorded_at": "2019-06-09T01:30:24+00:00",
        "latitude": -1.999058,
        "longitude": 34.64088
    },
    {
        "recorded_at": "2019-06-09T01:00:13+00:00",
        "latitude": -1.997177,
        "longitude": 34.64019
    },
    {
        "recorded_at": "2019-06-09T00:30:14+00:00",
        "latitude": -1.992731,
        "longitude": 34.64339
    },
    {
        "recorded_at": "2019-06-09T00:00:12+00:00",
        "latitude": -1.990911,
        "longitude": 34.64458
    },
    {
        "recorded_at": "2019-06-08T23:30:13+00:00",
        "latitude": -1.990348,
        "longitude": 34.64462
    },
    {
        "recorded_at": "2019-06-08T22:30:15+00:00",
        "latitude": -1.990396,
        "longitude": 34.64227
    },
    {
        "recorded_at": "2019-06-08T22:00:12+00:00",
        "latitude": -1.988877,
        "longitude": 34.64116
    },
    {
        "recorded_at": "2019-06-08T21:30:29+00:00",
        "latitude": -1.987667,
        "longitude": 34.64044
    },
    {
        "recorded_at": "2019-06-08T21:00:26+00:00",
        "latitude": -1.985083,
        "longitude": 34.64067
    },
    {
        "recorded_at": "2019-06-08T20:30:16+00:00",
        "latitude": -1.984885,
        "longitude": 34.64125
    },
    {
        "recorded_at": "2019-06-08T20:00:13+00:00",
        "latitude": -1.984962,
        "longitude": 34.64139
    },
    {
        "recorded_at": "2019-06-08T19:30:13+00:00",
        "latitude": -1.98488,
        "longitude": 34.64152
    },
    {
        "recorded_at": "2019-06-08T19:00:12+00:00",
        "latitude": -1.985043,
        "longitude": 34.6417
    },
    {
        "recorded_at": "2019-06-08T18:30:14+00:00",
        "latitude": -1.990115,
        "longitude": 34.64649
    },
    {
        "recorded_at": "2019-06-08T18:00:12+00:00",
        "latitude": -1.990798,
        "longitude": 34.64146
    },
    {
        "recorded_at": "2019-06-08T17:30:24+00:00",
        "latitude": -1.998143,
        "longitude": 34.64767
    },
    {
        "recorded_at": "2019-06-08T17:00:10+00:00",
        "latitude": -2.000495,
        "longitude": 34.64764
    },
    {
        "recorded_at": "2019-06-08T16:31:09+00:00",
        "latitude": -2.002382,
        "longitude": 34.64752
    },
    {
        "recorded_at": "2019-06-08T16:00:12+00:00",
        "latitude": -2.004187,
        "longitude": 34.64683
    },
    {
        "recorded_at": "2019-06-08T15:30:22+00:00",
        "latitude": -2.008941,
        "longitude": 34.64393
    },
    {
        "recorded_at": "2019-06-08T15:00:12+00:00",
        "latitude": -2.008311,
        "longitude": 34.63998
    },
    {
        "recorded_at": "2019-06-08T14:30:15+00:00",
        "latitude": -2.008008,
        "longitude": 34.6351
    },
    {
        "recorded_at": "2019-06-08T14:00:12+00:00",
        "latitude": -2.006057,
        "longitude": 34.62934
    },
    {
        "recorded_at": "2019-06-08T13:30:13+00:00",
        "latitude": -2.001542,
        "longitude": 34.62659
    },
    {
        "recorded_at": "2019-06-08T13:00:12+00:00",
        "latitude": -1.998768,
        "longitude": 34.62413
    },
    {
        "recorded_at": "2019-06-08T12:30:14+00:00",
        "latitude": -1.997308,
        "longitude": 34.62401
    },
    {
        "recorded_at": "2019-06-08T12:00:41+00:00",
        "latitude": -1.996412,
        "longitude": 34.62281
    },
    {
        "recorded_at": "2019-06-08T11:30:13+00:00",
        "latitude": -1.995647,
        "longitude": 34.62289
    },
    {
        "recorded_at": "2019-06-08T11:00:22+00:00",
        "latitude": -1.995632,
        "longitude": 34.62255
    },
    {
        "recorded_at": "2019-06-08T10:30:20+00:00",
        "latitude": -1.995043,
        "longitude": 34.62116
    },
    {
        "recorded_at": "2019-06-08T10:00:41+00:00",
        "latitude": -1.9951,
        "longitude": 34.62102
    },
    {
        "recorded_at": "2019-06-08T09:30:13+00:00",
        "latitude": -1.995102,
        "longitude": 34.62095
    },
    {
        "recorded_at": "2019-06-08T09:00:24+00:00",
        "latitude": -1.995136,
        "longitude": 34.62092
    },
    {
        "recorded_at": "2019-06-08T08:30:12+00:00",
        "latitude": -1.9952,
        "longitude": 34.62089
    },
    {
        "recorded_at": "2019-06-08T08:00:13+00:00",
        "latitude": -1.995612,
        "longitude": 34.62207
    },

]
KIMBIZWA_TRACKS = [
    {
        "recorded_at": "2019-06-09T23:30:35+00:00",
        "latitude": -1.90567,
        "longitude": 34.77718
    },
    {
        "recorded_at": "2019-06-09T23:00:28+00:00",
        "latitude": -1.913592,
        "longitude": 34.77566
    },
    {
        "recorded_at": "2019-06-09T22:30:23+00:00",
        "latitude": -1.92196,
        "longitude": 34.76801
    },
    {
        "recorded_at": "2019-06-09T22:00:14+00:00",
        "latitude": -1.923227,
        "longitude": 34.75812
    },
    {
        "recorded_at": "2019-06-09T21:30:23+00:00",
        "latitude": -1.923735,
        "longitude": 34.75824
    },
    {
        "recorded_at": "2019-06-09T21:00:14+00:00",
        "latitude": -1.930676,
        "longitude": 34.75423
    },
    {
        "recorded_at": "2019-06-09T20:30:23+00:00",
        "latitude": -1.935295,
        "longitude": 34.7422
    },
    {
        "recorded_at": "2019-06-09T20:00:23+00:00",
        "latitude": -1.935616,
        "longitude": 34.73832
    },
    {
        "recorded_at": "2019-06-09T19:30:12+00:00",
        "latitude": -1.9351,
        "longitude": 34.73817
    },
    {
        "recorded_at": "2019-06-09T19:00:13+00:00",
        "latitude": -1.935865,
        "longitude": 34.73355
    },
    {
        "recorded_at": "2019-06-09T18:30:41+00:00",
        "latitude": -1.93731,
        "longitude": 34.72545
    },
    {
        "recorded_at": "2019-06-09T18:00:23+00:00",
        "latitude": -1.939025,
        "longitude": 34.71878
    },
    {
        "recorded_at": "2019-06-09T17:30:15+00:00",
        "latitude": -1.942017,
        "longitude": 34.71814
    },
    {
        "recorded_at": "2019-06-09T17:00:19+00:00",
        "latitude": -1.943245,
        "longitude": 34.71973
    },
    {
        "recorded_at": "2019-06-09T16:30:16+00:00",
        "latitude": -1.951235,
        "longitude": 34.71626
    },
    {
        "recorded_at": "2019-06-09T16:00:14+00:00",
        "latitude": -1.957665,
        "longitude": 34.71315
    },
    {
        "recorded_at": "2019-06-09T15:30:12+00:00",
        "latitude": -1.962335,
        "longitude": 34.7095
    },
    {
        "recorded_at": "2019-06-09T15:00:13+00:00",
        "latitude": -1.966065,
        "longitude": 34.70816
    },
    {
        "recorded_at": "2019-06-09T14:31:05+00:00",
        "latitude": -1.968475,
        "longitude": 34.70975
    },
    {
        "recorded_at": "2019-06-09T14:00:12+00:00",
        "latitude": -1.970777,
        "longitude": 34.7058
    },
    {
        "recorded_at": "2019-06-09T13:30:26+00:00",
        "latitude": -1.9733,
        "longitude": 34.7047
    },
    {
        "recorded_at": "2019-06-09T13:00:25+00:00",
        "latitude": -1.975283,
        "longitude": 34.70509
    },
    {
        "recorded_at": "2019-06-09T12:30:24+00:00",
        "latitude": -1.975223,
        "longitude": 34.70517
    },
    {
        "recorded_at": "2019-06-09T12:00:13+00:00",
        "latitude": -1.975485,
        "longitude": 34.70518
    },
    {
        "recorded_at": "2019-06-09T11:30:16+00:00",
        "latitude": -1.975555,
        "longitude": 34.7051
    },
    {
        "recorded_at": "2019-06-09T11:00:13+00:00",
        "latitude": -1.976233,
        "longitude": 34.70511
    },
    {
        "recorded_at": "2019-06-09T10:30:12+00:00",
        "latitude": -1.976745,
        "longitude": 34.70535
    },
    {
        "recorded_at": "2019-06-09T10:00:14+00:00",
        "latitude": -1.98182,
        "longitude": 34.70472
    },
    {
        "recorded_at": "2019-06-09T09:30:12+00:00",
        "latitude": -1.985977,
        "longitude": 34.70376
    },
    {
        "recorded_at": "2019-06-09T09:00:41+00:00",
        "latitude": -1.986947,
        "longitude": 34.7023
    },
    {
        "recorded_at": "2019-06-09T08:30:12+00:00",
        "latitude": -1.98881,
        "longitude": 34.69659
    },
    {
        "recorded_at": "2019-06-09T08:00:19+00:00",
        "latitude": -1.99451,
        "longitude": 34.68947
    },
    {
        "recorded_at": "2019-06-09T07:30:11+00:00",
        "latitude": -2.003475,
        "longitude": 34.68517
    },
    {
        "recorded_at": "2019-06-09T07:00:14+00:00",
        "latitude": -2.01385,
        "longitude": 34.6796
    },
    {
        "recorded_at": "2019-06-09T06:30:12+00:00",
        "latitude": -2.016098,
        "longitude": 34.66854
    },
    {
        "recorded_at": "2019-06-09T06:00:15+00:00",
        "latitude": -2.018013,
        "longitude": 34.66372
    },
    {
        "recorded_at": "2019-06-09T05:30:13+00:00",
        "latitude": -2.014465,
        "longitude": 34.65578
    },
    {
        "recorded_at": "2019-06-09T05:00:13+00:00",
        "latitude": -2.010645,
        "longitude": 34.6507
    },
    {
        "recorded_at": "2019-06-09T04:30:18+00:00",
        "latitude": -2.01056,
        "longitude": 34.65059
    },
    {
        "recorded_at": "2019-06-09T04:00:41+00:00",
        "latitude": -2.010583,
        "longitude": 34.65063
    },

    {
        "recorded_at": "2019-06-09T03:30:21+00:00",
        "latitude": -2.007108,
        "longitude": 34.64523
    },
    {
        "recorded_at": "2019-06-09T03:00:19+00:00",
        "latitude": -2.005027,
        "longitude": 34.6455
    },
    {
        "recorded_at": "2019-06-09T02:30:14+00:00",
        "latitude": -2.002923,
        "longitude": 34.64616
    },
    {
        "recorded_at": "2019-06-09T02:00:24+00:00",
        "latitude": -2.001173,
        "longitude": 34.64214
    },
    {
        "recorded_at": "2019-06-09T01:30:24+00:00",
        "latitude": -1.999058,
        "longitude": 34.64088
    },
    {
        "recorded_at": "2019-06-09T01:00:13+00:00",
        "latitude": -1.997177,
        "longitude": 34.64019
    },
    {
        "recorded_at": "2019-06-09T00:30:14+00:00",
        "latitude": -1.992731,
        "longitude": 34.64339
    },
    {
        "recorded_at": "2019-06-09T00:00:12+00:00",
        "latitude": -1.990911,
        "longitude": 34.64458
    },
    {
        "recorded_at": "2019-06-08T23:30:13+00:00",
        "latitude": -1.990348,
        "longitude": 34.64462
    },
    {
        "recorded_at": "2019-06-08T22:30:15+00:00",
        "latitude": -1.990396,
        "longitude": 34.64227
    },
    {
        "recorded_at": "2019-06-08T22:00:12+00:00",
        "latitude": -1.988877,
        "longitude": 34.64116
    },
    {
        "recorded_at": "2019-06-08T21:30:29+00:00",
        "latitude": -1.987667,
        "longitude": 34.64044
    },
    {
        "recorded_at": "2019-06-08T21:00:26+00:00",
        "latitude": -1.985083,
        "longitude": 34.64067
    },
    {
        "recorded_at": "2019-06-08T20:30:16+00:00",
        "latitude": -1.984885,
        "longitude": 34.64125
    },
    {
        "recorded_at": "2019-06-08T20:00:13+00:00",
        "latitude": -1.984962,
        "longitude": 34.64139
    },
    {
        "recorded_at": "2019-06-08T19:30:13+00:00",
        "latitude": -1.98488,
        "longitude": 34.64152
    },
    {
        "recorded_at": "2019-06-08T19:00:12+00:00",
        "latitude": -1.985043,
        "longitude": 34.6417
    },
    {
        "recorded_at": "2019-06-08T18:30:14+00:00",
        "latitude": -1.990115,
        "longitude": 34.64649
    },
    {
        "recorded_at": "2019-06-08T18:00:12+00:00",
        "latitude": -1.990798,
        "longitude": 34.64146
    },
    {
        "recorded_at": "2019-06-08T17:30:24+00:00",
        "latitude": -1.998143,
        "longitude": 34.64767
    },
    {
        "recorded_at": "2019-06-08T17:00:10+00:00",
        "latitude": -2.000495,
        "longitude": 34.64764
    },
    {
        "recorded_at": "2019-06-08T16:31:09+00:00",
        "latitude": -2.002382,
        "longitude": 34.64752
    },
    {
        "recorded_at": "2019-06-08T16:00:12+00:00",
        "latitude": -2.004187,
        "longitude": 34.64683
    },
    {
        "recorded_at": "2019-06-08T15:30:22+00:00",
        "latitude": -2.008941,
        "longitude": 34.64393
    },
    {
        "recorded_at": "2019-06-08T15:00:12+00:00",
        "latitude": -2.008311,
        "longitude": 34.63998
    },
    {
        "recorded_at": "2019-06-08T14:30:15+00:00",
        "latitude": -2.008008,
        "longitude": 34.6351
    },
    {
        "recorded_at": "2019-06-08T14:00:12+00:00",
        "latitude": -2.006057,
        "longitude": 34.62934
    },
    {
        "recorded_at": "2019-06-08T13:30:13+00:00",
        "latitude": -2.001542,
        "longitude": 34.62659
    },
    {
        "recorded_at": "2019-06-08T13:00:12+00:00",
        "latitude": -1.998768,
        "longitude": 34.62413
    },
    {
        "recorded_at": "2019-06-08T12:30:14+00:00",
        "latitude": -1.997308,
        "longitude": 34.62401
    },
    {
        "recorded_at": "2019-06-08T12:00:41+00:00",
        "latitude": -1.996412,
        "longitude": 34.62281
    },
    {
        "recorded_at": "2019-06-08T11:30:13+00:00",
        "latitude": -1.995647,
        "longitude": 34.62289
    },
    {
        "recorded_at": "2019-06-08T11:00:22+00:00",
        "latitude": -1.995632,
        "longitude": 34.62255
    },
    {
        "recorded_at": "2019-06-08T10:30:20+00:00",
        "latitude": -1.995043,
        "longitude": 34.62116
    },
    {
        "recorded_at": "2019-06-08T10:00:41+00:00",
        "latitude": -1.9951,
        "longitude": 34.62102
    },
    {
        "recorded_at": "2019-06-08T09:30:13+00:00",
        "latitude": -1.995102,
        "longitude": 34.62095
    },
    {
        "recorded_at": "2019-06-08T09:00:24+00:00",
        "latitude": -1.995136,
        "longitude": 34.62092
    },
    {
        "recorded_at": "2019-06-08T08:30:12+00:00",
        "latitude": -1.9952,
        "longitude": 34.62089
    },
    {
        "recorded_at": "2019-06-08T08:00:13+00:00",
        "latitude": -1.995612,
        "longitude": 34.62207
    },

    {
        "recorded_at": "2019-06-08T07:30:12+00:00",
        "latitude": -1.995298,
        "longitude": 34.62344
    },
    {
        "recorded_at": "2019-06-08T07:00:12+00:00",
        "latitude": -1.995416,
        "longitude": 34.62327
    },
    {
        "recorded_at": "2019-06-08T06:30:13+00:00",
        "latitude": -1.996627,
        "longitude": 34.62171
    },
    {
        "recorded_at": "2019-06-08T06:00:41+00:00",
        "latitude": -1.99752,
        "longitude": 34.62139
    },
    {
        "recorded_at": "2019-06-08T05:30:12+00:00",
        "latitude": -1.997577,
        "longitude": 34.62064
    },
    {
        "recorded_at": "2019-06-08T05:00:26+00:00",
        "latitude": -1.997558,
        "longitude": 34.62069
    },
    {
        "recorded_at": "2019-06-08T04:30:14+00:00",
        "latitude": -1.9973,
        "longitude": 34.62049
    },
    {
        "recorded_at": "2019-06-08T04:00:15+00:00",
        "latitude": -1.997135,
        "longitude": 34.62056
    },
    {
        "recorded_at": "2019-06-08T03:30:18+00:00",
        "latitude": -1.996567,
        "longitude": 34.6211
    },
    {
        "recorded_at": "2019-06-08T03:00:13+00:00",
        "latitude": -1.996536,
        "longitude": 34.6211
    },
    {
        "recorded_at": "2019-06-08T02:30:15+00:00",
        "latitude": -1.996625,
        "longitude": 34.62116
    },
    {
        "recorded_at": "2019-06-08T02:00:13+00:00",
        "latitude": -1.996605,
        "longitude": 34.62146
    },
    {
        "recorded_at": "2019-06-08T01:30:34+00:00",
        "latitude": -1.994977,
        "longitude": 34.62664
    },
    {
        "recorded_at": "2019-06-08T01:00:13+00:00",
        "latitude": -1.991518,
        "longitude": 34.63308
    },
    {
        "recorded_at": "2019-06-08T00:30:13+00:00",
        "latitude": -1.990391,
        "longitude": 34.634
    },
    {
        "recorded_at": "2019-06-08T00:00:12+00:00",
        "latitude": -1.98583,
        "longitude": 34.64005
    }
]

# has midway points outside the containment area
DUMBO_TRACKS = [
    {'longitude': 35.299973487854004,
     'latitude': -1.2151856051753929,
     'recorded_at': '2020-04-10T09:00:00'
     },
    {'longitude': 35.301432609558105,
     'latitude': -1.215099793789057,
     'recorded_at': '2020-04-10T10:00:00'
     },
    {'longitude': 35.30233383178711,
     'latitude': -1.214155868359561,
     'recorded_at': '2020-04-10T11:00:00'
     },
    {'longitude': 35.30765533447265,
     'latitude': -1.2075054753252543,
     'recorded_at': '2020-04-10T12:00:00'
     },
    {'longitude': 35.312161445617676,
     'latitude': -1.2023996786596682,
     'recorded_at': '2020-04-10T13:00:00'
     },
    {'longitude': 35.31439304351806,
     'latitude': -1.2077629101976217,
     'recorded_at': '2020-04-10T14:00:00'
     },
    {'longitude': 35.3115177154541,
     'latitude': -1.2108092210009758,
     'recorded_at': '2020-04-10T15:00:00'
     },
    {'longitude': 35.311174392700195,
     'latitude': -1.214756548216476,
     'recorded_at': '2020-04-10T16:00:00'
     },
    {'longitude': 35.30877113342285,
     'latitude': -1.217245077629004,
     'recorded_at': '2020-04-10T17:00:00'
     }
]

# No midway points outside the containment area
TUMBO_TRACKS = [
    {'longitude': 35.29860019683838,
     'latitude': -1.2162153415986423,
     'recorded_at': '2020-04-10T09:00:00'
     },
    {'longitude': 35.30778408050537,
     'latitude': -1.2126541681334833,
     'recorded_at': '2020-04-10T10:00:00'
     },
    {'longitude': 35.314435958862305,
     'latitude': -1.2024854904473519,
     'recorded_at': '2020-04-10T11:00:00'
     },
    {'longitude': 35.31362056732178,
     'latitude': -1.2111095613174674,
     'recorded_at': '2020-04-10T12:00:00'
     },
    {'longitude': 35.31027317047119,
     'latitude': -1.2167302096629626,
     'recorded_at': '2020-04-10T13:00:00'
     }
]

ZERO_CROSSINGS = [
    {'longitude': 35.3032,
     'latitude': -1.2069,
     'recorded_at': '2020-04-10T09:00:00'
     },
    {'longitude': 35.3102,
     'latitude': -1.2024,
     'recorded_at': '2020-04-10T10:00:00'
     },
    {'longitude': 35.3083,
     'latitude': -1.2152,
     'recorded_at': '2020-04-10T10:00:00'
     }
]

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