GFW_AUTH_TOKEN = 'not_a_real_token'

DRC_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [22.423095700004104, 7.602107873650873],
            [24.301757809117316, 7.591217969892275],
            [22.785644528078144, 6.599130674292671],
            [22.423095700004104, 7.602107873650873]
        ]
    ]
}

DRC_GEOSTORE_ID = '8634fa7d0f3a3042778f2dc4a8dc9105'

GLAD_ALERT_SUBSCRIPTION_DATA = {
    'name': 'DRC Glad alerts',
    'datasets': ['glad-alerts', ],
}

FIRE_ALERT_SUBSCRIPTION_DATA = {
    'name': 'DRC Fire alerts',
    'datasets': ['viirs-active-fires', ],
}

TERRAI_ALERT_SUBSCRIPTION_DATA = {
    'name': 'DRC Terra-i alerts',
    'datasets': ['terrai-alerts', ],
}

ALL_ALERTS_SUBSCRIPTION_DATA = {
    'name': 'All alerts',
    'datasets': ['glad-alerts', 'viirs-active-fires', 'terrai-alerts', ],
}

VIIRS_FIRE_ALERT = {
    "layerSlug": "viirs-active-fires",
    "map_image": "https://gfw2stories.s3.us-west-2.amazonaws.com/map_preview/a4cbcf7484ae2f85c90a3acf3cd0e377%3A1561400790792_21.8087%2C-3.7927%2C24.8579%2C-1.0957.png",
    "alert_name": "all alerts parts of drc - webhook",
    "selected_area": "Custom Area",
    "unsubscribe_url": "http://production-api.globalforestwatch.org/subscriptions/5d11c24e062bed110071db94/unsubscribe?redirect=true",
    "subscriptions_url": "http://www.globalforestwatch.org/my_gfw/subscriptions",
    "alert_link": "http://www.globalforestwatch.org/map/3/0/0/ALL/grayscale/viirs_fires_alerts?begin=2019-06-24&end=2019-06-25&fit_to_geom=true&geostore=50d10bbca9011845c31c82fbe4a7c790",
    "alert_date_begin": "2019-06-24",
    "alert_date_end": "2019-06-25",
    "alerts": [{
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.55704,
        "longitude": 23.26341
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.52684,
        "longitude": 23.30476
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.51183,
        "longitude": 23.29754
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.52429,
        "longitude": 23.3015
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.50933,
        "longitude": 23.29426
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.4624,
        "longitude": 23.3127
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.46144,
        "longitude": 23.29224
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.45751,
        "longitude": 23.29166
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.34622,
        "longitude": 23.15069
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.32671,
        "longitude": 23.17357
    }]
}

GLAD_ALERT = {
    "value": 63,
    "downloadUrls": {
        "csv": "http://production-api.globalforestwatch.org/glad-alerts/download/?period=2019-07-01,2019-07-02&gladConfirmOnly=False&aggregate_values=False&aggregate_by=False&geostore=a8c46db68bc4b6f7f881f38ce61a8bcb&format=csv",
        "json": "http://production-api.globalforestwatch.org/glad-alerts/download/?period=2019-07-01,2019-07-02&gladConfirmOnly=False&aggregate_values=False&aggregate_by=False&geostore=a8c46db68bc4b6f7f881f38ce61a8bcb&format=json"
    },
    "alert_count": 63,
    "alerts": [{
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.55704,
        "longitude": 23.26341
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.52684,
        "longitude": 23.30476
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.51183,
        "longitude": 23.29754
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.52429,
        "longitude": 23.3015
    }, {
        "acq_date": "2019-06-24",
        "acq_time": "11:30",
        "latitude": -2.50933,
        "longitude": 23.29426
    }],
    "layerSlug": "glad-alerts",
    "alert_name": "DRC-DEV subscription",
    "selected_area": "Custom Area",
    "unsubscribe_url": "http://production-api.globalforestwatch.org/subscriptions/5d1f9014836a9b13000e7d1d/unsubscribe?redirect=true",
    "subscriptions_url": "http://www.globalforestwatch.org/my_gfw/subscriptions",
    "alert_link": "http://www.globalforestwatch.org/map/3/0/0/ALL/grayscale/umd_as_it_happens?begin=2019-07-01&end=2019-07-02&fit_to_geom=true&geostore=a8c46db68bc4b6f7f881f38ce61a8bcb",
    "alert_date_begin": "2019-07-01",
    "alert_date_end": "2019-07-02"
}

