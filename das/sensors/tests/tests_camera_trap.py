import base64
import datetime
import logging
from io import BytesIO

import piexif
import pytz
from PIL import Image

import django.contrib.auth
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import HttpResponse
from django.urls import resolve

from accounts.models import PermissionSet
from core.tests import BaseAPITest
from das_server.middleware import CommonMiddlewareAppendSlashWithoutRedirect
from sensors import camera_trap
from sensors.views import CameraTrapHandlerView
from utils import json

logger = logging.getLogger(__name__)
User = django.contrib.auth.get_user_model()


sensor_user_permissions = ['add_observation',
                           'change_observation',
                           'add_source',
                           'security_create']


SAMPLES = [
    {'EXIF': """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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEFTQ0lJAAAAAAkAAAABAAAABAICAAAAAQACAAAAAk4AAAAAAgAFAAAAAwAACGkAAwACAAAAAlcAAAAABAAFAAAAAwAACIEABQABAAAAAQAAAAAABgAFAAAAAQAACJkABwAFAAAAAwAACKEAHQACAAAACwAACLkAAAApAAAAAQAAACAAAAABAAAAFQAAAAEAAABJAAAAAQAAACYAAAABAAAACwAAAAEAAAFEAAAAAQAAABAAAAABAAAAOgAAAAEAAAAYAAAAATIwMTc6MTA6MjUA""",
     'provider_name': 'pantera',
     'image_name': 'CAM65593_2017-10-20_151152.jpg'
     },
    {
        'EXIF': """RXhpZgAATU0AKgAAAAgABAEPAAIAAAAJAAAAPgEQAAIAAAAJAAAAR4dpAAQAAAABAAAAUIglAAQAAAABAAAAhAAAAABUZXN0VW5pdABUZXN0VW5pdAAAApADAAIAAAAUAAAAapARAAIAAAAGAAAAfjIwMTc6MTI6MTEgMTY6MDQ6NDYALTU6MDAAAAYAAAABAAAABAICAAAAAQACAAAAAlMAAAAAAgAFAAAAAwAAAM4AAwACAAAAAkUAAAAABAAFAAAAAwAAAOYAEgACAAAABwAAAP4AAAACAAAAAQAAAAQAAAABAADVzwAAA+gAAAAiAAAAAQAAAB0AAAABAACg9AAAA+hXR1MtODQA""",
        'provider_name': 'generic',
        'image_name': 'TestUnit_2017-12-11__16h04m46s_EXIF.jpg'
    }
]

NO_LOCATION_SAMPLES = [
    {'EXIF': """""",
     'provider_name': 'jenga',
     'image_name': '2019-05-20_151152.jpg'
     },
]


class CameraTrapTest(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')
    sensor_type = 'camera-trap'

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'event_data_model.json')

        self.sensor_user = User.objects.create_user('sensor_user',
                                                    'sensor_user@test.com',
                                                    'sensoruser',
                                                    **self.user_const)

        self.sensor_permissionset = PermissionSet.objects.create(
            name='sensor_set')
        for perm in sensor_user_permissions:
            self.sensor_permissionset.permissions.add(
                Permission.objects.get(codename=perm))

    def get_image(self, sample):
        exif_dict = piexif.load(base64.b64decode(sample['EXIF']))
        exif_bytes = piexif.dump(exif_dict)

        file = BytesIO()
        image = Image.new('RGB', size=(50, 50), color=(155, 0, 0))
        image.save(file, 'JPEG', exif=exif_bytes)
        file.seek(0)
        return sample['provider_name'], sample['image_name'], file

    def post_cam_image(self, sample, data=None):
        provider, filename, f = self.get_image(sample)
        if not data:
            data = {}
        data.update({'filecontent.file': SimpleUploadedFile(filename, f.read(),
                                                            content_type='image/jpg')})

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, provider, 'status'))
        request = self.factory.post(path, data=data, format='multipart')

        common_middleware = CommonMiddlewareAppendSlashWithoutRedirect(
            self.get_response)
        common_middleware(request)
        resolver = resolve(request.path)

        self.assertEqual(resolver.func.cls, CameraTrapHandlerView)
        self.force_authenticate(request, self.sensor_user)
        return CameraTrapHandlerView.as_view()(request, provider)

    def get_response(self, request):
        response = HttpResponse()
        return response

    def test_post_image(self):
        for sample in SAMPLES:
            response = self.post_cam_image(sample)
            self.assertEqual(response.status_code, 201)

    def test_not_post_duplicate(self):
        sample = SAMPLES[0]
        response = self.post_cam_image(sample)
        self.assertEqual(response.status_code, 201)

        response = self.post_cam_image(sample)

        self.assertEqual(response.status_code, 409)

    def test_post_image_with_data(self):
        data = {'camera_name': 'With Data',
                'location': json.dumps({'latitude': -2.08187,
                                        'longitude': 34.49477}),
                'camera_description': 'Camera Description'
                }
        for sample in SAMPLES:
            response = self.post_cam_image(sample, data)
            self.assertEqual(response.status_code, 201)

    def test_post_image_with_no_location(self):
        data = {'camera_name': 'With Data',
                }
        for sample in SAMPLES:
            response = self.post_cam_image(sample, data)
            self.assertEqual(response.status_code, 201)

    def test_post_image_to_previous(self):
        group_id = None
        for sample in SAMPLES:
            if group_id:
                response = self.post_cam_image(sample,
                                               data={'group_id': group_id})
            else:
                response = self.post_cam_image(sample)
            self.assertEqual(response.status_code, 201)
            group_id = response.data['group_id']

    def test_default_priority_urgent(self):
        self.assertEqual(camera_trap.get_priority(),
                         camera_trap.Event.PRI_URGENT)

    def test_default_priority_loaded_from_settings(self):
        for priority in camera_trap.Event.PRIORITY_CHOICES:
            priority = priority[0]
            camera_settings = {
                'camera_trap': {
                    'default_time_zone': 'UTC',
                    'priority': priority,
                }}
            with self.settings(SENSORS=camera_settings):
                self.assertEqual(camera_trap.get_priority(),
                                 priority)

    def test_get_time_from_exif(self):
        exif_dict = {'DateTimeOriginal': b'2017:12:11 16:04:46',
                     'OffsetTimeOriginal': b'-5:00'}

        control = datetime.datetime(2017, 12, 11, 21, 4, 46, tzinfo=pytz.UTC)

        self.assertEquals(control, camera_trap.CameraTrapSensorHandler.get_time(
            None, exif_dict
        ))

    def test_invalid_exif_timezone(self):
        with self.assertRaises(ValueError):
            camera_trap.exif_time_zone('-10')

        with self.assertRaises(ValueError):
            camera_trap.exif_time_zone(':')

        with self.assertRaises(ValueError):
            camera_trap.exif_time_zone(':0')

    def test_exif_timzone(self):
        self.assertEquals(pytz.FixedOffset(-120),
                          camera_trap.exif_time_zone('-02:00'))

        self.assertEquals(pytz.FixedOffset(-125),
                          camera_trap.exif_time_zone('-02:05'))

        self.assertEquals(pytz.FixedOffset(0),
                          camera_trap.exif_time_zone('-00:00'))

        self.assertEquals(pytz.FixedOffset(-300),
                          camera_trap.exif_time_zone('-05:00'))
