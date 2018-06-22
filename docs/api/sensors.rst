.. _sensors:

Sensors
===========================

GPS Radio API
-----------------------------

.. http:post:: /sensors/gps-radio/<provider_key>/status

Camera Trap API
-----------------------------

.. http:post:: /sensors/camera-trap/<provider>/status

   Post a new camera trap image. Suggest making the imagename unique by including
   the camera name in the image name.

    There are two ways to submit location, time of capture, camera name, etc. The
    first is by posting additional json formatted data with the 'filecontent.file'
    field. A second way is to embed this data in the exif of the image. If both sources
    of data are submitted, the direct fields override the same data found in the images
    exif.

    Additional Fields:
    | "location": {"latitude": 36.02339, "longitude": 192.38282}
    | "camera_name": "<camera name here>"
    | "time": "<iso formatted time with timezone>"
    | "camera_description": "<description here>"
    | "camera_version": "<camera version>"

    Exif:
      | DateTimeOriginal -> report time
      | OffsetTimeOriginal -> if found is used to set the timezone offset for DateTimeOriginal
      | GPSLatitude, GPSLongitude -> parsed and used to set the location of the report

    Specific <provider> support:

    if provider is generic
      | "camera_name" or Model -> cameratraprep_camera-name
      | "camera_description" or Make -> cameratraprep_camera-make
      | "camera_version" or Software -> cameratraprep_camera-version


   :reqheader Authorization: Bearer <auth token>
   :reqheader Accept: application/json
   :reqheader Content-Type: multipart/form-data

   :form filecontent.file: <image> <filename>

   :statuscode 201: image successfully posted
   :statuscode 409: camera trap image has already been posted, this one ignored


   **Example request**:

   .. sourcecode:: http

      POST /sensors/camera-trap/generic/status HTTP/1.1
      Host: das-server
      Content-Type: application/octet-stream
      Accept: application/json

      filecontent.file


   **Example request**:

   .. sourcecode:: python

        import requests
        DAS_API_ROOT = 'https://<server>.pamdas.org/api/v1.0'
        DAS_TOKEN = '<oauth token here>'

        image_file = '2017-11-08.jpg'
        data = {'location': json.dumps({'latitude': 0,
                         'longitude': 0}),
               }
        content_type = 'application/jpeg'

        url = '{0}/sensors/camera-trap/generic/status'.format(DAS_API_ROOT)
        headers = {'Authorization': 'Bearer {token}'.format(token=DAS_TOKEN)}
        with open(image_file, 'rb') as fh:
            files = {'filecontent.file': (unique_image_name, fh,
                     content_type)}
            result = requests.post(url, headers=headers, files=files, data=data)

        if result.status_code != requests.codes.created:
            result.raise_for_status()