GLAD_ALERT_DOWNLOADED_DATA = {
    "data": [{
        "lat": -1.3626250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.212625000000063,
        "year": 2019
    }, {
        "lat": -1.3628750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.212625000000063,
        "year": 2019
    }, {
        "lat": -1.3636250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.246625000000066,
        "year": 2019
    }, {
        "lat": -1.3636250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.267875000000064,
        "year": 2019
    }, {
        "lat": -1.3641250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.212875000000064,
        "year": 2019
    }, {
        "lat": -1.3686250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.256125000000065,
        "year": 2019
    }, {
        "lat": -1.3691250000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 21.803625000000064,
        "year": 2019
    }, {
        "lat": -1.3696250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.402625000000064,
        "year": 2019
    }, {
        "lat": -1.3768750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 21.833875000000063,
        "year": 2019
    }, {
        "lat": -1.3858750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.253125000000065,
        "year": 2019
    }, {
        "lat": -1.3943750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.251375000000063,
        "year": 2019
    }, {
        "lat": -1.3978750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.177625000000063,
        "year": 2019
    }, {
        "lat": -1.3991250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.192625000000064,
        "year": 2019
    }, {
        "lat": -1.3998750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.479625000000063,
        "year": 2019
    }, {
        "lat": -1.4003750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.475875000000066,
        "year": 2019
    }, {
        "lat": -1.4013750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.248625000000064,
        "year": 2019
    }, {
        "lat": -1.4016250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.199125000000063,
        "year": 2019
    }, {
        "lat": -1.4018750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.198625000000064,
        "year": 2019
    }, {
        "lat": -1.4023750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.194375000000065,
        "year": 2019
    }, {
        "lat": -1.4023750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.194625000000066,
        "year": 2019
    }, {
        "lat": -1.4028750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.197125000000064,
        "year": 2019
    }, {
        "lat": -1.4043750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.257375000000064,
        "year": 2019
    }, {
        "lat": -1.4088750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.343125000000065,
        "year": 2019
    }, {
        "lat": -1.4088750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.343375000000066,
        "year": 2019
    }, {
        "lat": -1.4096250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.225875000000066,
        "year": 2019
    }, {
        "lat": -1.4103750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.273375000000065,
        "year": 2019
    }, {
        "lat": -1.4103750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.273625000000063,
        "year": 2019
    }, {
        "lat": -1.4111250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.272625000000065,
        "year": 2019
    }, {
        "lat": -1.4136250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.340875000000064,
        "year": 2019
    }, {
        "lat": -1.4141250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.242125000000065,
        "year": 2019
    }, {
        "lat": -1.4181250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.260625000000065,
        "year": 2019
    }, {
        "lat": -1.4228750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.249125000000063,
        "year": 2019
    }, {
        "lat": -1.4243750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.268125000000065,
        "year": 2019
    }, {
        "lat": -1.4263750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.254625000000065,
        "year": 2019
    }, {
        "lat": -1.4263750000000301,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.469125000000066,
        "year": 2019
    }, {
        "lat": -1.4266250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.254625000000065,
        "year": 2019
    }, {
        "lat": -1.4271250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.487125000000063,
        "year": 2019
    }, {
        "lat": -1.4273750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.226625000000066,
        "year": 2019
    }, {
        "lat": -1.4513750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.383375000000065,
        "year": 2019
    }, {
        "lat": -1.4521250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.299375000000065,
        "year": 2019
    }, {
        "lat": -1.4521250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.299625000000063,
        "year": 2019
    }, {
        "lat": -1.4523750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.299375000000065,
        "year": 2019
    }, {
        "lat": -1.4523750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.299625000000063,
        "year": 2019
    }, {
        "lat": -1.4533750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.376875000000066,
        "year": 2019
    }, {
        "lat": -1.4533750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.377125000000063,
        "year": 2019
    }, {
        "lat": -1.4533750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.377375000000065,
        "year": 2019
    }, {
        "lat": -1.4533750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.377625000000066,
        "year": 2019
    }, {
        "lat": -1.4723750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.463875000000066,
        "year": 2019
    }, {
        "lat": -1.4726250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.463875000000066,
        "year": 2019
    }, {
        "lat": -1.5036250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.326375000000063,
        "year": 2019
    }, {
        "lat": -1.5263750000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.390125000000065,
        "year": 2019
    }, {
        "lat": -1.5266250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.390375000000063,
        "year": 2019
    }, {
        "lat": -1.5803750000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.235875000000064,
        "year": 2019
    }, {
        "lat": -1.6016250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.425375000000063,
        "year": 2019
    }, {
        "lat": -1.6526250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.248625000000064,
        "year": 2019
    }, {
        "lat": -1.7121250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.169125000000065,
        "year": 2019
    }, {
        "lat": -1.7121250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.169375000000063,
        "year": 2019
    }, {
        "lat": -1.8281250000000302,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.232375000000065,
        "year": 2019
    }, {
        "lat": -1.9941250000000303,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.051875000000063,
        "year": 2019
    }, {
        "lat": -2.0513750000000304,
        "confidence": 3,
        "julian_day": 183,
        "long": 22.070625000000064,
        "year": 2019
    }, {
        "lat": -2.1571250000000304,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.166625000000064,
        "year": 2019
    }, {
        "lat": -2.1888750000000305,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.210875000000065,
        "year": 2019
    }, {
        "lat": -2.3918750000000304,
        "confidence": 2,
        "julian_day": 183,
        "long": 22.177125000000064,
        "year": 2019
    }]
}

