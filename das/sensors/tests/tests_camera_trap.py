import logging
import base64
from io import BytesIO

from PIL import Image
import pytz
import piexif
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test.testcases import TestCase
from django.core.management import call_command
import django.contrib.auth

from accounts.models import PermissionSet
from core.tests import BaseAPITest
from sensors.views import SensorObservation
from sensors import camera_trap

logger = logging.getLogger(__name__)
User = django.contrib.auth.get_user_model()


sensor_user_permissions = ['add_observation',
                           'change_observation', 'add_source']


class CameraTrapTest(BaseAPITest):
    user_const = dict(last_name='last', first_name='first')
    SAMPLE_PANTHERA_EXIF = """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AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAEFTQ0lJAAAAAAkAAAABAAAABAICAAAAAQACAAAAAk4AAAAAAgAFAAAAAwAACGkAAwACAAAAAlcAAAAABAAFAAAAAwAACIEABQABAAAAAQAAAAAABgAFAAAAAQAACJkABwAFAAAAAwAACKEAHQACAAAACwAACLkAAAApAAAAAQAAACAAAAABAAAAFQAAAAEAAABJAAAAAQAAACYAAAABAAAACwAAAAEAAAFEAAAAAQAAABAAAAABAAAAOgAAAAEAAAAYAAAAATIwMTc6MTA6MjUA"""
    sensor_type = 'camera-trap'
    provider_name = 'panthera'

    def setUp(self):
        super().setUp()
        call_command('loaddata', 'camera_trap_eventtype.json')

        self.sensor_user = User.objects.create_user('sensor_user',
                                                    'sensor_user@test.com',
                                                    'sensoruser',
                                                    **self.user_const)

        self.sensor_permissionset = PermissionSet.objects.create(
            name='sensor_set')
        for perm in sensor_user_permissions:
            self.sensor_permissionset.permissions.add(
                Permission.objects.get(codename=perm))

    def get_image(self):
        exif_dict = piexif.load(base64.b64decode(self.SAMPLE_PANTHERA_EXIF))
        exif_bytes = piexif.dump(exif_dict)

        file = BytesIO()
        image = Image.new('RGBA', size=(50, 50), color=(155, 0, 0))
        image.save(file, 'JPEG', exif=exif_bytes)
        file.seek(0)

        return 'CAM65593_2017-10-20_151152.jpg', file

    def post_cam_image(self):
        filename, f = self.get_image()
        data = {'filecontent.file': SimpleUploadedFile(filename, f.read(),
                                                       content_type='image/jpg')}

        path = '/'.join((self.api_base, 'sensors',
                         self.sensor_type, self.provider_name, 'status'))
        request = self.factory.post(
            path, data=data, format='multipart')

        self.force_authenticate(request, self.sensor_user)
        return SensorObservation.as_view()(request,
                                           sensor_type=self.sensor_type,
                                           provider_name=self.provider_name)

    def test_post_image(self):

        response = self.post_cam_image()

        self.assertEqual(response.status_code, 201)

    def test_not_post_duplicate(self):
        response = self.post_cam_image()
        self.assertEqual(response.status_code, 201)

        response = self.post_cam_image()

        self.assertEqual(response.status_code, 409)

    def test_exif_timzone(self):
        self.assertEquals(pytz.FixedOffset(-120),
                          camera_trap.exif_time_zone('-02:00'))