VIIRS_FIRE_ALERT_DOWNLOADED_DATA = {
    "rows": [
        {
            "cartodb_id": 372492,
            "the_geom": "0101000020E610000085251E5036153340E370E65773202A40",
            "the_geom_webmercator": "0101000020110F000050BE082103354041AD1BD8365E623641",
            "latitude": 13.06338,
            "longitude": 19.08286,
            "bright_ti4": 310.1,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 289.8,
            "frp": 1,
            "daynight": "N"
        },
        {
            "cartodb_id": 372493,
            "the_geom": "0101000020E6100000B4E55C8AAB1A334002D4D4B2B51E2A40",
            "the_geom_webmercator": "0101000020110F00008EC478CBA53940412224E9ACD9603641",
            "latitude": 13.05998,
            "longitude": 19.10418,
            "bright_ti4": 313,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 290.1,
            "frp": 1,
            "daynight": "N"
        },
        {
            "cartodb_id": 372494,
            "the_geom": "0101000020E6100000C1A8A44E401333403AAFB14B541F2A40",
            "the_geom_webmercator": "0101000020110F000042F47FC6583340413498ECF263613641",
            "latitude": 13.06119,
            "longitude": 19.0752,
            "bright_ti4": 340.3,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 298.4,
            "frp": 11.6,
            "daynight": "N"
        },
        {
            "cartodb_id": 372495,
            "the_geom": "0101000020E6100000A33B889D2914334090F7AA95091F2A40",
            "the_geom_webmercator": "0101000020110F00001DBD90EC1E344041082ACECF22613641",
            "latitude": 13.06062,
            "longitude": 19.07876,
            "bright_ti4": 322.7,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 291.6,
            "frp": 11.6,
            "daynight": "N"
        },
        {
            "cartodb_id": 372496,
            "the_geom": "0101000020E61000003E22A6441215334074982F2FC01E2A40",
            "the_geom_webmercator": "0101000020110F0000435A2484E4344041FC1645D1E2603641",
            "latitude": 13.06006,
            "longitude": 19.08231,
            "bright_ti4": 306.4,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 289.6,
            "frp": 1,
            "daynight": "N"
        },
        {
            "cartodb_id": 372497,
            "the_geom": "0101000020E61000006DE2E47E871A334094FB1D8A021D2A40",
            "the_geom_webmercator": "0101000020110F00008160942E873940413763AC485E5F3641",
            "latitude": 13.05666,
            "longitude": 19.10363,
            "bright_ti4": 310.4,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 289.6,
            "frp": 1,
            "daynight": "N"
        },
        {
            "cartodb_id": 372498,
            "the_geom": "0101000020E61000007AA52C431C1333405A2F8672A21D2A40",
            "the_geom_webmercator": "0101000020110F000035909B293A334041ABE3C0B2E95F3641",
            "latitude": 13.05788,
            "longitude": 19.07465,
            "bright_ti4": 329.8,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 302.4,
            "frp": 14,
            "daynight": "N"
        },
        {
            "cartodb_id": 372499,
            "the_geom": "0101000020E6100000DF32A7CB621A3340252367614F1B2A40",
            "the_geom_webmercator": "0101000020110F0000BBD032036839404176C0BDE5E25D3641",
            "latitude": 13.05334,
            "longitude": 19.10307,
            "bright_ti4": 320.1,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 290.3,
            "frp": 1.7,
            "daynight": "N"
        },
        {
            "cartodb_id": 372500,
            "the_geom": "0101000020E6100000158C4AEA04143340AF777FBC571D2A40",
            "the_geom_webmercator": "0101000020110F0000562D2FC1FF33404180A9DB8FA85F3641",
            "latitude": 13.05731,
            "longitude": 19.0782,
            "bright_ti4": 317.9,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 290.9,
            "frp": 14,
            "daynight": "N"
        },
        {
            "cartodb_id": 372501,
            "the_geom": "0101000020E6100000B0726891ED14334005C078060D1D2A40",
            "the_geom_webmercator": "0101000020110F00007DCAC258C5344041B448006D675F3641",
            "latitude": 13.05674,
            "longitude": 19.08175,
            "bright_ti4": 305.2,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 289.7,
            "frp": 0.7,
            "daynight": "N"
        },
        {
            "cartodb_id": 372502,
            "the_geom": "0101000020E610000092054CE0D6153340E960FD9FC31C2A40",
            "the_geom_webmercator": "0101000020110F00005793D37E8B3540411E15B96E275F3641",
            "latitude": 13.05618,
            "longitude": 19.08531,
            "bright_ti4": 302.3,
            "scan": 0.39,
            "track": 0.36,
            "acq_date": "2020-02-25T00:00:00Z",
            "acq_time": "0018",
            "satellite": "N",
            "confidence": "nominal",
            "version": "1.0NRT",
            "bright_ti5": 289.2,
            "frp": 0.7,
            "daynight": "N"
        }
    ],
    "time": 0.466,
    "fields": {
        "cartodb_id": {
            "type": "number",
            "pgtype": "int4"
        },
        "the_geom": {
            "type": "geometry",
            "wkbtype": "Unknown",
            "dims": 2,
            "srid": 4326
        },
        "the_geom_webmercator": {
            "type": "geometry",
            "wkbtype": "Unknown",
            "dims": 2,
            "srid": 3857
        },
        "latitude": {
            "type": "number",
            "pgtype": "float8"
        },
        "longitude": {
            "type": "number",
            "pgtype": "float8"
        },
        "bright_ti4": {
            "type": "number",
            "pgtype": "float8"
        },
        "scan": {
            "type": "number",
            "pgtype": "float8"
        },
        "track": {
            "type": "number",
            "pgtype": "float8"
        },
        "acq_date": {
            "type": "date",
            "pgtype": "date"
        },
        "acq_time": {
            "type": "string",
            "pgtype": "text"
        },
        "satellite": {
            "type": "string",
            "pgtype": "text"
        },
        "confidence": {
            "type": "string",
            "pgtype": "text"
        },
        "version": {
            "type": "string",
            "pgtype": "text"
        },
        "bright_ti5": {
            "type": "number",
            "pgtype": "float8"
        },
        "frp": {
            "type": "number",
            "pgtype": "float8"
        },
        "daynight": {
            "type": "string",
            "pgtype": "text"
        }
    },
    "total_rows": 24425
}

VIIRS_CALLBACK_DATA = {
    "data": {
        "type": "viirs-fires",
        "id": "undefined",
        "attributes": {
            "value": 28086,
            "period": "Past 24 hours",
            "downloadUrls": {
                "csv": "https://wri-01.cartodb.com/api/v2/sql?q=%0A%20%20%20%20%20%20%20%20SELECT%20pt.*%20%0A%20%20%20%20%20%20%20%20FROM%20vnp14imgtdl_nrt_global_7d%20pt%20%0A%20%20%20%20%20%20%20%20where%20acq_date%20%3E%3D%20'2020-3-1'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20acq_date%20%3C%3D%20'2020-3-2'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20ST_INTERSECTS(ST_SetSRID(ST_GeomFromGeoJSON('%7B%22type%22%3A%22Polygon%22%2C%22coordinates%22%3A%5B%5B%5B-14.969671%2C9.528301%5D%2C%5B-13.438718%2C20.291592%5D%2C%5B51.825167%2C18.746957%5D%2C%5B49.547742%2C-16.469007%5D%2C%5B48.362407%2C-28.64872%5D%2C%5B3.272027%2C-29.200593%5D%2C%5B-14.969671%2C9.528301%5D%5D%5D%7D')%2C%204326)%2C%20the_geom)%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20(confidence%3D'normal'%20OR%20confidence%3D'nominal')%0A%20%20%20%20%20%20%20%20&format=csv",
                "geojson": "https://wri-01.cartodb.com/api/v2/sql?q=%0A%20%20%20%20%20%20%20%20SELECT%20pt.*%20%0A%20%20%20%20%20%20%20%20FROM%20vnp14imgtdl_nrt_global_7d%20pt%20%0A%20%20%20%20%20%20%20%20where%20acq_date%20%3E%3D%20'2020-3-1'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20acq_date%20%3C%3D%20'2020-3-2'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20ST_INTERSECTS(ST_SetSRID(ST_GeomFromGeoJSON('%7B%22type%22%3A%22Polygon%22%2C%22coordinates%22%3A%5B%5B%5B-14.969671%2C9.528301%5D%2C%5B-13.438718%2C20.291592%5D%2C%5B51.825167%2C18.746957%5D%2C%5B49.547742%2C-16.469007%5D%2C%5B48.362407%2C-28.64872%5D%2C%5B3.272027%2C-29.200593%5D%2C%5B-14.969671%2C9.528301%5D%5D%5D%7D')%2C%204326)%2C%20the_geom)%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20(confidence%3D'normal'%20OR%20confidence%3D'nominal')%0A%20%20%20%20%20%20%20%20&format=geojson",
                "kml": "https://wri-01.cartodb.com/api/v2/sql?q=%0A%20%20%20%20%20%20%20%20SELECT%20pt.*%20%0A%20%20%20%20%20%20%20%20FROM%20vnp14imgtdl_nrt_global_7d%20pt%20%0A%20%20%20%20%20%20%20%20where%20acq_date%20%3E%3D%20'2020-3-1'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20acq_date%20%3C%3D%20'2020-3-2'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20ST_INTERSECTS(ST_SetSRID(ST_GeomFromGeoJSON('%7B%22type%22%3A%22Polygon%22%2C%22coordinates%22%3A%5B%5B%5B-14.969671%2C9.528301%5D%2C%5B-13.438718%2C20.291592%5D%2C%5B51.825167%2C18.746957%5D%2C%5B49.547742%2C-16.469007%5D%2C%5B48.362407%2C-28.64872%5D%2C%5B3.272027%2C-29.200593%5D%2C%5B-14.969671%2C9.528301%5D%5D%5D%7D')%2C%204326)%2C%20the_geom)%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20(confidence%3D'normal'%20OR%20confidence%3D'nominal')%0A%20%20%20%20%20%20%20%20&format=kml",
                "shp": "https://wri-01.cartodb.com/api/v2/sql?q=%0A%20%20%20%20%20%20%20%20SELECT%20pt.*%20%0A%20%20%20%20%20%20%20%20FROM%20vnp14imgtdl_nrt_global_7d%20pt%20%0A%20%20%20%20%20%20%20%20where%20acq_date%20%3E%3D%20'2020-3-1'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20acq_date%20%3C%3D%20'2020-3-2'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20ST_INTERSECTS(ST_SetSRID(ST_GeomFromGeoJSON('%7B%22type%22%3A%22Polygon%22%2C%22coordinates%22%3A%5B%5B%5B-14.969671%2C9.528301%5D%2C%5B-13.438718%2C20.291592%5D%2C%5B51.825167%2C18.746957%5D%2C%5B49.547742%2C-16.469007%5D%2C%5B48.362407%2C-28.64872%5D%2C%5B3.272027%2C-29.200593%5D%2C%5B-14.969671%2C9.528301%5D%5D%5D%7D')%2C%204326)%2C%20the_geom)%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20(confidence%3D'normal'%20OR%20confidence%3D'nominal')%0A%20%20%20%20%20%20%20%20&format=shp",
                "svg": "https://wri-01.cartodb.com/api/v2/sql?q=%0A%20%20%20%20%20%20%20%20SELECT%20pt.*%20%0A%20%20%20%20%20%20%20%20FROM%20vnp14imgtdl_nrt_global_7d%20pt%20%0A%20%20%20%20%20%20%20%20where%20acq_date%20%3E%3D%20'2020-3-1'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20acq_date%20%3C%3D%20'2020-3-2'%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20ST_INTERSECTS(ST_SetSRID(ST_GeomFromGeoJSON('%7B%22type%22%3A%22Polygon%22%2C%22coordinates%22%3A%5B%5B%5B-14.969671%2C9.528301%5D%2C%5B-13.438718%2C20.291592%5D%2C%5B51.825167%2C18.746957%5D%2C%5B49.547742%2C-16.469007%5D%2C%5B48.362407%2C-28.64872%5D%2C%5B3.272027%2C-29.200593%5D%2C%5B-14.969671%2C9.528301%5D%5D%5D%7D')%2C%204326)%2C%20the_geom)%0A%20%20%20%20%20%20%20%20%20%20%20%20AND%20(confidence%3D'normal'%20OR%20confidence%3D'nominal')%0A%20%20%20%20%20%20%20%20&format=svg"
            },
            "areaHa": 3601106922.25816
        }
    }
}
